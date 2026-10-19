"""Figure 1: from language goal to an executable, checked rehearsal.

The five upper cards are the only comparable panel group.  The hero render and
the validation ladder are intentionally separate evidence modules and are
excluded from the equal-grid alignment group with explicit reasons.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, FancyArrowPatch, Rectangle

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
    ASSAY_COLORS,
    COLORS,
    DATA,
    REND,
    V3,
    arrow,
    figure_size,
    panel,
    read_json,
    require_file,
    rounded_box,
    save_figure,
)


def _hero_path() -> Path:
    candidates = [
        REND / "unified-scene-hero.png",
        REND / "final-workbench" / "white" / "rehearsal-1.png",
        REND / "final-workbench" / "transparent" / "rehearsal-1.png",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No evaluated workbench hero render found: {candidates}")


def _draw_intent(ax):
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    panel(ax, "a", "Natural-language goal")
    rounded_box(
        ax,
        (0.05, 0.18),
        0.90,
        0.58,
        "3 assays · 1 window",
        "GFP + BCA + PicoGreen\nshared instruments\n8 h deadline",
        face="#F7FAFB",
    )
    ax.text(0.10, 0.10, "throughput · deadline · budget", fontsize=5.5, color=COLORS["muted"])


def _draw_typed(ax):
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    panel(ax, "b", "Typed intent")
    rounded_box(ax, (0.04, 0.12), 0.92, 0.68, "", "", face="#F8FAFC")
    # Keep the heading clear of the rounded-box stroke at final size.
    ax.text(0.10, 0.64, "registered request", fontsize=6.4, fontweight="bold", color=COLORS["ink"])
    rows = [
        ("assays", "GFP+BCA+PG"),
        ("replicates", "1–2"),
        ("deadline", "8 h"),
        ("mode", "replay"),
    ]
    for i, (key, value) in enumerate(rows):
        y = 0.54 - i * 0.11
        ax.text(0.10, y, key, fontsize=5.5, family="DejaVu Sans Mono", color=COLORS["muted"])
        ax.text(0.52, y, value, fontsize=5.5, family="DejaVu Sans Mono", color=COLORS["ink"])
    ax.add_patch(Rectangle((0.08, 0.18), 0.84, 0.56, fill=False, lw=0.45, ec="#B8C1C7"))


def _draw_dag(ax, plan: dict):
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    panel(ax, "c", "Method task graph")
    graph = plan["graph"]
    experiments = graph["experiments"]
    tasks = graph["tasks"]
    by_exp = {str(ex["id"]): str(ex["method"]) for ex in experiments}
    exp_ids = [str(ex["id"]) for ex in experiments]
    # Keep a deterministic compact subset while retaining all three assay chains.
    selected = [t for t in tasks if t.get("experiment") in exp_ids]
    chains = {}
    for ex in exp_ids:
        chain = [t for t in selected if t.get("experiment") == ex]
        if len(chain) > 4:
            keep = np.linspace(0, len(chain) - 1, 4, dtype=int)
            chain = [chain[index] for index in sorted(set(keep))]
        chains[ex] = chain
    coords = {}
    short_labels = {"gfp": "GFP", "bca": "BCA", "picogreen": "PG"}
    for row, ex in enumerate(exp_ids):
        chain = chains[ex]
        color = ASSAY_COLORS[by_exp[ex]]
        for col, task in enumerate(chain):
            x = 0.25 + 0.33 * (col / max(len(chain) - 1, 1))
            y = 0.72 - row * 0.24
            coords[task["id"]] = (x, y)
            ax.add_patch(Circle((x, y), 0.030, facecolor=color, edgecolor="white", lw=0.5))
        ax.text(0.04, 0.72 - row * 0.24, short_labels.get(by_exp[ex], by_exp[ex].upper()), fontsize=5.5, color=color, va="center")
        for left, right in zip(chain, chain[1:]):
            arrow(ax, coords[left["id"]], coords[right["id"]], color="#9BA6AD", lw=0.45, mutation=5)
    ax.text(0.12, 0.08, "registered stages\n+ dependencies", fontsize=5.5, color=COLORS["muted"], linespacing=1.1)


def _draw_gantt(ax, plan: dict):
    ax.set_xlim(0, plan["makespan_s"] / 3600.0)
    resources = ["device:19", "device:18", "demo:ks4000:1", "device:67", "bench", "operator"]
    labels = ["F1080", "F780", "KS4000", "iD5", "Bench", "Operator"]
    ax.set_ylim(-0.6, len(resources) - 0.35)
    ax.set_yticks(range(len(resources)), labels)
    ax.invert_yaxis()
    ax.set_xlabel("Time after 09:00 (h)", labelpad=2)
    ax.tick_params(length=2.2, pad=1.5)
    ax.grid(axis="x", color="#E8EAEC", lw=0.45)
    ax.set_axisbelow(True)
    panel(ax, "d", "Shared schedule")
    methods = {str(ex["id"]): str(ex["method"]) for ex in plan["graph"]["experiments"]}
    for row in plan["rows"]:
        if row.get("resource") not in resources:
            continue
        y = resources.index(row["resource"])
        start_h = row["start_s"] / 3600.0
        width_h = (row["end_s"] - row["start_s"]) / 3600.0
        color = ASSAY_COLORS[methods[row["experiment"]]]
        if row.get("kind") == "operation":
            ax.broken_barh(
                [(start_h, width_h)], (y - 0.27, 0.54),
                facecolor=color, edgecolor="white", lw=0.25,
            )
        elif row.get("kind") == "transfer":
            # Transfers are explicit operator reservations in the plan;
            # lighter bars with finite diagonal marks distinguish them from
            # device operations without relying on a page-wide hatch fill.
            ax.broken_barh(
                [(start_h, width_h)], (y - 0.22, 0.44),
                facecolor=color, edgecolor=color, alpha=0.30, lw=0.35,
            )
            for offset in np.linspace(0.02, max(width_h - 0.02, 0.02), 3):
                ax.plot([start_h + offset, start_h + offset + 0.012], [y - 0.19, y + 0.16], color=color, lw=0.35, clip_on=True)
    ax.set_xlim(left=0)


def _draw_rehearsal(ax):
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    panel(ax, "e", "3D state rehearsal")
    ax.text(0.08, 0.65, "asset poses", fontsize=6.0, weight="bold", color=COLORS["ink"])
    ax.text(0.08, 0.49, "carrier locations", fontsize=5.8, color=COLORS["muted"])
    ax.text(0.08, 0.34, "liquid ledger", fontsize=5.8, color=COLORS["muted"])
    ax.add_patch(Circle((0.78, 0.52), 0.18, facecolor="#EDF2F4", edgecolor="#A9B3BA", lw=0.6))
    for angle, color in zip((0.0, 2.1, 4.2), ASSAY_COLORS.values()):
        ax.add_patch(Circle((0.78 + 0.12 * __import__("math").cos(angle), 0.52 + 0.12 * __import__("math").sin(angle)), 0.035, facecolor=color, edgecolor="white", lw=0.4))
    ax.text(0.78, 0.10, "pre-execution", ha="center", fontsize=6.0, color=COLORS["muted"])


def _draw_hero(fig, plan):
    # The native workbench render is a 1.6:1 image.  Give it a matching
    # figure slot so the instrument and bench geometry remain undistorted.
    ax = fig.add_axes((0.17, 0.285, 0.66, 0.38), facecolor="white")
    ax.imshow(plt.imread(_hero_path()), aspect="equal")
    ax.axis("off")
    panel(ax, "f", "Evaluated assay configuration")
    return ax


def _draw_checks(fig):
    ax = fig.add_axes((0.035, 0.04, 0.93, 0.18), facecolor="white")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    # The checks span nearly the full page width, so place the letter inside
    # the left margin rather than allowing the standard outside anchor to clip.
    ax.text(0.0, 1.02, "g", transform=ax.transAxes, ha="left", va="bottom",
            fontsize=8, fontweight="bold", color=COLORS["ink"], clip_on=False)
    ax.text(0.03, 1.02, "Layered pre-execution checks", transform=ax.transAxes,
            ha="left", va="bottom", fontsize=7, color=COLORS["ink"], clip_on=False)
    checks = [
        ("Intent", "target, assay and limits", ASSAY_COLORS["gfp"]),
        ("Schedule", "devices + operator\nwindows", COLORS["ink"]),
        ("Mass balance", "volumes and components", COLORS["pass"]),
        ("Material location", "stock at the required site", COLORS["warning"]),
        ("Asset contract", "open · load · close order", COLORS["serial_sgs"] if "serial_sgs" in COLORS else COLORS["muted"]),
    ]
    for i, (title, body, color) in enumerate(checks):
        x = i * 0.2 + 0.005
        ax.add_patch(Rectangle((x, 0.20), 0.18, 0.62, facecolor="#F7F9FA", edgecolor="#B8C1C7", lw=0.5))
        ax.add_patch(Rectangle((x, 0.20), 0.012, 0.62, facecolor=color, edgecolor="none"))
        ax.text(x + 0.026, 0.66, title, fontsize=6.0, weight="bold", color=COLORS["ink"])
        ax.text(x + 0.026, 0.47, body, fontsize=6.0, color=COLORS["muted"], va="top", wrap=True)
    return ax


def main() -> None:
    example = read_json(DATA / "example.json")
    plan = example["plan"]
    fig = plt.figure(figsize=figure_size(158), facecolor="white")
    # Five equal-width cards form one auditable comparable row.
    cards = []
    x0, gap, width = 0.035, 0.012, (0.93 - 4 * 0.012) / 5
    drawers = [_draw_intent, _draw_typed, lambda ax: _draw_dag(ax, plan), lambda ax: _draw_gantt(ax, plan), _draw_rehearsal]
    for i, drawer in enumerate(drawers):
        ax = fig.add_axes((x0 + i * (width + gap), 0.73, width, 0.19), facecolor="white")
        drawer(ax)
        cards.append(ax)
    # A small figure-coordinate arrow makes the intended compilation flow
    # explicit without changing the equal-width card geometry.
    for i in range(4):
        x_start = x0 + (i + 1) * width + i * gap + 0.002
        x_end = x_start + gap - 0.004
        fig.add_artist(FancyArrowPatch(
            (x_start, 0.825), (x_end, 0.825), transform=fig.transFigure,
            arrowstyle="-|>", mutation_scale=7, lw=0.65, color=COLORS["muted"],
        ))
    hero = _draw_hero(fig, plan)
    checks = _draw_checks(fig)
    save_figure(
        fig,
        "fig1_system",
        cards,
        panel_ids=[f"card{i}" for i in range(5)],
        row_groups=[[f"card{i}" for i in range(5)]],
        exclude_axes=[hero, checks],
        exemptions=[
            {"panels": ["card0", "card1", "card2", "card3", "card4"], "checks": ["panel-width"], "reason": "Equal-width intent-to-rehearsal cards are visually encoded as a single flow row; each card has the same measured width."}
        ],
        height_mm=158,
    )
    for suffix in ("pdf", "svg", "png"):
        shutil.copy2(V3 / f"fig1_system.{suffix}", V3 / f"fig1_concept.{suffix}")
    for suffix in ("json", "svg"):
        shutil.copy2(V3 / f"fig1_system.alignment.{suffix}", V3 / f"fig1_concept.alignment.{suffix}")


if __name__ == "__main__":
    main()
