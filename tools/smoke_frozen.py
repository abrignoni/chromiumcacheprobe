"""Check that the built executables give the same output as the Python file they were built from.

    python tools/smoke_frozen.py <source folder> <command line executable> <window executable>

<source folder> is a checkout holding chromiumcacheprobe.py and tests/ (the build workflow
checks out the tag being released there). The public DFRWS 2021 cache subset in
tests/fixtures is unpacked, then `entries` and `recover` are run through
`python chromiumcacheprobe.py`, through the command line executable, and through the
window executable's --cli re-entry, which is how the window starts the tool. The entries
listing must be identical, and every file each recover run writes (the rebuilt clips and
provenance.json) must be byte-identical. Both executables' --version must name the
source's __version__.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

CACHE = "Dump/data/data/com.android.chrome/cache/Cache"


def run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False)
    if r.returncode != 0:
        sys.exit(f"FAILED ({r.returncode}): {' '.join(cmd)}\n{r.stdout[-2000:]}\n{r.stderr[-4000:]}")
    return r.stdout


def tree(folder: Path) -> dict[str, str]:
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


def main(src: Path, cli: str, gui: str) -> int:
    version = re.search(r'^__version__ = "([^"]+)"', (src / "chromiumcacheprobe.py").read_text(), re.M).group(1)
    source = [sys.executable, str(src / "chromiumcacheprobe.py")]
    runners = {"source": source, "cli": [cli], "gui --cli": [gui, "--cli"]}
    for name, command in runners.items():
        shown = run(command + ["--version"]).strip()
        if shown != version:
            sys.exit(f"{name} --version printed {shown!r}, expected {version!r}")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(src / "tests/fixtures/dfrws2021_s10_subset.zip") as archive:
            archive.extractall(root / "in")
        cache = str(root / "in" / CACHE)
        listings = {name: run(command + ["entries", cache]) for name, command in runners.items()}
        trees = {}
        for name, command in runners.items():
            out = root / ("out-" + name.replace(" ", "").replace("-", ""))
            run(command + ["recover", cache, "-o", str(out), "--progress"])
            runs = [p for p in out.iterdir() if p.is_dir()]
            assert len(runs) == 1, runs
            trees[name] = tree(runs[0])
    for name in ("cli", "gui --cli"):
        if listings[name] != listings["source"]:
            sys.exit(f"{name}: entries listing differs from the source's")
        if trees[name] != trees["source"]:
            sys.exit(f"{name}: recover wrote different files from the source:\n"
                     f"{sorted(set(trees[name].items()) ^ set(trees['source'].items()))}")
    clips = sum(1 for path in trees["source"] if path.endswith(".mp4"))
    print(f"{version}: entries identical ({len(listings['source'].splitlines()) - 1} entries); "
          f"recover identical ({clips} clips, {len(trees['source'])} files) for the command line "
          "executable and the window executable's --cli")
    return 0 if clips == 12 else 1


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    sys.exit(main(Path(sys.argv[1]), sys.argv[2], sys.argv[3]))
