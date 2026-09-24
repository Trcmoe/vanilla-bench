import math
import unittest

from vanilla_bench.metrics import bootstrap_mean_fps_ci, summarize_results, summarize_run


def run(frames, **kwargs):
    return {"pack": "A", "scenario": "static", "repetition": 1, "status": "ok",
            "frames_ms": frames, "resources": []} | kwargs


class MetricsTests(unittest.TestCase):
    def test_frame_tails_percentiles_and_hitch_rate(self):
        frames = [10.0] * 998 + [60.0, 110.0]
        result = summarize_run(run(frames))
        self.assertAlmostEqual(result["avg_fps"], 1000 / (10150 / 1000))
        self.assertAlmostEqual(result["low_1pct_fps"], 1000 / ((8 * 10 + 60 + 110) / 10))
        self.assertAlmostEqual(result["low_0_1pct_fps"], 1000 / 110)
        self.assertEqual(result["p50_frame_ms"], 10)
        self.assertEqual(result["p95_frame_ms"], 10)
        self.assertEqual(result["p99_frame_ms"], 10)
        self.assertEqual(result["hitch_count"], 2)
        self.assertAlmostEqual(result["hitches_over_50ms_per_min"], 2 * 60000 / 10150)

    def test_resources_and_missing_optional_measurements(self):
        result = summarize_run(run([20], resources=[{"cpu_percent": 125, "rss_bytes": 1048576},
                                                        {"cpu_percent": 75, "rss_bytes": 3 * 1048576}]))
        self.assertEqual(result["cpu_mean_percent"], 100)
        self.assertEqual(result["cpu_peak_percent"], 125)
        self.assertEqual(result["ram_mean_mib"], 2)
        self.assertEqual(result["ram_peak_mib"], 3)
        self.assertIsNone(result["startup_ms"])
        self.assertIsNone(summarize_run(run([20]))["cpu_mean_percent"])

    def test_invalid_frames_rejected(self):
        for frames in ([], [0], [-1], [math.nan], [math.inf], [True]):
            with self.subTest(frames=frames), self.assertRaises(ValueError):
                summarize_run(run(frames))

    def test_invalid_resource_sample_becomes_group_failure(self):
        group = summarize_results({"schema_version": 1, "runs": [run([16], resources=[None])]})["groups"][0]
        self.assertEqual(group["failure_count"], 1)
        self.assertEqual(group["successful_count"], 0)

    def test_bootstrap_is_deterministic_and_single_run_is_degenerate(self):
        self.assertEqual(bootstrap_mean_fps_ci([60]), (60, 60))
        self.assertEqual(bootstrap_mean_fps_ci([30, 60, 90], resamples=500),
                         bootstrap_mean_fps_ci([30, 60, 90], resamples=500))
        low, high = bootstrap_mean_fps_ci([30, 60, 90], resamples=500)
        self.assertLessEqual(low, 60)
        self.assertGreaterEqual(high, 60)

    def test_run_level_aggregation_and_failed_runs(self):
        results = {"schema_version": 1, "runs": [
            run([10] * 1000), run([20]),
            {"pack": "A", "scenario": "static", "repetition": 3, "status": "failed", "error": "crash"},
            run([0]),
        ]}
        group = summarize_results(results)["groups"][0]
        self.assertEqual(group["repeat_count"], 4)
        self.assertEqual(group["successful_count"], 2)
        self.assertEqual(group["failure_count"], 2)
        self.assertTrue(group["uncertain"])
        self.assertEqual(group["metrics"]["avg_fps"], 75)
        self.assertEqual(group["mean_fps_ci95_low"], 50)
        self.assertEqual(group["mean_fps_ci95_high"], 100)
        self.assertIn("crash", group["failures"][0]["error"])


if __name__ == "__main__":
    unittest.main()
