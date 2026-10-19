"""Figure 3: one three-assay workload linked across schedule and state."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, ConnectionPatch, FancyArrowPatch, Rectangle

import matplotlib

matplotlib.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 6.5, "xtick.labelsize": 5.6, "ytick.labelsize": 5.6,
    "svg.fonttype": "none", "pdf.fonttype": 42, "savefig.dpi": 400,
})
# The shared save_figure helper invokes require_matplotlib_panel_alignment(...) after the final draw.
# Final editable exports: fig.savefig("figure.svg"), fig.savefig("figure.pdf"), fig.savefig("figure.png", dpi=400).

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sharedstyle import (  # noqa: E402
    ASSAY_COLORS,
    ASSAY_LABELS,
    COLORS,
    DATA,
    REND,
    V3,
    configure_axis,
    figure_size,
    hide_axes,
    normalized_well,
    panel,
    plan_experiment_methods,
    read_json,
    require_file,
    component_cmap,
    save_figure,
)


def _frame_paths() -> list[Path]:
    paths = []
    for i in range(1, 5):
        candidates = [
            REND / f"rehearsal-frame-{i:02d}.png",
            REND / "final-workbench" / "white" / f"rehearsal-{i}.png",
            REND / "final-workbench" / "transparent" / f"rehearsal-{i}.png",
        ]
        paths.append(next((candidate for candidate in candidates if candidate.exists()), candidates[0]))
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError(f"v3 rehearsal frame renders are missing: {missing}")
    return paths


def _closeup_paths() -> list[Path]:
    paths = []
    for i in range(1, 5):
        candidates = [
            REND / f"rehearsal-frame-{i:02d}-closeup.png",
            REND / "final-workbench" / "white" / f"rehearsal-{i}-closeup.png",
            REND / "final-workbench" / "transparent" / f"rehearsal-{i}-closeup.png",
        ]
        paths.append(next((candidate for candidate in candidates if candidate.exists()), candidates[0]))
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError(f"v3 rehearsal close-up renders are missing: {missing}")
    return paths


def _gantt(ax, plan: dict, frame_times: list[float]):
    resources = ["device:19", "device:18", "demo:ks4000:1", "device:67", "bench", "operator"]
    labels = ["Fluent 1080", "Fluent 780", "KS4000", "iD5", "Human bench", "Operator"]
    methods = plan_experiment_methods(plan)
    ax.set_xlim(0, plan["makespan_s"] / 3600.0)
    ax.set_ylim(-0.6, len(resources) - 0.35)
    ax.set_yticks(range(len(resources)), labels)
    ax.invert_yaxis()
    ax.set_xlabel("Time after 09:00 (h)", labelpad=2)
    configure_axis(ax, grid=True)
    panel(ax, "a", "A shared-device schedule coordinates three assays")
    for row in plan["rows"]:
        if row.get("kind") not in {"operation", "transfer"} or row.get("resource") not in resources:
            continue
        y = resources.index(row["resource"])
        is_transfer = row.get("kind") == "transfer"
        x0 = row["start_s"] / 3600.0
        width = (row["end_s"] - row["start_s"]) / 3600.0
        color = ASSAY_COLORS[methods[row["experiment"]]]
        y0, height = y - 0.27, 0.54
        # Matplotlib's hatch pattern is emitted as a page-sized clipping
        # pattern in PDF.  That is visually harmless but makes a geometry
        # collision audit report the pattern as crossing every tick label.
        # Draw the finite diagonal transfer strokes explicitly instead; the
        # assay colour remains the fill and the slash pattern is still visible
        # at final size without leaking beyond the transfer bar.
        bar = Rectangle(
            (x0, y0), width, height,
            facecolor=color,
            edgecolor="white",
            linewidth=0.25,
            alpha=0.78 if is_transfer else 1.0,
            zorder=2,
        )
        ax.add_patch(bar)
        if is_transfer and width > 0:
            diagonal = max(width * 0.34, 1e-5)
            for offset in np.arange(-diagonal, width + diagonal, diagonal * 1.25):
                t0 = max(0.0, -offset / diagonal)
                t1 = min(1.0, (width - offset) / diagonal)
                if t1 <= t0:
                    continue
                ax.add_line(
                    Line2D(
                        [x0 + offset + diagonal * t0, x0 + offset + diagonal * t1],
                        [y0 + height * t0, y0 + height * t1],
                        color=COLORS["ink"], linewidth=0.42, alpha=0.55,
                        solid_capstyle="butt", zorder=3,
                    )
                )
    for i, time_s in enumerate(frame_times):
        x = time_s / 3600.0
        ax.axvline(x, color="#59656D", lw=0.55, ls=(0, (2, 2)), zorder=1)
        # The phase titles in panel b identify these marked times; leaving the
        # schedule marker unlabelled keeps the vertical guide unobstructed.
    ax.set_xlim(left=0)


def _filmstrip(fig, frame_paths: list[Path], closeup_paths: list[Path], frame_data: list[dict], provenance: dict):
    axes = []
    phase_titles = {
        "E3:assemble": "GFP assembly",
        "E2:read": "PicoGreen read",
        "E3:prepare_plate": "GFP dilution",
        "E1:read": "BCA read",
    }
    state_records = {int(record.get("frame", index + 1)): record for index, record in enumerate(provenance.get("state_records", []))}
    # The four images share an equal row, but their frame-specific active
    # borders make the temporal changes readable at final size.
    for i, (path, closeup, frame) in enumerate(zip(frame_paths, closeup_paths, frame_data)):
        x = 0.035 + i * 0.238
        ax = fig.add_axes((x, 0.46, 0.216, 0.205), facecolor="white")
        ax.imshow(plt.imread(path), aspect="auto")
        ax.set_axis_off()
        record = state_records.get(i + 1, {})
        active_point = None
        for glyph in record.get("glyphs", []):
            projection = glyph.get("projection_normalized_xy")
            if not projection or len(projection) != 2:
                continue
            assay = str(glyph.get("assay", "")).lower()
            color = ASSAY_COLORS.get(assay, COLORS["muted"])
            point = (float(projection[0]), 1.0 - float(projection[1]))
            if active_point is None:
                active_point = point
            ax.add_patch(Circle(point, 0.028, transform=ax.transAxes, facecolor=color,
                                 edgecolor=color, linewidth=0.75, alpha=0.14, zorder=5))
            ax.add_patch(Circle(point, 0.028, transform=ax.transAxes, fill=False,
                                 edgecolor=color, linewidth=0.8, alpha=0.95, zorder=6))
        phase = phase_titles.get(str(frame.get("task", "")), str(frame.get("task", "")).replace("_", " "))
        ax.text(0.02, 0.985, f"{phase}\n{frame['time_s'] / 60:.1f} min", transform=ax.transAxes,
                ha="left", va="top", fontsize=5.8, color=COLORS["ink"], fontweight="bold",
                bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.0}, zorder=8)
        # Each wide frame carries the corresponding native close-up as a
        # small inset.  The inset is an evidence view, not an additional panel,
        # and therefore is intentionally excluded from the alignment audit.
        inset = fig.add_axes((x + 0.128, 0.478, 0.078, 0.078), facecolor="white")
        inset.imshow(plt.imread(closeup), aspect="equal")
        inset.set_axis_off()
        inset.set_frame_on(True)
        inset.patch.set_facecolor("white")
        inset.patch.set_edgecolor(COLORS["ink"])
        inset.patch.set_linewidth(0.8)
        for spine in inset.spines.values():
            spine.set_visible(True)
            spine.set_color(COLORS["ink"])
            spine.set_linewidth(0.8)
        if active_point is not None:
            # The connector ties each native close-up to the active carrier
            # circle in the corresponding frame without baking annotations
            # into the renderer output.
            connector = ConnectionPatch(
                xyA=(0.5, 0.5), coordsA=inset.transAxes,
                xyB=active_point, coordsB=ax.transAxes,
                arrowstyle="-", linewidth=0.55, color=COLORS["muted"], alpha=0.8,
                zorder=7,
            )
            fig.add_artist(connector)
        axes.append(ax)
    fig.text(0.035, 0.715, "b", fontsize=8, weight="bold", color=COLORS["ink"])
    fig.text(0.065, 0.715, "State-linked 3D replay at the marked schedule times", fontsize=7, color=COLORS["ink"])
    fig.text(0.065, 0.442, "Circles mark recorded active carriers; insets zoom the working deck or handoff.", fontsize=5.8, color=COLORS["muted"])
    return axes


def _plate_matrix(plan: dict, state: dict, experiment_id: str, field: str):
    matrix = np.full((8, 12), np.nan, dtype=float)
    for well in plan["graph"]["plate_map"]:
        if str(well["experiment"]) != experiment_id:
            continue
        container = state["containers"].get(well["container"], {})
        r, c = normalized_well(well["well"])
        if field == "volume":
            matrix[r, c] = float(container.get("volume_ul", 0.0))
        else:
            components = container.get("components_ul", {}) or {}
            total = sum(float(v) for v in components.values())
            matrix[r, c] = max(components.values()) / total if components and total > 0 else np.nan
    return matrix


def _component_category(component_id: str) -> str:
    suffix = str(component_id).split(":", 1)[-1].lower()
    if suffix == "water":
        return "water"
    if suffix in {"wr", "mix"}:
        return "reagent"
    if suffix.startswith("std"):
        return "standards"
    if suffix.startswith("sample"):
        return "samples"
    if suffix == "dna":
        return "DNA"
    return "other"


def _component_totals(plan: dict, final_state: dict) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, float]] = {}
    for experiment in plan["graph"]["experiments"]:
        experiment_id = str(experiment["id"])
        grouped: dict[str, float] = {}
        for well in plan["graph"]["plate_map"]:
            if str(well["experiment"]) != experiment_id:
                continue
            container = final_state["containers"].get(well["container"], {})
            for component, amount in (container.get("components_ul", {}) or {}).items():
                category = _component_category(component)
                grouped[category] = grouped.get(category, 0.0) + float(amount)
        totals[experiment_id] = grouped
    return totals


def _heatmaps(fig, plan: dict, final_state: dict):
    methods = plan_experiment_methods(plan)
    experiments = list(plan["graph"]["experiments"])
    axes = []
    # One row of absolute volume heatmaps, followed by a compact component
    # composition strip. This keeps the plate geometry readable while
    # retaining the liquid-ledger composition in a quantitative panel.
    left = [0.035, 0.245, 0.455]
    # Volume is a quantitative state variable shared across assays.  Keep its
    # encoding assay-independent so the three plates can be compared directly;
    # assay colours are reserved for titles and component-composition panels.
    volume_matrices = {
        str(experiment["id"]): _plate_matrix(plan, final_state, str(experiment["id"]), "volume")
        for experiment in experiments
    }
    finite_volumes = [matrix[np.isfinite(matrix)] for matrix in volume_matrices.values()]
    vmax = max(225.0, *(float(values.max()) for values in finite_volumes if values.size))
    volume_cmap = component_cmap("#526876")
    for col, experiment in enumerate(experiments):
        method = methods[str(experiment["id"])]
        x = left[col]
        ax_vol = fig.add_axes((x, 0.255, 0.155, 0.125), facecolor="white")
        vol = volume_matrices[str(experiment["id"])]
        im_vol = ax_vol.imshow(vol, vmin=0, vmax=vmax, cmap=volume_cmap, aspect="equal")
        ax_vol.set_xticks([0, 5, 11], ["1", "6", "12"])
        ax_vol.set_yticks([0, 3, 7], ["A", "D", "H"])
        ax_vol.tick_params(length=1.5, pad=1)
        ax_vol.set_title(f"{ASSAY_LABELS[method]} · volume (µl)", fontsize=6.0, color=ASSAY_COLORS[method], pad=2)
        axes.append(ax_vol)
        # Dedicated narrow volume colorbars, excluded from comparable axes.
        cb1 = fig.add_axes((x + 0.158, 0.255, 0.010, 0.125))
        cbar1 = fig.colorbar(im_vol, cax=cb1)
        cbar1.ax.tick_params(labelsize=5.6, length=1.5, pad=1)
    component_axis = fig.add_axes((0.055, 0.105, 0.61, 0.080), facecolor="white")
    totals = _component_totals(plan, final_state)
    component_colors = {
        "reagent": "#526876", "samples": "#8AA1AC", "standards": "#C4D0D5",
        "water": "#6EA7C5", "DNA": "#A49BBE", "other": "#D9DEE2",
    }
    categories = ["reagent", "samples", "standards", "water", "DNA", "other"]
    for index, experiment in enumerate(experiments):
        experiment_id = str(experiment["id"])
        grouped = totals[experiment_id]
        total = sum(grouped.values())
        bottom = 0.0
        for category in categories:
            amount = grouped.get(category, 0.0)
            if total <= 0 or amount <= 0:
                continue
            height = 100.0 * amount / total
            component_axis.bar(index, height, bottom=bottom, width=0.48,
                               color=component_colors[category], edgecolor="white", linewidth=0.25,
                               label=category)
            if height >= 10:
                component_axis.text(index, bottom + height / 2.0, f"{height:.0f}%", ha="center", va="center",
                                    fontsize=5.6, color="white" if category == "reagent" else COLORS["ink"])
            bottom += height
    component_axis.set_ylim(0, 100)
    component_axis.set_xlim(-0.6, len(experiments) - 0.4)
    component_axis.set_xticks(range(len(experiments)), [ASSAY_LABELS[methods[str(e["id"])] ] for e in experiments])
    component_axis.set_ylabel("final volume (%)", fontsize=5.8, labelpad=1)
    component_axis.set_title("Ledger composition by assay", fontsize=6.0, color=COLORS["ink"], pad=2, loc="left")
    component_axis.tick_params(length=1.5, pad=1)
    handles, labels = component_axis.get_legend_handles_labels()
    unique = dict(zip(labels, handles))
    component_axis.legend(unique.values(), unique.keys(), loc="upper left", bbox_to_anchor=(0.34, 1.65),
                          ncol=3, frameon=False, fontsize=5.6, handlelength=0.9, columnspacing=1.0)
    axes.append(component_axis)
    fig.text(0.035, 0.405, "c", fontsize=8, weight="bold", color=COLORS["ink"])
    fig.text(0.065, 0.405, "Liquid-ledger state at the final recorded milestone", fontsize=7, color=COLORS["ink"])
    fig.text(0.065, 0.078, "Top: volume per well on a shared scale. Bottom: recorded component composition; white cells are unallocated.", fontsize=6.0, color=COLORS["muted"])
    return axes


def _routes(fig, plan: dict):
    catalog = read_json(DATA / "catalog.json")
    positions = catalog["layouts"][plan["layout"]]["positions"]
    ax = fig.add_axes((0.72, 0.105, 0.245, 0.27), facecolor="white")
    panel(ax, "d", "Configured transfer routes")
    keys = ["bench", "device:19", "device:18", "device:67", "demo:ks4000:1"]
    labels = ["Bench", "Fluent 1080", "Fluent 780", "iD5", "KS4000"]
    for i, (key, label) in enumerate(zip(keys, labels)):
        x, y = positions[key]
        ax.scatter([x], [y], s=36, facecolor="#F4F7F8", edgecolor="#66737D", linewidth=0.55, zorder=3)
        ax.annotate(
            label,
            (x, y),
            xytext=(0, -11 if i in (0, 1) else 8),
            textcoords="offset points",
            ha="center",
            fontsize=6.0,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.8},
            zorder=5,
        )
    methods = plan_experiment_methods(plan)
    seen = set()
    for route_index, row in enumerate(plan["rows"]):
        if row.get("kind") != "transfer" or row.get("source") not in positions or row.get("destination") not in positions:
            continue
        source, destination = row["source"], row["destination"]
        key = (source, destination, methods.get(row["experiment"], "gfp"))
        if key in seen:
            continue
        seen.add(key)
        a, b = positions[source], positions[destination]
        color = ASSAY_COLORS[methods.get(row["experiment"], "gfp")]
        # Scheduler transport times use the configured Manhattan distance.
        # Draw the same L-shaped path so the visual route does not suggest a
        # shorter Euclidean transfer than the measured model.
        via = (b[0], a[1])
        ax.plot([a[0], via[0], b[0]], [a[1], via[1], b[1]], color=color, lw=0.65, alpha=0.72, zorder=1)
        if via != b:
            ax.add_patch(FancyArrowPatch(via, b, arrowstyle="-|>", mutation_scale=5, lw=0.65, color=color, alpha=0.78, zorder=2))
        else:
            ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=5, lw=0.65, color=color, alpha=0.78, zorder=2))
    ax.set_xlim(-0.8, 6.2)
    ax.set_ylim(-0.8, 4.2)
    ax.set_aspect("equal")
    ax.set_xlabel("configured x (m); Manhattan routes", labelpad=2)
    ax.set_ylabel("y (m)", labelpad=2)
    ax.tick_params(length=2, pad=1)
    return ax


def main() -> None:
    example = read_json(DATA / "example.json")
    plan = example["plan"]
    frame_data = example["frames"]
    frame_paths = _frame_paths()
    closeup_paths = _closeup_paths()
    provenance = read_json(REND / "final-workbench" / "unified-scene-provenance.json")
    fig = plt.figure(figsize=figure_size(172), facecolor="white")
    frame_times = [float(frame["time_s"]) for frame in frame_data]
    a = fig.add_axes((0.10, 0.77, 0.86, 0.15), facecolor="white")
    _gantt(a, plan, frame_times)
    films = _filmstrip(fig, frame_paths, closeup_paths, frame_data, provenance)
    heatmaps = _heatmaps(fig, plan, frame_data[-1]["state"])
    routes = _routes(fig, plan)

    # Export the numerical state matrices used by panel c.
    V3.mkdir(parents=True, exist_ok=True)
    with (V3 / "fig3_state-source.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["experiment", "assay", "well", "volume_ul", "dominant_component_category", "dominant_component_fraction", "frame_time_s"])
        methods = plan_experiment_methods(plan)
        final_state = frame_data[-1]["state"]
        for experiment in plan["graph"]["experiments"]:
            ex = str(experiment["id"])
            method = methods[ex]
            for well in plan["graph"]["plate_map"]:
                if str(well["experiment"]) != ex:
                    continue
                container = final_state["containers"].get(well["container"], {})
                comps = container.get("components_ul", {}) or {}
                total = sum(float(v) for v in comps.values())
                dominant_component = max(comps, key=comps.get) if comps and total > 0 else ""
                dominant_category = _component_category(dominant_component) if dominant_component else ""
                dominant = max(comps.values()) / total if comps and total > 0 else ""
                writer.writerow([ex, ASSAY_LABELS[method], well["well"], container.get("volume_ul", ""), dominant_category, dominant, frame_data[-1]["time_s"]])

    # Export the exact grouped totals behind the component-composition strip.
    component_totals = _component_totals(plan, final_state)
    with (V3 / "fig3_component-source.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["experiment", "assay", "component_category", "volume_ul"])
        for experiment in plan["graph"]["experiments"]:
            ex = str(experiment["id"])
            method = methods[ex]
            for category, amount in sorted(component_totals[ex].items()):
                writer.writerow([ex, ASSAY_LABELS[method], category, amount])

    save_figure(
        fig,
        "fig3_rehearsal",
        [a, *films, *heatmaps, routes],
        panel_ids=["gantt", *[f"frame{i}" for i in range(4)], *[f"heat{i}" for i in range(3)], "components", "routes"],
        row_groups=[[f"frame{i}" for i in range(4)], [f"heat{i}" for i in range(3)]],
        exclude_axes=[routes],
        exemptions=[
            {"panels": [f"frame{i}" for i in range(4)], "checks": ["panel-label"], "reason": "Filmstrip frames are time-indexed and carry frame labels rather than independent panel letters."},
            {"panels": [f"heat{i}" for i in range(3)] + ["components"], "checks": ["panel-label"], "reason": "Volume heatmaps and the component strip are sub-panels of panel c; the shared c label is placed above the block."},
        ],
        require_panel_labels=False,
        height_mm=172,
    )


if __name__ == "__main__":
    main()
