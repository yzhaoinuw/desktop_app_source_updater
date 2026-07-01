import json
import os
import shutil
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory


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
            self._commit(repo, "v1.0.1")
            self._git(repo, "tag", "v1.0.1")

            self._write(repo, "demo_src/__init__.py", 'VERSION = "v1.0.2"\n')
            self._write(repo, "demo_src/app.py", "VALUE = 'new2'\n")
            self._commit(repo, "v1.0.2")

            output_zip = Path(temp_dir) / "demo_app_update_v1.0.2.zip"
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "desktop_source_updater.build_update_asset",
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
                env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
                capture_output=True,
                check=True,
                text=True,
            )

            with zipfile.ZipFile(output_zip) as zf:
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))

            self.assertEqual("demo_app", manifest["app"])
            self.assertEqual(["v1.0.0", "v1.0.1"], manifest["from_versions"])
            app_entry = next(item for item in manifest["files"] if item["path"] == "demo_src/app.py")
            self.assertEqual({"v1.0.0", "v1.0.1"}, set(app_entry["previous_sha256_by_version"]))

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
                    "desktop_source_updater.build_update_asset",
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
                env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
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

    def _commit(self, repo, message):
        self._git(repo, "add", ".")
        self._git(repo, "commit", "-m", message)

    def _git(self, repo, *args):
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True, text=True)


if __name__ == "__main__":
    unittest.main()
