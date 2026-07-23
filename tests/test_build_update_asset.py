import json
import hashlib
import os
import shutil
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from desktop_app_source_updater import UpdateConfig, run_startup_update


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestBuildUpdateAsset(unittest.TestCase):
    def test_builds_multi_baseline_update_asset(self):
        if shutil.which("git") is None:
            self.skipTest("git is not available on PATH")

        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir()
            self._git(repo, "init", "-b", "main")
            self._git(repo, "config", "user.email", "test@example.com")
            self._git(repo, "config", "user.name", "Test User")

            self._write(repo, "demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            self._write(repo, "demo_src/app.py", "VALUE = 'old0'\n")
            self._commit(repo, "v1.0.0")
            self._git(repo, "tag", "v1.0.0")

            self._write(repo, "demo_src/__init__.py", 'VERSION = "v1.0.1"\n')
            self._write(repo, "demo_src/app.py", "VALUE = 'old1'\n")
            self._write(repo, "demo_src/extra.py", "EXTRA = 'old1'\n")
            self._commit(repo, "v1.0.1")
            self._git(repo, "tag", "v1.0.1")

            self._write(repo, "demo_src/__init__.py", 'VERSION = "v1.0.2"\n')
            self._write(repo, "demo_src/app.py", "VALUE = 'new2'\n")
            self._write(repo, "demo_src/extra.py", "EXTRA = 'new2'\n")
            self._commit(repo, "v1.0.2")

            output_zip = Path(temp_dir) / "demo_app_update_v1.0.2.zip"
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "desktop_app_source_updater.build_update_asset",
                    "--repo",
                    str(repo),
                    "--app-name",
                    "demo_app",
                    "--runtime-path",
                    "demo_src",
                    "--from-ref",
                    "v1.0.0",
                    "--from-ref",
                    "v1.0.1",
                    "--to-ref",
                    "HEAD",
                    "--version-file",
                    "demo_src/__init__.py",
                    "--output",
                    str(output_zip),
                ],
                cwd=REPO_ROOT,
                env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
                capture_output=True,
                check=True,
                text=True,
            )

            with zipfile.ZipFile(output_zip) as zf:
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))

            self.assertEqual("demo_app", manifest["app"])
            self.assertEqual(1, manifest["schema_version"])
            self.assertEqual(["v1.0.0", "v1.0.1"], manifest["from_versions"])
            app_entry = next(item for item in manifest["files"] if item["path"] == "demo_src/app.py")
            self.assertEqual({"v1.0.0", "v1.0.1"}, set(app_entry["previous_sha256_by_version"]))
            extra_entry = next(item for item in manifest["files"] if item["path"] == "demo_src/extra.py")
            self.assertEqual(
                {
                    "v1.0.0": None,
                    "v1.0.1": self._sha256(b"EXTRA = 'old1'\n"),
                },
                extra_entry["previous_sha256_by_version"],
            )

    def test_accepts_multiple_installed_byte_baselines_for_same_version(self):
        if shutil.which("git") is None:
            self.skipTest("git is not available on PATH")

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo = temp_path / "repo"
            repo.mkdir()
            self._git(repo, "init", "-b", "main")
            self._git(repo, "config", "user.email", "test@example.com")
            self._git(repo, "config", "user.name", "Test User")

            lf_baseline = b"VALUE = 'old'\n"
            crlf_baseline = b"VALUE = 'old'\r\n"
            new_payload = b"VALUE = 'new'\n"
            self._write(repo, "demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            self._write_bytes(repo, "demo_src/app.py", lf_baseline)
            self._commit(repo, "v1.0.0")
            self._git(repo, "tag", "v1.0.0")

            self._write_bytes(repo, "demo_src/app.py", new_payload)
            self._commit(repo, "v1.0.1")

            lf_manifest = temp_path / "v1.0.0-lf.json"
            crlf_manifest = temp_path / "v1.0.0-crlf.json"
            self._write_baseline_manifest(lf_manifest, "v1.0.0", {"demo_src/app.py": lf_baseline})
            self._write_baseline_manifest(crlf_manifest, "v1.0.0", {"demo_src/app.py": crlf_baseline})

            output_zip = temp_path / "demo_app_update_v1.0.1.zip"
            self._run_builder(
                repo,
                "--version",
                "v1.0.1",
                "--installed-baseline-manifest",
                str(lf_manifest),
                "--installed-baseline-manifest",
                str(crlf_manifest),
                "--output",
                str(output_zip),
                check=True,
            )

            with zipfile.ZipFile(output_zip) as zf:
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            app_entry = next(item for item in manifest["files"] if item["path"] == "demo_src/app.py")
            self.assertEqual(
                {self._sha256(lf_baseline), self._sha256(crlf_baseline)},
                set(app_entry["previous_sha256"]),
            )
            self.assertEqual(2, len(app_entry["previous_sha256"]))
            self.assertNotIn("previous_sha256_by_version", app_entry)

            for name, installed_bytes in (("lf", lf_baseline), ("crlf", crlf_baseline)):
                app_root = temp_path / f"installed-{name}"
                self._write_bytes(app_root, "demo_src/app.py", installed_bytes)
                result = run_startup_update(
                    UpdateConfig(
                        app_name="demo_app",
                        app_root=app_root,
                        allowed_payload_paths=("demo_src/",),
                        installed_version="v1.0.0",
                        update_url=str(output_zip),
                    )
                )
                self.assertEqual("updated", result.status)
                self.assertEqual(new_payload, (app_root / "demo_src/app.py").read_bytes())

            edited_root = temp_path / "installed-edited"
            edited_bytes = b"VALUE = 'user edit'\n"
            self._write_bytes(edited_root, "demo_src/app.py", edited_bytes)
            result = run_startup_update(
                UpdateConfig(
                    app_name="demo_app",
                    app_root=edited_root,
                    allowed_payload_paths=("demo_src/",),
                    installed_version="v1.0.0",
                    update_url=str(output_zip),
                )
            )
            self.assertEqual("skipped", result.status)
            self.assertEqual(edited_bytes, (edited_root / "demo_src/app.py").read_bytes())

    def test_builds_and_applies_python_config_merge_asset(self):
        if shutil.which("git") is None:
            self.skipTest("git is not available on PATH")

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo = temp_path / "repo"
            repo.mkdir()
            self._git(repo, "init", "-b", "main")
            self._git(repo, "config", "user.email", "test@example.com")
            self._git(repo, "config", "user.name", "Test User")

            old_config = '''# old config
MODEL = "default-old"
WINDOW_CONFIG = {"length": 30, "removed": True}
DERIVED = old_runtime_value()
'''
            self._write(repo, "demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            self._write(repo, "demo_src/app.py", "VALUE = 'old'\n")
            self._write(repo, "demo_src/config.py", old_config)
            self._commit(repo, "v1.0.0")
            self._git(repo, "tag", "v1.0.0")

            new_config = '''# downloaded config
MODEL = "default-new"
WINDOW_CONFIG = {"length": 60, "added": True}
NEW_SETTING = "new default"
DERIVED = new_runtime_value()
'''
            self._write(repo, "demo_src/__init__.py", 'VERSION = "v1.0.1"\n')
            self._write(repo, "demo_src/app.py", "VALUE = 'new'\n")
            self._write(repo, "demo_src/config.py", new_config)
            self._commit(repo, "v1.0.1")

            output_zip = temp_path / "demo_app_update_v1.0.1.zip"
            self._run_builder(
                repo,
                "--python-config-merge",
                "demo_src/config.py",
                "--editable-assignment",
                "MODEL",
                "--editable-assignment",
                "WINDOW_CONFIG",
                "--editable-assignment",
                "NEW_SETTING",
                "--output",
                str(output_zip),
                check=True,
            )

            with zipfile.ZipFile(output_zip) as zf:
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            self.assertEqual(2, manifest["schema_version"])
            config_entry = next(
                item for item in manifest["files"] if item["path"] == "demo_src/config.py"
            )
            self.assertEqual("python-config-merge", config_entry["update_strategy"])
            self.assertEqual(
                ["MODEL", "WINDOW_CONFIG", "NEW_SETTING"],
                config_entry["editable_assignments"],
            )
            ordinary_entries = [
                item for item in manifest["files"] if item["path"] != "demo_src/config.py"
            ]
            self.assertTrue(ordinary_entries)
            self.assertTrue(all("update_strategy" not in item for item in ordinary_entries))

            app_root = temp_path / "installed"
            self._write(app_root, "demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            self._write(app_root, "demo_src/app.py", "VALUE = 'old'\n")
            self._write(
                app_root,
                "demo_src/config.py",
                old_config.replace('MODEL = "default-old"', 'MODEL = "user-choice"'),
            )
            result = run_startup_update(
                UpdateConfig(
                    app_name="demo_app",
                    app_root=app_root,
                    allowed_payload_paths=("demo_src/",),
                    installed_version_file="demo_src/__init__.py",
                    update_url=str(output_zip),
                )
            )

            self.assertEqual("updated", result.status)
            merged_config = (app_root / "demo_src/config.py").read_text(encoding="utf-8")
            self.assertIn('MODEL = "user-choice"', merged_config)
            self.assertIn('"length": 30', merged_config)
            self.assertIn('"added": True', merged_config)
            self.assertIn('NEW_SETTING = "new default"', merged_config)
            self.assertIn("DERIVED = new_runtime_value()", merged_config)
            self.assertNotIn("removed", merged_config)
            self.assertEqual("VALUE = 'new'\n", (app_root / "demo_src/app.py").read_text())

    def test_refuses_python_config_merge_name_missing_from_template(self):
        if shutil.which("git") is None:
            self.skipTest("git is not available on PATH")

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo = temp_path / "repo"
            repo.mkdir()
            self._git(repo, "init", "-b", "main")
            self._git(repo, "config", "user.email", "test@example.com")
            self._git(repo, "config", "user.name", "Test User")

            self._write(repo, "demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            self._write(repo, "demo_src/config.py", 'MODEL = "old"\n')
            self._commit(repo, "v1.0.0")
            self._git(repo, "tag", "v1.0.0")
            self._write(repo, "demo_src/config.py", 'MODEL = "new"\n')
            self._commit(repo, "v1.0.1")

            result = self._run_builder(
                repo,
                "--version",
                "v1.0.1",
                "--python-config-merge",
                "demo_src/config.py",
                "--editable-assignment",
                "MISSING_SETTING",
                "--output",
                str(temp_path / "should-not-exist.zip"),
                check=False,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("missing editable assignment MISSING_SETTING", result.stderr)

    def test_refuses_unrepresentable_missing_and_present_same_version_baselines(self):
        if shutil.which("git") is None:
            self.skipTest("git is not available on PATH")

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo = temp_path / "repo"
            repo.mkdir()
            self._git(repo, "init", "-b", "main")
            self._git(repo, "config", "user.email", "test@example.com")
            self._git(repo, "config", "user.name", "Test User")

            self._write(repo, "demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            self._commit(repo, "v1.0.0")
            self._git(repo, "tag", "v1.0.0")

            added_bytes = b"VALUE = 'added'\n"
            self._write_bytes(repo, "demo_src/app.py", added_bytes)
            self._commit(repo, "v1.0.1")

            baseline_manifest = temp_path / "v1.0.0-present.json"
            self._write_baseline_manifest(
                baseline_manifest,
                "v1.0.0",
                {"demo_src/app.py": added_bytes},
            )
            result = self._run_builder(
                repo,
                "--version",
                "v1.0.1",
                "--installed-baseline-manifest",
                str(baseline_manifest),
                "--output",
                str(temp_path / "should-not-exist.zip"),
                check=False,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("missing-file states", result.stderr)
            self.assertIn("demo_src/app.py", result.stderr)

    def test_refuses_dependency_changes(self):
        if shutil.which("git") is None:
            self.skipTest("git is not available on PATH")

        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir()
            self._git(repo, "init", "-b", "main")
            self._git(repo, "config", "user.email", "test@example.com")
            self._git(repo, "config", "user.name", "Test User")

            self._write(repo, "demo_src/__init__.py", 'VERSION = "v1.0.0"\n')
            self._write(repo, "demo_src/app.py", "VALUE = 'old'\n")
            self._write(repo, "requirements.txt", "dash==1\n")
            self._commit(repo, "v1.0.0")
            self._git(repo, "tag", "v1.0.0")

            self._write(repo, "demo_src/__init__.py", 'VERSION = "v1.0.1"\n')
            self._write(repo, "requirements.txt", "dash==2\n")
            self._commit(repo, "v1.0.1")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "desktop_app_source_updater.build_update_asset",
                    "--repo",
                    str(repo),
                    "--app-name",
                    "demo_app",
                    "--runtime-path",
                    "demo_src",
                    "--from-ref",
                    "v1.0.0",
                    "--to-ref",
                    "HEAD",
                    "--version-file",
                    "demo_src/__init__.py",
                ],
                cwd=REPO_ROOT,
                env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
                capture_output=True,
                check=False,
                text=True,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("source-only update", result.stderr)

    def _write(self, repo, relative_path, text):
        path = repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def _write_bytes(self, repo, relative_path, data):
        path = repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def _write_baseline_manifest(self, path, version, files):
        path.write_text(
            json.dumps(
                {
                    "version": version,
                    "files": {
                        relative_path: None if data is None else self._sha256(data)
                        for relative_path, data in files.items()
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def _run_builder(self, repo, *extra_args, check):
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "desktop_app_source_updater.build_update_asset",
                "--repo",
                str(repo),
                "--app-name",
                "demo_app",
                "--runtime-path",
                "demo_src",
                "--from-ref",
                "v1.0.0",
                "--to-ref",
                "HEAD",
                "--version-file",
                "demo_src/__init__.py",
                *extra_args,
            ],
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
            capture_output=True,
            check=check,
            text=True,
        )

    def _sha256(self, data):
        return hashlib.sha256(data).hexdigest()

    def _commit(self, repo, message):
        self._git(repo, "add", ".")
        self._git(repo, "commit", "-m", message)

    def _git(self, repo, *args):
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True, text=True)


if __name__ == "__main__":
    unittest.main()
