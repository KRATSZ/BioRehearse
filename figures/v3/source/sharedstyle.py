"""Shared publication style and evidence-safe helpers for BioRehearse v3.

The plotting backend is deliberately Python/matplotlib throughout the v3
package.  Quantitative panels read recorded source tables; missing prospective
benchmark outputs raise an error instead of silently drawing a placeholder.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, ListedColormap
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

PAPER = Path(__file__).resolve().parents[3]
V3 = PAPER / "figures" / "v3"
DATA = PAPER / "source-data" / "v2"
DATA_V3 = PAPER / "source-data" / "v3"
REND = V3 / "renders"
QA_TOOLS = PAPER / "reproducibility" / "figure-qa"

MM = 1.0 / 25.4
FIG_WIDTH_MM = 180.0
COL_MM = 87.0
GUTTER_MM = 6.0

COLORS = {
    "gfp": "#2A7F9E",
    "bca": "#D88A40",
    "picogreen": "#8A78B0",
    "cp_sat": "#17242E",
    "parallel_greedy": "#7A858D",
    "serial_fifo": "#C2C8CD",
    "serial_sgs": "#3C6E71",
    "pass": "#64727C",
    "warning": "#B82932",
    "neutral": "#D9DEE2",
    "guide": "#A9B3BA",
    "ink": "#17242E",
    "muted": "#5D6972",
    "paper": "#FFFFFF",
}
ASSAY_LABELS = {"gfp": "GFP", "bca": "BCA", "picogreen": "PicoGreen"}
METHOD_LABELS = {
    "cp_sat": "CP-SAT",
    "parallel_greedy": "Parallel greedy",
    "serial_fifo": "Serial FIFO",
    "serial_sgs": "Serial SGS",
}

METHOD_COLORS = {key: COLORS[key] for key in METHOD_LABELS}
ASSAY_COLORS = {key: COLORS[key] for key in ASSAY_LABELS}

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 6.5,
        "axes.labelsize": 6.5,
        "axes.titlesize": 7,
        "xtick.labelsize": 5.5,
        "ytick.labelsize": 5.5,
        "legend.fontsize": 6.0,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 0.5,
        "xtick.major.width": 0.5,
        "ytick.major.width": 0.5,
        "lines.linewidth": 0.8,
        "savefig.dpi": 400,
    }
)


def read_json(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Required evidence file is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Required evidence file is missing: {path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def require_file(path: str | Path) -> Path:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Native or quantitative evidence is not available: {path}")
    return path


def mm(value: float) -> float:
    return float(value) * MM


def figure_size(height_mm: float) -> tuple[float, float]:
    return mm(FIG_WIDTH_MM), mm(height_mm)


def panel(ax, letter: str, title: str, *, title_color: str = COLORS["ink"]) -> None:
    """Place a consistently anchored panel label and title."""
    ax.text(
        -0.085,
        1.02,
        letter,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=8,
        fontweight="bold",
        color=COLORS["ink"],
        clip_on=False,
    )
    ax.text(
        0.0,
        1.02,
        title,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=7,
        color=title_color,
        clip_on=False,
    )


def hide_axes(ax) -> None:
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_frame_on(False)


def rounded_box(ax, xy: tuple[float, float], width: float, height: float, title: str, body: str,
                *, face: str = "#F7F9FA", edge: str = "#A9B3BA", title_color: str = COLORS["ink"]):
    x, y = xy
    patch = FancyBboxPatch(
        (x, y), width, height,
        boxstyle="round,pad=0.006,rounding_size=0.012",
        facecolor=face,
        edgecolor=edge,
        linewidth=0.6,
    )
    ax.add_patch(patch)
    ax.text(x + 0.012, y + height - 0.065, title, fontsize=6.4, fontweight="bold",
            color=title_color, va="top")
    ax.text(x + 0.012, y + height - 0.25, body, fontsize=6.0, color=COLORS["muted"],
            va="top", linespacing=1.35)
    return patch


def arrow(ax, start, end, *, color: str = COLORS["muted"], lw: float = 0.8, mutation: float = 7,
          rad: float = 0.0, linestyle: str = "-"):
    patch = FancyArrowPatch(
        start, end,
        arrowstyle="-|>",
        mutation_scale=mutation,
        linewidth=lw,
        color=color,
        linestyle=linestyle,
        connectionstyle=f"arc3,rad={rad}",
        shrinkA=2,
        shrinkB=2,
    )
    ax.add_patch(patch)
    return patch


def assay_color(method: str) -> str:
    if method not in ASSAY_COLORS:
        raise KeyError(f"Unknown assay key {method!r}")
    return ASSAY_COLORS[method]


def method_color(method: str) -> str:
    if method not in METHOD_COLORS:
        raise KeyError(f"Unknown method key {method!r}")
    return METHOD_COLORS[method]


def component_cmap(color: str, low: str = "#F6F8F9") -> LinearSegmentedColormap:
    return LinearSegmentedColormap.from_list("component", [low, color], N=256)


def discrete_status_cmap() -> ListedColormap:
    return ListedColormap([COLORS["neutral"], COLORS["pass"], COLORS["warning"]])


def image_axis(fig, rect, path: str | Path, *, aspect: str = "auto", facecolor: str = "white"):
    path = require_file(path)
    ax = fig.add_axes(rect, facecolor=facecolor)
    ax.imshow(plt.imread(path), aspect=aspect)
    hide_axes(ax)
    return ax


def save_figure(
    fig,
    name: str,
    axes: Sequence,
    *,
    panel_ids: Sequence[str] | None = None,
    row_groups: Sequence[Sequence[str] | Mapping] | None = None,
    column_groups: Sequence[Sequence[str] | Mapping] | None = None,
    exclude_axes: Iterable | None = None,
    exemptions: Sequence[Mapping] | None = None,
    height_mm: float | None = None,
    require_panel_labels: bool = True,
) -> dict:
    """Run the render-time alignment gate and export editable final assets."""
    if str(QA_TOOLS) not in sys.path:
        sys.path.insert(0, str(QA_TOOLS))
    from audit_panel_alignment import require_matplotlib_panel_alignment

    fig.canvas.draw()
    if height_mm is not None:
        fig.set_size_inches(mm(FIG_WIDTH_MM), mm(height_mm), forward=True)
        fig.canvas.draw()
    all_axes = list(axes)
    excluded_ids = {id(axis) for axis in (exclude_axes or [])}
    selected_axes = [axis for axis in all_axes if id(axis) not in excluded_ids]
    if panel_ids is None:
        panel_ids = [str(index) for index in range(len(selected_axes))]
    elif len(panel_ids) == len(all_axes) and excluded_ids:
        panel_ids = [panel_id for axis, panel_id in zip(all_axes, panel_ids) if id(axis) not in excluded_ids]
    elif len(panel_ids) != len(selected_axes):
        raise ValueError("panel_ids must match the non-excluded axes")
    alignment_path = V3 / f"{name}.alignment.json"
    overlay_path = V3 / f"{name}.alignment.svg"
    report = require_matplotlib_panel_alignment(
        fig,
        axes=all_axes,
        panel_ids=list(panel_ids),
        row_groups=list(row_groups or []),
        column_groups=list(column_groups or []),
        exclude_axes=list(exclude_axes or []),
        exemptions=list(exemptions or []),
        json_out=alignment_path,
        overlay_svg=overlay_path,
        tolerance_pt=1.5,
        gutter_tolerance_pt=1.5,
        require_panel_labels=require_panel_labels,
        strict=True,
    )
    for ext in ("pdf", "svg", "png"):
        fig.savefig(V3 / f"{name}.{ext}", dpi=400, facecolor="white", edgecolor="none")
    plt.close(fig)
    return report


def normalized_well(well: str) -> tuple[int, int]:
    match = re.fullmatch(r"([A-H])(\d{1,2})", well.upper())
    if not match:
        raise ValueError(f"Expected 96-well coordinate, got {well!r}")
    return ord(match.group(1)) - ord("A"), int(match.group(2)) - 1


def plan_experiment_methods(plan: Mapping) -> dict[str, str]:
    return {str(ex["id"]): str(ex["method"]) for ex in plan["graph"]["experiments"]}


def station_names() -> tuple[list[str], list[str]]:
    resources = ["device:19", "device:18", "demo:ks4000:1", "device:67", "bench", "operator"]
    labels = ["Fluent 1080", "Fluent 780", "KS4000", "iD5", "Human bench", "Shared operator"]
    return resources, labels


def configure_axis(ax, *, xlabel: str | None = None, ylabel: str | None = None, grid: bool = False):
    if xlabel:
        ax.set_xlabel(xlabel, labelpad=2)
    if ylabel:
        ax.set_ylabel(ylabel, labelpad=2)
    ax.tick_params(length=2.5, pad=2, width=0.5)
    if grid:
        ax.grid(axis="x", color="#E8EAEC", linewidth=0.45, zorder=0)
        ax.set_axisbelow(True)
    return ax


__all__ = [
    "PAPER", "V3", "DATA", "DATA_V3", "REND", "QA_TOOLS", "COLORS", "ASSAY_LABELS",
    "METHOD_LABELS", "ASSAY_COLORS", "METHOD_COLORS", "MM", "FIG_WIDTH_MM", "COL_MM",
    "GUTTER_MM", "read_json", "read_jsonl", "require_file", "figure_size", "panel", "hide_axes",
    "rounded_box", "arrow", "assay_color", "method_color", "component_cmap", "image_axis",
    "save_figure", "normalized_well", "plan_experiment_methods", "station_names", "configure_axis",
]
