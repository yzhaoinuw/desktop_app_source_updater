import ast
import unittest

from desktop_app_source_updater.python_config import (
    PythonConfigMergeError,
    merge_python_config,
    validate_python_config_template,
)


class TestPythonConfigMerge(unittest.TestCase):
    def test_preserves_declared_values_in_downloaded_template(self):
        downloaded = b'''# downloaded header
import new_runtime

MODEL = "default"
CHANNELS = ["EEG"]  # downloaded channel comment
WINDOW_CONFIG = {
    "length": 30,
    "nested": {
        "caf\xc3\xa9": "blue",
        "new_only": 7,
    },
    "new_only": 9,
}
NEW_SETTING = True
DERIVED = build_new()

def new_function():
    return "new"
'''
        installed = b'''# installed header
import old_runtime

MODEL = "user"
CHANNELS = ["EEG", "EMG"]
WINDOW_CONFIG = {
    "length": 20,
    "nested": {
        "caf\xc3\xa9": "red",
        "old_only": 5,
    },
    "old_only": 99,
}
REMOVED_SETTING = "gone"
DERIVED = build_old()
'''

        merged = merge_python_config(
            downloaded,
            installed,
            ("MODEL", "CHANNELS", "WINDOW_CONFIG", "NEW_SETTING"),
            path="app_src/config.py",
        )
        merged_text = merged.decode("utf-8")
        assignments = self._literal_assignments(merged_text)

        self.assertEqual("user", assignments["MODEL"])
        self.assertEqual(["EEG", "EMG"], assignments["CHANNELS"])
        self.assertEqual(
            {
                "length": 20,
                "nested": {"caf\u00e9": "red", "new_only": 7},
                "new_only": 9,
            },
            assignments["WINDOW_CONFIG"],
        )
        self.assertIs(True, assignments["NEW_SETTING"])
        self.assertIn("# downloaded header", merged_text)
        self.assertIn("# downloaded channel comment", merged_text)
        self.assertIn("import new_runtime", merged_text)
        self.assertIn("DERIVED = build_new()", merged_text)
        self.assertIn("def new_function():", merged_text)
        self.assertNotIn("installed header", merged_text)
        self.assertNotIn("old_only", merged_text)
        self.assertNotIn("REMOVED_SETTING", merged_text)
        compile(merged, "app_src/config.py", "exec")

    def test_rejects_invalid_installed_python(self):
        with self.assertRaisesRegex(PythonConfigMergeError, "installed Python config.*invalid"):
            merge_python_config(
                b'MODEL = "default"\n',
                b'MODEL = [\n',
                ("MODEL",),
                path="app_src/config.py",
            )

    def test_rejects_invalid_downloaded_python(self):
        with self.assertRaisesRegex(PythonConfigMergeError, "downloaded Python config.*invalid"):
            validate_python_config_template(
                b'MODEL = {\n',
                ("MODEL",),
                path="app_src/config.py",
            )

    def test_rejects_duplicate_installed_assignment(self):
        with self.assertRaisesRegex(PythonConfigMergeError, "duplicate editable assignment MODEL"):
            merge_python_config(
                b'MODEL = "default"\n',
                b'MODEL = "first"\nMODEL = "second"\n',
                ("MODEL",),
                path="app_src/config.py",
            )

    def test_rejects_nonliteral_installed_value(self):
        with self.assertRaisesRegex(PythonConfigMergeError, "must use a Python literal value"):
            merge_python_config(
                b'MODEL = "default"\n',
                b"MODEL = choose_model()\n",
                ("MODEL",),
                path="app_src/config.py",
            )

    def test_rejects_declared_name_missing_from_downloaded_template(self):
        with self.assertRaisesRegex(PythonConfigMergeError, "missing editable assignment MODEL"):
            validate_python_config_template(
                b"OTHER = 1\n",
                ("MODEL",),
                path="app_src/config.py",
            )

    def _literal_assignments(self, source):
        result = {}
        for statement in ast.parse(source).body:
            if (
                isinstance(statement, ast.Assign)
                and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
            ):
                try:
                    result[statement.targets[0].id] = ast.literal_eval(statement.value)
                except (ValueError, TypeError):
                    pass
        return result


if __name__ == "__main__":
    unittest.main()
