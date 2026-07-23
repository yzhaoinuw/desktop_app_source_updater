from __future__ import annotations

import ast
import keyword
from dataclasses import dataclass


PYTHON_CONFIG_MERGE_STRATEGY = "python-config-merge"
REPLACE_STRATEGY = "replace"


class PythonConfigMergeError(ValueError):
    pass


@dataclass(frozen=True)
class _ParsedSource:
    data: bytes
    tree: ast.Module
    line_starts: tuple[int, ...]


def validate_editable_assignment_names(names: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    if not names:
        raise PythonConfigMergeError("python config merge requires at least one editable assignment")

    validated = []
    for name in names:
        if not isinstance(name, str) or not name.isidentifier() or keyword.iskeyword(name):
            raise PythonConfigMergeError(f"invalid editable Python assignment name: {name!r}")
        if name in validated:
            raise PythonConfigMergeError(f"duplicate editable Python assignment name: {name}")
        validated.append(name)
    return tuple(validated)


def validate_python_config_template(
    downloaded: bytes,
    editable_assignments: tuple[str, ...],
    *,
    path: str,
) -> None:
    names = validate_editable_assignment_names(editable_assignments)
    document = _parse_source(downloaded, path=path, role="downloaded")
    assignments = _top_level_assignments(document, names, path=path, role="downloaded")
    for name in names:
        if name not in assignments:
            raise PythonConfigMergeError(
                f"downloaded Python config {path} is missing editable assignment {name}"
            )
        _literal_value(assignments[name], path=path, role="downloaded", name=name)


def merge_python_config(
    downloaded: bytes,
    installed: bytes,
    editable_assignments: tuple[str, ...],
    *,
    path: str,
) -> bytes:
    names = validate_editable_assignment_names(editable_assignments)
    downloaded_document = _parse_source(downloaded, path=path, role="downloaded")
    installed_document = _parse_source(installed, path=path, role="installed")
    downloaded_assignments = _top_level_assignments(
        downloaded_document, names, path=path, role="downloaded"
    )
    installed_assignments = _top_level_assignments(
        installed_document, names, path=path, role="installed"
    )

    replacements: list[tuple[int, int, bytes]] = []
    for name in names:
        if name not in downloaded_assignments:
            raise PythonConfigMergeError(
                f"downloaded Python config {path} is missing editable assignment {name}"
            )
        downloaded_value = downloaded_assignments[name]
        _literal_value(downloaded_value, path=path, role="downloaded", name=name)

        installed_value = installed_assignments.get(name)
        if installed_value is None:
            continue
        _literal_value(installed_value, path=path, role="installed", name=name)
        _merge_value(
            downloaded_document,
            downloaded_value,
            installed_document,
            installed_value,
            replacements,
            path=path,
            name=name,
        )

    merged = downloaded_document.data
    for start, end, replacement in sorted(replacements, reverse=True):
        merged = merged[:start] + replacement + merged[end:]

    try:
        compile(merged, path, "exec")
    except (SyntaxError, ValueError, TypeError) as exc:
        raise PythonConfigMergeError(
            f"merged Python config {path} is invalid: {_syntax_detail(exc)}"
        ) from exc
    return merged


def _parse_source(source: bytes, *, path: str, role: str) -> _ParsedSource:
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PythonConfigMergeError(f"{role} Python config {path} must be UTF-8") from exc
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as exc:
        raise PythonConfigMergeError(
            f"{role} Python config {path} is invalid: {_syntax_detail(exc)}"
        ) from exc

    starts = []
    offset = 0
    for line in source.splitlines(keepends=True):
        starts.append(offset)
        offset += len(line)
    if not starts:
        starts.append(0)
    return _ParsedSource(data=source, tree=tree, line_starts=tuple(starts))


def _top_level_assignments(
    document: _ParsedSource,
    editable_assignments: tuple[str, ...],
    *,
    path: str,
    role: str,
) -> dict[str, ast.expr]:
    wanted = set(editable_assignments)
    assignments: dict[str, list[ast.expr]] = {name: [] for name in editable_assignments}
    unsupported = set()

    for statement in document.tree.body:
        if isinstance(statement, ast.Assign):
            target_names = {
                name
                for target in statement.targets
                for name in _assigned_names(target)
                if name in wanted
            }
            if not target_names:
                continue
            if len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
                assignments[statement.targets[0].id].append(statement.value)
            else:
                unsupported.update(target_names)
        elif isinstance(statement, ast.AnnAssign):
            target_names = {name for name in _assigned_names(statement.target) if name in wanted}
            if not target_names:
                continue
            if isinstance(statement.target, ast.Name) and statement.value is not None:
                assignments[statement.target.id].append(statement.value)
            else:
                unsupported.update(target_names)
        elif isinstance(statement, ast.AugAssign):
            unsupported.update(name for name in _assigned_names(statement.target) if name in wanted)

    if unsupported:
        raise PythonConfigMergeError(
            f"{role} Python config {path} uses an unsupported assignment for "
            + ", ".join(sorted(unsupported))
        )

    result = {}
    for name, values in assignments.items():
        if len(values) > 1:
            raise PythonConfigMergeError(
                f"{role} Python config {path} contains duplicate editable assignment {name}"
            )
        if values:
            result[name] = values[0]
    return result


def _assigned_names(target: ast.expr) -> tuple[str, ...]:
    if isinstance(target, ast.Name):
        return (target.id,)
    if isinstance(target, (ast.Tuple, ast.List)):
        return tuple(name for item in target.elts for name in _assigned_names(item))
    return ()


def _merge_value(
    downloaded_document: _ParsedSource,
    downloaded_value: ast.expr,
    installed_document: _ParsedSource,
    installed_value: ast.expr,
    replacements: list[tuple[int, int, bytes]],
    *,
    path: str,
    name: str,
) -> None:
    if isinstance(downloaded_value, ast.Dict) and isinstance(installed_value, ast.Dict):
        downloaded_items = _dict_items(downloaded_value, path=path, role="downloaded", name=name)
        installed_items = _dict_items(installed_value, path=path, role="installed", name=name)
        for key, downloaded_item in downloaded_items.items():
            installed_item = installed_items.get(key)
            if installed_item is not None:
                _merge_value(
                    downloaded_document,
                    downloaded_item,
                    installed_document,
                    installed_item,
                    replacements,
                    path=path,
                    name=name,
                )
        return

    start, end = _node_span(downloaded_document, downloaded_value, path=path)
    replacement_start, replacement_end = _node_span(installed_document, installed_value, path=path)
    replacements.append(
        (start, end, installed_document.data[replacement_start:replacement_end])
    )


def _dict_items(
    value: ast.Dict,
    *,
    path: str,
    role: str,
    name: str,
) -> dict[object, ast.expr]:
    items = {}
    for key_node, value_node in zip(value.keys, value.values):
        if key_node is None:
            raise PythonConfigMergeError(
                f"{role} editable assignment {name} in {path} cannot use dictionary unpacking"
            )
        key = _literal_value(key_node, path=path, role=role, name=name)
        try:
            duplicate = key in items
        except TypeError as exc:
            raise PythonConfigMergeError(
                f"{role} editable assignment {name} in {path} has an unhashable dictionary key"
            ) from exc
        if duplicate:
            raise PythonConfigMergeError(
                f"{role} editable assignment {name} in {path} has a duplicate dictionary key {key!r}"
            )
        items[key] = value_node
    return items


def _literal_value(node: ast.expr, *, path: str, role: str, name: str) -> object:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError) as exc:
        raise PythonConfigMergeError(
            f"{role} editable assignment {name} in {path} must use a Python literal value"
        ) from exc


def _node_span(document: _ParsedSource, node: ast.expr, *, path: str) -> tuple[int, int]:
    if node.end_lineno is None or node.end_col_offset is None:
        raise PythonConfigMergeError(f"could not locate editable value source in {path}")
    try:
        start = document.line_starts[node.lineno - 1] + node.col_offset
        end = document.line_starts[node.end_lineno - 1] + node.end_col_offset
    except IndexError as exc:
        raise PythonConfigMergeError(f"could not locate editable value source in {path}") from exc
    return start, end


def _syntax_detail(exc: Exception) -> str:
    if isinstance(exc, SyntaxError):
        location = f"line {exc.lineno}" if exc.lineno else "unknown line"
        return f"{exc.msg} ({location})"
    return str(exc)
