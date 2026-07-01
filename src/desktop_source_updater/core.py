from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any


DEFAULT_TIMEOUT_SECONDS = 6
DEFAULT_MAX_UPDATE_BYTES = 80 * 1024 * 1024
MANIFEST_NAME = "manifest.json"

DEFAULT_BLOCKED_PATH_NAMES = frozenset(
    {
        "app.spec",
        "environment.yml",
        "poetry.lock",
        "pyproject.toml",
        "requirements.txt",
        "setup.cfg",
        "setup.py",
    }
)
DEFAULT_BLOCKED_PATH_SUFFIXES = (".lock", ".spec")
DEFAULT_BLOCKED_PATH_PREFIXES = (
    ".worktrees/",
    "archive/",
    "build/",
    "cache/",
    "data/",
    "dist/",
)


@dataclass(frozen=True)
class UpdateConfig:
    app_name: str
    app_root: str | os.PathLike[str]
    release_api_url: str = ""
    asset_prefix: str = ""
    allowed_payload_paths: tuple[str, ...] = ()
    installed_version: str | None = None
    installed_version_file: str | os.PathLike[str] | None = None
    version_pattern: str = r"VERSION\s*=\s*['\"]([^'\"]+)['\"]"
    update_url: str | None = None
    skip_update_env: str | None = None
    update_zip_url_env: str | None = None
    release_api_env: str | None = None
    asset_prefix_env: str | None = None
    timeout_env: str | None = None
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_update_bytes: int = DEFAULT_MAX_UPDATE_BYTES
    blocked_path_names: frozenset[str] = DEFAULT_BLOCKED_PATH_NAMES
    blocked_path_prefixes: tuple[str, ...] = DEFAULT_BLOCKED_PATH_PREFIXES
    blocked_path_suffixes: tuple[str, ...] = DEFAULT_BLOCKED_PATH_SUFFIXES


@dataclass(frozen=True)
class StartupUpdateResult:
    status: str
    message: str
    changed_files: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class UpdateFile:
    path: str
    sha256: str
    previous_sha256: tuple[str, ...] = field(default_factory=tuple)
    previous_sha256_by_version: dict[str, str | None] = field(default_factory=dict)


@dataclass(frozen=True)
class UpdatePackage:
    app_name: str
    version: str
    files: tuple[UpdateFile, ...]
    changed_files: tuple[str, ...]
    from_versions: tuple[str, ...] = field(default_factory=tuple)
    minimum_version: str | None = None


class UpdateError(Exception):
    pass


def run_startup_update(config: UpdateConfig) -> StartupUpdateResult:
    """Apply a compatible code-only release asset before app imports occur."""
    if config.skip_update_env and _env_flag_is_enabled(config.skip_update_env):
        return StartupUpdateResult("disabled", "startup update disabled by environment")

    root = Path(config.app_root).resolve()
    timeout_seconds = _get_timeout_seconds(config)
    try:
        installed_version = _resolve_installed_version(root, config)
        if not installed_version:
            return StartupUpdateResult("skipped", "could not determine installed app version")

        resolved_url = _resolve_update_url(config, timeout_seconds)
        if not resolved_url:
            return StartupUpdateResult("up-to-date", "no source update asset found in the latest release")

        with tempfile.TemporaryDirectory(prefix=f"{config.app_name}-update-") as temp_dir:
            update_zip = Path(temp_dir) / "update.zip"
            update_zip.write_bytes(_read_url_bytes(resolved_url, timeout_seconds, config.max_update_bytes))

            package = _load_update_package(update_zip, config)
            if not _is_newer_version(package.version, installed_version):
                return StartupUpdateResult("up-to-date", f"installed version {installed_version} is up to date")

            compatibility_error = _get_compatibility_error(installed_version, package)
            if compatibility_error:
                return StartupUpdateResult("blocked", compatibility_error, package.changed_files)

            blocked_files = tuple(path for path in package.changed_files if _blocks_hot_update(path, config))
            if blocked_files:
                return StartupUpdateResult(
                    "blocked",
                    "update includes dependency, packaging, or local-data paths; packaged refresh required",
                    blocked_files,
                )

            local_edit_error = _get_local_edit_error(root, installed_version, package)
            if local_edit_error:
                return StartupUpdateResult("skipped", local_edit_error, package.changed_files)

            _apply_update_package(root, update_zip, package)
            return StartupUpdateResult("updated", f"updated to {package.version}", package.changed_files)
    except UpdateError as exc:
        return StartupUpdateResult("failed", str(exc))


def format_update_message(result: StartupUpdateResult) -> str:
    if result.status in {"disabled", "up-to-date"}:
        return ""
    if result.status == "updated":
        return f"{result.message} ({len(result.changed_files)} changed files)"
    if result.changed_files:
        preview = ", ".join(result.changed_files[:3])
        if len(result.changed_files) > 3:
            preview = f"{preview}, ..."
        return f"{result.message}: {preview}"
    return result.message


def read_python_assignment_version(path: str | os.PathLike[str], pattern: str = UpdateConfig.version_pattern) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""
    match = re.search(pattern, text)
    return match.group(1) if match else ""


def _resolve_installed_version(root: Path, config: UpdateConfig) -> str:
    if config.installed_version:
        return config.installed_version
    if not config.installed_version_file:
        return ""
    return read_python_assignment_version(root / config.installed_version_file, config.version_pattern)


def _env_flag_is_enabled(name: str) -> bool:
    value = os.environ.get(name, "")
    return value.lower() in {"1", "true", "yes", "on"}


def _get_timeout_seconds(config: UpdateConfig) -> int:
    value = os.environ.get(config.timeout_env or "") if config.timeout_env else None
    if not value:
        return config.timeout_seconds
    try:
        return max(1, int(value))
    except ValueError:
        return config.timeout_seconds


def _resolve_update_url(config: UpdateConfig, timeout_seconds: int) -> str:
    direct_url = config.update_url
    if not direct_url and config.update_zip_url_env:
        direct_url = os.environ.get(config.update_zip_url_env)
    if direct_url:
        return direct_url

    api_url = config.release_api_url
    if config.release_api_env:
        api_url = os.environ.get(config.release_api_env, api_url)
    if not api_url:
        return ""

    try:
        release = json.loads(_read_url_bytes(api_url, timeout_seconds, config.max_update_bytes).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise UpdateError(f"could not read update release metadata: {exc}") from exc

    asset_prefix = config.asset_prefix
    if config.asset_prefix_env:
        asset_prefix = os.environ.get(config.asset_prefix_env, asset_prefix)
    if not asset_prefix:
        return ""

    tag_name = str(release.get("tag_name") or "")
    assets = release.get("assets") or []
    candidates = [asset for asset in assets if _is_update_asset_name(str(asset.get("name") or ""), asset_prefix)]
    if not candidates:
        return ""

    exact_name = f"{asset_prefix}{tag_name}.zip" if tag_name else ""
    selected = next((asset for asset in candidates if str(asset.get("name") or "") == exact_name), candidates[0])
    return str(selected.get("browser_download_url") or "")


def _is_update_asset_name(name: str, asset_prefix: str) -> bool:
    return name.startswith(asset_prefix) and name.lower().endswith(".zip")


def _read_url_bytes(url: str, timeout_seconds: int, max_update_bytes: int) -> bytes:
    local_path = Path(url)
    if local_path.exists():
        data = local_path.read_bytes()
    else:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme == "file":
            data = Path(urllib.request.url2pathname(parsed.path)).read_bytes()
        else:
            request = urllib.request.Request(
                url,
                headers={"Accept": "application/octet-stream", "User-Agent": "desktop-source-updater"},
            )
            try:
                with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                    data = response.read(max_update_bytes + 1)
            except (OSError, urllib.error.URLError) as exc:
                raise UpdateError(f"could not download update metadata or asset: {exc}") from exc

    if len(data) > max_update_bytes:
        raise UpdateError("update asset is too large")
    return data


def _load_update_package(update_zip: Path, config: UpdateConfig) -> UpdatePackage:
    try:
        with zipfile.ZipFile(update_zip) as zf:
            names = {_normalize_payload_path(name) for name in zf.namelist() if not name.endswith("/")}
            if MANIFEST_NAME not in names:
                raise UpdateError("update zip is missing manifest.json")

            manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
            package = _parse_manifest(manifest, zf, config)
            expected_names = {MANIFEST_NAME, *(file.path for file in package.files)}
            extra_names = tuple(sorted(names - expected_names))
            if extra_names:
                raise UpdateError(f"update zip contains unexpected files: {', '.join(extra_names[:3])}")
            return package
    except zipfile.BadZipFile as exc:
        raise UpdateError("update asset is not a valid zip file") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise UpdateError(f"could not read update manifest: {exc}") from exc


def _parse_manifest(manifest: dict[str, Any], zf: zipfile.ZipFile, config: UpdateConfig) -> UpdatePackage:
    if manifest.get("schema_version") != 1:
        raise UpdateError("update manifest has an unsupported schema version")

    app_name = str(manifest.get("app") or "")
    if app_name != config.app_name:
        raise UpdateError("update manifest is for a different app")

    version = str(manifest.get("version") or "")
    if not version:
        raise UpdateError("update manifest is missing version")

    zip_names = {_normalize_payload_path(name) for name in zf.namelist()}
    files = tuple(_parse_update_file(item, zf, zip_names) for item in manifest.get("files") or [])
    if not files:
        raise UpdateError("update manifest does not list any files")

    changed_files = tuple(_normalize_payload_path(path) for path in (manifest.get("changed_files") or [file.path for file in files]))
    from_versions = tuple(str(version) for version in manifest.get("from_versions") or [])
    minimum_version = manifest.get("minimum_version")
    if minimum_version is not None:
        minimum_version = str(minimum_version)

    return UpdatePackage(app_name=app_name, version=version, files=files, changed_files=changed_files, from_versions=from_versions, minimum_version=minimum_version)


def _parse_update_file(item: dict[str, Any], zf: zipfile.ZipFile, zip_names: set[str]) -> UpdateFile:
    if not isinstance(item, dict):
        raise UpdateError("update manifest files must be objects")

    path = _normalize_payload_path(str(item.get("path") or ""))
    if path not in zip_names:
        raise UpdateError(f"update zip is missing payload file: {path}")

    payload_sha256 = _sha256_bytes(zf.read(path))
    expected_sha256 = str(item.get("sha256") or "")
    if expected_sha256 and payload_sha256 != expected_sha256:
        raise UpdateError(f"payload hash mismatch for {path}")

    return UpdateFile(
        path=path,
        sha256=payload_sha256,
        previous_sha256=_coerce_previous_sha256_values(item.get("previous_sha256")),
        previous_sha256_by_version=_coerce_previous_sha256_by_version(item.get("previous_sha256_by_version")),
    )


def _normalize_payload_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    pure_path = PurePosixPath(normalized)
    if not normalized or normalized.startswith("/") or any(part in {"", ".", ".."} for part in pure_path.parts):
        raise UpdateError(f"unsafe update path: {path}")
    return str(pure_path)


def _is_allowed_payload_path(path: str, allowed_payload_paths: tuple[str, ...]) -> bool:
    normalized = path.replace("\\", "/")
    for allowed in allowed_payload_paths:
        allowed_normalized = allowed.replace("\\", "/")
        if allowed_normalized.endswith("/") and normalized.startswith(allowed_normalized):
            return True
        if normalized == allowed_normalized:
            return True
    return False


def _blocks_hot_update(path: str, config: UpdateConfig) -> bool:
    normalized = path.replace("\\", "/")
    root_name = normalized.rsplit("/", maxsplit=1)[-1]
    suffix = Path(root_name).suffix.lower()
    return (
        not _is_allowed_payload_path(normalized, config.allowed_payload_paths)
        or normalized in config.blocked_path_names
        or root_name in config.blocked_path_names
        or suffix in config.blocked_path_suffixes
        or normalized.startswith(config.blocked_path_prefixes)
    )


def _is_newer_version(candidate: str, installed: str) -> bool:
    return _version_key(candidate) > _version_key(installed)


def _version_key(version: str) -> tuple[int, ...]:
    parts = tuple(int(part) for part in re.findall(r"\d+", version))
    return parts or (0,)


def _get_compatibility_error(installed_version: str, package: UpdatePackage) -> str:
    if package.from_versions and installed_version not in package.from_versions:
        return f"update {package.version} is not compatible with installed version {installed_version}"
    if package.minimum_version and _version_key(installed_version) < _version_key(package.minimum_version):
        return f"update {package.version} requires at least {package.minimum_version}"
    return ""


def _coerce_previous_sha256_values(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(str(item) for item in value if item is not None)
    raise UpdateError("previous_sha256 must be a string or list of strings")


def _coerce_previous_sha256_by_version(value: Any) -> dict[str, str | None]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise UpdateError("previous_sha256_by_version must be an object")
    return {str(version): None if digest is None else str(digest) for version, digest in value.items()}


def _get_local_edit_error(root: Path, installed_version: str, package: UpdatePackage) -> str:
    for update_file in package.files:
        target = root / update_file.path
        if update_file.previous_sha256_by_version:
            if installed_version not in update_file.previous_sha256_by_version:
                return f"update manifest cannot verify {update_file.path} from installed version {installed_version}"
            expected_hash = update_file.previous_sha256_by_version[installed_version]
            if expected_hash is None:
                if target.exists():
                    return "local runtime files differ from the update baseline; not auto-updating"
                continue
            if not target.exists():
                return f"local file is missing: {update_file.path}"
            if _sha256_file(target) != expected_hash:
                return "local runtime files differ from the update baseline; not auto-updating"
            continue

        if not target.exists():
            if update_file.previous_sha256:
                return f"local file is missing: {update_file.path}"
            continue
        if not update_file.previous_sha256:
            return "update manifest cannot verify local source state; packaged refresh required"
        if _sha256_file(target) not in update_file.previous_sha256:
            return "local runtime files differ from the update baseline; not auto-updating"
    return ""


def _apply_update_package(root: Path, update_zip: Path, package: UpdatePackage) -> None:
    temp_backup = tempfile.TemporaryDirectory(prefix=f".{package.app_name}-update-backup-", dir=root)
    backup_root = Path(temp_backup.name)
    applied: list[tuple[Path, Path, bool]] = []
    try:
        with zipfile.ZipFile(update_zip) as zf:
            for update_file in package.files:
                target = root / update_file.path
                backup = backup_root / update_file.path
                staged = backup_root / "__staged__" / update_file.path
                existed = target.exists()
                if existed:
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, backup)

                staged.parent.mkdir(parents=True, exist_ok=True)
                staged.write_bytes(zf.read(update_file.path))
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged, target)
                applied.append((target, backup, existed))
    except Exception as exc:
        _roll_back_update(applied)
        raise UpdateError(f"could not apply update: {exc}") from exc
    finally:
        temp_backup.cleanup()


def _roll_back_update(applied: list[tuple[Path, Path, bool]]) -> None:
    for target, backup, existed in reversed(applied):
        if existed and backup.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)
        elif target.exists():
            target.unlink()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


