"""Shared region-slicing utilities for display sub-areas."""

# Inter-region gap: 2% on each side of a boundary → 4% visual gap between
# adjacent regions (e.g. left/right share the 50% line, now 48%/52%).
_GAP = 0.02

# 40/60 top-bottom split preserves a neutral center band to reduce edge overlap.
REGION_SLICES = {
    "top": (0.0, 0.0, 1.0, 0.4 - _GAP),
    "bottom": (0.0, 0.6 + _GAP, 1.0, 1.0),
    "left": (0.0, 0.0, 0.5 - _GAP, 1.0),
    "right": (0.5 + _GAP, 0.0, 1.0, 1.0),
    "top-left": (0.0, 0.0, 0.5 - _GAP, 0.4 - _GAP),
    "top-right": (0.5 + _GAP, 0.0, 1.0, 0.4 - _GAP),
    "bottom-left": (0.0, 0.6 + _GAP, 0.5 - _GAP, 1.0),
    "bottom-right": (0.5 + _GAP, 0.6 + _GAP, 1.0, 1.0),
    "center": (0.2, 0.2, 0.8, 0.8),
}


def slice_bounds_for_region(
    bounds: tuple[float, float, float, float],
    region: str,
) -> tuple[float, float, float, float] | None:
    """Slice full display bounds into a sub-region.

    Args:
        bounds: (min_x, min_y, max_x, max_y) of the full display area.
        region: Region name (e.g. "top", "bottom-left").

    Returns:
        Sliced (min_x, min_y, max_x, max_y) or None if *region* is unknown.
    """
    fractions = REGION_SLICES.get(region.lower())
    if not fractions:
        return None
    min_x, min_y, max_x, max_y = bounds
    w = max_x - min_x
    h = max_y - min_y
    return (
        min_x + w * fractions[0],
        min_y + h * fractions[1],
        min_x + w * fractions[2],
        min_y + h * fractions[3],
    )
