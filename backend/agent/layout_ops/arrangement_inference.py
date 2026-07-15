"""Heuristic inference of layout organizing axes.

Given a set of views on a display plus their semantic fields, determine
which field best explains the row- and column-band structure, with a
per-band rationale. Feeds the layer 2 self-assessment capability so the
agent can name what organizes an arrangement without another LLM call.
"""

from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from .constants import MAX_THEMES_PER_ENTITY
from .snapshot import _BAND_TOLERANCE, _SEMANTIC_FIELDS, _build_semantics_by_id

_HOMOGENEITY_FLOOR = 0.67


def _assign_bands(
    values: List[float], tolerance: float = _BAND_TOLERANCE
) -> List[int]:
    """Assign each 1D value to a band index by proximity tolerance.

    Values within ``tolerance`` of their predecessor share a band; a larger
    gap starts a new band. Preserves input order in the returned list.
    """
    if not values:
        return []
    indexed = sorted(enumerate(values), key=lambda t: t[1])
    band_of = [0] * len(values)
    current_band = 0
    band_of[indexed[0][0]] = 0
    prev_val = indexed[0][1]
    for i in range(1, len(indexed)):
        orig_idx, val = indexed[i]
        if val - prev_val > tolerance:
            current_band += 1
        band_of[orig_idx] = current_band
        prev_val = val
    return band_of


def _score_axis(
    bands: List[int],
    values: List[Optional[str]],
) -> Tuple[float, Dict[int, Tuple[Optional[str], int, int]]]:
    """Score how homogeneously a field aligns with a given band assignment.

    Homogeneity = fraction of views whose field value equals the modal
    value in their band. ``None`` values still count toward the band total
    (a band where most views lack the field scores poorly).
    """
    if not bands or not values:
        return 0.0, {}
    by_band: Dict[int, List[Optional[str]]] = {}
    for b, v in zip(bands, values):
        by_band.setdefault(b, []).append(v)

    total = 0
    matched = 0
    per_band: Dict[int, Tuple[Optional[str], int, int]] = {}
    for band_idx, vals in by_band.items():
        present = [v for v in vals if v]
        if not present:
            per_band[band_idx] = (None, 0, len(vals))
            total += len(vals)
            continue
        modal_value, modal_count = Counter(present).most_common(1)[0]
        per_band[band_idx] = (modal_value, modal_count, len(vals))
        total += len(vals)
        matched += modal_count

    return (matched / total if total else 0.0), per_band


def _collect_field_values(
    semantics_by_id: Dict[str, Dict[str, Any]],
    entity_ids: List[str],
) -> Dict[str, List[Optional[str]]]:
    """Build per-field value vectors (same order as entity_ids).

    Scalar fields use raw values; themes are expanded into binary
    ``theme:<name>`` fields so each theme competes independently.
    """
    result: Dict[str, List[Optional[str]]] = {}
    for field in _SEMANTIC_FIELDS:
        result[field] = [
            semantics_by_id.get(eid, {}).get(field) for eid in entity_ids
        ]

    theme_set: set = set()
    for eid in entity_ids:
        themes = (semantics_by_id.get(eid, {}).get("key_themes") or [])[
            :MAX_THEMES_PER_ENTITY
        ]
        theme_set.update(themes)
    for theme in theme_set:
        result[f"theme:{theme}"] = [
            theme
            if theme
            in (
                (semantics_by_id.get(eid, {}).get("key_themes") or [])[
                    :MAX_THEMES_PER_ENTITY
                ]
            )
            else None
            for eid in entity_ids
        ]
    return result


def _format_rationale(
    per_band: Dict[int, Tuple[Optional[str], int, int]],
    axis_kind: str,
) -> str:
    """Render per-band stats as 'row 0: weather (3/3), row 1: sports (2/3)'."""
    parts = []
    for band_idx in sorted(per_band.keys()):
        modal, matched, total = per_band[band_idx]
        label = modal if modal else "—"
        parts.append(f"{axis_kind} {band_idx}: {label} ({matched}/{total})")
    return ", ".join(parts)


def infer_display_arrangement(
    layout: Dict[str, Any],
    entity_ids: List[str],
    semantics_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Infer the organizing axes of a set of views on one display.

    For each semantic field (scalars + binary theme features), score
    homogeneity along row-bands and col-bands. Highest-scoring field per
    axis wins (subject to a 0.67 floor); a field cannot claim both axes
    unless one axis has only a single band.

    Returns a dict with ``row_axis``, ``col_axis`` (each ``None`` or
    ``{field, score, rationale}``), ``bands``, ``unexplained_views``, and
    a ``note`` when no axis meets the floor.
    """
    node_positions = layout.get("node_positions", {})
    positioned = [eid for eid in entity_ids if eid in node_positions]
    if len(positioned) < 2:
        return {
            "entity_count": len(positioned),
            "row_axis": None,
            "col_axis": None,
            "bands": {"row": 0, "col": 0},
            "unexplained_views": [],
            "note": "need at least 2 positioned views to infer an arrangement",
        }

    xs = [node_positions[eid][0] for eid in positioned]
    ys = [node_positions[eid][1] for eid in positioned]
    col_bands = _assign_bands(xs)
    row_bands = _assign_bands(ys)
    num_row_bands = max(row_bands) + 1
    num_col_bands = max(col_bands) + 1

    field_values = _collect_field_values(semantics_by_id, positioned)

    row_scored: List[Tuple[str, float, Dict]] = []
    col_scored: List[Tuple[str, float, Dict]] = []
    for field_name, values in field_values.items():
        if num_row_bands >= 2:
            rs, rper = _score_axis(row_bands, values)
            row_scored.append((field_name, rs, rper))
        if num_col_bands >= 2:
            cs, cper = _score_axis(col_bands, values)
            col_scored.append((field_name, cs, cper))

    row_scored.sort(key=lambda x: x[1], reverse=True)
    col_scored.sort(key=lambda x: x[1], reverse=True)

    row_axis: Optional[Dict[str, Any]] = None
    row_claimed: Optional[str] = None
    row_per_band: Optional[Dict[int, Tuple[Optional[str], int, int]]] = None
    for field_name, score, per_band in row_scored:
        if score >= _HOMOGENEITY_FLOOR:
            row_axis = {
                "field": field_name,
                "score": round(score, 3),
                "rationale": _format_rationale(per_band, "row"),
            }
            row_claimed = field_name
            row_per_band = per_band
            break

    col_axis: Optional[Dict[str, Any]] = None
    col_per_band: Optional[Dict[int, Tuple[Optional[str], int, int]]] = None
    for field_name, score, per_band in col_scored:
        if field_name == row_claimed and num_row_bands > 1 and num_col_bands > 1:
            continue
        if score >= _HOMOGENEITY_FLOOR:
            col_axis = {
                "field": field_name,
                "score": round(score, 3),
                "rationale": _format_rationale(per_band, "col"),
            }
            col_per_band = per_band
            break

    entity_names = layout.get("entity_names", {})
    unexplained: List[str] = []
    axes_claimed = (1 if row_axis else 0) + (1 if col_axis else 0)
    for idx, eid in enumerate(positioned):
        fails = 0
        if row_axis and row_per_band is not None:
            modal, _, _ = row_per_band[row_bands[idx]]
            if field_values[row_axis["field"]][idx] != modal:
                fails += 1
        if col_axis and col_per_band is not None:
            modal, _, _ = col_per_band[col_bands[idx]]
            if field_values[col_axis["field"]][idx] != modal:
                fails += 1
        if axes_claimed and fails == axes_claimed:
            unexplained.append(entity_names.get(eid, eid))

    result: Dict[str, Any] = {
        "entity_count": len(positioned),
        "bands": {"row": num_row_bands, "col": num_col_bands},
        "row_axis": row_axis,
        "col_axis": col_axis,
        "unexplained_views": unexplained,
    }
    if row_axis is None and col_axis is None:
        result["note"] = (
            f"no clear organizing axis (no field above {_HOMOGENEITY_FLOOR:.2f} "
            "homogeneity on either axis)"
        )
    return result


def infer_arrangement(
    layout: Dict[str, Any],
    entities: Optional[list] = None,
    display_id: Optional[str] = None,
    entity_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Run arrangement inference for each display in scope.

    Scoping follows the same rules as ``gather_layout_snapshot``:
    ``entity_ids`` takes precedence over ``display_id``; omit both for the
    full layout. Entity scopes spanning multiple displays are grouped
    per-display internally — axes are always display-local.
    """
    surface_assignments = layout.get("surface_assignments", {})

    if entity_ids:
        scope_set: Optional[set] = set(entity_ids)
    elif display_id:
        scope_set = set(surface_assignments.get(display_id, []))
    else:
        scope_set = None

    if scope_set is not None:
        scoped = {
            sid: [e for e in eids if e in scope_set]
            for sid, eids in surface_assignments.items()
        }
        scoped = {k: v for k, v in scoped.items() if v}
    else:
        scoped = surface_assignments

    valid_ids = set(layout.get("node_positions", {}).keys())
    if scope_set is not None:
        valid_ids &= scope_set
    semantics_by_id = _build_semantics_by_id(entities, valid_ids)

    display_labels: Dict[str, str] = {}
    for disp in layout.get("displays", []):
        peer_id = disp.get("peer_id", "")
        tags = disp.get("tags", [])
        display_labels[peer_id] = ", ".join(tags) if tags else peer_id

    results: List[Dict[str, Any]] = []
    for surface_id, eids in scoped.items():
        entry = infer_display_arrangement(layout, eids, semantics_by_id)
        entry["display"] = display_labels.get(surface_id, surface_id)
        entry["display_id"] = surface_id
        results.append(entry)
    return results
