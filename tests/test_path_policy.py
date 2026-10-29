import tempfile
import unittest
from pathlib import Path

from astrbot_plugin_multisim.application.path_policy import WorkspacePathPolicy
from astrbot_plugin_multisim.domain.errors import InvalidRequest, PermissionDenied


class WorkspacePathPolicyTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "workspace"
        self.root.mkdir()
        self.policy = WorkspacePathPolicy(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_relative_path_resolves_inside(self):
        resolved = self.policy.resolve("circuits/rc.ms14")
        self.assertEqual(resolved, (self.root / "circuits" / "rc.ms14").resolve())

    def test_absolute_inside_allowed(self):
        target = self.root / "a.txt"
        self.assertEqual(self.policy.resolve(str(target)), target.resolve())

    def test_parent_traversal_rejected(self):
        with self.assertRaises(PermissionDenied):
            self.policy.resolve("../outside.txt")

    def test_absolute_outside_rejected(self):
        with self.assertRaises(PermissionDenied):
            self.policy.resolve(str(Path(self._tmp.name) / "elsewhere.txt"))

    def test_must_exist(self):
        with self.assertRaises(InvalidRequest):
            self.policy.resolve("missing.json", must_exist=True)

    def test_ensure_output_dir_creates(self):
        target = self.policy.ensure_output_dir("runs/demo")
        self.assertTrue(target.is_dir())
        self.assertIn(self.root, target.parents)

    def test_empty_path_rejected(self):
        with self.assertRaises(InvalidRequest):
            self.policy.resolve("   ")


if __name__ == "__main__":
    unittest.main()
