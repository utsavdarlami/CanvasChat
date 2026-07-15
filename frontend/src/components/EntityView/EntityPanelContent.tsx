import { memo, useCallback, useMemo, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
import { Entity } from '@/types/entity';
import { useGraphCurrentEntities } from '@/stores/graphStore';
import { useHighlightStore, type TextHighlight } from '@/stores/highlightStore';
import { findEntityById } from './entityNodeUtils';
import { normalizeMarkdownInput } from './markdownTextUtils';
import { LazyVegaChart } from './LazyVegaChart';
import { getCanvasSnapshot } from './vegaSpecCache';
import { TextSelectionToolbar } from './TextSelectionToolbar';
import { highlightTextChildren } from './highlightTextChildren';
import './EntityPanel.css';

interface EntityPanelContentProps {
  entity: Entity;
  isNodeSelected: boolean;
  isTransientRender?: boolean;
}

function areEntityPanelPropsEqual(prev: EntityPanelContentProps, next: EntityPanelContentProps): boolean {
  if (prev.entity === next.entity) {
    return prev.isNodeSelected === next.isNodeSelected
      && Boolean(prev.isTransientRender) === Boolean(next.isTransientRender);
  }

  return prev.isNodeSelected === next.isNodeSelected
    && Boolean(prev.isTransientRender) === Boolean(next.isTransientRender)
    && prev.entity.id === next.entity.id
    && prev.entity.display_name === next.entity.display_name
    && prev.entity.type === next.entity.type
    && prev.entity.value === next.entity.value;
}

const EMPTY_HIGHLIGHTS: TextHighlight[] = [];
const FALLBACK_VISUAL_PLACEHOLDER_HEIGHT = 180;

function resolveVisualPlaceholderHeight(spec: Record<string, unknown> | null): number {
  if (!spec) return FALLBACK_VISUAL_PLACEHOLDER_HEIGHT;
  const directHeight = typeof spec.height === 'number' ? spec.height : null;
  const config =
    typeof spec.config === 'object' && spec.config !== null
      ? (spec.config as { height?: number })
      : null;
  const configHeight = typeof config?.height === 'number' ? config.height : null;
  return Math.max(directHeight ?? configHeight ?? FALLBACK_VISUAL_PLACEHOLDER_HEIGHT, 120);
}

function buildHighlightComponents(highlights: TextHighlight[]): Components {
  const wrap = (Tag: string) =>
    function HighlightWrapper({ children, ...props }: Record<string, unknown>) {
      return (
        // @ts-expect-error -- dynamic tag
        <Tag {...props}>
          {highlightTextChildren(children as React.ReactNode, highlights)}
        </Tag>
      );
    };

  return {
    p: wrap('p'),
    li: wrap('li'),
    h1: wrap('h1'),
    h2: wrap('h2'),
    h3: wrap('h3'),
    h4: wrap('h4'),
    h5: wrap('h5'),
    h6: wrap('h6'),
    blockquote: wrap('blockquote'),
    td: wrap('td'),
    th: wrap('th'),
  };
}

function EntityPanelContentComponent({
  entity,
  isNodeSelected,
  isTransientRender = false,
}: EntityPanelContentProps) {
  const { id, display_name } = entity;
  const currentEntities = useGraphCurrentEntities();
  const textRef = useRef<HTMLDivElement>(null);

  const originalEntity = useMemo(
    () => findEntityById(currentEntities || [], entity),
    [currentEntities, entity]
  );

  const rawData = useMemo(
    () => originalEntity || entity,
    [originalEntity, entity]
  );

  const content_type = rawData.type || 'unknown';
  const content_value = rawData.value || 'No value';

  const highlights = useHighlightStore(
    useCallback((s) => s.highlights.get(id) ?? EMPTY_HIGHLIGHTS, [id]),
  );
  const clearHighlights = useHighlightStore((s) => s.clearHighlights);

  const markdownComponents = useMemo(
    () => (highlights.length > 0 ? buildHighlightComponents(highlights) : undefined),
    [highlights],
  );

  const vegaSpec = useMemo(
    () => content_type === 'visual' && content_value && typeof content_value === 'object'
      ? content_value as Record<string, unknown>
      : null,
    [content_type, content_value]
  );
  const vegaOptions = useMemo(
    () => ({
      renderer: 'canvas',
      actions: false,
    }),
    []
  );
  const transientSnapshot = useMemo(
    () => (vegaSpec ? getCanvasSnapshot(vegaSpec) : null),
    [vegaSpec],
  );
  const visualPlaceholderHeight = useMemo(
    () => resolveVisualPlaceholderHeight(vegaSpec),
    [vegaSpec],
  );
  
  return (
    <div className="entity-panel-content">

      <div className="entity-header">
        <span className="entity-id">ID: {id}</span>
        <span className="entity-id">{display_name}</span>
      </div>

      <div className="entity-section">
        <div className="entity-type-row">
          <h4>Type: {content_type}</h4>
          {content_type === 'text' && highlights.length > 0 && (
            <button
              className="clear-highlights-btn nodrag"
              onClick={() => clearHighlights(id)}
              title="Clear all highlights"
              type="button"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <path d="m15 9-6 6" />
                <path d="m9 9 6 6" />
              </svg>
            </button>
          )}
        </div>
        {content_type === 'text' && (
          <>
            <div
              ref={textRef}
              className={[
                'entity-text-markdown',
                isNodeSelected ? 'nowheel' : '',
                isNodeSelected ? 'nodrag' : '',
                isNodeSelected ? 'entity-text-markdown--selectable' : 'entity-text-markdown--locked',
              ].join(' ')}
              style={{ userSelect: isNodeSelected ? 'text' : 'none' }}
            >
              <ReactMarkdown components={markdownComponents}>
                {normalizeMarkdownInput(String(content_value))}
              </ReactMarkdown>
            </div>
            <TextSelectionToolbar containerRef={textRef} entityId={id} enabled={isNodeSelected} />
          </>
        )}

        {content_type === 'visual' && vegaSpec && !isTransientRender && (
          <LazyVegaChart spec={vegaSpec} options={vegaOptions} />
        )}

        {content_type === 'visual' && vegaSpec && isTransientRender && (
          transientSnapshot ? (
            <div className="lazy-vega-chart__snapshot">
              <img
                src={transientSnapshot}
                alt="Chart preview"
                style={{ width: '100%', height: 'auto', display: 'block' }}
              />
              <div className="lazy-vega-chart__snapshot-overlay">Moving chart...</div>
            </div>
          ) : (
            <div
              className="lazy-vega-chart__placeholder"
              style={{ minHeight: visualPlaceholderHeight }}
            >
              Moving chart...
            </div>
          )
        )}

        {content_type === 'visual' && !vegaSpec && (
          <div>Invalid chart specification</div>
        )}

        {content_type === 'image' && content_value && (
          <div className="entity-image-container">
            <img
              src={String(content_value)}
              alt={display_name || 'Image entity'}
              className="entity-image"
              draggable={false}
            />
          </div>
        )}

        {content_type !== 'text' && content_type !== 'visual' && content_type !== 'image' && (
          <pre className="metadata-dump">
            {JSON.stringify(content_value, null, 2)}
          </pre>
        )}
      </div>

    </div>
  );
}

export const EntityPanelContent = memo(EntityPanelContentComponent, areEntityPanelPropsEqual);
