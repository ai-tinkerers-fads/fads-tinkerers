import unittest
from pathlib import Path


class LayoutTests(unittest.TestCase):
    def test_contract_first_and_all_owned_parts_inside_module(self):
        module = Path(__file__).resolve().parents[1]
        self.assertTrue((module / "README.md").read_text().startswith("# Hooks contract"))
        for name in ("fixtures", "tests", "scripts", "web"):
            self.assertTrue((module / name).is_dir())
        self.assertTrue((module / "fixtures/branch-removal.json").is_file())
