# chromiumcacheprobe

Reads the Chromium Simple Cache as Chrome keeps it on Android, and rebuilds the H.264 video it holds as MP4 files.

One Python file, standard library only. Brotli-compressed bodies need the optional `brotli` package; without it they are reported as not decodable instead of being skipped quietly.

## What it reads

- **Entries** in a Simple Cache folder (`cache/Cache` or `cache/Cache/Cache_Data`): the `_0` file with the cache key, the body (stream 1) and the HTTP response metadata (stream 0), and the `_s` file that holds partial (range) responses.
- **HTTP metadata**: request, response and original response times, the status line and the headers, with header names lowercased.
- **The cache index** (`index-dir/the-real-index`, version 9): the last-used time of each entry.
- **Bodies**, decoded by their `Content-Encoding`: gzip, deflate and, with `brotli` installed, br. Other encodings, zstd included, are reported as unsupported.

## What it rebuilds

Video players fetch video in pieces. Chrome can keep those pieces as MP4 fragments (`moof` and `mdat` boxes), and the header (`moov`) a player needs may not be cached with them. chromiumcacheprobe finds the fragments in the cache bodies, groups them by resource URL (byte-range query parameters and `_partN` suffixes removed) inside one cache folder and cache partition, and writes them out as a regular MP4:

- The sample bytes are copied exactly as stored. Only the container around them is written.
- When the original header survives in the cache, its codec and audio settings are used. When it does not, the H.264 settings are taken from the samples themselves and the clip is marked `video_header_reconstructed`.
- A clip starts at a key frame. Gaps, overlaps and configuration changes start a new clip, and a clip is also cut at the first key frame after 300 seconds. Nothing is filled in.
- A complete progressive MP4 found in the cache is copied byte for byte.
- No decoder is run. Each run writes `provenance.json`: the source file hashes, the offset and size of every sample, the original timing values, warnings and counts of what was skipped and why.

It does not handle encrypted media, codecs other than H.264 video and AAC audio, or audio without its original header.

## Use

```bash
python chromiumcacheprobe.py entries <cache folder>
python chromiumcacheprobe.py recover <cache folder> -o <output parent folder>
```

`entries` prints one tab-separated row per entry file: URL, HTTP status, content type, request, response and last-used times. `recover` creates a new run folder under the output parent (which must be outside the input) with `Videos/` and `provenance.json`.

From Python:

```python
import chromiumcacheprobe as ccp

meta = ccp.entry_metadata("cache/Cache/06b0441e4b13e306_0")   # key, url, times, headers
body, meta = ccp.entry_body("cache/Cache/150cd3c003b715bc_0")  # decoded stream 1
last_used = ccp.index_times("cache/Cache/index-dir/the-real-index")
out, manifest = ccp.recover_files([(path, relative_path), ...], "output")
```

Times are UTC `datetime` values, or an empty string when the cache holds none. They describe the HTTP exchange and the cache entry, not playback. Cached video does not show that anyone watched it.

## Validation

On the public DFRWS 2021 Galaxy S10 extraction, the cache produced 12 clips from three resources. ffmpeg 9.0.1, run by hand on the 12 outputs, decoded all of them with no errors; the test suite's decode check covers the synthetic clip only. All 170 samples in the 12 clips are byte-identical to the cache bytes they came from. The test suite carries that subset (`tests/fixtures/dfrws2021_s10_subset.zip`, unmodified files with their hashes) and synthetic fixtures for the cases the public data does not cover: sparse files, missing headers, gaps, duplicate and conflicting fragments, two Android users and cache partitions.

```bash
python -m pytest tests -q
```

## Credit

The recovery engine was written by Forensik.IT GmbH ([@ForensikITGmbH](https://github.com/ForensikITGmbH)) and first submitted to ALEAPP in abrignoni/ALEAPP#1721. Thank you for the work.

## References

- [Simple Cache entry format](https://chromium.googlesource.com/chromium/src/+/1bf6fdabfac5220b788324a5bf064f0a60457328/net/disk_cache/simple/simple_entry_format.h)
- [Entry file names](https://github.com/chromium/chromium/blob/587f22761bc5cb496b96db73fc4ec61df7d0b189/net/disk_cache/simple/simple_util.cc) and [index file](https://github.com/chromium/chromium/blob/c19136c8095bf8e466ea5061d8309b801f9c5607/net/disk_cache/simple/simple_index_file.cc)
- [Simple Cache index entries](https://chromium.googlesource.com/chromium/src/+/refs/tags/90.0.4430.91/net/disk_cache/simple/simple_index.cc)
- [HttpResponseInfo](https://github.com/chromium/chromium/blob/b749bc4d79b8ce0668165551b54f4a987ad31907/net/http/http_response_info.cc), including the extra flags that carry the original response time
- [ISO BMFF byte stream format](https://www.w3.org/TR/2024/NOTE-mse-byte-stream-format-isobmff-20240723/)

## Licence

MIT. See [LICENSE](LICENSE).
