"""Entry metadata, index times, body decoding and the command line."""

import builtins
import datetime
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import zlib

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
import chromiumcacheprobe as ccp  # pylint: disable=wrong-import-position

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PUBLIC = FIXTURES / "dfrws2021_s10_subset.zip"
CACHE = "Dump/data/data/com.android.chrome/cache/Cache"

try:
    import brotli  # pylint: disable=unused-import
    HAVE_BROTLI = True
except ImportError:
    HAVE_BROTLI = False


class PublicCacheTests(unittest.TestCase):
    """The DFRWS 2021 Galaxy S10 subset: public, unmodified cache files."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        with zipfile.ZipFile(PUBLIC) as archive:
            archive.extractall(cls.root)
        cls.cache = cls.root / CACHE

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_entry_metadata_reads_http_times_and_headers(self):
        entries = sorted(self.cache.glob("*_0"))
        self.assertEqual(len(entries), 6)
        for path in entries:
            meta = ccp.entry_metadata(path)
            self.assertTrue(meta["url"].startswith("https://"), path.name)
            self.assertEqual(meta["status_detail"], "HTTP metadata parsed", path.name)
            self.assertTrue(meta["status"].startswith("HTTP/"))
            self.assertIsInstance(meta["response_time"], datetime.datetime)
            self.assertEqual(meta["response_time"].tzinfo, datetime.timezone.utc)
            self.assertLessEqual(meta["request_time"], meta["response_time"])
            self.assertIn("content-type", meta["headers"])

    def test_sparse_entry_key_matches_its_metadata_entry(self):
        for sparse in sorted(self.cache.glob("*_s")):
            dense = sparse.with_name(sparse.name[:-2] + "_0")
            if dense.exists():
                self.assertEqual(ccp.raw_cache_key(sparse), ccp.entry_metadata(dense)["cache_key"])

    def test_index_times_cover_the_entries(self):
        times = ccp.index_times(self.cache / "index-dir/the-real-index")
        names = {path.name[:16] for path in self.cache.iterdir() if ccp.ENTRY_NAME.fullmatch(path.name)}
        self.assertTrue(names <= set(times))
        self.assertTrue(all(isinstance(times[name], datetime.datetime) for name in names))

    def test_cli_recover_reproduces_the_published_clips(self):
        expected = json.loads((FIXTURES / "dfrws2021_sources.json").read_text())
        out = self.root / "cli-output"
        with patch("sys.stdout") as stdout:
            self.assertEqual(ccp.main(["recover", str(self.cache), "-o", str(out)]), 0)
        report = json.loads("".join(call.args[0] for call in stdout.write.call_args_list))
        provenance = json.loads((Path(report["output"]) / "provenance.json").read_text())
        self.assertEqual({clip["sha256"] for clip in provenance["clips"]},
                         set(expected["output_sha256"]))

    def test_cli_entries_lists_every_entry_file(self):
        with patch("sys.stdout") as stdout:
            self.assertEqual(ccp.main(["entries", str(self.cache)]), 0)
        lines = "".join(call.args[0] for call in stdout.write.call_args_list).splitlines()
        rows = [line.split("\t") for line in lines[1:]]
        names = sorted(path.name for path in self.cache.iterdir() if ccp.ENTRY_NAME.fullmatch(path.name))
        self.assertEqual(sorted(row[0] for row in rows), names)
        self.assertTrue(all(row[6] for row in rows))  # every entry has a last-used time


class DecodeBodyTests(unittest.TestCase):
    BODY = b'{"kind": "Listing", "data": {"children": []}}' * 20

    def test_identity_and_gzip(self):
        self.assertEqual(ccp.decode_body(self.BODY, ""), self.BODY)
        self.assertEqual(ccp.decode_body(gzip.compress(self.BODY), "gzip"), self.BODY)
        # gzip is recognised by its magic bytes when the header is missing.
        self.assertEqual(ccp.decode_body(gzip.compress(self.BODY), ""), self.BODY)

    def test_deflate_with_and_without_zlib_wrapper(self):
        self.assertEqual(ccp.decode_body(zlib.compress(self.BODY), "deflate"), self.BODY)
        raw = zlib.compressobj(wbits=-15)
        data = raw.compress(self.BODY) + raw.flush()
        self.assertEqual(ccp.decode_body(data, "deflate"), self.BODY)

    @unittest.skipUnless(HAVE_BROTLI, "brotli package not installed")
    def test_brotli(self):
        import brotli  # pylint: disable=import-outside-toplevel,redefined-outer-name
        self.assertEqual(ccp.decode_body(brotli.compress(self.BODY), "br"), self.BODY)

    def test_brotli_without_the_package_is_reported(self):
        real_import = builtins.__import__

        def no_brotli(name, *args, **kwargs):
            if name == "brotli":
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", no_brotli):
            with self.assertRaisesRegex(ccp.BodyError, "brotli package is not installed"):
                ccp.decode_body(b"\x0b\x02\x80", "br")

    def test_limits_truncation_and_unknown_encodings(self):
        with self.assertRaises(ccp.BodyError):
            ccp.decode_body(gzip.compress(self.BODY), "gzip", limit=10)
        with self.assertRaises(ccp.BodyError):
            ccp.decode_body(gzip.compress(self.BODY)[:-12], "gzip")
        with self.assertRaises(ccp.BodyError):
            ccp.decode_body(self.BODY, "", limit=10)
        with self.assertRaisesRegex(ccp.BodyError, "unsupported content encoding"):
            ccp.decode_body(self.BODY, "zstd")


if __name__ == "__main__":
    unittest.main()
