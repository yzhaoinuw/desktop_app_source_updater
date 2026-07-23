from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .core import (
    DEFAULT_BLOCKED_PATH_NAMES,
    DEFAULT_BLOCKED_PATH_PREFIXES,
    DEFAULT_BLOCKED_PATH_SUFFIXES,
)
from .python_config import (
    PYTHON_CONFIG_MERGE_STRATEGY,
    PythonConfigMergeError,
    validate_editable_assignment_names,
    validate_python_config_template,
)


@dataclass(frozen=True)
class InstalledBaseline:
    source: Path
    version: str
    files: dict[str, str | None]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo = args.repo.resolve()
    version = args.version or read_version_from_ref(repo, args.to_ref, args.version_file, args.version_pattern)
    from_refs = args.from_refs
    from_versions_by_ref = {
        from_ref: read_version_from_ref(repo, from_ref, args.version_file, args.version_pattern)
        for from_ref in from_refs
    }
    from_versions = list(dict.fromkeys(from_versions_by_ref.values()))
    installed_baselines = load_installed_baseline_manifests(args.installed_baseline_manifest)
    unknown_baseline_versions = sorted(
        {baseline.version for baseline in installed_baselines} - set(from_versions)
    )
    if unknown_baseline_versions:
        raise SystemExit(
            "Installed baseline versions must also be declared by --from-ref: "
            + ", ".join(unknown_baseline_versions)
        )
    asset_prefix = args.asset_prefix or f"{args.app_name}_update_"
    output = args.output or repo / "dist" / f"{asset_prefix}{version}.zip"

    blocked_names = frozenset(args.blocked_path_name or DEFAULT_BLOCKED_PATH_NAMES)
    blocked_prefixes = tuple(args.blocked_path_prefix or DEFAULT_BLOCKED_PATH_PREFIXES)
    blocked_suffixes = tuple(args.blocked_path_suffix or DEFAULT_BLOCKED_PATH_SUFFIXES)

    all_changed = sorted(
        {
            path
            for from_ref in from_refs
            for path in git_lines(repo, "diff", "--name-only", f"{from_ref}..{args.to_ref}")
        }
    )
    blocked = [
        path
        for path in all_changed
        if requires_packaged_refresh(path, blocked_names, blocked_prefixes, blocked_suffixes)
    ]
    if blocked:
        print("Refusing to build a source-only update because these paths changed:", file=sys.stderr)
        for path in blocked:
            print(f"  {path}", file=sys.stderr)
        return 1

    changed_runtime = sorted(
        {
            path
            for from_ref in from_refs
            for path in changed_runtime_paths(repo, from_ref, args.to_ref, tuple(args.runtime_path))
        }
    )
    if not changed_runtime:
        print("No runtime source files changed.", file=sys.stderr)
        return 1

    merge_path, editable_assignments = resolve_python_config_merge(
        args.python_config_merge,
        args.editable_assignment,
        changed_runtime,
    )
    if merge_path is not None:
        try:
            validate_python_config_template(
                git_file_bytes(repo, args.to_ref, merge_path),
                editable_assignments,
                path=merge_path,
            )
        except PythonConfigMergeError as exc:
            raise SystemExit(str(exc)) from exc

    manifest_files = []
    payloads = {}
    for path in changed_runtime:
        current_bytes = git_file_bytes(repo, args.to_ref, path)
        previous_states_by_version = {from_version: [] for from_version in from_versions}
        for from_ref, from_version in from_versions_by_ref.items():
            previous_bytes = git_file_bytes(repo, from_ref, path, allow_missing=True)
            add_unique(
                previous_states_by_version[from_version],
                None if previous_bytes is None else sha256(previous_bytes),
            )
        for baseline in installed_baselines:
            if path not in baseline.files:
                raise SystemExit(
                    f"Installed baseline manifest {baseline.source} does not describe changed file {path}; "
                    "list its SHA-256 or null when the file was absent"
                )
            add_unique(previous_states_by_version[baseline.version], baseline.files[path])

        manifest_file = {"path": path, "sha256": sha256(current_bytes)}
        manifest_file.update(encode_previous_baselines(path, previous_states_by_version))
        if path == merge_path:
            manifest_file["update_strategy"] = PYTHON_CONFIG_MERGE_STRATEGY
            manifest_file["editable_assignments"] = list(editable_assignments)
        manifest_files.append(manifest_file)
        payloads[path] = current_bytes

    manifest = {
        "schema_version": 2 if merge_path is not None else 1,
        "app": args.app_name,
        "version": version,
        "from_versions": from_versions,
        "changed_files": changed_runtime,
        "files": manifest_files,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        for path, data in payloads.items():
            zf.writestr(path, data)

    print(output)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a code-only desktop source update zip.")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="App repository root. Defaults to cwd.")
    parser.add_argument("--app-name", required=True, help="Manifest app name expected by the runtime updater.")
    parser.add_argument(
        "--runtime-path",
        action="append",
        required=True,
        help="Runtime source file or folder to package when changed. Repeat as needed.",
    )
    parser.add_argument(
        "--from-ref",
        action="append",
        dest="from_refs",
        required=True,
        help="Previous release tag or commit users may have installed. Repeat for jump-ahead support.",
    )
    parser.add_argument(
        "--installed-baseline-manifest",
        action="append",
        type=Path,
        default=[],
        help=(
            "JSON file describing an exact installed byte baseline. Repeat for multiple package or "
            "source-patched baselines. Each manifest maps paths to SHA-256 strings or null."
        ),
    )
    parser.add_argument(
        "--python-config-merge",
        help=(
            "Changed runtime .py file whose downloaded template should preserve explicitly declared "
            "installed values. Schema 2 supports one such file per asset."
        ),
    )
    parser.add_argument(
        "--editable-assignment",
        action="append",
        default=[],
        help=(
            "Top-level literal assignment to preserve in --python-config-merge. Repeat for each "
            "user-editable setting."
        ),
    )
    parser.add_argument("--to-ref", default="HEAD", help="New release tag or commit to package. Defaults to HEAD.")
    parser.add_argument("--version", help="Target version string. Defaults to VERSION in --version-file at --to-ref.")
    parser.add_argument(
        "--version-file",
        required=True,
        help="Python file containing the version assignment, relative to the app repo.",
    )
    parser.add_argument(
        "--version-pattern",
        default=r"VERSION\s*=\s*['\"]([^'\"]+)['\"]",
        help="Regex with one capture group used to read versions from --version-file.",
    )
    parser.add_argument("--asset-prefix", help="Output asset prefix. Defaults to <app-name>_update_.")
    parser.add_argument("--output", type=Path, help="Output zip path. Defaults to dist/<asset-prefix><version>.zip.")
    parser.add_argument("--blocked-path-name", action="append", help="Exact filename/path that requires full packaging. Repeat to override defaults.")
    parser.add_argument("--blocked-path-prefix", action="append", help="Path prefix that requires full packaging. Repeat to override defaults.")
    parser.add_argument("--blocked-path-suffix", action="append", help="Path suffix that requires full packaging. Repeat to override defaults.")
    return parser.parse_args(argv)


def resolve_python_config_merge(
    merge_path: str | None,
    editable_assignments: list[str],
    changed_runtime: list[str],
) -> tuple[str | None, tuple[str, ...]]:
    if merge_path is None:
        if editable_assignments:
            raise SystemExit("--editable-assignment requires --python-config-merge")
        return None, ()

    normalized = normalize_path(merge_path)
    if not normalized.lower().endswith(".py"):
        raise SystemExit("--python-config-merge must identify a .py runtime path")
    if normalized not in changed_runtime:
        raise SystemExit(
            f"Python config merge path {normalized} is not a changed runtime file in this asset"
        )
    try:
        names = validate_editable_assignment_names(editable_assignments)
    except PythonConfigMergeError as exc:
        raise SystemExit(str(exc)) from exc
    return normalized, names


def load_installed_baseline_manifests(paths: list[Path]) -> list[InstalledBaseline]:
    baselines = []
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise SystemExit(f"Could not read installed baseline manifest {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Could not parse installed baseline manifest {path}: {exc}") from exc

        if not isinstance(data, dict):
            raise SystemExit(f"Installed baseline manifest {path} must contain a JSON object")
        version = data.get("version")
        if not isinstance(version, str) or not version:
            raise SystemExit(f"Installed baseline manifest {path} must contain a non-empty string version")
        raw_files = data.get("files")
        if not isinstance(raw_files, dict):
            raise SystemExit(f"Installed baseline manifest {path} must contain a files object")

        files = {}
        for raw_path, digest in raw_files.items():
            if not isinstance(raw_path, str):
                raise SystemExit(f"Installed baseline manifest {path} contains a non-string file path")
            normalized = normalize_manifest_path(raw_path, path)
            if normalized in files:
                raise SystemExit(
                    f"Installed baseline manifest {path} contains duplicate normalized path {normalized}"
                )
            if digest is not None and (
                not isinstance(digest, str) or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None
            ):
                raise SystemExit(
                    f"Installed baseline manifest {path} must map {normalized} to a SHA-256 string or null"
                )
            files[normalized] = None if digest is None else digest.lower()
        baselines.append(InstalledBaseline(source=path, version=version, files=files))
    return baselines


def normalize_manifest_path(path: str, source: Path) -> str:
    normalized = normalize_path(path)
    pure_path = PurePosixPath(normalized)
    if not normalized or normalized.startswith("/") or any(
        part in {"", ".", ".."} for part in pure_path.parts
    ):
        raise SystemExit(f"Installed baseline manifest {source} contains unsafe path {path!r}")
    return str(pure_path)


def add_unique(values: list[str | None], value: str | None) -> None:
    if value not in values:
        values.append(value)


def encode_previous_baselines(
    path: str, states_by_version: dict[str, list[str | None]]
) -> dict[str, object]:
    if all(len(states) == 1 for states in states_by_version.values()):
        return {
            "previous_sha256_by_version": {
                version: states[0] for version, states in states_by_version.items()
            }
        }

    versions_with_missing = [
        version for version, states in states_by_version.items() if None in states
    ]
    if versions_with_missing:
        raise SystemExit(
            f"Cannot represent all installed baselines for {path} in manifest schema 1 because "
            "missing-file states cannot be combined with multiple present-file hashes; "
            f"conflicting version(s): {', '.join(versions_with_missing)}"
        )

    accepted_hashes = []
    for states in states_by_version.values():
        for digest in states:
            if digest is not None:
                add_unique(accepted_hashes, digest)
    return {"previous_sha256": accepted_hashes}


def changed_runtime_paths(repo: Path, from_ref: str, to_ref: str, runtime_paths: tuple[str, ...]) -> list[str]:
    result = git_lines(repo, "diff", "--name-status", f"{from_ref}..{to_ref}", "--", *runtime_paths)
    paths = []
    unsupported = []
    for line in result:
        parts = line.split("\t")
        status = parts[0]
        if status.startswith(("A", "M")) and len(parts) == 2:
            paths.append(normalize_path(parts[1]))
        else:
            unsupported.append(line)

    if unsupported:
        print("Runtime deletions, renames, or complex changes need a packaged refresh:", file=sys.stderr)
        for line in unsupported:
            print(f"  {line}", file=sys.stderr)
        raise SystemExit(1)

    return sorted(paths)


def read_version_from_ref(repo: Path, ref: str, version_file: str, version_pattern: str) -> str:
    text = git_file_bytes(repo, ref, version_file).decode("utf-8")
    match = re.search(version_pattern, text)
    if not match:
        raise SystemExit(f"Could not read version from {ref}:{version_file}")
    return match.group(1)


def git_lines(repo: Path, *args: str) -> list[str]:
    result = run_git(repo, *args)
    return [line for line in result.stdout.splitlines() if line]


def git_file_bytes(repo: Path, ref: str, path: str, *, allow_missing: bool = False) -> bytes | None:
    result = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{path}"], capture_output=True, check=False)
    if result.returncode == 0:
        return result.stdout
    if allow_missing:
        return None
    message = result.stderr.decode("utf-8", errors="replace").strip()
    raise SystemExit(message or f"Could not read {ref}:{path}")


def run_git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False, text=True)
    if check and result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "git command failed")
    return result


def normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def requires_packaged_refresh(
    path: str,
    blocked_names: frozenset[str],
    blocked_prefixes: tuple[str, ...],
    blocked_suffixes: tuple[str, ...],
) -> bool:
    normalized = normalize_path(path)
    root_name = normalized.rsplit("/", maxsplit=1)[-1]
    suffix = Path(root_name).suffix.lower()
    return (
        normalized in blocked_names
        or root_name in blocked_names
        or suffix in blocked_suffixes
        or normalized.startswith(blocked_prefixes)
    )


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
