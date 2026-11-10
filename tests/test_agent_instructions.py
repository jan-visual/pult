import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import install  # noqa: E402


class AgentInstructions(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = tmp.name
        self.md = os.path.join(self.home, ".claude", "CLAUDE.md")
        os.makedirs(os.path.dirname(self.md))
        for patcher in (mock.patch.object(install, "HOME", self.home),
                        mock.patch.object(install.shutil, "which", return_value=None),
                        mock.patch.dict(os.environ, {"CODEX_HOME": ""}),
                        mock.patch.object(install.config, "library", return_value="/lib")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def read(self):
        with open(self.md, encoding="utf-8") as f:
            return f.read()

    def write(self, text):
        with open(self.md, "w", encoding="utf-8") as f:
            f.write(text)

    def test_default_leaves_global_file_untouched(self):
        self.write("mine\n")
        self.assertEqual(install.sync_agent_blocks("/bin/pult", 7858, False), [])
        self.assertEqual(self.read(), "mine\n")

    def test_opt_in_appends_block(self):
        self.write("mine\n")
        install.sync_agent_blocks("/bin/pult", 7858, True)
        self.assertTrue(self.read().startswith("mine\n\n" + install.MARK_A))

    def test_existing_block_is_refreshed_not_duplicated(self):
        self.write("a\n\n%s\nSTALE\n%s\n\nb\n" % (install.MARK_A, install.MARK_B))
        install.sync_agent_blocks("/bin/pult", 7858, False)
        text = self.read()
        self.assertEqual(text.count(install.MARK_A), 1)
        self.assertNotIn("STALE", text)
        self.assertIn("b\n", text)

    def test_remove_keeps_user_content(self):
        self.write("a\n\n%s\nx\n%s\n\nb\n" % (install.MARK_A, install.MARK_B))
        install.remove_agent_blocks()
        self.assertEqual(self.read(), "a\n\nb\n")


if __name__ == "__main__":
    unittest.main()
