"""The GUI's command line re-entry, progress stream and a hidden end-to-end run."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
import chromiumcacheprobe as ccp  # pylint: disable=wrong-import-position
import chromiumcacheprobe_gui as gui  # pylint: disable=wrong-import-position

GUI = str(REPO_ROOT / "chromiumcacheprobe_gui.py")
PUBLIC = REPO_ROOT / "tests" / "fixtures" / "dfrws2021_s10_subset.zip"
CACHE = "Dump/data/data/com.android.chrome/cache/Cache"


def run(*args):
    return subprocess.run([sys.executable, GUI, *args], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=300, check=False)


def tk_display_available():
    """Ask a separate process, so this one never creates a Tk root of its own."""
    probe = subprocess.run([sys.executable, "-c", "import tkinter; tkinter.Tk().destroy()"],
                           capture_output=True, stdin=subprocess.DEVNULL, timeout=60, check=False)
    return probe.returncode == 0


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        with zipfile.ZipFile(PUBLIC) as archive:
            archive.extractall(cls.root / "in")
        cls.cache = cls.root / "in" / CACHE
        expected = json.loads((REPO_ROOT / "tests/fixtures/dfrws2021_sources.json").read_text())
        cls.expected = set(expected["output_sha256"])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_cli_reentry_rebuilds_the_published_clips_and_streams_progress(self):
        result = run("--cli", "recover", str(self.cache), "-o", str(self.root / "cli"), "--progress")
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        status, rows = gui.clip_rows(summary["output"])
        self.assertEqual(status, "completed")
        self.assertEqual({row[-1] for row in rows}, self.expected)
        records = [json.loads(line) for line in result.stderr.splitlines()]
        self.assertTrue(all(record["total_files"] == 12 for record in records))
        self.assertEqual(records[-1]["stage"], "completed")
        self.assertEqual(records[-1]["clips"], 12)

    def test_cli_reentry_lists_entries(self):
        result = run("--cli", "entries", str(self.cache))
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0].split("\t"), list(gui.ENTRY_COLUMNS))
        self.assertEqual(len(lines) - 1,
                         sum(1 for path in self.cache.iterdir() if ccp.ENTRY_NAME.fullmatch(path.name)))

    def test_cli_errors_exit_two_with_a_message(self):
        missing = run("--cli", "recover", str(self.root / "missing"), "-o", str(self.root / "x"))
        self.assertEqual(missing.returncode, 2)
        self.assertIn("not a folder", missing.stderr)
        inside = run("--cli", "recover", str(self.cache), "-o", str(self.cache / "out"))
        self.assertEqual(inside.returncode, 2)
        self.assertIn("outside the input", inside.stderr)

    def test_hidden_window_runs_a_rebuild(self):
        if not tk_display_available():
            self.skipTest("Tk cannot open a display here")
        result = run("--smoke", str(self.cache), str(self.root / "smoke"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout.strip().splitlines()[-1]), {"exit": 0, "rows": 12})


if __name__ == "__main__":
    unittest.main()
