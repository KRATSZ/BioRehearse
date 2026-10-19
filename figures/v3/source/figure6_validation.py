"""Figure 6: layered validation and a material-location correction."""

from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Circle, FancyArrowPatch, Rectangle

import matplotlib

matplotlib.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 6.5, "xtick.labelsize": 5.7, "ytick.labelsize": 5.7,
    "svg.fonttype": "none", "pdf.fonttype": 42, "savefig.dpi": 400,
})
# The shared save_figure helper invokes require_matplotlib_panel_alignment(...) after the final draw.
# Final editable exports: fig.savefig("figure.svg"), fig.savefig("figure.pdf"), fig.savefig("figure.png", dpi=400).

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sharedstyle import (  # noqa: E402
    COLORS,
    DATA_V3,
    REND,
    V3,
    figure_size,
    hide_axes,
    panel,
    read_json,
    require_file,
    save_figure,
)

# sharedstyle sets the journal defaults on import; use a small safety margin
# over the 5.5-pt floor for this dense matrix's tick labels.
plt.rcParams.update({"xtick.labelsize": 5.8, "ytick.labelsize": 5.8})


LAYER_LABELS = {
    "intent": "Intent",
    "schedule": "Schedule",
    "mass": "Liquid balance",
    "material": "Material location",
    "asset_contract": "Asset contract",
    "asset": "Asset contract",
}
ERROR_LABELS = {
    "control": "Control plans",
    "delete_transfer": "Deleted transfer",
    "incompatible_device": "Incompatible device",
    "shift_time": "Shifted operation",
    "change_volume": "Changed volume",
    "access_order": "Access-order violation",
    "intent_mismatch": "Intent mismatch",
    "resource_overlap": "Resource overlap",
    "liquid_overdraw": "Liquid overdraw",
    "missing_water_movement": "Missing water move",
    "asset_lifecycle": "Asset lifecycle",
    "closed_access": "Closed-access load",
    "unchanged": "Unchanged control",
}


def _validation_file() -> Path:
    candidates = [
        DATA_V3 / "fig6-validation-matrix.csv",
        DATA_V3 / "validation-matrix.csv",
        DATA_V3 / "mutation-matrix.csv",
        DATA_V3 / "layered-validation.csv",
        DATA_V3 / "validation-matrix.json",
        DATA_V3 / "mutation-matrix.json",
        DATA_V3 / "layered-validation.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Prospective v3 layered-validation or mutation-matrix output is required for Fig. 6")


def _exploratory_volume_row(layers: list[str]) -> tuple[str, np.ndarray, str, int] | None:
    """Summarize the exploratory 48-plan volume challenge from its raw JSONL.

    The frozen directed matrix and this challenge answer different questions.
    The latter is intentionally appended as a dashed exploratory row, and all
    rates are computed from the recorded per-plan layer outcomes.
    """
    raw_path = DATA_V3 / "mutation-challenge.jsonl"
    if not raw_path.exists():
        return None
    records = [
        json.loads(line)
        for line in raw_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records = [record for record in records if record.get("category") == "volume_factor"]
    if not records:
        return None
    label = f"Moderate volume changes (exploratory, n={len(records)})"
    raw_layer_names = {
        "intent": "intent",
        "schedule": "schedule",
        "mass_balance": "mass_balance",
        "material_location": "material_location",
        "asset_contract": "asset_contract",
        "asset": "asset_contract",
        "access_lifecycle": "asset_contract",
    }
    values: list[float] = []
    for layer in layers:
        raw_key = raw_layer_names.get(layer.lower(), layer)
        observed = [record.get("layers", {}).get(raw_key) for record in records]
        observed = [value for value in observed if value is not None]
        if not observed:
            values.append(float("nan"))
        else:
            values.append(float(sum(bool(value) for value in observed)) / len(observed))
    return label, np.asarray(values, dtype=float), str(raw_path), len(records)


def _load_matrix(path: Path) -> tuple[list[str], list[str], np.ndarray, list[str], list[int | None]]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            raise ValueError("Validation matrix is empty")
        meta_keys = {"error_type", "error", "mutation", "category", "n", "total", "scope", "source", "union"}
        layer_keys = [key for key in rows[0] if key.lower() not in meta_keys and not key.lower().endswith("_applicable")]
        error_keys = [str(row.get("category") or row.get("error_type") or row.get("error") or row.get("mutation")) for row in rows]
        matrix = np.asarray([[_cell_value(row.get(key)) for key in layer_keys] for row in rows], dtype=float)
        matrix = _apply_scope(rows, error_keys, layer_keys, matrix)
        sources = [str(row.get("source") or path) for row in rows]
        denominators = []
        for row in rows:
            try:
                denominators.append(int(float(row.get("n"))))
            except (TypeError, ValueError):
                denominators.append(None)
        exploratory = _exploratory_volume_row(layer_keys)
        if exploratory is not None and not any("exploratory" in error.lower() for error in error_keys):
            label, values, source, denominator = exploratory
            error_keys.append(label)
            matrix = np.vstack([matrix, values])
            sources.append(source)
            denominators.append(denominator)
        return error_keys, layer_keys, matrix, sources, denominators
    data = read_json(path)
    layers = list(data.get("layers") or data.get("checks") or [])
    errors = list(data.get("error_types") or data.get("mutations") or data.get("rows") or [])
    raw = data.get("matrix")
    if isinstance(raw, dict):
        layers = list(raw.get("layers") or layers)
        errors = list(raw.get("errors") or raw.get("error_types") or errors)
        raw = raw.get("values") or raw.get("matrix")
    if not layers or not errors or raw is None:
        raise ValueError(f"Cannot decode layered-validation matrix from {path}")
    matrix = np.asarray(raw, dtype=float)
    if matrix.shape != (len(errors), len(layers)):
        raise ValueError(f"Validation matrix shape {matrix.shape} does not match {len(errors)} errors × {len(layers)} layers")
    return [str(e) for e in errors], [str(layer) for layer in layers], matrix, [str(path)] * len(errors), [None] * len(errors)


def _cell_value(value) -> float:
    """Decode numeric cells while preserving explicit not-applicable values."""
    if value is None or str(value).strip().lower() in {"", "na", "n/a", "nan", "null", "-"}:
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Validation matrix cell is not numeric: {value!r}")


def _apply_scope(rows: list[dict], errors: list[str], layers: list[str], matrix: np.ndarray) -> np.ndarray:
    """Apply only explicit scope flags; preserve measured zeros as evidence.

    The v3.1 matrix records which checks actually ran.  In particular, a zero
    is a measured non-detection and must not be rewritten to NA from a guessed
    mutation target.  White/hatched cells therefore arise only from explicit
    ``NA`` values or an explicit ``scope``/``*_applicable`` declaration.
    """
    if not layers:
        return matrix
    has_explicit_scope = any(
        row.get("scope") not in (None, "")
        or any(row.get(f"{layer}_applicable") not in (None, "") for layer in layers)
        for row in rows
    )
    if has_explicit_scope:
        for i, row in enumerate(rows):
            scope = str(row.get("scope") or "").lower()
            for j, layer in enumerate(layers):
                flag = row.get(f"{layer}_applicable")
                if flag is not None and str(flag).strip() != "":
                    if str(flag).strip().lower() in {"0", "false", "no", "na", "n/a"}:
                        matrix[i, j] = np.nan
                elif scope and layer.lower() not in scope.replace(";", ",").split(","):
                    matrix[i, j] = np.nan
        return matrix

    return matrix


def _provenance() -> dict:
    for candidate in (
        REND / "water-provenance.json",
        REND / "rehearsal-provenance.json",
        REND / "final-workbench-water" / "unified-scene-provenance.json",
        REND / "final-workbench" / "unified-scene-provenance.json",
        V3 / "water-provenance.json",
    ):
        if candidate.exists():
            return read_json(candidate)
    raise FileNotFoundError("Water-location render provenance is required for Fig. 6")


def _water_projection(provenance: dict, image_name: str) -> tuple[float, float]:
    image_basename = Path(image_name).name
    case = "correct" if "correct" in image_basename else "injected" if "inject" in image_basename or "wrong" in image_basename else None
    for item in provenance.get("images", []):
        item_name = Path(str(item.get("image") or item.get("file") or "")).name
        if item_name == image_basename or item.get("water_case") == case:
            proj = item.get("container_projection", {}).get("E3:WATER")
            if proj is not None:
                return float(proj[0]), float(proj[1])
    for record in provenance.get("state_records", []):
        if case is not None and record.get("water_case") != case:
            continue
        glyph = record.get("glyph", {})
        if glyph.get("container_id") == "E3:WATER":
            proj = glyph.get("projection_normalized_xy")
            if proj is not None:
                return float(proj[0]), float(proj[1])
    # Accept a direct v3 mapping for concise provenance manifests.
    direct = provenance.get("water_projection", {}).get(image_name)
    if direct is not None:
        return float(direct[0]), float(direct[1])
    raise KeyError(f"No E3:WATER projection for {image_name}")


def _water_render_path(logical_name: str) -> tuple[Path, str]:
    """Resolve the renderer's semantic water case to its recorded PNG."""
    actual_name = "water-injected.png" if logical_name in {"water-wrong.png", "water-injected.png"} else "water-correct.png"
    candidates = [
        REND / logical_name,
        REND / actual_name,
        REND / "final-workbench-water" / "white" / actual_name,
        REND / "final-workbench-water" / "transparent" / actual_name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate, actual_name
    raise FileNotFoundError(f"Native water render is missing for {logical_name}: {candidates}")


def _draw_matrix(ax, errors: list[str], layers: list[str], matrix: np.ndarray, denominators: list[int | None]):
    layer_display = [LAYER_LABELS.get(layer, layer.replace("_", " ").title()) for layer in layers]
    error_display = [ERROR_LABELS.get(error, error.replace("_", " ").title()) for error in errors]
    error_display = [
        "Moderate volume changes\n(exploratory, n=48)" if "exploratory" in error.lower() else label
        for error, label in zip(errors, error_display)
    ]
    max_value = max(1, float(np.nanmax(matrix)))
    # Keep every measured cell pale enough for dark count labels.  The matrix
    # communicates detection strength through a light sequential tint; NA is
    # reserved for explicitly out-of-scope checks and is hatched below.
    cmap = LinearSegmentedColormap.from_list("layered-checks", ["#F7FAFB", "#E6F0F3", "#C7DCE3", "#9DBAC5"], N=256)
    cmap.set_bad("#FFFFFF")
    im = ax.imshow(matrix, cmap=cmap, vmin=0, vmax=max_value, aspect="auto", interpolation="nearest")
    ax.set_yticks(np.arange(len(errors)), error_display)
    ax.set_xticks(np.arange(len(layers)), layer_display)
    plt.setp(ax.get_xticklabels(), rotation=25, rotation_mode="anchor", ha="right")
    ax.tick_params(length=0, pad=3)
    panel(ax, "a", "Injected mutations are localized by complementary checks")
    for i in range(matrix.shape[0]):
        if "exploratory" in errors[i].lower():
            ax.axhline(i - 0.5, color=COLORS["guide"], linewidth=0.65, linestyle=(0, (2, 2)), zorder=5)
        for j in range(matrix.shape[1]):
            value = matrix[i, j]
            if np.isnan(value):
                ax.add_patch(Rectangle((j - 0.5, i - 0.5), 1, 1, facecolor="white", edgecolor="#D4DDE1", hatch="///", linewidth=0.25, zorder=3))
                ax.text(j, i, "NA", ha="center", va="center", fontsize=5.6, color=COLORS["muted"], zorder=4)
                continue
            denominator = denominators[i] if i < len(denominators) else None
            if denominator is not None and max_value <= 1.01:
                numerator = int(round(float(value) * denominator))
                label = f"{numerator}/{denominator}"
            elif denominator is not None:
                label = f"{int(round(float(value)))}/{denominator}"
            else:
                label = f"{100 * value:.0f}%" if max_value <= 1.01 else f"{int(value) if float(value).is_integer() else value:g}"
            ax.text(j, i, label, ha="center", va="center", fontsize=5.6, color=COLORS["ink"], zorder=4)
    ax.set_xlabel("Validation layer · detections / tested", labelpad=2)
    ax.text(1.0, -0.26, "Hatched: outside declared scope", transform=ax.transAxes,
            fontsize=5.8, color=COLORS["muted"], ha="right")
    return im


def _draw_location_image(fig, image_name: str, letter: str, title: str, *, red: bool, provenance: dict):
    path, provenance_name = _water_render_path(image_name)
    ax = fig.add_axes((0.075 if red else 0.525, 0.10, 0.40, 0.30), facecolor="white")
    ax.imshow(plt.imread(path), aspect="auto")
    ax.set_axis_off()
    panel(ax, letter, title)
    x, y = _water_projection(provenance, provenance_name)
    # Projection coordinates are normalized to image coordinates; the red
    # callout is deliberately identical in both views.
    if red:
        ax.add_patch(Circle((x, 1 - y), 0.065, transform=ax.transAxes, fill=False, ec=COLORS["warning"], lw=1.5))
        ax.annotate("water remains on Fluent", xy=(x, 1 - y), xycoords="axes fraction", xytext=(0.12, 0.88), textcoords="axes fraction",
                    fontsize=6.0, color=COLORS["warning"], ha="left", va="center",
                    arrowprops={"arrowstyle": "-|>", "lw": 0.8, "color": COLORS["warning"]},
                    bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.2})
    else:
        ax.add_patch(Circle((x, 1 - y), 0.065, transform=ax.transAxes, fill=False, ec=COLORS["warning"], lw=1.5))
        ax.annotate("water staged at bench", xy=(x, 1 - y), xycoords="axes fraction", xytext=(0.12, 0.88), textcoords="axes fraction",
                    fontsize=6.0, color=COLORS["ink"], ha="left", va="center",
                    arrowprops={"arrowstyle": "-|>", "lw": 0.8, "color": COLORS["warning"]},
                    bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.2})
    ax.text(0.01, -0.04, "same camera; red outline marks the GFP dilution-water stock", transform=ax.transAxes, fontsize=6.0, color=COLORS["muted"], va="top")
    return ax


def main() -> None:
    matrix_path = _validation_file()
    errors, layers, matrix, sources, denominators = _load_matrix(matrix_path)
    if not any(layer in {"asset_contract", "asset", "access_lifecycle"} for layer in layers):
        raise ValueError("Fig. 6 requires a fifth asset-contract/access-lifecycle validation layer")
    provenance = _provenance()
    fig = plt.figure(figsize=figure_size(155), facecolor="white")
    a = fig.add_axes((0.17, 0.55, 0.77, 0.30), facecolor="white")
    _draw_matrix(a, errors, layers, matrix, denominators)
    wrong = _draw_location_image(fig, "water-wrong.png", "b", "Location mismatch found by state replay", red=True, provenance=provenance)
    correct = _draw_location_image(fig, "water-correct.png", "c", "Corrected location and replay", red=False, provenance=provenance)
    V3.mkdir(parents=True, exist_ok=True)
    with (V3 / "fig6_validation-source.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["error_type", "n", *layers, "source"])
        for error, values, source, denominator in zip(errors, matrix, sources, denominators):
            writer.writerow([error, denominator if denominator is not None else "", *values, source])
    save_figure(
        fig,
        "fig6_validation",
        [a, wrong, correct],
        panel_ids=["matrix", "wrong", "correct"],
        row_groups=[["wrong", "correct"]],
        exclude_axes=[a],
        height_mm=155,
    )
    for suffix in ("pdf", "svg", "png"):
        shutil.copy2(V3 / f"fig6_validation.{suffix}", V3 / f"fig6_layers.{suffix}")
    for suffix in ("json", "svg"):
        shutil.copy2(V3 / f"fig6_validation.alignment.{suffix}", V3 / f"fig6_layers.alignment.{suffix}")


if __name__ == "__main__":
    main()
