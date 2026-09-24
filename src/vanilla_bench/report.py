"""Portable, dependency-free benchmark reports."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path

from .metrics import summarize_results


_COLUMNS = (
    ("avg_fps", "Average FPS"), ("low_1pct_fps", "1% low FPS"),
    ("low_0_1pct_fps", "0.1% low FPS"), ("p50_frame_ms", "p50 frame ms"),
    ("p95_frame_ms", "p95 frame ms"), ("p99_frame_ms", "p99 frame ms"),
    ("hitches_over_50ms_per_min", ">50 ms hitches/min"),
    ("startup_ms", "Startup ms"), ("world_load_ms", "World load ms"),
    ("ram_peak_mib", "Peak RAM MiB"), ("ram_mean_mib", "Mean RAM MiB"),
    ("cpu_mean_percent", "Mean CPU %"), ("cpu_peak_percent", "Peak CPU %"),
)


def _fmt(value) -> str:
    return "—" if value is None else f"{value:.2f}"


def _h(value) -> str:
    return html.escape(str(value), quote=True)


def _md(value) -> str:
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ").replace("<", "&lt;").replace(">", "&gt;")


def build_report(results: dict, output_dir: Path) -> None:
    """Write standalone HTML, Markdown and CSV summaries into output_dir."""
    summary = summarize_results(results)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    groups = summary["groups"]
    metadata = results.get("metadata") or {}
    metadata_json = json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    synthetic = bool(results.get("synthetic"))

    csv_fields = ["pack", "scenario", "repeat_count", "successful_count", "failure_count",
                  "uncertain", "fps_variation_cv_percent", "mean_fps_ci95_low", "mean_fps_ci95_high"] + [key for key, _ in _COLUMNS]
    with (output_dir / "summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=csv_fields)
        writer.writeheader()
        for group in groups:
            writer.writerow({**{key: group[key] for key in csv_fields if key in group}, **group["metrics"]})

    headers = ["Pack", "Scenario", "Runs", "OK", "Failed", "Uncertain",
               "FPS variation CV %", "Mean FPS 95% CI"] + [title for _, title in _COLUMNS]
    rows = []
    for group in groups:
        ci = (f'{_fmt(group["mean_fps_ci95_low"])}–{_fmt(group["mean_fps_ci95_high"])}'
              if group["mean_fps_ci95_low"] is not None else "—")
        rows.append([group["pack"], group["scenario"], str(group["repeat_count"]),
                     str(group["successful_count"]), str(group["failure_count"]),
                     "YES" if group["uncertain"] else "", _fmt(group["fps_variation_cv_percent"]), ci]
                    + [_fmt(group["metrics"][key]) for key, _ in _COLUMNS])

    failures = [(group["pack"], group["scenario"], failure["repetition"], failure["error"])
                for group in groups for failure in group["failures"]]
    md = ["# Vanilla Bench report", "",
          "**SYNTHETIC DATA — NOT A REAL BENCHMARK**" if synthetic else "Measured benchmark data.",
          "", f'Runs: {summary["total_runs"]}; failures: {summary["total_failures"]}.', "",
          "| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    md.extend("| " + " | ".join(_md(cell) for cell in row) + " |" for row in rows)
    if not rows:
        md.extend(["", "No runs were supplied."])
    md.extend(["", "## Failed or invalid runs", ""])
    md.extend(f'- {_md(pack)} / {_md(scenario)}, repetition {_md(rep)}: {_md(error)}'
              for pack, scenario, rep, error in failures)
    if not failures:
        md.append("None.")
    md.extend(["", "## Methodology", "",
               "Each run is summarized separately; group values are medians of successful runs. "
               "Average FPS = 1000 / mean frame time in ms. The 1% and 0.1% lows use "
               "1000 / mean of the slowest ceil(1% or 0.1%) frame times. Frame-time "
               "p50/p95/p99 use nearest rank. Hitches count frames strictly over 50 ms "
               "and divide by measured frame duration in minutes. RAM is process RSS in MiB "
               "(2^20 bytes). CPU is process CPU, where 100% represents one logical core. "
               "The variation is sample standard deviation / mean of run FPS. The 95% "
               "confidence interval uses a fixed-seed, 10,000-resample percentile bootstrap "
               "of the mean run FPS. Groups with fewer than five successful runs are marked uncertain. "
               "Failed or invalid runs are excluded from performance metrics.",
               "", "## Host metadata", "", "```json", metadata_json, "```", ""])
    (output_dir / "report.md").write_text("\n".join(md), encoding="utf-8")

    max_fps = max((group["metrics"]["avg_fps"] or 0 for group in groups), default=0)
    bars = []
    for i, group in enumerate(groups):
        fps = group["metrics"]["avg_fps"]
        width = 540 * fps / max_fps if max_fps and fps is not None else 0
        label = f'{group["pack"]} / {group["scenario"]}: {_fmt(fps)} median average FPS'
        y = 30 + i * 48
        bars.append(f'<g><title>{_h(label)}</title><text x="0" y="{y+14}">{_h(group["pack"])} / {_h(group["scenario"])}</text>'
                    f'<rect x="330" y="{y}" width="{width:.1f}" height="22" fill="#4388b9" />'
                    f'<text x="{335+width:.1f}" y="{y+16}">{_h(_fmt(fps))}</text></g>')
    svg_height = max(80, 55 + len(groups) * 48)
    th = "".join(f'<th scope="col">{_h(header)}</th>' for header in headers)
    table_rows = "".join("<tr>" + "".join(f"<td>{_h(cell)}</td>" for cell in row) + "</tr>" for row in rows)
    failure_html = "".join(f'<li><strong>{_h(pack)} / {_h(scenario)}, repetition {_h(rep)}</strong>: {_h(error)}</li>'
                           for pack, scenario, rep, error in failures) or "<li>None.</li>"
    watermark = ('<div class="watermark" role="alert">SYNTHETIC DATA — NOT A REAL BENCHMARK</div>'
                 if synthetic else "")
    html_document = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vanilla Bench report</title><style>
body{{font:16px/1.5 system-ui,sans-serif;color:#17212b;background:#fff;max-width:1300px;margin:2rem auto;padding:0 1rem}}
h1,h2{{line-height:1.2}} .watermark{{background:#8d1020;color:white;font-size:1.4rem;font-weight:bold;padding:1rem;margin:1rem 0}}
.notice{{background:#fff3ca;padding:.75rem}} .scroll{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-size:.85rem}}
th,td{{border:1px solid #bfc8d0;padding:.45rem;text-align:right;white-space:nowrap}} th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){{text-align:left}}
th{{background:#eaf2f8}} tr:nth-child(even){{background:#f6f8fa}} svg{{max-width:100%;height:auto}} pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:1rem}}
</style></head><body><h1>Vanilla Bench report</h1>{watermark}
<p class="notice">{summary["total_runs"]} runs; <strong>{summary["total_failures"]} failed or invalid</strong>. Groups with fewer than five successful runs are marked uncertain.</p>
<h2>Median average FPS by pack and scenario</h2><svg viewBox="0 0 950 {svg_height}" role="img" aria-label="Median average FPS bars; exact values follow in the table"><title>Median average FPS</title>{''.join(bars)}</svg>
<h2>Results</h2><div class="scroll"><table><caption>Group medians, run counts and confidence intervals</caption><thead><tr>{th}</tr></thead><tbody>{table_rows}</tbody></table></div>
<h2>Failed or invalid runs</h2><ul>{failure_html}</ul>
<h2>Methodology</h2><p>Each run is summarized separately; group values are medians of successful runs. Average FPS = 1000 / mean frame time in ms. The 1% and 0.1% lows use 1000 / mean of the slowest ceil(1% or 0.1%) frame times. Frame-time p50/p95/p99 use nearest rank. Hitches count frames strictly over 50 ms and divide by measured frame duration in minutes. RAM is process RSS in MiB (2²⁰ bytes). CPU is process CPU, where 100% represents one logical core. Variation is sample standard deviation / mean of run FPS. The 95% confidence interval uses a fixed-seed, 10,000-resample percentile bootstrap of the mean run FPS. Groups with fewer than five successful runs are marked uncertain. Failed or invalid runs are excluded from performance metrics.</p>
<h2>Host metadata</h2><pre>{_h(metadata_json)}</pre></body></html>'''
    (output_dir / "report.html").write_text(html_document, encoding="utf-8")
