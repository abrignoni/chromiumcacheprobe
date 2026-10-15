chromiumcacheprobe {{VERSION}}: standalone executables of `chromiumcacheprobe.py` and its window, `chromiumcacheprobe_gui.py`, built by this repository's own GitHub Actions workflow from the tagged commit.

- `chromiumcacheprobe-{{VERSION}}-windows-x64.zip` runs on Intel and AMD PCs, and on Windows on ARM through its x64 emulation.
- `chromiumcacheprobe-{{VERSION}}-windows-arm64.zip` is native for Windows on ARM.
- `chromiumcacheprobe-{{VERSION}}-macos-arm64.zip` for Apple silicon Macs, `chromiumcacheprobe-{{VERSION}}-macos-x64.zip` for Intel Macs.
- `chromiumcacheprobe-{{VERSION}}-linux-x64.tar.gz` and `chromiumcacheprobe-{{VERSION}}-linux-arm64.tar.gz`, built on Ubuntu 22.04 so they run on distributions with a glibc at least that old.
- `chromiumcacheprobe.py` and `chromiumcacheprobe_gui.py`, the tagged source files themselves.

Each archive holds the command line tool, the window, `README.txt`, `LICENSE` and `SHA256SUMS.txt`. `SHA256SUMS.txt` beside the archives covers the archives and the two source files. Before they were attached, both executables were run on the public DFRWS 2021 Galaxy S10 cache subset in the tests, and wrote the same bytes as `python chromiumcacheprobe.py` for `entries` and `recover`. The window was also started and checked to stay up.

Where a prebuilt brotli wheel exists for the target, the executables carry it and read Brotli-compressed cache bodies; the others report those bodies as not decodable. None of them is code signed: Windows SmartScreen and macOS Gatekeeper will each ask once, and the README inside says what to do.

`chromiumcacheprobe.py` needs nothing built: `python3 chromiumcacheprobe.py` works on macOS, Linux and Windows with Python 3.10 or later and the standard library alone.
