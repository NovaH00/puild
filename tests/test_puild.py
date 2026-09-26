import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from puild.command import Command, Pipeline, Result, is_dry_run, set_dry_run
from puild.fs import copy, find_files, mkdir, needs_rebuild, rm
from puild.logging import set_quiet


class TestCommand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        set_quiet(True)

    def test_basic_command_run(self):
        cmd = Command("echo", "hello")
        res = cmd.run(text=True)
        self.assertTrue(res.ok)
        self.assertEqual(res.return_code, 0)
        self.assertEqual(res.stdout.strip(), "hello")
        self.assertEqual(res.unwrap().strip(), "hello")

    def test_fluent_args(self):
        cmd = Command("echo")
        cmd.arg("foo").arg("bar")
        self.assertEqual(cmd.to_list(), ["echo", "foo", "bar"])
        res = cmd.run(text=True)
        self.assertEqual(res.stdout.strip(), "foo bar")

    def test_list_args_backward_compatibility(self):
        cmd = Command("echo", ["one", "two"])
        self.assertEqual(cmd.to_list(), ["echo", "one", "two"])
        res = cmd.run(text=True)
        self.assertEqual(res.stdout.strip(), "one two")

    def test_env_variables(self):
        cmd = Command("python3", "-c", "import os; print(os.environ.get('PUILD_TEST_ENV'))")
        cmd.env("PUILD_TEST_ENV", "awesome_value")
        res = cmd.run(text=True)
        self.assertEqual(res.stdout.strip(), "awesome_value")

    def test_stdin_input(self):
        cmd = Command("cat")
        res = cmd.run(input="input text", text=True)
        self.assertEqual(res.stdout, "input text")

    def test_stream_output(self):
        cmd = Command("python3", "-c", "import sys; sys.stdout.write('live_out\\n'); sys.stderr.write('live_err\\n')")
        res = cmd.run(stream=True, text=True)
        self.assertIn("live_out", res.stdout)
        self.assertIn("live_err", res.stderr)

    def test_dry_run_mode(self):
        cmd = Command("rm", "-rf", "/nonexistent_safely_ignored_12345")
        res = cmd.run(dry_run=True, text=True)
        self.assertTrue(res.ok)
        self.assertEqual(res.return_code, 0)

        set_dry_run(True)
        try:
            res_global = cmd.run(text=True)
            self.assertTrue(res_global.ok)
        finally:
            set_dry_run(False)

    def test_redirection_overwrite_and_append(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "output.txt"
            cmd1 = Command("echo", "line 1") > out_file
            cmd1.run()
            self.assertEqual(out_file.read_text().strip(), "line 1")

            cmd2 = Command("echo", "line 2") >> out_file
            cmd2.run()
            lines = out_file.read_text().splitlines()
            self.assertEqual(lines, ["line 1", "line 2"])

    def test_piping(self):
        pipe = Command("printf", "apple\\nbanana\\ncherry") | Command("grep", "banana")
        res = pipe.run(text=True)
        self.assertTrue(res.ok)
        self.assertEqual(res.stdout.strip(), "banana")


class TestFilesystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        set_quiet(True)

    def test_mkdir_rm_copy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            test_dir = mkdir(base / "nested" / "dir")
            self.assertTrue(test_dir.is_dir())

            test_file = test_dir / "sample.txt"
            test_file.write_text("content")

            copied_file = copy(test_file, base / "copied.txt")
            self.assertTrue(copied_file.is_file())
            self.assertEqual(copied_file.read_text(), "content")

            rm(test_file)
            self.assertFalse(test_file.exists())

            rm(base / "nested", recursive=True)
            self.assertFalse((base / "nested").exists())

    def test_find_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "a.c").write_text("")
            (base / "b.h").write_text("")
            sub = base / "sub"
            sub.mkdir()
            (sub / "c.c").write_text("")

            c_files = find_files(base, "*.c", recursive=True)
            names = [f.name for f in c_files]
            self.assertEqual(sorted(names), ["a.c", "c.c"])

            c_files_non_rec = find_files(base, "*.c", recursive=False)
            names_non_rec = [f.name for f in c_files_non_rec]
            self.assertEqual(names_non_rec, ["a.c"])

    def test_needs_rebuild(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            src = base / "main.c"
            target = base / "main.o"

            # 1. Target missing -> should rebuild
            src.write_text("int main() {}")
            self.assertTrue(needs_rebuild(target, src))

            # 2. Target created after source -> up to date
            time.sleep(0.01)
            target.write_text("object bytes")
            self.assertFalse(needs_rebuild(target, src))

            # 3. Source updated after target -> should rebuild
            time.sleep(0.01)
            src.write_text("int main() { return 0; }")
            self.assertTrue(needs_rebuild(target, src))

            # 4. Non-existent source -> raises FileNotFoundError
            self.assertRaises(FileNotFoundError, needs_rebuild, target, base / "missing.c")


if __name__ == "__main__":
    unittest.main()
