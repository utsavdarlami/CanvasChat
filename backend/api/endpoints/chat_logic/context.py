"""
Context enrichment for agent requests.

Builds a structured summary of the current layout state so the agent
has richer situational awareness without needing to call analysis tools.
"""

from typing import Any, Dict, List, Optional

from agent.layout_ops.planning import validate_layout
from core.logger import logger


def build_context_summary(
    session_state: Dict[str, Any],
    display_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a context summary dict that will be injected into agent state.

    Includes:
      - layout_quality: validation issue count and top issues
      - display_density: entity count per display
      - viewport: visible canvas per display (from display_context)
      - recent_actions: last 3 modification descriptions from history

    Returns:
        Dictionary suitable for ``state_delta["context_summary"]``.
    """
    summary: Dict[str, Any] = {}
    layout = session_state.get("current_layout")

    summary["layout_quality"] = _build_layout_quality(layout, session_state)
    summary["display_density"] = _build_display_density(layout)
    summary["viewport"] = _build_viewport(display_context)
    summary["recent_actions"] = _build_recent_actions(session_state)

    return summary


_CRITICAL_ISSUE_TYPES = {"overlap", "overflow"}


def _build_layout_quality(
    layout: Optional[Dict], session_state: Dict[str, Any]
) -> Dict[str, Any]:
    """Run validation and return a compact quality summary."""
    if not layout:
        return {"issue_count": 0, "top_issues": []}

    try:
        entities = session_state.get("entities", [])
        report = validate_layout(layout, entities)
        issues = report.get("issues", [])
        top = [_summarize_issue(i) for i in issues[:5]]
        return {"issue_count": len(issues), "top_issues": top}
    except Exception as e:
        logger.warning(f"Context: layout validation failed: {e}")
        return {"issue_count": 0, "top_issues": []}


def _summarize_issue(issue: Dict) -> Dict[str, str]:
    """Convert a raw validation issue into a compact {severity, message} dict."""
    issue_type = issue.get("type", "unknown")
    severity = "critical" if issue_type in _CRITICAL_ISSUE_TYPES else "minor"

    if issue_type == "overlap":
        names = issue.get("entities", [])
        msg = f"Overlap between {names[0]} and {names[1]}" if len(names) >= 2 else "Overlap detected"
    elif issue_type == "overflow":
        msg = f"{issue.get('entity', 'Entity')} overflows display {issue.get('display', '?')}"
    elif issue_type == "spacing":
        names = issue.get("entities", [])
        msg = f"Poor spacing between {names[0]} and {names[1]}" if len(names) >= 2 else "Poor spacing"
    elif issue_type == "cluster_split":
        msg = f"Cluster '{issue.get('cluster', '?')}' split across {len(issue.get('displays', []))} displays"
    elif issue_type == "balance":
        msg = f"Uneven display load: {issue.get('status', 'imbalanced')}"
    else:
        msg = f"Issue: {issue_type}"

    return {"severity": severity, "message": msg}


def _build_display_density(layout: Optional[Dict]) -> List[Dict[str, Any]]:
    """Count entities per display/surface using surface_assignments."""
    if not layout:
        return []

    surface_assignments = layout.get("surface_assignments", {})
    if not surface_assignments:
        # Fall back to single-surface density when assignments are unavailable.
        total = len(layout.get("node_positions", {}))
        return [{"display": "surface_0", "entity_count": total}] if total else []

    return [
        {"display": surface_id, "entity_count": len(entity_ids)}
        for surface_id, entity_ids in surface_assignments.items()
    ]


def _build_viewport(display_context: Optional[Dict]) -> List[Dict[str, Any]]:
    """Extract visible canvas info per display from client context."""
    if not display_context:
        return []

    vd = display_context.get("virtual_desktop")
    if not vd:
        return []

    displays = vd.get("displays", [])
    viewports = []
    for d in displays:
        vc = d.get("visible_canvas")
        if vc:
            viewports.append({
                "display": d.get("peer_id", "unknown"),
                "tags": d.get("tags", []),
                "visible_canvas": vc,
            })
    return viewports


def _build_recent_actions(session_state: Dict[str, Any]) -> List[str]:
    """Pull last 3 action labels from the frontend timeline context."""
    tc = session_state.get("timeline_context")
    if not tc or not tc.get("entries"):
        return []
    return [e["label"] for e in tc["entries"][-3:]]


def build_query_with_selection(
    query: str,
    selected_entity_ids: Optional[List[str]],
    session_state: Dict[str, Any],
) -> str:
    """
    Prepend selection context to the user query so the LLM can see it.

    The LLM cannot read session state directly — only tool functions can.
    This injects a short prefix so the agent knows which entities are selected
    without needing an extra tool call.
    """
    if not selected_entity_ids:
        return query

    layout = session_state.get("current_layout") or {}
    entity_names = layout.get("entity_names", {})

    parts = []
    for eid in selected_entity_ids:
        name = entity_names.get(eid, eid)
        parts.append(f'- {eid} ("{name}")')
    entity_list = "\n".join(parts)

    return (
        f"[Selected entities on canvas ({len(selected_entity_ids)}):\n"
        f"{entity_list}]\n\n"
        f"{query}"
    )
