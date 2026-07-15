"""Shared constants for layout operations."""

DEFAULT_NODE_GAP = 40.0
MIN_CAMERA_ZOOM = 0.05
MAX_CAMERA_ZOOM = 4.0
CAMERA_FIT_MARGIN = 40.0

MAX_THEMES_PER_ENTITY = 10

DEFAULT_MIN_NODE_DISTANCE = 50.0

GROUP_GAP = 60.0  # Base gap between group regions (pixels), scaled by viewport

# Multipliers for intra-group node spacing (applied to DEFAULT_NODE_GAP)
INTRA_GROUP_SPACING_MULTIPLIERS = {
    "tight": 0.6,
    "medium": 1.0,
    "large": 1.8,
}

# ---------------------------------------------------------------------------
# Display-proportional gap computation
# ---------------------------------------------------------------------------

# Structural inter-group gap as fraction of display's shorter pixel dimension.
REGION_GAP_FRACTION = 0.03
REGION_MIN_GAP_PX = 30.0
REGION_MAX_GAP_PX = 120.0

# ---------------------------------------------------------------------------
# Display profile — shape classification thresholds (aspect ratio)
# ---------------------------------------------------------------------------

SHAPE_ULTRAWIDE = 2.1   # 21:9 and wider
SHAPE_LANDSCAPE = 1.3   # 16:9, 16:10
SHAPE_SQUARE = 0.77     # ~1:1
SHAPE_PORTRAIT = 0.48   # 9:16

# ---------------------------------------------------------------------------
# Display profile — capacity estimation
# ---------------------------------------------------------------------------

# Square pixels per readable entity at zoom >= 0.6.  Accounts for entity
# area (~400×300 = 120k) plus gap/margin budget.  Calibrated so that a
# 1920×1080 display → capacity ~11, 2560×1440 → ~20.
CAPACITY_AREA_PER_ENTITY = 180_000.0
