from __future__ import annotations

import email.utils
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .python_config import (
    PYTHON_CONFIG_MERGE_STRATEGY,
    REPLACE_STRATEGY,
    PythonConfigMergeError,
    merge_python_config,
    validate_editable_assignment_names,
)


DEFAULT_TIMEOUT_SECONDS = 6
DEFAULT_MAX_UPDATE_BYTES = 80 * 1024 * 1024
DEFAULT_CHECK_INTERVAL_SECONDS = 24 * 60 * 60
DEFAULT_FAILURE_RETRY_SECONDS = 60 * 60
MANIFEST_NAME = "manifest.json"
RELEASE_METADATA_ACCEPT = "application/vnd.github+json"
UPDATE_ASSET_ACCEPT = "application/octet-stream"
MISSING_ASSET_STATUSES = frozenset({404, 410})
METHOD_NOT_SUPPORTED_STATUSES = frozenset({405, 501})

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
    latest_release_url: str = ""
    latest_release_env: str | None = None
    check_state_file: str | os.PathLike[str] | None = None
    check_interval_seconds: int = DEFAULT_CHECK_INTERVAL_SECONDS
    failure_retry_seconds: int = DEFAULT_FAILURE_RETRY_SECONDS
    force_check_env: str | None = None
    on_update_available: Callable[[str, str], None] | None = field(
        default=None,
        repr=False,
        compare=False,
    )


@dataclass(frozen=True)
class StartupUpdateResult:
    status: str
    message: str
    changed_files: tuple[str, ...] = field(default_factory=tuple)
    installed_version: str | None = None
    target_version: str | None = None


@dataclass(frozen=True)
class ReleaseDiscovery:
    tag_name: str
    asset_url: str
    # True when the URL was composed from the tag rather than read from a
    # release asset list, so its existence has not been established yet.
    asset_is_composed: bool = False


@dataclass(frozen=True)
class UpdateFile:
    path: str
    sha256: str
    previous_sha256: tuple[str, ...] = field(default_factory=tuple)
    previous_sha256_by_version: dict[str, str | None] = field(default_factory=dict)
    update_strategy: str = REPLACE_STRATEGY
    editable_assignments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class UpdatePackage:
    schema_version: int
    app_name: str
    version: str
    files: tuple[UpdateFile, ...]
    changed_files: tuple[str, ...]
    from_versions: tuple[str, ...] = field(default_factory=tuple)
    minimum_version: str | None = None


class UpdateError(Exception):
    pass


class UpdateRequestError(UpdateError):
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.headers = headers or {}


def run_startup_update(
    config: UpdateConfig,
    *,
    force_check: bool = False,
) -> StartupUpdateResult:
    """Apply a compatible code-only release asset before app imports occur."""
    if config.skip_update_env and _env_flag_is_enabled(config.skip_update_env):
        return StartupUpdateResult("disabled", "startup update disabled by environment")

    root = Path(config.app_root).resolve()
    timeout_seconds = _get_timeout_seconds(config)
    installed_version: str | None = None
    target_version: str | None = None
    state_path: Path | None = None
    source_key = ""
    try:
        installed_version = _resolve_installed_version(root, config)
        if not installed_version:
            return StartupUpdateResult("skipped", "could not determine installed app version")

        resolved_url = _resolve_direct_update_url(config)
        discovered_tag = ""
        asset_is_composed = False
        if not resolved_url:
            release_mode, release_url = _resolve_release_source(config)
            if not release_url:
                return StartupUpdateResult(
                    "up-to-date",
                    "no source update location is configured",
                    installed_version=installed_version,
                )

            asset_prefix = _get_asset_prefix(config)
            state_path = _resolve_check_state_path(root, config, release_url)
            source_key = _check_source_key(config.app_name, release_mode, release_url, asset_prefix)
            force_check = force_check or bool(
                config.force_check_env and _env_flag_is_enabled(config.force_check_env)
            )
            now = time.time()
            if (
                not force_check
                and state_path is not None
                and _check_is_throttled(state_path, source_key, now)
            ):
                return StartupUpdateResult(
                    "up-to-date",
                    "startup update check deferred by the configured interval",
                    installed_version=installed_version,
                )

            discovery = _discover_release(
                release_mode,
                release_url,
                asset_prefix,
                timeout_seconds,
                config.max_update_bytes,
            )
            discovered_tag = discovery.tag_name
            target_version = discovered_tag
            if state_path is not None:
                _write_check_state(
                    state_path,
                    source_key,
                    now + max(0, config.check_interval_seconds),
                )

            if not _is_newer_version(discovered_tag, installed_version):
                return StartupUpdateResult(
                    "up-to-date",
                    f"installed version {installed_version} is up to date",
                    installed_version=installed_version,
                    target_version=target_version,
                )
            # Redirect discovery composes the asset URL from the tag instead of
            # reading a release asset list, so confirm the asset exists before
            # telling the user an update is on the way. A release that ships no
            # source update asset is a normal outcome, not a failure.
            if not discovery.asset_url or (
                discovery.asset_is_composed
                and not _asset_is_available(discovery.asset_url, timeout_seconds)
            ):
                return StartupUpdateResult(
                    "up-to-date",
                    f"release {discovered_tag} has no matching source update asset",
                    installed_version=installed_version,
                    target_version=target_version,
                )

            _notify_update_available(config, installed_version, discovered_tag)
            resolved_url = discovery.asset_url
            asset_is_composed = discovery.asset_is_composed

        with tempfile.TemporaryDirectory(prefix=f"{config.app_name}-update-") as temp_dir:
            update_zip = Path(temp_dir) / "update.zip"
            try:
                asset_bytes = _read_url_bytes(
                    resolved_url,
                    timeout_seconds,
                    config.max_update_bytes,
                    error_context="could not download update asset",
                )
            except UpdateRequestError as exc:
                # The asset can still disappear between the availability probe
                # and this download; report it the same way either path finds it.
                if not (asset_is_composed and exc.status in MISSING_ASSET_STATUSES):
                    raise
                return StartupUpdateResult(
                    "up-to-date",
                    f"release {discovered_tag} has no matching source update asset",
                    installed_version=installed_version,
                    target_version=target_version,
                )
            update_zip.write_bytes(asset_bytes)

            package = _load_update_package(update_zip, config)
            target_version = package.version
            if discovered_tag and not _versions_agree(package.version, discovered_tag):
                raise UpdateError(
                    f"update manifest version {package.version} does not match "
                    f"discovered release tag {discovered_tag}"
                )
            if not _is_newer_version(package.version, installed_version):
                return StartupUpdateResult(
                    "up-to-date",
                    f"installed version {installed_version} is up to date",
                    installed_version=installed_version,
                    target_version=target_version,
                )

            if not discovered_tag:
                _notify_update_available(config, installed_version, package.version)

            compatibility_error = _get_compatibility_error(installed_version, package)
            if compatibility_error:
                return StartupUpdateResult(
                    "blocked",
                    compatibility_error,
                    package.changed_files,
                    installed_version,
                    target_version,
                )

            blocked_files = tuple(path for path in package.changed_files if _blocks_hot_update(path, config))
            if blocked_files:
                return StartupUpdateResult(
                    "blocked",
                    "update includes dependency, packaging, or local-data paths; packaged refresh required",
                    blocked_files,
                    installed_version,
                    target_version,
                )

            local_edit_error = _get_local_edit_error(root, installed_version, package)
            if local_edit_error:
                return StartupUpdateResult(
                    "skipped",
                    local_edit_error,
                    package.changed_files,
                    installed_version,
                    target_version,
                )

            prepared_payloads = _prepare_update_payloads(root, update_zip, package)
            _apply_update_package(root, prepared_payloads, package)
            return StartupUpdateResult(
                "updated",
                f"updated to {package.version}",
                package.changed_files,
                installed_version,
                target_version,
            )
    except UpdateRequestError as exc:
        if state_path is not None and source_key:
            now = time.time()
            if exc.status in {403, 429}:
                # A quota response carries its own, longer, window; never let
                # the ordinary failure retry shorten it.
                retry_at = _retry_at_from_response(exc.headers, now, config.check_interval_seconds)
            else:
                retry_at = _failure_retry_at(now, config)
            _write_check_state(state_path, source_key, retry_at)
        return StartupUpdateResult(
            "failed",
            str(exc),
            installed_version=installed_version,
            target_version=target_version,
        )
    except UpdateError as exc:
        if state_path is not None and source_key:
            _write_check_state(state_path, source_key, _failure_retry_at(time.time(), config))
        return StartupUpdateResult(
            "failed",
            str(exc),
            installed_version=installed_version,
            target_version=target_version,
        )


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


def _resolve_direct_update_url(config: UpdateConfig) -> str:
    direct_url = config.update_url
    if not direct_url and config.update_zip_url_env:
        direct_url = os.environ.get(config.update_zip_url_env)
    return direct_url or ""


def _resolve_release_source(config: UpdateConfig) -> tuple[str, str]:
    latest_release_url = config.latest_release_url
    if config.latest_release_env:
        latest_release_url = os.environ.get(config.latest_release_env, latest_release_url)
    if latest_release_url:
        return "redirect", latest_release_url

    api_url = config.release_api_url
    if config.release_api_env:
        api_url = os.environ.get(config.release_api_env, api_url)
    return ("api", api_url) if api_url else ("", "")


def _get_asset_prefix(config: UpdateConfig) -> str:
    asset_prefix = config.asset_prefix
    if config.asset_prefix_env:
        asset_prefix = os.environ.get(config.asset_prefix_env, asset_prefix)
    return asset_prefix


def _discover_release(
    mode: str,
    url: str,
    asset_prefix: str,
    timeout_seconds: int,
    max_update_bytes: int,
) -> ReleaseDiscovery:
    if mode == "redirect":
        return _discover_release_from_redirect(url, asset_prefix, timeout_seconds)
    return _discover_release_from_api(url, asset_prefix, timeout_seconds, max_update_bytes)


def _discover_release_from_redirect(
    latest_release_url: str,
    asset_prefix: str,
    timeout_seconds: int,
) -> ReleaseDiscovery:
    release_url = _read_latest_release_redirect(latest_release_url, timeout_seconds)
    tag_name, repo_url = _release_tag_and_repo_url(release_url)
    asset_name = f"{asset_prefix}{tag_name}.zip" if asset_prefix else ""
    asset_url = ""
    if asset_name:
        asset_url = (
            f"{repo_url}/releases/download/"
            f"{urllib.parse.quote(tag_name, safe='')}/"
            f"{urllib.parse.quote(asset_name, safe='')}"
        )
    return ReleaseDiscovery(tag_name, asset_url, asset_is_composed=bool(asset_url))


def _discover_release_from_api(
    api_url: str,
    asset_prefix: str,
    timeout_seconds: int,
    max_update_bytes: int,
) -> ReleaseDiscovery:
    try:
        release = json.loads(
            _read_url_bytes(
                api_url,
                timeout_seconds,
                max_update_bytes,
                accept=RELEASE_METADATA_ACCEPT,
                error_context="could not discover update release metadata",
            ).decode("utf-8")
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise UpdateError(f"could not read update release metadata: {exc}") from exc
    if not isinstance(release, dict):
        raise UpdateError("could not read update release metadata: expected an object")

    tag_name = str(release.get("tag_name") or "")
    if not tag_name:
        raise UpdateError("could not discover update release tag: metadata is missing tag_name")

    if not asset_prefix:
        return ReleaseDiscovery(tag_name, "")

    assets = release.get("assets") or []
    if not isinstance(assets, list):
        assets = []
    candidates = [
        asset
        for asset in assets
        if isinstance(asset, dict)
        and _is_update_asset_name(str(asset.get("name") or ""), asset_prefix)
    ]
    if not candidates:
        return ReleaseDiscovery(tag_name, "")

    exact_name = f"{asset_prefix}{tag_name}.zip"
    selected = next((asset for asset in candidates if str(asset.get("name") or "") == exact_name), candidates[0])
    return ReleaseDiscovery(tag_name, str(selected.get("browser_download_url") or ""))


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def _read_latest_release_redirect(url: str, timeout_seconds: int) -> str:
    try:
        return _request_latest_release_location(url, timeout_seconds, method="HEAD")
    except UpdateRequestError as exc:
        if exc.status not in METHOD_NOT_SUPPORTED_STATUSES:
            raise
    return _request_latest_release_location(url, timeout_seconds, method="GET")


def _request_latest_release_location(
    url: str,
    timeout_seconds: int,
    *,
    method: str,
) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "desktop-app-source-updater"},
        method=method,
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            location = response.headers.get("Location")
            resolved_url = urllib.parse.urljoin(url, location) if location else response.geturl()
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400 and exc.headers.get("Location"):
            return urllib.parse.urljoin(url, exc.headers["Location"])
        raise _request_error("could not discover latest release tag", exc) from exc
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise _request_error("could not discover latest release tag", exc) from exc

    if resolved_url == url:
        raise UpdateError("could not discover latest release tag: latest-release URL did not redirect")
    return resolved_url


def _asset_is_available(url: str, timeout_seconds: int) -> bool:
    """Report whether a composed asset URL resolves, without downloading it.

    A release download URL answers with a redirect to storage when the asset
    exists and 404 when it does not, so the redirect is deliberately not
    followed: the status alone settles existence and no payload is fetched.

    Only a definitive missing status answers False. Every other outcome, including
    a rejected HEAD or a network error, leaves existence unknown and answers True
    so the download stays the operation that reports the real failure. This probe
    guards the update-available announcement; it must not add a failure mode of
    its own.
    """
    if not _is_remote_url(url):
        return True

    request = urllib.request.Request(
        url,
        headers={"Accept": UPDATE_ASSET_ACCEPT, "User-Agent": "desktop-app-source-updater"},
        method="HEAD",
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout_seconds):
            return True  # only 2xx reaches here; redirects raise below
    except urllib.error.HTTPError as exc:
        return exc.code not in MISSING_ASSET_STATUSES
    except (OSError, ValueError, urllib.error.URLError):
        return True


def _release_tag_and_repo_url(release_url: str) -> tuple[str, str]:
    parsed = urllib.parse.urlparse(release_url)
    marker = "/releases/tag/"
    if marker not in parsed.path:
        raise UpdateError("could not discover latest release tag from redirect location")
    repo_path, encoded_tag = parsed.path.split(marker, maxsplit=1)
    tag_name = urllib.parse.unquote(encoded_tag).strip("/")
    if not tag_name:
        raise UpdateError("could not discover latest release tag from redirect location")
    repo_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, repo_path.rstrip("/"), "", "", ""))
    return tag_name, repo_url


def _is_update_asset_name(name: str, asset_prefix: str) -> bool:
    return name.startswith(asset_prefix) and name.lower().endswith(".zip")


def _read_url_bytes(
    url: str,
    timeout_seconds: int,
    max_update_bytes: int,
    *,
    accept: str = UPDATE_ASSET_ACCEPT,
    error_context: str,
) -> bytes:
    try:
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
                    headers={"Accept": accept, "User-Agent": "desktop-app-source-updater"},
                )
                with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                    data = response.read(max_update_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise _request_error(error_context, exc) from exc
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise _request_error(error_context, exc) from exc

    if len(data) > max_update_bytes:
        raise UpdateError(f"{error_context}: response is too large")
    return data


def _request_error(context: str, exc: BaseException) -> UpdateRequestError:
    status = getattr(exc, "code", None)
    raw_headers = getattr(exc, "headers", None)
    headers = dict(raw_headers.items()) if raw_headers is not None else {}
    detail = f"HTTP {status}" if status is not None else str(exc)
    return UpdateRequestError(
        f"{context}: {detail}",
        status=status,
        headers=headers,
    )


def _resolve_check_state_path(
    root: Path,
    config: UpdateConfig,
    release_url: str,
) -> Path | None:
    if config.check_state_file is None or not _is_remote_url(release_url):
        return None
    state_path = Path(config.check_state_file).expanduser()
    return state_path if state_path.is_absolute() else root / state_path


def _is_remote_url(url: str) -> bool:
    return urllib.parse.urlparse(url).scheme.lower() in {"http", "https"}


def _check_source_key(app_name: str, mode: str, url: str, asset_prefix: str) -> str:
    return f"{app_name}|{mode}|{url}|{asset_prefix}"


def _check_is_throttled(state_path: Path, source_key: str, now: float) -> bool:
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        return (
            isinstance(state, dict)
            and state.get("source") == source_key
            and float(state.get("next_check_at", 0)) > now
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _write_check_state(state_path: Path, source_key: str, next_check_at: float) -> None:
    temp_path: Path | None = None
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=state_path.parent,
            prefix=f".{state_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(
                {
                    "schema_version": 1,
                    "source": source_key,
                    "next_check_at": next_check_at,
                },
                handle,
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, state_path)
    except OSError:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except OSError:
                pass


def _failure_retry_at(now: float, config: UpdateConfig) -> float:
    """Return the next check time after a failed run.

    A failed run has already paid its network cost, so the state is rewritten
    with a shorter window than a clean check: an offline launch or a transient
    download error should not cost a full interval, but repeating the attempt
    on every launch would put the timeout back on the startup path.
    """
    retry_seconds = min(max(0, config.failure_retry_seconds), max(0, config.check_interval_seconds))
    return now + retry_seconds


def _retry_at_from_response(
    headers: dict[str, str],
    now: float,
    check_interval_seconds: int,
) -> float:
    retry_candidates: list[float] = []
    retry_after = _get_header(headers, "Retry-After")
    if retry_after:
        try:
            retry_candidates.append(now + max(0, int(retry_after)))
        except ValueError:
            try:
                retry_candidates.append(email.utils.parsedate_to_datetime(retry_after).timestamp())
            except (TypeError, ValueError):
                pass

    rate_limit_reset = _get_header(headers, "X-RateLimit-Reset")
    if rate_limit_reset:
        try:
            retry_candidates.append(float(rate_limit_reset))
        except ValueError:
            pass

    future_candidates = [candidate for candidate in retry_candidates if candidate > now]
    if future_candidates:
        return max(future_candidates)
    return now + max(60, check_interval_seconds)


def _get_header(headers: dict[str, str], name: str) -> str:
    lowered_name = name.lower()
    return next(
        (str(value) for key, value in headers.items() if key.lower() == lowered_name),
        "",
    )


def _notify_update_available(
    config: UpdateConfig,
    installed_version: str,
    target_version: str,
) -> None:
    if config.on_update_available is None:
        return
    try:
        config.on_update_available(installed_version, target_version)
    except Exception as exc:
        raise UpdateError(f"update-available callback failed: {exc}") from exc


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
    schema_version = manifest.get("schema_version")
    if schema_version not in {1, 2}:
        raise UpdateError("update manifest has an unsupported schema version")

    app_name = str(manifest.get("app") or "")
    if app_name != config.app_name:
        raise UpdateError("update manifest is for a different app")

    version = str(manifest.get("version") or "")
    if not version:
        raise UpdateError("update manifest is missing version")

    zip_names = {_normalize_payload_path(name) for name in zf.namelist()}
    files = tuple(
        _parse_update_file(item, zf, zip_names, schema_version)
        for item in manifest.get("files") or []
    )
    if not files:
        raise UpdateError("update manifest does not list any files")
    merge_files = tuple(
        update_file for update_file in files
        if update_file.update_strategy == PYTHON_CONFIG_MERGE_STRATEGY
    )
    if schema_version == 2 and len(merge_files) != 1:
        raise UpdateError("schema 2 update manifests must declare exactly one Python config merge file")

    changed_files = tuple(
        _normalize_payload_path(path)
        for path in (manifest.get("changed_files") or [file.path for file in files])
    )
    from_versions = tuple(str(version) for version in manifest.get("from_versions") or [])
    minimum_version = manifest.get("minimum_version")
    if minimum_version is not None:
        minimum_version = str(minimum_version)

    return UpdatePackage(
        schema_version=schema_version,
        app_name=app_name,
        version=version,
        files=files,
        changed_files=changed_files,
        from_versions=from_versions,
        minimum_version=minimum_version,
    )


def _parse_update_file(
    item: dict[str, Any],
    zf: zipfile.ZipFile,
    zip_names: set[str],
    schema_version: int,
) -> UpdateFile:
    if not isinstance(item, dict):
        raise UpdateError("update manifest files must be objects")

    path = _normalize_payload_path(str(item.get("path") or ""))
    if path not in zip_names:
        raise UpdateError(f"update zip is missing payload file: {path}")

    payload_sha256 = _sha256_bytes(zf.read(path))
    expected_sha256 = str(item.get("sha256") or "")
    if expected_sha256 and payload_sha256 != expected_sha256:
        raise UpdateError(f"payload hash mismatch for {path}")

    update_strategy = item.get("update_strategy", REPLACE_STRATEGY)
    if not isinstance(update_strategy, str):
        raise UpdateError(f"update strategy for {path} must be a string")
    if schema_version == 1:
        if "update_strategy" in item or "editable_assignments" in item:
            raise UpdateError("schema 1 update manifests cannot declare update strategies")
        update_strategy = REPLACE_STRATEGY
    elif update_strategy not in {REPLACE_STRATEGY, PYTHON_CONFIG_MERGE_STRATEGY}:
        raise UpdateError(f"unsupported update strategy for {path}: {update_strategy}")

    editable_assignments = _parse_editable_assignments(item, path, update_strategy)

    return UpdateFile(
        path=path,
        sha256=payload_sha256,
        previous_sha256=_coerce_previous_sha256_values(item.get("previous_sha256")),
        previous_sha256_by_version=_coerce_previous_sha256_by_version(item.get("previous_sha256_by_version")),
        update_strategy=update_strategy,
        editable_assignments=editable_assignments,
    )


def _parse_editable_assignments(
    item: dict[str, Any], path: str, update_strategy: str
) -> tuple[str, ...]:
    value = item.get("editable_assignments")
    if update_strategy == REPLACE_STRATEGY:
        if value is not None:
            raise UpdateError(f"replace strategy file {path} cannot declare editable assignments")
        return ()
    if not path.lower().endswith(".py"):
        raise UpdateError("python config merge strategy requires a .py payload path")
    if not isinstance(value, list) or any(not isinstance(name, str) for name in value):
        raise UpdateError(f"editable assignments for {path} must be a list of strings")
    try:
        return validate_editable_assignment_names(value)
    except PythonConfigMergeError as exc:
        raise UpdateError(str(exc)) from exc


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


def _versions_agree(left: str, right: str) -> bool:
    return _canonical_version(left) == _canonical_version(right)


def _canonical_version(version: str) -> str:
    normalized = version.strip()
    return normalized[1:] if normalized.lower().startswith("v") else normalized


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
        if update_file.update_strategy == PYTHON_CONFIG_MERGE_STRATEGY:
            continue
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


def _prepare_update_payloads(
    root: Path, update_zip: Path, package: UpdatePackage
) -> dict[str, bytes]:
    prepared = {}
    try:
        with zipfile.ZipFile(update_zip) as zf:
            for update_file in package.files:
                payload = zf.read(update_file.path)
                if update_file.update_strategy == PYTHON_CONFIG_MERGE_STRATEGY:
                    target = root / update_file.path
                    if not target.is_file():
                        raise UpdateError(f"installed Python config is missing: {update_file.path}")
                    try:
                        payload = merge_python_config(
                            payload,
                            target.read_bytes(),
                            update_file.editable_assignments,
                            path=update_file.path,
                        )
                    except OSError as exc:
                        raise UpdateError(
                            f"could not read installed Python config {update_file.path}: {exc}"
                        ) from exc
                    except PythonConfigMergeError as exc:
                        raise UpdateError(str(exc)) from exc
                prepared[update_file.path] = payload
    except KeyError as exc:
        raise UpdateError(f"update zip is missing payload file: {exc.args[0]}") from exc
    return prepared


def _apply_update_package(
    root: Path,
    prepared_payloads: dict[str, bytes],
    package: UpdatePackage,
) -> None:
    temp_backup = tempfile.TemporaryDirectory(prefix=f".{package.app_name}-update-backup-", dir=root)
    backup_root = Path(temp_backup.name)
    applied: list[tuple[Path, Path, bool]] = []
    try:
        for update_file in package.files:
            target = root / update_file.path
            backup = backup_root / update_file.path
            staged = backup_root / "__staged__" / update_file.path
            existed = target.exists()
            if existed:
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)

            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(prepared_payloads[update_file.path])
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
