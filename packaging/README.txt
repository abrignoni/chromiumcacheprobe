chromiumcacheprobe, built as standalone executables
===================================================

  chromiumcacheprobe      the command line tool (chromiumcacheprobe.exe on
                          Windows). Open a terminal in this folder and run:
                              chromiumcacheprobe entries Cache/
                              chromiumcacheprobe recover Cache/ -o out/
                              chromiumcacheprobe --help
                          On Windows write chromiumcacheprobe.exe; on macOS and
                          Linux write ./chromiumcacheprobe from this folder.
                          `Cache/` is the Cache (or Cache_Data) folder from
                          data/data/com.android.chrome/cache in an Android
                          extraction.

  chromiumcacheprobe_gui  the same tool in a window (chromiumcacheprobe_gui.exe
                          on Windows, chromiumcacheprobe_gui.app on macOS).
                          Choose the cache folder and an output folder, then
                          List entries or Rebuild videos. Double-click a clip
                          to open it.

  SHA256SUMS.txt          the hashes of the executables as built. Check them with
                              certutil -hashfile chromiumcacheprobe.exe SHA256   (Windows)
                              shasum -a 256 -c SHA256SUMS.txt                    (macOS)
                              sha256sum -c SHA256SUMS.txt                        (Linux)

Both read the cache folder read-only and write only into a new folder inside the
output folder you choose. They install nothing and need no administrator rights.
They are built from chromiumcacheprobe.py and chromiumcacheprobe_gui.py in
https://github.com/abrignoni/chromiumcacheprobe by the repository's own GitHub
Actions workflow, and are not code signed:

  Windows   SmartScreen may ask once before running them. Unzip to a local
            folder rather than running from a network share.
  macOS     Gatekeeper will refuse a downloaded, unsigned program on first
            run. Right-click (Control-click) it in Finder and choose Open,
            once, or remove the quarantine mark from this folder:
                xattr -dr com.apple.quarantine .
  Linux     mark the files executable if the archive did not keep the bit:
                chmod +x chromiumcacheprobe chromiumcacheprobe_gui

Builds: windows-x64, windows-arm64 (native for Windows on ARM; the x64 build
also runs there through emulation), macos-arm64 (Apple silicon), macos-x64
(Intel), linux-x64, linux-arm64.
