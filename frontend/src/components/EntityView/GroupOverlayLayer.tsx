/**
 * GroupOverlayLayer - Renders colored boundary overlays behind grouped entities.
 *
 * Displayed inside the React Flow canvas when the agent performs a grouping
 * action (e.g., "group by sentiment"). Each overlay is a semi-transparent
 * rectangle with a label showing the group name and member count.
 *
 * Uses ViewportPortal to render in canvas/flow coordinate space — overlays
 * automatically pan and zoom with the viewport alongside nodes.
 */
import React from 'react';
import { ViewportPortal } from '@xyflow/react';
import { useAppStore } from '@/stores/appStore';

const GROUP_PALETTE = [
  '#3b82f6', // blue
  '#ef4444', // red
  '#10b981', // emerald
  '#f59e0b', // amber
  '#8b5cf6', // violet
  '#ec4899', // pink
  '#06b6d4', // cyan
  '#84cc16', // lime
];

export const GroupOverlayLayer: React.FC = () => {
  const allOverlays = useAppStore((s) => s.graph.groupOverlays);
  const localPeerId = useAppStore((s) => s.session.localPeerId);

  // In multi-display mode, only render overlays belonging to this display.
  // In single-display mode (no localPeerId), render all overlays.
  const overlays = localPeerId
    ? allOverlays.filter((o) => !o.display_id || o.display_id === localPeerId)
    : allOverlays;

  if (!overlays.length) return null;

  return (
    <ViewportPortal>
      <div style={{ pointerEvents: 'none' }}>
        {overlays.map((overlay) => {
          const { min_x, min_y, max_x, max_y } = overlay.bounds;
          const color = GROUP_PALETTE[overlay.color_index % GROUP_PALETTE.length];
          const width = max_x - min_x;
          const height = max_y - min_y;

          return (
            <div
              key={`${overlay.label}-${overlay.color_index}`}
              style={{
                position: 'absolute',
                transform: `translate(${min_x}px, ${min_y}px)`,
                width,
                height,
                background: `${color}18`,
                border: `2px solid ${color}50`,
                borderRadius: 12,
              }}
            >
              <span
                style={{
                  position: 'absolute',
                  top: 6,
                  left: 10,
                  fontSize: 14,
                  fontWeight: 600,
                  color: `${color}DD`,
                  whiteSpace: 'nowrap',
                  textShadow: '0 1px 2px rgba(255,255,255,0.8)',
                }}
              >
                {overlay.label} ({overlay.entity_ids.length})
              </span>
            </div>
          );
        })}
      </div>
    </ViewportPortal>
  );
};
