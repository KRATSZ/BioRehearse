"""Figure 4: language-to-intent evaluation and its remaining boundaries."""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

import matplotlib

matplotlib.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 6.5, "svg.fonttype": "none", "pdf.fonttype": 42, "savefig.dpi": 400,
})
# The shared save_figure helper invokes require_matplotlib_panel_alignment(...) after the final draw.
# Final editable exports: fig.savefig("figure.svg"), fig.savefig("figure.pdf"), fig.savefig("figure.png", dpi=400).

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sharedstyle import (  # noqa: E402
    COLORS,
    DATA,
    METHOD_LABELS,
    PAPER,
    V3,
    configure_axis,
    figure_size,
    panel,
    read_json,
    read_jsonl,
    save_figure,
)


MODELS = ["deepseek-flash", "deepseek-v4-pro"]
MODEL_LABELS = {"deepseek-flash": "DeepSeek Flash", "deepseek-v4-pro": "DeepSeek Pro"}
MODEL_COLORS = {"deepseek-flash": "#526876", "deepseek-v4-pro": "#17242E"}
CATEGORIES = ["controlled", "open", "mixed", "clarify", "reject"]
CATEGORY_LABELS = ["Controlled", "Open", "Mixed zh–en", "Clarify", "Reject"]
TARIFF_INTERVALS = {
    # Provider-list-price estimates applied to the recorded 120-call
    # aggregate; these are planning ranges, not account invoices.
    "deepseek-flash": (0.042, 0.084),
    "deepseek-v4-pro": (0.292, 0.584),
}


def _scores(model: str) -> list[dict]:
    return read_jsonl(DATA / "heldout" / "language" / model / "scores.jsonl")


def _rule_rows() -> list[dict]:
    return read_jsonl(DATA / "heldout" / "language" / "rules.jsonl")


def _rate(rows: list[dict], category: str, *, model: bool = False) -> tuple[float, int, int]:
    if model:
        subset = [r for r in rows if r.get("repeat") == 0 and ((r.get("style") == category) if category in {"controlled", "open", "mixed"} else (r.get("decision") == category))]
    else:
        # The parser has no model-side clarification score; its abstention is
        # represented separately and is not converted to a false failure.
        subset = [r for r in rows if r.get("style") == category and r.get("decision") == "compile"]
    if not subset:
        return float("nan"), 0, 0
    success = sum(bool(r.get("success")) for r in subset)
    return success / len(subset), success, len(subset)


def _draw_success(ax, summary: dict, rules: list[dict]):
    x = np.arange(len(CATEGORIES))
    width = 0.22
    parser = []
    parser_n = []
    for category in CATEGORIES:
        if category == "controlled":
            rate, n_success, n = _rate(rules, category)
        else:
            rate, n_success, n = float("nan"), 0, 0
        parser.append(rate)
        parser_n.append((n_success, n))
    offsets = [-0.30, 0.0, 0.30]
    ax.bar(x + offsets[0], parser, width=width, color="#C8D0D4", label="Rule parser", edgecolor="white", linewidth=0.35)
    for offset, model in enumerate(MODELS):
        groups = summary["language"][model]["groups"]
        values = [groups[c]["success"] / groups[c]["n"] for c in CATEGORIES]
        ax.bar(x + offsets[offset + 1], values, width=width, color=MODEL_COLORS[model], label=MODEL_LABELS[model], edgecolor="white", linewidth=0.35)
        for xi, value, category in zip(x + offsets[offset + 1], values, CATEGORIES):
            n = groups[category]["n"]
            # Keep the exact successful-count labels inside their bars.  This
            # preserves the values while leaving the top legend and title
            # visually separate at final size.
            ax.text(xi, max(0.08, value - 0.045), f"{int(round(value * n))}",
                    ha="center", va="top", fontsize=6.0, color="white", zorder=4)
    ax.set_ylim(0, 1.18)
    ax.set_yticks([0, 0.5, 1], ["0", "50", "100"])
    ax.set_ylabel("Strict success (%)")
    ax.set_xticks(x, CATEGORY_LABELS)
    ax.tick_params(length=2, pad=2)
    ax.legend(frameon=False, ncol=3, loc="upper left", bbox_to_anchor=(0, 1.03), handlelength=1.3, columnspacing=1.0)
    ax.text(0.0, -0.24, f"Numbers are successful requests (n=24 per compile family; n=12 for clarify/reject). Rule parser abstained on {sum(r.get('parser_decision') == 'abstain' for r in rules)}/{len(rules)} requests.", transform=ax.transAxes, fontsize=6.0, color=COLORS["muted"])
    panel(ax, "a", "Supported language families are preserved; abstention remains visible")


def _latency_stats(model: str) -> tuple[float, float, float]:
    """Return p5, median and p95 from the frozen first-run diagnostics."""
    values = [float(row["wall_s"]) for row in _scores(model) if row.get("repeat") == 0 and row.get("wall_s") is not None]
    if not values:
        raise ValueError(f"No latency diagnostics for {model}")
    return tuple(float(value) for value in np.percentile(values, [5, 50, 95]))


def _draw_latency(ax):
    stats = [_latency_stats(model) for model in MODELS]
    y = np.arange(len(MODELS))
    for yi, model, (p5, median, p95) in zip(y, MODELS, stats):
        ax.errorbar(
            median,
            yi,
            xerr=[[median - p5], [p95 - median]],
            fmt="o",
            color=MODEL_COLORS[model],
            ecolor=MODEL_COLORS[model],
            elinewidth=1.0,
            capsize=2.2,
            markersize=4.2,
            zorder=3,
        )
        ax.text(p95 - 0.80, yi - 0.18, f"{median:.1f} s", va="center", ha="right", fontsize=5.8, color=MODEL_COLORS[model])
    ax.set_yticks(y, ["Flash", "Pro"])
    ax.invert_yaxis()
    ax.set_ylim(1.35, -0.35)
    ax.set_xlabel("Inference latency (s)")
    ax.set_xlim(0, max(p95 for _, _, p95 in stats) * 1.30)
    ax.tick_params(length=2, pad=2)
    ax.grid(False)
    panel(ax, "b", "Inference latency (p5–p95)")


def _draw_tariff(ax):
    y = np.arange(len(MODELS))
    for yi, model in zip(y, MODELS):
        low, high = TARIFF_INTERVALS[model]
        color = MODEL_COLORS[model]
        ax.plot([low, high], [yi, yi], color=color, linewidth=1.5, solid_capstyle="round", zorder=2)
        ax.scatter([low, high], [yi, yi], s=16, facecolor="white", edgecolor=color, linewidth=0.7, zorder=3)
        ax.text(0.56, yi - 0.18, f"{low:.3f}–{high:.3f}", va="center", ha="right", fontsize=5.8, color=color)
    ax.set_yticks(y, ["Flash", "Pro"])
    ax.invert_yaxis()
    ax.set_xlim(0, 0.70)
    ax.set_xticks([0, 0.3, 0.6], ["0", "0.3", "0.6"])
    ax.set_ylim(1.35, -0.35)
    ax.set_xlabel("US$ per 120 calls")
    ax.tick_params(length=2, pad=1.5)
    ax.grid(False)
    panel(ax, "c", "Estimated tariff interval")


def _requested_deadline_s(request: str) -> int | None:
    """Parse the stated completion horizon using the frozen time-origin contract."""
    hours = re.findall(r"(\d{1,2}):00", request)
    if hours:
        # Requests mention the 09:00 origin and may mention a 10:00 release;
        # the latest stated clock time is the completion deadline.
        end_hour = max(int(hour) for hour in hours)
        if end_hour >= 9:
            return (end_hour - 9) * 3600
    within = re.search(r"within\s+(\d+)\s+hours?", request, flags=re.I)
    if within:
        return int(within.group(1)) * 3600
    return None


def _assay_summary(request: str) -> str:
    lower = request.lower()
    assays = []
    if "cfxpress" in lower or "gfp" in lower:
        assays.append("GFP")
    if "bca" in lower:
        assays.append("BCA")
    if "picogreen" in lower:
        assays.append("PG")
    return "+".join(assays) if assays else "multi-assay"


def _deadline_diagnostics() -> list[dict]:
    """Read the seven first-run deadline mismatches from raw model traces."""
    mismatches = []
    for model in MODELS:
        score_path = DATA / "heldout" / "language" / model / "scores.jsonl"
        for score in read_jsonl(score_path):
            if score.get("repeat") != 0 or score.get("decision") != "compile" or score.get("success"):
                continue
            raw_path = PAPER / str(score["raw_file"])
            raw = read_json(raw_path)["result"]
            request = str(raw.get("request", ""))
            requested = _requested_deadline_s(request)
            generated = raw.get("generated") or {}
            returned = ((generated.get("graph") or {}).get("intent") or {}).get("deadline_s")
            if requested is None or returned is None or int(returned) == requested:
                continue
            mismatches.append(
                {
                    "model": model,
                    "style": score.get("style", ""),
                    "assays": _assay_summary(request),
                    "requested_s": requested,
                    "returned_s": int(returned),
                    "request": request,
                    "source": str(raw_path),
                }
            )
    if len(mismatches) != 7:
        raise ValueError(f"Expected seven recorded deadline mismatches, found {len(mismatches)}")
    return mismatches


def _draw_deadline_diagnostics(ax, diagnostics: list[dict]):
    rows = list(reversed(diagnostics))
    y = np.arange(len(rows))
    for yi, record in zip(y, rows):
        requested_h = record["requested_s"] / 3600.0
        returned_h = record["returned_s"] / 3600.0
        color = MODEL_COLORS[record["model"]]
        ax.plot([requested_h, returned_h], [yi, yi], color=COLORS["guide"], linewidth=0.9, zorder=1)
        ax.scatter(requested_h, yi, s=22, facecolor="white", edgecolor=COLORS["ink"], linewidth=0.8, zorder=3)
        ax.scatter(returned_h, yi, s=22, facecolor=color, edgecolor="white", linewidth=0.35, zorder=4)
    labels = [
        f"{('Flash' if row['model'] == 'deepseek-flash' else 'Pro')} · {row['assays']} · {row['requested_s'] / 3600:g} h · {row['style']}"
        for row in rows
    ]
    ax.set_yticks(y, labels)
    ax.set_xlim(4.4, 8.6)
    ax.set_xticks([5, 6, 7, 8], ["5", "6", "7", "8"])
    ax.set_xlabel("Deadline after 09:00 (h)")
    ax.tick_params(length=2, pad=2)
    ax.grid(axis="x", color="#E8EAEC", linewidth=0.45)
    ax.set_axisbelow(True)
    requested_handle = ax.scatter([], [], s=22, facecolor="white", edgecolor=COLORS["ink"], linewidth=0.8, label="Requested")
    returned_handles = [ax.scatter([], [], s=22, facecolor=MODEL_COLORS[m], edgecolor="white", linewidth=0.35, label=MODEL_LABELS[m]) for m in MODELS]
    ax.legend(handles=[requested_handle, *returned_handles], frameon=False, ncol=3, loc="lower right", bbox_to_anchor=(1.0, 1.02),
              handletextpad=0.35, columnspacing=1.0)
    ax.text(0.0, -0.24, "Seven first-run compile cases with a deadline mismatch; rows are labelled by assay and requested horizon.",
            transform=ax.transAxes, fontsize=5.8, color=COLORS["muted"])
    panel(ax, "d", "Supported-request errors change the deadline")


def main() -> None:
    summary = read_json(DATA / "summary.json")
    rules = _rule_rows()
    diagnostics = _deadline_diagnostics()
    fig = plt.figure(figsize=figure_size(124), facecolor="white")
    a = fig.add_axes((0.09, 0.56, 0.48, 0.32), facecolor="white")
    b = fig.add_axes((0.59, 0.56, 0.17, 0.32), facecolor="white")
    b_cost = fig.add_axes((0.79, 0.56, 0.17, 0.32), facecolor="white")
    c = fig.add_axes((0.20, 0.14, 0.73, 0.30), facecolor="white")
    _draw_success(a, summary, rules)
    _draw_latency(b)
    _draw_tariff(b_cost)
    _draw_deadline_diagnostics(c, diagnostics)
    V3.mkdir(parents=True, exist_ok=True)
    with (V3 / "fig4_language-source.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["model", "category", "success", "n", "rate", "latency_median_s", "latency_p95_s"])
        for model in MODELS:
            groups = summary["language"][model]["groups"]
            for category in CATEGORIES:
                group = groups[category]
                writer.writerow([model, category, group["success"], group["n"], group["success"] / group["n"], summary["language"][model]["latency_s_median"], summary["language"][model]["latency_s_p95"]])
    with (V3 / "fig4_deadline-source.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["model", "style", "assay_summary", "requested_deadline_s", "returned_deadline_s", "source"])
        for record in diagnostics:
            writer.writerow([record["model"], record["style"], record["assays"], record["requested_s"], record["returned_s"], record["source"]])
    with (V3 / "fig4_cost-source.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["model", "calls", "fee_low_usd", "fee_high_usd", "basis"])
        for model in MODELS:
            low, high = TARIFF_INTERVALS[model]
            writer.writerow([model, 120, low, high, "provider list-price estimate applied to recorded call aggregate; not invoice"])
    save_figure(
        fig,
        "fig4_language",
        [a, b, b_cost, c],
        panel_ids=["success", "latency", "tariff", "errors"],
        row_groups=[["latency", "tariff"]],
        exclude_axes=[c],
        height_mm=124,
    )


if __name__ == "__main__":
    main()
