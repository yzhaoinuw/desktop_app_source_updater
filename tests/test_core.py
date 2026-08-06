import ast
import dataclasses
import hashlib
import json
import os
import socket
import threading
import time
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from desktop_app_source_updater import UpdateConfig, run_startup_update
from desktop_app_source_updater import core


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class ReleaseZipFixture:
    def __init__(self, temp_dir):
        self.root = Path(temp_dir)
        self.app_root = self.root / "app"
        self.release_dir = self.root / "release"
        self.release_dir.mkdir()

    def write_app_file(self, relative_path, text):
        path = self.app_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def read_app_file(self, relative_path):
        return (self.app_root / relative_path).read_text(encoding="utf-8")

    def config(self, update_zip=None, release_metadata=None):
        return UpdateConfig(
            app_name="demo_app",
            app_root=self.app_root,
            installed_version_file="demo_src/__init__.py",
            release_api_url=str(release_metadata or ""),
            update_url=str(update_zip) if update_zip else None,
            asset_prefix="demo_app_update_",
            allowed_payload_paths=("demo_src/",),
        )

    def build_update_zip(
        self,
        *,
        version="v1.0.1",
        payloads=None,
        from_versions=None,
        previous_payloads_by_version=None,
        include_previous_hashes=True,
        schema_version=1,
        merge_path=None,
        editable_assignments=(),
    ):
        payloads = payloads or {
            "demo_src/__init__.py": f'VERSION = "{version}"\n',
            "demo_src/app.py": "VALUE = 'new'\n",
        }
        files = []
        for relative_path, text in payloads.items():
            item = {"path": relative_path, "sha256": sha256(text.encode("utf-8"))}
            if include_previous_hashes and previous_payloads_by_version is not None:
                item["previous_sha256_by_version"] = {
                    prior_version: (
                        None
                        if relative_path not in prior_payloads
                        else sha256(prior_payloads[relative_path].encode("utf-8"))
                    )
                    for prior_version, prior_payloads in previous_payloads_by_version.items()
                }
            elif include_previous_hashes:
                installed = self.app_root / relative_path
                if installed.exists():
                    versions = from_versions or ["v1.0.0"]
                    item["previous_sha256_by_version"] = {
                        prior_version: sha256(installed.read_bytes())
                        for prior_version in versions
                    }
            if relative_path == merge_path:
                item["update_strategy"] = "python-config-merge"
                item["editable_assignments"] = list(editable_assignments)
            files.append(item)

        manifest = {
            "schema_version": schema_version,
            "app": "demo_app",
            "version": version,
            "from_versions": from_versions or ["v1.0.0"],
            "changed_files": list(payloads),
            "files": files,
        }
        update_zip = self.release_dir / f"demo_app_update_{version}.zip"
        with zipfile.ZipFile(update_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            for relative_path, text in payloads.items():
                zf.writestr(relative_path, text)
        return update_zip

    def build_release_metadata(self, asset_path, tag_name="v1.0.1"):
        metadata_path = self.release_dir / "latest_release.json"
        metadata = {
            "tag_name": tag_name,
            "assets": [
                {"name": asset_path.name, "browser_download_url": str(asset_path)}
            ],
        }
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        return metadata_path


class LocalReleaseServer:
    def __init__(
        self,
        asset_bytes,
        *,
        tag_name="v1.0.1",
        latest_status=302,
        latest_headers=None,
        asset_status=200,
        asset_headers=None,
        api_status=200,
        api_headers=None,
    ):
        self.asset_bytes = asset_bytes
        self.tag_name = tag_name
        self.latest_status = latest_status
        self.latest_headers = latest_headers or {}
        self.asset_status = asset_status
        self.asset_headers = asset_headers or {}
        self.api_status = api_status
        self.api_headers = api_headers or {}
        self.requests = []
        self.events = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_HEAD(self):
                self._handle_request(send_body=False)

            def do_GET(self):
                self._handle_request(send_body=True)

            def _handle_request(self, *, send_body):
                owner.requests.append((self.command, self.path))
                owner.events.append(f"{self.command} {self.path}")
                if self.path == "/owner/repo/releases/latest":
                    headers = dict(owner.latest_headers)
                    if 300 <= owner.latest_status < 400:
                        headers.setdefault(
                            "Location",
                            f"/owner/repo/releases/tag/{owner.tag_name}",
                        )
                    self._send(owner.latest_status, headers, b"", send_body)
                    return

                if self.path == "/api/repos/owner/repo/releases/latest":
                    metadata = {
                        "tag_name": owner.tag_name,
                        "assets": [
                            {
                                "name": f"demo_app_update_{owner.tag_name}.zip",
                                "browser_download_url": owner.asset_url,
                            }
                        ],
                    }
                    self._send(
                        owner.api_status,
                        owner.api_headers,
                        json.dumps(metadata).encode("utf-8"),
                        send_body,
                    )
                    return

                if self.path == owner.asset_path:
                    self._send(
                        owner.asset_status,
                        owner.asset_headers,
                        owner.asset_bytes,
                        send_body,
                    )
                    return

                self._send(404, {}, b"", send_body)

            def _send(self, status, headers, body, send_body):
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, str(value))
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if send_body and body:
                    self.wfile.write(body)

            def log_message(self, format, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )

    @property
    def base_url(self):
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    @property
    def latest_url(self):
        return f"{self.base_url}/owner/repo/releases/latest"

    @property
    def api_url(self):
        return f"{self.base_url}/api/repos/owner/repo/releases/latest"

    @property
    def asset_path(self):
        return (
            f"/owner/repo/releases/download/{self.tag_name}/"
            f"demo_app_update_{self.tag_name}.zip"
        )

    @property
    def asset_url(self):
        return f"{self.base_url}{self.asset_path}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)


class TestStartupUpdate(unittest.TestCase):
    def test_applies_compatible_release_zip(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            fixture.write_app_file("demo_src/app.py", "VALUE = 'old'\n")
            update_zip = fixture.build_update_zip()

            result = run_startup_update(fixture.config(update_zip=update_zip))

            self.assertEqual("updated", result.status)
            self.assertEqual('VERSION = "v1.0.1"\n', fixture.read_app_file("demo_src/__init__.py"))
            self.assertEqual("VALUE = 'new'\n", fixture.read_app_file("demo_src/app.py"))

    def test_jumps_from_supported_older_versions(self):
        prior_payloads = {
            "v1.0.0": {
                "demo_src/__init__.py": 'VERSION = "v1.0.0"\n',
                "demo_src/app.py": "VALUE = 'old0'\n",
            },
            "v1.0.1": {
                "demo_src/__init__.py": 'VERSION = "v1.0.1"\n',
                "demo_src/app.py": "VALUE = 'old1'\n",
            },
        }
        for installed_version, installed_payloads in prior_payloads.items():
            with self.subTest(installed_version=installed_version):
                with TemporaryDirectory() as temp_dir:
                    fixture = ReleaseZipFixture(temp_dir)
                    for path, text in installed_payloads.items():
                        fixture.write_app_file(path, text)
                    update_zip = fixture.build_update_zip(
                        version="v1.0.2",
                        from_versions=list(prior_payloads),
                        previous_payloads_by_version=prior_payloads,
                        payloads={
                            "demo_src/__init__.py": 'VERSION = "v1.0.2"\n',
                            "demo_src/app.py": "VALUE = 'new2'\n",
                        },
                    )

                    result = run_startup_update(fixture.config(update_zip=update_zip))

                    self.assertEqual("updated", result.status)
                    self.assertEqual('VERSION = "v1.0.2"\n', fixture.read_app_file("demo_src/__init__.py"))

    def test_discovers_update_zip_from_release_metadata(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            fixture.write_app_file("demo_src/app.py", "VALUE = 'old'\n")
            update_zip = fixture.build_update_zip()
            metadata = fixture.build_release_metadata(update_zip)

            result = run_startup_update(fixture.config(release_metadata=metadata))

            self.assertEqual("updated", result.status)

    def test_http_metadata_requests_json_and_asset_requests_binary(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            fixture.write_app_file("demo_src/app.py", "VALUE = 'old'\n")
            update_zip = fixture.build_update_zip()
            asset_url = "https://downloads.example.test/demo_app_update_v1.0.1.zip"
            metadata = {
                "tag_name": "v1.0.1",
                "assets": [
                    {"name": update_zip.name, "browser_download_url": asset_url}
                ],
            }
            config = UpdateConfig(
                app_name="demo_app",
                app_root=fixture.app_root,
                installed_version_file="demo_src/__init__.py",
                release_api_url="https://api.example.test/repos/demo/releases/latest",
                asset_prefix="demo_app_update_",
                allowed_payload_paths=("demo_src/",),
            )

            with patch(
                "desktop_app_source_updater.core.urllib.request.urlopen",
                side_effect=[
                    BytesIO(json.dumps(metadata).encode("utf-8")),
                    BytesIO(update_zip.read_bytes()),
                ],
            ) as urlopen:
                result = run_startup_update(config)

            self.assertEqual("updated", result.status)
            requests = [call.args[0] for call in urlopen.call_args_list]
            self.assertEqual("application/vnd.github+json", requests[0].get_header("Accept"))
            self.assertEqual("application/octet-stream", requests[1].get_header("Accept"))

    def test_redirect_discovery_checks_current_version_without_downloading_zip(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.1"\n')
            update_zip = fixture.build_update_zip()
            state_file = fixture.root / "state" / "update-check.json"

            with LocalReleaseServer(update_zip.read_bytes()) as server:
                result = run_startup_update(
                    self._redirect_config(fixture, server, state_file)
                )

            self.assertEqual("up-to-date", result.status)
            self.assertEqual("v1.0.1", result.installed_version)
            self.assertEqual("v1.0.1", result.target_version)
            self.assertEqual(
                [("HEAD", "/owner/repo/releases/latest")],
                server.requests,
            )

    def test_redirect_discovery_does_not_download_for_newer_installed_version(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.2"\n')
            update_zip = fixture.build_update_zip(version="v1.0.1")

            with LocalReleaseServer(update_zip.read_bytes()) as server:
                result = run_startup_update(
                    self._redirect_config(
                        fixture,
                        server,
                        fixture.root / "update-check.json",
                    )
                )

            self.assertEqual("up-to-date", result.status)
            self.assertEqual(
                [("HEAD", "/owner/repo/releases/latest")],
                server.requests,
            )

    def test_second_redirect_check_inside_interval_makes_zero_network_requests(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.1"\n')
            update_zip = fixture.build_update_zip()
            state_file = fixture.root / "update-check.json"

            with LocalReleaseServer(update_zip.read_bytes()) as server:
                config = self._redirect_config(fixture, server, state_file)
                first = run_startup_update(config)
                second = run_startup_update(config)

            self.assertEqual("up-to-date", first.status)
            self.assertEqual("up-to-date", second.status)
            self.assertIn("deferred", second.message)
            self.assertEqual(
                [("HEAD", "/owner/repo/releases/latest")],
                server.requests,
            )

    def test_redirect_discovery_downloads_only_newer_release_and_notifies_first(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            fixture.write_app_file("demo_src/app.py", "VALUE = 'old'\n")
            update_zip = fixture.build_update_zip()
            state_file = fixture.root / "update-check.json"

            with LocalReleaseServer(update_zip.read_bytes()) as server:
                config = self._redirect_config(
                    fixture,
                    server,
                    state_file,
                    on_update_available=lambda installed, target: server.events.append(
                        f"callback {installed} {target}"
                    ),
                )
                result = run_startup_update(config)

            self.assertEqual("updated", result.status)
            self.assertEqual("v1.0.0", result.installed_version)
            self.assertEqual("v1.0.1", result.target_version)
            self.assertEqual(
                [
                    ("HEAD", "/owner/repo/releases/latest"),
                    ("HEAD", server.asset_path),
                    ("GET", server.asset_path),
                ],
                server.requests,
            )
            # The asset is confirmed to exist before the user is told an update
            # is coming, and the announcement still precedes the slow download.
            self.assertEqual(
                [
                    "HEAD /owner/repo/releases/latest",
                    f"HEAD {server.asset_path}",
                    "callback v1.0.0 v1.0.1",
                    f"GET {server.asset_path}",
                ],
                server.events,
            )

    def test_force_check_bypasses_persistent_interval(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.1"\n')
            update_zip = fixture.build_update_zip()

            with LocalReleaseServer(update_zip.read_bytes()) as server:
                config = self._redirect_config(
                    fixture,
                    server,
                    fixture.root / "update-check.json",
                )
                run_startup_update(config)
                forced = run_startup_update(config, force_check=True)

            self.assertEqual("up-to-date", forced.status)
            self.assertEqual(
                [
                    ("HEAD", "/owner/repo/releases/latest"),
                    ("HEAD", "/owner/repo/releases/latest"),
                ],
                server.requests,
            )

    def test_rate_limit_responses_persist_server_backoff(self):
        for status, headers, minimum_delay in (
            (403, {"X-RateLimit-Reset": str(int(time.time()) + 600)}, 500),
            (429, {"Retry-After": "300"}, 250),
        ):
            with self.subTest(status=status):
                with TemporaryDirectory() as temp_dir:
                    fixture = ReleaseZipFixture(temp_dir)
                    fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
                    update_zip = fixture.build_update_zip()
                    state_file = fixture.root / "update-check.json"

                    with LocalReleaseServer(
                        update_zip.read_bytes(),
                        latest_status=status,
                        latest_headers=headers,
                    ) as server:
                        config = self._redirect_config(fixture, server, state_file)
                        before = time.time()
                        first = run_startup_update(config)
                        second = run_startup_update(config)

                    self.assertEqual("failed", first.status)
                    self.assertIn(f"HTTP {status}", first.message)
                    self.assertEqual("up-to-date", second.status)
                    self.assertEqual(
                        [("HEAD", "/owner/repo/releases/latest")],
                        server.requests,
                    )
                    state = json.loads(state_file.read_text(encoding="utf-8"))
                    self.assertGreaterEqual(
                        state["next_check_at"],
                        before + minimum_delay,
                    )

    def test_corrupt_or_missing_state_is_ignored_safely(self):
        for state_contents in (None, "{not json"):
            with self.subTest(state_contents=state_contents):
                with TemporaryDirectory() as temp_dir:
                    fixture = ReleaseZipFixture(temp_dir)
                    fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.1"\n')
                    update_zip = fixture.build_update_zip()
                    state_file = fixture.root / "update-check.json"
                    if state_contents is not None:
                        state_file.write_text(state_contents, encoding="utf-8")

                    with LocalReleaseServer(update_zip.read_bytes()) as server:
                        result = run_startup_update(
                            self._redirect_config(fixture, server, state_file)
                        )

                    self.assertEqual("up-to-date", result.status)
                    self.assertEqual(
                        [("HEAD", "/owner/repo/releases/latest")],
                        server.requests,
                    )
                    state = json.loads(state_file.read_text(encoding="utf-8"))
                    self.assertEqual(1, state["schema_version"])

    def test_legacy_api_compares_tag_before_downloading_current_release(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.1"\n')
            update_zip = fixture.build_update_zip()

            with LocalReleaseServer(update_zip.read_bytes()) as server:
                config = UpdateConfig(
                    app_name="demo_app",
                    app_root=fixture.app_root,
                    installed_version_file="demo_src/__init__.py",
                    release_api_url=server.api_url,
                    asset_prefix="demo_app_update_",
                    allowed_payload_paths=("demo_src/",),
                )
                result = run_startup_update(config)

            self.assertEqual("up-to-date", result.status)
            self.assertEqual(
                [("GET", "/api/repos/owner/repo/releases/latest")],
                server.requests,
            )

    def test_manifest_version_must_match_discovered_release_tag(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            fixture.write_app_file("demo_src/app.py", "VALUE = 'old'\n")
            update_zip = fixture.build_update_zip(version="v1.0.1")

            with LocalReleaseServer(
                update_zip.read_bytes(),
                tag_name="v1.0.2",
            ) as server:
                result = run_startup_update(
                    self._redirect_config(
                        fixture,
                        server,
                        fixture.root / "update-check.json",
                    )
                )

            self.assertEqual("failed", result.status)
            self.assertIn("does not match discovered release tag", result.message)
            self.assertEqual("VALUE = 'old'\n", fixture.read_app_file("demo_src/app.py"))

    def test_direct_local_update_url_bypasses_remote_check_state(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            fixture.write_app_file("demo_src/app.py", "VALUE = 'old'\n")
            update_zip = fixture.build_update_zip()
            state_file = fixture.root / "update-check.json"
            state_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "source": (
                            "demo_app|redirect|"
                            "https://example.test/releases/latest|demo_app_update_"
                        ),
                        "next_check_at": time.time() + 86400,
                    }
                ),
                encoding="utf-8",
            )
            config = fixture.config(update_zip=update_zip)
            config = UpdateConfig(
                **{
                    **config.__dict__,
                    "check_state_file": state_file,
                    "latest_release_url": "https://example.test/releases/latest",
                }
            )

            result = run_startup_update(config)

            self.assertEqual("updated", result.status)

    def test_asset_download_failure_is_distinct_and_persists_backoff(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            fixture.write_app_file("demo_src/app.py", "VALUE = 'old'\n")
            update_zip = fixture.build_update_zip()
            state_file = fixture.root / "update-check.json"

            with LocalReleaseServer(
                update_zip.read_bytes(),
                asset_status=429,
                asset_headers={"Retry-After": "300"},
            ) as server:
                config = self._redirect_config(fixture, server, state_file)
                first = run_startup_update(config)
                second = run_startup_update(config)

            self.assertEqual("failed", first.status)
            # A throttled probe cannot prove the asset is missing, so the
            # download stays the operation that reports the failure.
            self.assertIn("could not download update asset: HTTP 429", first.message)
            self.assertEqual("up-to-date", second.status)
            self.assertEqual(
                [
                    ("HEAD", "/owner/repo/releases/latest"),
                    ("HEAD", server.asset_path),
                    ("GET", server.asset_path),
                ],
                server.requests,
            )

    def test_release_without_composed_asset_is_up_to_date_and_stays_quiet(self):
        # A full-package release carries no source update asset. Redirect
        # discovery composes the asset name from the tag, so the only way to
        # learn it is absent is to ask before announcing anything.
        for missing_status in (404, 410):
            with self.subTest(missing_status=missing_status):
                with TemporaryDirectory() as temp_dir:
                    fixture = ReleaseZipFixture(temp_dir)
                    fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
                    fixture.write_app_file("demo_src/app.py", "VALUE = 'old'\n")
                    update_zip = fixture.build_update_zip()
                    state_file = fixture.root / "update-check.json"
                    announcements = []

                    with LocalReleaseServer(
                        update_zip.read_bytes(),
                        asset_status=missing_status,
                    ) as server:
                        config = self._redirect_config(
                            fixture,
                            server,
                            state_file,
                            on_update_available=lambda installed, target: announcements.append(
                                (installed, target)
                            ),
                        )
                        result = run_startup_update(config)

                    self.assertEqual("up-to-date", result.status)
                    self.assertIn("no matching source update asset", result.message)
                    self.assertEqual("v1.0.1", result.target_version)
                    self.assertEqual([], announcements)
                    # The probe settles it; the asset is never downloaded.
                    self.assertEqual(
                        [
                            ("HEAD", "/owner/repo/releases/latest"),
                            ("HEAD", server.asset_path),
                        ],
                        server.requests,
                    )
                    self.assertEqual("VALUE = 'old'\n", fixture.read_app_file("demo_src/app.py"))

    def test_asset_deleted_after_probe_is_reported_as_no_asset(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            update_zip = fixture.build_update_zip()

            with LocalReleaseServer(update_zip.read_bytes()) as server:
                config = self._redirect_config(
                    fixture,
                    server,
                    fixture.root / "update-check.json",
                )

                original_probe = core._asset_is_available

                def probe_then_delete(url, timeout_seconds):
                    available = original_probe(url, timeout_seconds)
                    server.asset_status = 404
                    return available

                with patch.object(core, "_asset_is_available", probe_then_delete):
                    result = run_startup_update(config)

            self.assertEqual("up-to-date", result.status)
            self.assertIn("no matching source update asset", result.message)

    def test_failed_run_retries_sooner_than_a_clean_check(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            update_zip = fixture.build_update_zip()
            state_file = fixture.root / "update-check.json"

            with LocalReleaseServer(update_zip.read_bytes(), asset_status=500) as server:
                config = self._redirect_config(fixture, server, state_file)
                before = time.time()
                result = run_startup_update(config)

            self.assertEqual("failed", result.status)
            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertGreater(state["next_check_at"], before)
            self.assertLessEqual(
                state["next_check_at"],
                before + core.DEFAULT_FAILURE_RETRY_SECONDS + 5,
            )

    def test_unreachable_host_persists_backoff_instead_of_retrying_every_launch(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            state_file = fixture.root / "update-check.json"

            # Bind and close a port so the connection is refused rather than
            # hanging, standing in for a launch with no network.
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                dead_port = probe.getsockname()[1]

            config = UpdateConfig(
                app_name="demo_app",
                app_root=fixture.app_root,
                installed_version_file="demo_src/__init__.py",
                latest_release_url=f"http://127.0.0.1:{dead_port}/owner/repo/releases/latest",
                asset_prefix="demo_app_update_",
                allowed_payload_paths=("demo_src/",),
                check_state_file=state_file,
            )
            before = time.time()
            first = run_startup_update(config)
            second = run_startup_update(config)

            self.assertEqual("failed", first.status)
            self.assertEqual("up-to-date", second.status)
            self.assertIn("deferred by the configured interval", second.message)
            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertLessEqual(
                state["next_check_at"],
                before + core.DEFAULT_FAILURE_RETRY_SECONDS + 5,
            )

    def test_quota_backoff_outlives_the_shorter_failure_retry(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            update_zip = fixture.build_update_zip()
            state_file = fixture.root / "update-check.json"
            reset_at = int(time.time()) + core.DEFAULT_FAILURE_RETRY_SECONDS + 3600

            with LocalReleaseServer(
                update_zip.read_bytes(),
                latest_status=403,
                latest_headers={"X-RateLimit-Reset": str(reset_at)},
            ) as server:
                result = run_startup_update(
                    self._redirect_config(fixture, server, state_file)
                )

            self.assertEqual("failed", result.status)
            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(float(reset_at), state["next_check_at"])

    def test_merges_declared_config_values_and_replaces_ordinary_source(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            self._write_config_merge_baseline(fixture)
            update_zip = self._build_config_merge_update(fixture)

            result = run_startup_update(fixture.config(update_zip=update_zip))

            self.assertEqual("updated", result.status)
            merged_config = fixture.read_app_file("demo_src/config.py")
            self.assertIn("# downloaded config", merged_config)
            self.assertIn('MODEL = "user"', merged_config)
            self.assertIn('"length": 20', merged_config)
            self.assertIn('"new_only": 2', merged_config)
            self.assertIn('"Wake": "green"', merged_config)
            self.assertIn('"NREM": "purple"', merged_config)
            self.assertIn("DERIVED = new_runtime_value()", merged_config)
            self.assertNotIn("old_only", merged_config)
            self.assertEqual("VALUE = 'new'\n", fixture.read_app_file("demo_src/app.py"))
            self.assertEqual('VERSION = "v1.0.1"\n', fixture.read_app_file("demo_src/__init__.py"))

    def test_ordinary_local_edit_skips_entire_schema_2_update(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            self._write_config_merge_baseline(fixture)
            update_zip = self._build_config_merge_update(fixture)
            original_config = fixture.read_app_file("demo_src/config.py")
            fixture.write_app_file("demo_src/app.py", "VALUE = 'local edit'\n")

            result = run_startup_update(fixture.config(update_zip=update_zip))

            self.assertEqual("skipped", result.status)
            self.assertIn("differ from the update baseline", result.message)
            self.assertEqual(original_config, fixture.read_app_file("demo_src/config.py"))
            self.assertEqual("VALUE = 'local edit'\n", fixture.read_app_file("demo_src/app.py"))
            self.assertEqual('VERSION = "v1.0.0"\n', fixture.read_app_file("demo_src/__init__.py"))

    def test_schema_1_rejects_config_merge_metadata(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            self._write_config_merge_baseline(fixture)
            update_zip = fixture.build_update_zip(
                schema_version=1,
                merge_path="demo_src/config.py",
                editable_assignments=("MODEL",),
                payloads={
                    "demo_src/config.py": 'MODEL = "new default"\n',
                    "demo_src/__init__.py": 'VERSION = "v1.0.1"\n',
                },
            )
            original_config = fixture.read_app_file("demo_src/config.py")

            result = run_startup_update(fixture.config(update_zip=update_zip))

            self.assertEqual("failed", result.status)
            self.assertIn("schema 1", result.message)
            self.assertEqual(original_config, fixture.read_app_file("demo_src/config.py"))
            self.assertEqual('VERSION = "v1.0.0"\n', fixture.read_app_file("demo_src/__init__.py"))

    def test_invalid_installed_config_fails_before_any_file_changes(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            self._write_config_merge_baseline(fixture)
            update_zip = self._build_config_merge_update(fixture)
            invalid_config = "MODEL = [\n"
            fixture.write_app_file("demo_src/config.py", invalid_config)

            result = run_startup_update(fixture.config(update_zip=update_zip))

            self.assertEqual("failed", result.status)
            self.assertIn("installed Python config", result.message)
            self.assertEqual(invalid_config, fixture.read_app_file("demo_src/config.py"))
            self.assertEqual("VALUE = 'old'\n", fixture.read_app_file("demo_src/app.py"))
            self.assertEqual('VERSION = "v1.0.0"\n', fixture.read_app_file("demo_src/__init__.py"))

    def test_later_apply_failure_rolls_back_merged_config(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            self._write_config_merge_baseline(fixture)
            update_zip = self._build_config_merge_update(fixture)
            original_config = fixture.read_app_file("demo_src/config.py")
            real_replace = os.replace

            def fail_on_app_file(source, destination):
                if Path(destination).name == "app.py":
                    raise OSError("simulated apply failure")
                return real_replace(source, destination)

            with patch("desktop_app_source_updater.core.os.replace", side_effect=fail_on_app_file):
                result = run_startup_update(fixture.config(update_zip=update_zip))

            self.assertEqual("failed", result.status)
            self.assertIn("simulated apply failure", result.message)
            self.assertEqual(original_config, fixture.read_app_file("demo_src/config.py"))
            self.assertEqual("VALUE = 'old'\n", fixture.read_app_file("demo_src/app.py"))
            self.assertEqual('VERSION = "v1.0.0"\n', fixture.read_app_file("demo_src/__init__.py"))

    def test_blocks_unallowed_dependency_path(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            update_zip = fixture.build_update_zip(
                payloads={
                    "demo_src/__init__.py": 'VERSION = "v1.0.1"\n',
                    "requirements.txt": "dash==9\n",
                }
            )

            result = run_startup_update(fixture.config(update_zip=update_zip))

            self.assertEqual("blocked", result.status)
            self.assertIn("packaged refresh required", result.message)

    def test_skips_local_edit_hash_mismatch(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            fixture.write_app_file("demo_src/app.py", "VALUE = 'old'\n")
            update_zip = fixture.build_update_zip()
            fixture.write_app_file("demo_src/app.py", "VALUE = 'local edit'\n")

            result = run_startup_update(fixture.config(update_zip=update_zip))

            self.assertEqual("skipped", result.status)
            self.assertIn("differ from the update baseline", result.message)
            self.assertEqual("VALUE = 'local edit'\n", fixture.read_app_file("demo_src/app.py"))

    def test_refuses_python_payload_that_will_not_parse(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            fixture.write_app_file("demo_src/app.py", "VALUE = 'old'\n")
            update_zip = fixture.build_update_zip(
                payloads={
                    "demo_src/__init__.py": 'VERSION = "v1.0.1"\n',
                    "demo_src/app.py": "def broken(\n",
                }
            )

            result = run_startup_update(fixture.config(update_zip=update_zip))

            self.assertEqual("failed", result.status)
            self.assertIn("demo_src/app.py is not valid Python", result.message)
            # Validation runs while every payload is still staged in memory, so
            # a bad asset must leave the whole install untouched rather than
            # applying the files that happened to be listed before it.
            self.assertEqual("VALUE = 'old'\n", fixture.read_app_file("demo_src/app.py"))
            self.assertEqual('VERSION = "v1.0.0"\n', fixture.read_app_file("demo_src/__init__.py"))

    def test_refuses_python_payload_containing_null_bytes(self):
        # Null bytes raise ValueError rather than SyntaxError. run_startup_update
        # only converts UpdateError into a result, so anything uncaught here
        # would crash the launcher on the startup path.
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            fixture.write_app_file("demo_src/app.py", "VALUE = 'old'\n")
            update_zip = fixture.build_update_zip(
                payloads={
                    "demo_src/__init__.py": 'VERSION = "v1.0.1"\n',
                    "demo_src/app.py": "VALUE = 'new'\x00\n",
                }
            )

            result = run_startup_update(fixture.config(update_zip=update_zip))

            self.assertEqual("failed", result.status)
            self.assertIn("demo_src/app.py is not valid Python", result.message)
            self.assertEqual("VALUE = 'old'\n", fixture.read_app_file("demo_src/app.py"))

    def test_accepts_python_payload_with_an_encoding_declaration(self):
        # Parsing the raw bytes honors PEP 263 the way import will. Decoding as
        # UTF-8 first would reject a legitimate latin-1 payload.
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            fixture.write_app_file("demo_src/app.py", "VALUE = 'old'\n")
            payload = "# -*- coding: latin-1 -*-\nVALUE = 'caf\xe9'\n"
            update_zip = fixture.release_dir / "demo_app_update_v1.0.1.zip"
            manifest = {
                "schema_version": 1,
                "app": "demo_app",
                "version": "v1.0.1",
                "from_versions": ["v1.0.0"],
                "changed_files": ["demo_src/__init__.py", "demo_src/app.py"],
                "files": [
                    {
                        "path": "demo_src/__init__.py",
                        "sha256": sha256(b'VERSION = "v1.0.1"\n'),
                        "previous_sha256_by_version": {
                            "v1.0.0": sha256(b'VERSION = "v1.0.0"\n')
                        },
                    },
                    {
                        "path": "demo_src/app.py",
                        "sha256": sha256(payload.encode("latin-1")),
                        "previous_sha256_by_version": {
                            "v1.0.0": sha256(b"VALUE = 'old'\n")
                        },
                    },
                ],
            }
            with zipfile.ZipFile(update_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("manifest.json", json.dumps(manifest))
                zf.writestr("demo_src/__init__.py", 'VERSION = "v1.0.1"\n')
                zf.writestr("demo_src/app.py", payload.encode("latin-1"))

            result = run_startup_update(fixture.config(update_zip=update_zip))

            self.assertEqual("updated", result.status)

    def test_non_python_payloads_skip_syntax_validation(self):
        with TemporaryDirectory() as temp_dir:
            fixture = ReleaseZipFixture(temp_dir)
            fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            fixture.write_app_file("demo_src/notes.txt", "old notes\n")
            update_zip = fixture.build_update_zip(
                payloads={
                    "demo_src/__init__.py": 'VERSION = "v1.0.1"\n',
                    "demo_src/notes.txt": "def broken(\n",
                }
            )

            result = run_startup_update(fixture.config(update_zip=update_zip))

            self.assertEqual("updated", result.status)
            self.assertEqual("def broken(\n", fixture.read_app_file("demo_src/notes.txt"))

    def _write_config_merge_baseline(self, fixture):
        fixture.write_app_file("demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
        fixture.write_app_file("demo_src/app.py", "VALUE = 'old'\n")
        fixture.write_app_file(
            "demo_src/config.py",
            '''# installed config
MODEL = "user"
WINDOW_CONFIG = {
    "length": 20,
    "old_only": 1,
}
STAGE_COLORS = {"Wake": "green"}
DERIVED = old_runtime_value()
''',
        )

    def _build_config_merge_update(self, fixture):
        return fixture.build_update_zip(
            schema_version=2,
            merge_path="demo_src/config.py",
            editable_assignments=("MODEL", "WINDOW_CONFIG", "STAGE_COLORS"),
            payloads={
                "demo_src/config.py": '''# downloaded config
MODEL = "default"
WINDOW_CONFIG = {
    "length": 30,
    "new_only": 2,
}
STAGE_COLORS = {"Wake": "blue", "NREM": "purple"}
DERIVED = new_runtime_value()
''',
                "demo_src/app.py": "VALUE = 'new'\n",
                "demo_src/__init__.py": 'VERSION = "v1.0.1"\n',
            },
        )

    def _redirect_config(
        self,
        fixture,
        server,
        state_file,
        *,
        on_update_available=None,
    ):
        return UpdateConfig(
            app_name="demo_app",
            app_root=fixture.app_root,
            installed_version_file="demo_src/__init__.py",
            latest_release_url=server.latest_url,
            asset_prefix="demo_app_update_",
            allowed_payload_paths=("demo_src/",),
            check_state_file=state_file,
            on_update_available=on_update_available,
        )


class TestConfigCompatibility(unittest.TestCase):
    """UpdateConfig's field order is a compatibility surface.

    Adopters pin this package by commit and build their own UpdateConfig in a
    launcher that ships frozen inside a packaged app. Inserting a field
    renumbers every positional parameter after it, so a positional caller would
    silently misbind rather than fail. New fields must be appended.
    """

    # The complete public constructor order, newest field last. This is checked
    # for exact equality rather than as a prefix: a prefix leaves whichever
    # field was added most recently unprotected, so inserting a field just
    # before it would shift a real positional parameter without failing.
    # Appending here is the deliberate acknowledgment that the surface changed.
    PUBLIC_FIELD_ORDER = (
        "app_name",
        "app_root",
        "release_api_url",
        "asset_prefix",
        "allowed_payload_paths",
        "installed_version",
        "installed_version_file",
        "version_pattern",
        "update_url",
        "skip_update_env",
        "update_zip_url_env",
        "release_api_env",
        "asset_prefix_env",
        "timeout_env",
        "timeout_seconds",
        "max_update_bytes",
        "blocked_path_names",
        "blocked_path_prefixes",
        "blocked_path_suffixes",
        "latest_release_url",
        "latest_release_env",
        "check_state_file",
        "check_interval_seconds",
        "force_check_env",
        "on_update_available",
        "failure_retry_seconds",
    )

    def test_new_config_fields_are_appended_not_inserted(self):
        actual_order = tuple(field.name for field in dataclasses.fields(UpdateConfig))
        self.assertEqual(
            self.PUBLIC_FIELD_ORDER,
            actual_order,
            "UpdateConfig's constructor order is public. Append a new field to "
            "the end of the dataclass and to PUBLIC_FIELD_ORDER; never insert "
            "one, which renumbers every positional parameter after it.",
        )

    def test_every_optional_config_field_keeps_a_default(self):
        # Appending is only safe while every field after the required pair
        # still has a default; otherwise adopters break on construction.
        optional_fields = dataclasses.fields(UpdateConfig)[2:]
        missing_defaults = [
            field.name
            for field in optional_fields
            if field.default is dataclasses.MISSING
            and field.default_factory is dataclasses.MISSING
        ]
        self.assertEqual([], missing_defaults)


class TestSelfUpdateSafetyContract(unittest.TestCase):
    """The runtime modules must be fully loaded before an update is applied.

    An update can overwrite the updater's own source: adopters may vendor this
    package into the updateable source tree so that updater fixes ship as
    ordinary source updates instead of full packaged releases. When that
    happens the running process has already imported these modules, so the
    swap is safe — the old code finishes the run from memory and the new code
    takes effect on the next launch.

    That safety holds only while every import completes at module load. An
    import deferred into a function inside the apply path would execute after
    the files on disk had already been replaced, loading new code into a
    process running the old code. The failure would be intermittent, would
    depend on which files a given release happened to touch, and would strike
    during an update — the worst moment to be half-loaded.

    These are the modules a launcher imports and the apply path runs through.
    build_update_asset.py is deliberately excluded: it is a maintainer-side
    CLI that never runs inside an installed app.
    """

    RUNTIME_MODULE_NAMES = ("__init__.py", "core.py", "python_config.py")

    def _runtime_modules(self):
        package_root = Path(core.__file__).resolve().parent
        for name in self.RUNTIME_MODULE_NAMES:
            path = package_root / name
            self.assertTrue(path.is_file(), f"missing runtime module: {name}")
            yield name, ast.parse(path.read_bytes(), filename=name)

    def test_runtime_modules_have_no_deferred_imports(self):
        deferred = []
        for name, tree in self._runtime_modules():
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                for inner in ast.walk(node):
                    if isinstance(inner, (ast.Import, ast.ImportFrom)):
                        deferred.append(f"{name}:{inner.lineno}")

        self.assertEqual(
            [],
            sorted(set(deferred)),
            "Imports in these modules must stay at module level. A function-level "
            "import runs after an update has already replaced files on disk, so "
            "the process would load new code into old code mid-update.",
        )

    def test_runtime_modules_do_not_import_dynamically(self):
        # __import__ and importlib.import_module defer a load just as a
        # function-level import statement does, and the AST check above cannot
        # see them.
        dynamic = []
        for name, tree in self._runtime_modules():
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                function = node.func
                if (isinstance(function, ast.Name) and function.id == "__import__") or (
                    isinstance(function, ast.Attribute) and function.attr == "import_module"
                ):
                    dynamic.append(f"{name}:{node.lineno}")

        self.assertEqual(
            [],
            sorted(set(dynamic)),
            "Dynamic imports defer module loading past the point where an "
            "update has replaced files on disk.",
        )


if __name__ == "__main__":
    unittest.main()
