import csv
import tempfile
import unittest
from pathlib import Path

from vanilla_bench.report import build_report


class ReportTests(unittest.TestCase):
    def test_report_files_failure_and_escaping(self):
        results = {"schema_version": 1, "synthetic": True,
                   "metadata": {"host": '<script>alert("x")</script>'},
                   "runs": [
                       {"pack": '<img src=x onerror="bad">', "scenario": "static", "repetition": 1,
                        "status": "ok", "frames_ms": [20], "resources": []},
                       {"pack": '<img src=x onerror="bad">', "scenario": "static", "repetition": 2,
                        "status": "failed", "error": '<script>bad()</script>'},
                   ]}
        with tempfile.TemporaryDirectory() as directory:
            build_report(results, Path(directory))
            html = (Path(directory) / "report.html").read_text(encoding="utf-8")
            md = (Path(directory) / "report.md").read_text(encoding="utf-8")
            with (Path(directory) / "summary.csv").open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
        self.assertIn("SYNTHETIC DATA", html)
        self.assertIn("SYNTHETIC DATA", md)
        self.assertIn("&lt;script&gt;bad()&lt;/script&gt;", html)
        self.assertIn("&lt;img src=x onerror=&quot;bad&quot;&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertEqual(rows[0]["failure_count"], "1")
        self.assertEqual(rows[0]["avg_fps"], "50.0")

    def test_empty_and_missing_resource_fields(self):
        results = {"schema_version": 1, "runs": [
            {"pack": "A", "scenario": "rotate", "status": "ok", "frames_ms": [16],
             "resources": [{"cpu_percent": 0, "rss_bytes": 0}]},
            {"pack": "A", "scenario": "rotate", "status": "ok"},
        ]}
        with tempfile.TemporaryDirectory() as directory:
            build_report(results, Path(directory))
            html = (Path(directory) / "report.html").read_text(encoding="utf-8")
            self.assertIn("Invalid measurement", html)
            self.assertIn("<strong>1 failed or invalid</strong>", html)
            self.assertTrue((Path(directory) / "summary.csv").exists())


if __name__ == "__main__":
    unittest.main()
