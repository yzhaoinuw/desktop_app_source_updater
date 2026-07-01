from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

from .core import (
    DEFAULT_BLOCKED_PATH_NAMES,
    DEFAULT_BLOCKED_PATH_PREFIXES,
    DEFAULT_BLOCKED_PATH_SUFFIXES,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo = args.repo.resolve()
    version = args.version or read_version_from_ref(repo, args.to_ref, args.version_file, args.version_pattern)
    from_refs = args.from_refs
    from_versions_by_ref = {
        from_ref: read_version_from_ref(repo, from_ref, args.version_file, args.version_pattern)
        for from_ref in from_refs
    }
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

    manifest_files = []
    payloads = {}
    for path in changed_runtime:
        current_bytes = git_file_bytes(repo, args.to_ref, path)
        previous_sha256_by_version = {}
        for from_ref, from_version in from_versions_by_ref.items():
            previous_bytes = git_file_bytes(repo, from_ref, path, allow_missing=True)
            previous_sha256_by_version[from_version] = None if previous_bytes is None else sha256(previous_bytes)
        manifest_files.append(
            {
                "path": path,
                "sha256": sha256(current_bytes),
                "previous_sha256_by_version": previous_sha256_by_version,
            }
        )
        payloads[path] = current_bytes

    manifest = {
        "schema_version": 1,
        "app": args.app_name,
        "version": version,
        "from_versions": list(from_versions_by_ref.values()),
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
