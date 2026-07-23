import hashlib
import json
import os
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from desktop_app_source_updater import UpdateConfig, run_startup_update


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


if __name__ == "__main__":
    unittest.main()
