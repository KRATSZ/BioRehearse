"""Figure 2: a facility-bound digital asset library."""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

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
    REND,
    V3,
    configure_axis,
    figure_size,
    hide_axes,
    image_axis,
    panel,
    read_json,
    require_file,
    save_figure,
)


DISPLAY_NAMES = [
    "Fluent 1080", "Fluent 780", "AssayMAP Bravo", "Opentrons Flex", "SpectraMax iD5", "SpectraMax i3x",
    "CLARIOstar Plus", "iBright FL1500", "KS4000", "LogPhase 600", "CellXpert C170i", "ambr 15",
    "AKTA pure 25M1", "1290 Infinity II", "RapidFire 400 / 6470", "ZenoTOF 7600", "LSRFortessa",
    "CytoFLEX LX", "DNBSEQ G99RS", "Helios", "Optima XE100", "Optima XPN100", "Sorvall LYNX6000", "Eppendorf 5910Ri",
]

SHORT_LABELS = {
    "agilent_bravo_assaymap": "AssayMAP Bravo",
    "opentrons_flex_project": "Opentrons Flex",
    "spectramax-i3x": "SpectraMax i3X",
    "thermo_ibrightfl1500": "iBright FL1500",
    "ika_ks4000": "KS 4000 i control",
    "cytiva_akta_pure_25m1": "AKTA pure",
    "agilent-rapidfire400-6470": "RapidFire 400/6470",
    "sciex_zenotof_7600": "ZenoTOF 7600",
    "bd_lsrfortessa": "LSRFortessa",
    "mgi_dnbseq_g99rs": "DNBSEQ-G99RS",
    "thermo_sorvall_lynx6000": "Sorvall LYNX 6000",
}


def _manifest():
    for candidate in (
        REND / "final-gallery" / "asset-gallery-provenance.json",
        REND / "gallery-provenance.json",
        V3 / "gallery-provenance.json",
    ):
        if candidate.exists():
            manifest = read_json(candidate)
            # Keep the renderer's relative image paths traceable while
            # resolving them from the manifest directory.  This private key is
            # only used by the source script and is not written to the public
            # provenance JSON.
            manifest["_base_dir"] = str(candidate.parent)
            return manifest
    raise FileNotFoundError("final-gallery/asset-gallery-provenance.json is required before Fig. 2 export")


def _record_image(manifest: dict, record: dict) -> Path:
    raw = record.get("image") or record.get("path")
    if not raw:
        raise ValueError("Gallery provenance record has no image path")
    candidates = [Path(manifest.get("_base_dir", "")) / raw, REND / raw, V3 / raw, Path(raw)]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Gallery render is missing: {raw}")


def _draw_gallery(fig, manifest):
    records = manifest.get("images", [])
    if len(records) < 24:
        raise ValueError(f"Fig. 2 requires at least 24 native gallery assets, found {len(records)}")
    records = records[:24]
    axes = []
    # A six-column contact sheet keeps 24 native renders readable at full
    # figure width.  The source renders all have a common 4:3 canvas, but
    # aspect='equal' is retained so a future asset cannot be geometrically
    # stretched silently.
    group_abbrev = {
        "Liquid handling": "liquid handling",
        "Optical detection": "optical detection",
        "Incubation and culture": "incubation/culture",
        "Chromatography and mass spectrometry": "chromatography/mass spec",
        "Cytometry and sequencing": "cytometry/sequencing",
        "Centrifugation": "centrifugation",
    }
    for i, record in enumerate(records):
        row, col = divmod(i, 6)
        x = 0.035 + col * 0.155
        image_w, image_h = 0.145, 0.086
        y_top = 0.895 - row * 0.108
        ax = fig.add_axes((x, y_top - image_h, image_w, image_h), facecolor="white")
        ax.imshow(plt.imread(_record_image(manifest, record)), aspect="equal")
        hide_axes(ax)
        label = SHORT_LABELS.get(str(record.get("asset_id", "")), str(record.get("display_name", record.get("asset_id", i))))
        label = re.sub(r"[^\x00-\x7F]+", " ", label).replace("/", "/").strip()
        if len(label) > 24:
            # Keep all labels descriptive without a truncation ellipsis.  The
            # source manifest remains the authoritative full display name.
            label = label[:24].rstrip()
        group = group_abbrev.get(str(record.get("group", "")), str(record.get("group", "")))
        ax.text(0.5, -0.045, label, transform=ax.transAxes, ha="center", va="top", fontsize=5.5, color=COLORS["ink"])
        ax.text(0.5, -0.19, group, transform=ax.transAxes, ha="center", va="top", fontsize=5.5, color=COLORS["muted"])
        axes.append(ax)
    fig.text(0.035, 0.985, "a", fontsize=8, weight="bold", color=COLORS["ink"])
    fig.text(0.065, 0.985, "Representative assets from the registered instrument library", fontsize=7, color=COLORS["ink"])
    fig.text(0.965, 0.985, "thumbnail geometry not to scale", fontsize=6.0, ha="right", color=COLORS["muted"])
    return axes


def _draw_anatomy(fig):
    candidates = [
        REND / "final-anatomy" / "white" / "fluent-anatomy.png",
        REND / "final-anatomy" / "transparent" / "fluent-anatomy.png",
        REND / "fluent-anatomy.png",
    ]
    path = next((candidate for candidate in candidates if candidate.exists()), None)
    if path is None:
        raise FileNotFoundError(f"Fluent anatomy render is missing: {candidates}")
    ax = image_axis(fig, (0.035, 0.26, 0.42, 0.18), path, aspect="equal")
    panel(ax, "b", "Fluent 1080 asset anatomy")
    provenance = None
    for p in (
        REND / "final-anatomy" / "anatomy-provenance.json",
        REND / "anatomy-provenance.json",
        V3 / "anatomy-provenance.json",
    ):
        if p.exists():
            provenance = read_json(p)
            break
    if provenance and provenance.get("landmarks"):
        for text, key, tx in [
            ("FCA nozzle", "FCA", (0.05, 0.78)),
            ("MCA96 head", "MCA96", (0.70, 0.82)),
            ("deck reference", "Deck", (0.06, 0.12)),
            ("plate site", "Plate sites", (0.76, 0.15)),
        ]:
            point = provenance["landmarks"].get(key, {}).get("xy")
            if point is not None:
                ax.annotate(text, xy=(point[0], 1 - point[1]), xycoords="axes fraction", xytext=tx,
                            textcoords="axes fraction", fontsize=6.0, color=COLORS["ink"],
                            arrowprops={"arrowstyle": "-", "lw": 0.5, "color": COLORS["muted"]},
                            bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.0})
    return ax


def _draw_feature_coverage(fig):
    summary = read_json(DATA / "asset-summary.json")
    ax = fig.add_axes((0.505, 0.26, 0.215, 0.18), facecolor="white")
    features = [
        ("Joint contracts", summary["assets_with_joint_contract"]),
        ("Animation poses", summary["assets_with_animation_poses"]),
        ("Access lifecycle", summary["access_lifecycle_assets"]),
        ("Liquid profiles", summary["liquid_accounting_assets"]),
    ]
    y = np.arange(len(features))
    vals = [v for _, v in features]
    ax.barh(y, vals, color=["#526876", "#718690", "#90A2A9", "#B4C1C6"], height=0.55)
    ax.set_yticks(y, [k for k, _ in features])
    ax.set_xlim(0, 71)
    ax.set_xticks([0, 35, 71])
    ax.set_xlabel("Assets (of 71)", labelpad=2)
    ax.invert_yaxis()
    ax.tick_params(length=2, pad=2)
    for yi, val in zip(y, vals):
        ax.text(val + 1.4, yi, str(val), va="center", fontsize=6.0)
    panel(ax, "c", "Capability coverage")
    return ax


def _draw_binding(fig):
    # Leave a small left margin for the panel letter, which is anchored just
    # outside the data axes by the shared style helper.
    ax = fig.add_axes((0.055, 0.025, 0.40, 0.17), facecolor="white")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    hide_axes(ax)
    panel(ax, "d", "Facility inventory to reusable assets")
    stages = [("instances", 73, "#526876"), ("model designations", 52, "#718690"), ("library assets", 71, "#90A2A9")]
    xstarts = [0.03, 0.35, 0.69]
    for (name, value, color), x in zip(stages, xstarts):
        # These are independent inventory counts, not a conservation flow;
        # equal node boxes make that distinction visible.
        ax.add_patch(Rectangle((x, 0.28), 0.22, 0.36, facecolor="#F6F8F9", edgecolor=color, lw=0.8))
        ax.add_patch(Rectangle((x + 0.085, 0.40), 0.05, 0.12, facecolor=color, edgecolor="none"))
        ax.text(x + 0.11, 0.76, str(value), ha="center", fontsize=7, weight="bold")
        ax.text(x + 0.11, 0.12, name, ha="center", fontsize=6.0, color=COLORS["muted"])
    ax.text(0.50, 0.91, "54 assigned instances → 43 asset IDs", ha="center", va="bottom", fontsize=6.0)
    ax.text(0.50, 0.02, "19 instances remain unassigned", ha="center", va="bottom", fontsize=6.0, color=COLORS["muted"])
    return ax


def _draw_rizon(fig):
    candidates = [
        REND / "final-rizon" / "transparent" / "rizon-island.png",
        REND / "final-rizon" / "white" / "rizon-island.png",
        REND / "rizon-island.png",
    ]
    path = next((candidate for candidate in candidates if candidate.exists()), None)
    if path is None:
        raise FileNotFoundError(f"Rizon island render is missing: {candidates}")
    arr = plt.imread(path)
    rgb = arr[..., :3]
    if arr.shape[-1] >= 4:
        mask = arr[..., 3] > 0.03
    else:
        mask = np.min(rgb, axis=2) < 0.985
    ys, xs = np.where(mask)
    if len(xs):
        pad_x = max(8, int(0.04 * (xs.max() - xs.min() + 1)))
        pad_y = max(8, int(0.06 * (ys.max() - ys.min() + 1)))
        x0, x1 = max(0, xs.min() - pad_x), min(arr.shape[1], xs.max() + pad_x + 1)
        y0, y1 = max(0, ys.min() - pad_y), min(arr.shape[0], ys.max() + pad_y + 1)
        arr = arr[y0:y1, x0:x1]
    ax = fig.add_axes((0.505, 0.025, 0.46, 0.17), facecolor="white")
    ax.imshow(arr, aspect="equal", extent=(0, 1, 1, 0))
    ax.set_xlim(0, 1)
    ax.set_ylim(1, 0)
    hide_axes(ax)
    panel(ax, "e", "Rizon4 island: independent handoff capability")
    provenance = read_json(REND / "final-rizon" / "rizon-island-provenance.json")
    projection = provenance.get("projection", {})
    for station, point in projection.items():
        if not point or len(point) != 2:
            continue
        ax.scatter([point[0]], [point[1]], s=8, c=COLORS["ink"], edgecolors="white", linewidths=0.35, zorder=5)
    ax.text(0.99, 0.08, "projected handoff points", ha="right", va="center", fontsize=5.5,
            color=COLORS["muted"], bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.6}, zorder=6)
    ax.text(0.50, -0.04, "Rizon4 island · digital asset", transform=ax.transAxes,
            fontsize=5.5, color=COLORS["muted"], va="top", ha="center")
    return ax


def main() -> None:
    manifest = _manifest()
    fig = plt.figure(figsize=figure_size(190), facecolor="white")
    gallery = _draw_gallery(fig, manifest)
    anatomy = _draw_anatomy(fig)
    coverage = _draw_feature_coverage(fig)
    binding = _draw_binding(fig)
    rizon = _draw_rizon(fig)

    # Keep the reusable display labels as a traceable source table without
    # altering the v2 source data.
    V3.mkdir(parents=True, exist_ok=True)
    with (V3 / "fig2_asset-source.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["index", "asset_id", "display_name", "source_image"])
        for i, record in enumerate(manifest.get("images", [])[:24]):
            writer.writerow([i, record.get("asset_id", ""), record.get("display_name", ""), str(_record_image(manifest, record))])

    # The gallery thumbnails are a distinct row group with equal spans.  The
    # lower modules are also included in the alignment audit: anatomy and
    # coverage share a row height, as do inventory binding and the Rizon4
    # capability view.  The gallery has one shared panel label above its
    # contact sheet, so only its per-cell label check is exempted.
    all_axes = [*gallery, anatomy, coverage, binding, rizon]
    panel_ids = [f"gallery{i}" for i in range(len(gallery))] + ["anatomy", "coverage", "binding", "rizon"]
    row_groups = [[f"gallery{i}" for i in range(6 * row, 6 * row + 6)] for row in range(4)]
    row_groups.extend([["anatomy", "coverage"], ["binding", "rizon"]])
    save_figure(
        fig,
        "fig2_assets",
        all_axes,
        panel_ids=panel_ids,
        row_groups=row_groups,
        exclude_axes=[],
        exemptions=[{"panels": [f"gallery{i}" for i in range(len(gallery))], "checks": ["panel-label"], "reason": "The gallery is a contact sheet; the shared panel a label and title sit above the first row."}],
        require_panel_labels=False,
        height_mm=190,
    )


if __name__ == "__main__":
    main()
