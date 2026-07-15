import { memo, useCallback, useEffect, useState, type PointerEvent } from 'react';
import { useAppStore } from '@/stores/appStore';
import './EntityPanel.css';

type EntityNodeTagsProps = {
  entityId: string;
  selected: boolean;
};

export const EntityNodeTags = memo(function EntityNodeTags({
  entityId,
  selected,
}: EntityNodeTagsProps) {
  const entityTags = useAppStore((s) => s.graph.entityTags[entityId]);
  const addEntityTags = useAppStore((s) => s.graph.addEntityTags);
  const removeEntityTags = useAppStore((s) => s.graph.removeEntityTags);
  const [tagInput, setTagInput] = useState('');
  const [isOverlayOpen, setIsOverlayOpen] = useState(false);

  const commitAdd = useCallback(() => {
    const trimmed = tagInput.trim();
    if (!trimmed) return;
    addEntityTags(entityId, [trimmed]);
    setTagInput('');
  }, [addEntityTags, entityId, tagInput]);

  const onRemoveTag = useCallback(
    (tag: string) => {
      removeEntityTags(entityId, [tag]);
    },
    [entityId, removeEntityTags],
  );

  const onTagRowPointerDown = useCallback((e: PointerEvent<HTMLDivElement>) => {
    e.stopPropagation();
  }, []);

  useEffect(() => {
    if (!selected) {
      setIsOverlayOpen(false);
      setTagInput('');
    }
  }, [selected]);

  const tags = entityTags && entityTags.length > 0 ? entityTags : [];
  const showBar = tags.length > 0 || selected;
  if (!showBar) return null;

  return (
    <div
      className="entity-node-tags nodrag"
      onPointerDown={onTagRowPointerDown}
    >
      {tags.length > 0 ? (
        <div className="entity-node-tags__chips">
          {tags.map((tag, i) => (
            <span
              key={`${tag}-${i}`}
              className="entity-node-tags__chip"
              title={tag}
            >
              <span className="entity-node-tags__chip-label">{tag}</span>
              {selected ? (
                <button
                  type="button"
                  className="entity-node-tags__chip-remove"
                  aria-label={`Remove tag ${tag}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onRemoveTag(tag);
                  }}
                >
                  ×
                </button>
              ) : null}
            </span>
          ))}
        </div>
      ) : (
        <div />
      )}
      {selected ? (
        <div className="entity-node-tags__controls">
          <button
            type="button"
            className="entity-node-tags__toggle-btn"
            onClick={(e) => {
              e.stopPropagation();
              setIsOverlayOpen((open) => !open);
            }}
          >
            {isOverlayOpen ? 'Close' : 'Tag'}
          </button>
          {isOverlayOpen ? (
            <div className="entity-node-tags__overlay" onPointerDown={onTagRowPointerDown}>
              <div className="entity-node-tags__add-row">
                <input
                  type="text"
                  className="entity-node-tags__input"
                  placeholder="Add tag…"
                  value={tagInput}
                  onChange={(e) => setTagInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      e.stopPropagation();
                      commitAdd();
                    }
                    if (e.key === 'Escape') {
                      e.preventDefault();
                      e.stopPropagation();
                      setIsOverlayOpen(false);
                    }
                  }}
                  onClick={(e) => e.stopPropagation()}
                  autoFocus
                />
                <button
                  type="button"
                  className="entity-node-tags__add-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    commitAdd();
                  }}
                >
                  Add
                </button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
});
