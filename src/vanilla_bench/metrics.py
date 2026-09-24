"""Frame and resource statistics for one measured run or a set of runs."""

from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict


_MEDIAN_FIELDS = (
    "avg_fps", "low_1pct_fps", "low_0_1pct_fps", "p50_frame_ms",
    "p95_frame_ms", "p99_frame_ms", "hitches_over_50ms_per_min",
    "startup_ms", "world_load_ms", "ram_peak_mib", "ram_mean_mib",
    "cpu_mean_percent", "cpu_peak_percent",
)


def _number(value, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    value = float(value)
    if not math.isfinite(value) or (value <= 0 if positive else value < 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'nonnegative'} and finite")
    return value


def _nearest_rank(sorted_values: list[float], fraction: float) -> float:
    return sorted_values[math.ceil(len(sorted_values) * fraction) - 1]


def summarize_run(run: dict) -> dict:
    """Summarize a successful run. Failed runs have no performance metrics.

    FPS tails use the mean of the slowest ceil(1% or 0.1%) frame durations.
    Percentiles use nearest rank. CPU is process CPU where 100% is one core.
    Missing optional startup/resource measurements become ``None``.
    """
    if run.get("status") != "ok":
        if run.get("status") == "failed":
            return {key: None for key in _MEDIAN_FIELDS} | {"frame_count": 0, "hitch_count": 0}
        raise ValueError("run status must be 'ok' or 'failed'")
    frames = run.get("frames_ms")
    if not isinstance(frames, list) or not frames:
        raise ValueError("successful run requires nonempty frames_ms")
    ordered = sorted(_number(value, "frame duration", positive=True) for value in frames)
    count = len(ordered)
    duration_ms = sum(ordered)
    hitches = sum(value > 50 for value in ordered)
    resources = run.get("resources") or []
    if not isinstance(resources, list):
        raise ValueError("resources must be a list")
    if any(not isinstance(sample, dict) for sample in resources):
        raise ValueError("resource samples must be objects")
    cpu = [_number(sample["cpu_percent"], "cpu_percent") for sample in resources if sample.get("cpu_percent") is not None]
    ram = [_number(sample["rss_bytes"], "rss_bytes") / 1048576 for sample in resources if sample.get("rss_bytes") is not None]
    optional = {}
    for field in ("startup_ms", "world_load_ms"):
        optional[field] = None if run.get(field) is None else _number(run[field], field)
    return {
        "frame_count": count,
        "avg_fps": 1000 / statistics.mean(ordered),
        "low_1pct_fps": 1000 / statistics.mean(ordered[-math.ceil(count * .01):]),
        "low_0_1pct_fps": 1000 / statistics.mean(ordered[-math.ceil(count * .001):]),
        "p50_frame_ms": _nearest_rank(ordered, .5),
        "p95_frame_ms": _nearest_rank(ordered, .95),
        "p99_frame_ms": _nearest_rank(ordered, .99),
        "hitch_count": hitches,
        "hitches_over_50ms_per_min": hitches * 60000 / duration_ms,
        "ram_peak_mib": max(ram) if ram else None,
        "ram_mean_mib": statistics.mean(ram) if ram else None,
        "cpu_mean_percent": statistics.mean(cpu) if cpu else None,
        "cpu_peak_percent": max(cpu) if cpu else None,
        **optional,
    }


def bootstrap_mean_fps_ci(values: list[float], *, seed: int = 20260924,
                          resamples: int = 10000) -> tuple[float, float] | None:
    """Deterministic percentile bootstrap 95% CI for the run-level mean FPS."""
    if not values:
        return None
    values = [_number(value, "run FPS", positive=True) for value in values]
    if resamples < 1:
        raise ValueError("resamples must be positive")
    rng = random.Random(seed)
    estimates = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(resamples))
    return (_nearest_rank(estimates, .025), _nearest_rank(estimates, .975))


def summarize_results(results: dict) -> dict:
    """Group by pack and scenario, with failed/incomplete runs kept visible."""
    if results.get("schema_version") != 1:
        raise ValueError("Unsupported results schema_version")
    runs = results.get("runs")
    if not isinstance(runs, list):
        raise ValueError("results.runs must be a list")
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for run in runs:
        if not isinstance(run, dict):
            raise ValueError("Each run must be an object")
        grouped[(str(run.get("pack", "Unknown")), str(run.get("scenario", "Unknown")))].append(run)
    groups = []
    for (pack, scenario), members in sorted(grouped.items()):
        successful = []
        failures = []
        for run in members:
            try:
                metrics = summarize_run(run)
                if run.get("status") == "failed":
                    failures.append({"repetition": run.get("repetition"), "error": str(run.get("error") or "Run failed")})
                else:
                    successful.append(metrics)
            except (ValueError, KeyError, TypeError) as exc:
                failures.append({"repetition": run.get("repetition"), "error": f"Invalid measurement: {exc}"})
        fps = [item["avg_fps"] for item in successful]
        medians = {
            field: statistics.median(values) if (values := [item[field] for item in successful if item[field] is not None]) else None
            for field in _MEDIAN_FIELDS
        }
        variation = statistics.stdev(fps) / statistics.mean(fps) * 100 if len(fps) > 1 else None
        ci = bootstrap_mean_fps_ci(fps)
        groups.append({
            "pack": pack, "scenario": scenario, "repeat_count": len(members),
            "successful_count": len(successful), "failure_count": len(failures),
            "uncertain": len(successful) < 5,
            "fps_variation_cv_percent": variation,
            "mean_fps_ci95_low": ci[0] if ci else None,
            "mean_fps_ci95_high": ci[1] if ci else None,
            "metrics": medians, "failures": failures,
        })
    return {"groups": groups, "total_runs": len(runs),
            "total_failures": sum(group["failure_count"] for group in groups)}
