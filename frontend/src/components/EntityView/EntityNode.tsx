import { memo, useCallback, useMemo } from 'react';
import { NodeProps, NodeResizer } from '@xyflow/react';
import { EntityPanelContent } from './EntityPanelContent';
import { Entity } from '@/types/entity';
import {
  DEFAULT_TEXT_NODE_WIDTH,
  DEFAULT_TEXT_NODE_HEIGHT,
  computeOptimalFontSize,
  getTagOverlayOffset,
} from './entityNodeUtils';
import type { GraphNode } from '@/types/graph';
import { EntityNodeTags } from './EntityNodeTags';
import { useAppStore } from '@/stores/appStore';
import { GATHER_ANIMATION_MS } from '@/stores/slices/animationSlice';

function normalizeHighlightColor(raw: unknown): string | undefined {
  if (typeof raw !== 'string') return undefined;
  const color = raw.trim();
  if (!color || color.length > 64) return undefined;
  if (typeof window !== 'undefined' && typeof CSS !== 'undefined' && typeof CSS.supports === 'function') {
    if (!CSS.supports('color', color)) return undefined;
  }
  return color;
}

function areEntityRenderFieldsEqual(prev?: GraphNode, next?: GraphNode): boolean {
  if (prev === next) return true;
  if (!prev || !next) return false;

  return prev.id === next.id
    && prev.displayId === next.displayId
    && prev.display_name === next.display_name
    && prev.type === next.type
    && prev.value === next.value;
}

function areNodePropsEqual(prev: NodeProps, next: NodeProps): boolean {
  const prevData = prev.data as {
    entity?: GraphNode;
    isAgentHighlighted?: boolean;
    isAgentDimmed?: boolean;
    isTransientRender?: boolean;
  };
  const nextData = next.data as {
    entity?: GraphNode;
    isAgentHighlighted?: boolean;
    isAgentDimmed?: boolean;
    isTransientRender?: boolean;
  };

  return prev.selected === next.selected
    && prev.width === next.width
    && prev.height === next.height
    && areEntityRenderFieldsEqual(prevData.entity, nextData.entity)
    && Boolean(prevData.isAgentHighlighted) === Boolean(nextData.isAgentHighlighted)
    && Boolean(prevData.isAgentDimmed) === Boolean(nextData.isAgentDimmed)
    && Boolean(prevData.isTransientRender) === Boolean(nextData.isTransientRender);
}

// Wrapper to adapt EntityPanelContent for React Flow
export const EntityNode = memo(({ data, selected, width, height }: NodeProps) => {
  const entity = data.entity as Entity;
  const graphNode = data.entity as GraphNode;
  const entityId = graphNode.entity_id || graphNode.id;
  const isAgentHighlighted = Boolean((data as { isAgentHighlighted?: boolean }).isAgentHighlighted);
  const isAgentDimmed = Boolean((data as { isAgentDimmed?: boolean }).isAgentDimmed);
  const isTransientRender = Boolean((data as { isTransientRender?: boolean }).isTransientRender);
  const highlightedNodeColor = useAppStore((s) => s.graph.highlightedNodeColors[graphNode.id]);
  const agentHighlightColor = isAgentHighlighted
    ? normalizeHighlightColor(highlightedNodeColor)
    : undefined;

  // Gather animation: CSS transform to centroid (visual only, no position change)
  const gatherTarget = useAppStore((s) => s.animation.gatherTargets[graphNode.id]);
  const gatherTransform = useMemo(() => {
    if (!gatherTarget) return undefined;
    // Calculate offset from current position to gather target (centroid)
    const currentX = graphNode.x ?? 0;
    const currentY = graphNode.y ?? 0;
    const offsetX = gatherTarget.x - currentX;
    const offsetY = gatherTarget.y - currentY;
    return `translate(${offsetX}px, ${offsetY}px)`;
  }, [gatherTarget, graphNode.x, graphNode.y]);

  // Use node dimensions from React Flow, with fallbacks from constants
  const nodeWidth = width || DEFAULT_TEXT_NODE_WIDTH;
  const nodeHeight = height || DEFAULT_TEXT_NODE_HEIGHT;

  // Compute optimal font size so text best-fills the node
  const contentType = graphNode.type || 'unknown';
  const contentValue = graphNode.value;
  const entityTags = useAppStore((s) => s.graph.entityTags[entityId]);
  const tagCount = entityTags?.length ?? 0;
  const nodeFontSize = useMemo(() => {
    if (contentType !== 'text' || !contentValue) return undefined;
    return computeOptimalFontSize(String(contentValue), nodeWidth, nodeHeight, tagCount);
  }, [contentType, contentValue, nodeWidth, nodeHeight, tagCount]);

  const handleResizeEnd = useCallback(
    (_event: unknown, params: { x: number; y: number; width: number; height: number }) => {
      useAppStore.getState().graph.updateNode(graphNode.id, {
        nodeWidth: params.width,
        nodeHeight: params.height,
        x: params.x,
        y: params.y,
      });
    },
    [graphNode.id],
  );

  return (
    <div
      className={[
        'entity-node-container',
        selected ? 'selected' : '',
        isAgentHighlighted ? 'agent-highlighted' : '',
        isAgentDimmed ? 'agent-dimmed' : '',
        gatherTarget ? 'gathering' : '',
      ].filter(Boolean).join(' ')}
      style={{
        width: nodeWidth,
        height: nodeHeight,
        ...(nodeFontSize != null && { '--node-font-size': `${nodeFontSize}px` }),
        '--entity-tags-offset': `${getTagOverlayOffset(tagCount)}px`,
        ...(isAgentHighlighted && agentHighlightColor && {
          '--agent-highlight-color': agentHighlightColor,
        }),
        ...(gatherTransform && {
          transform: gatherTransform,
          transition: `transform ${GATHER_ANIMATION_MS}ms ease-out`,
        }),
      } as React.CSSProperties}
    >
      <NodeResizer
        isVisible={selected}
        minWidth={200}
        minHeight={100}
        maxWidth={2000}
        maxHeight={1500}
        onResizeEnd={handleResizeEnd}
      />
      <EntityNodeTags entityId={entityId} selected={selected} />
      <div className="entity-node-content-wrapper">
        <EntityPanelContent
          entity={entity}
          isNodeSelected={selected}
          isTransientRender={isTransientRender}
        />
      </div>
    </div>
  );
}, areNodePropsEqual);
