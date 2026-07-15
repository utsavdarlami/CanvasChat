import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useHighlightStore } from '@/stores/highlightStore';

interface TextSelectionToolbarProps {
  containerRef: React.RefObject<HTMLDivElement | null>;
  entityId: string;
  enabled: boolean;
}

interface ToolbarPosition {
  x: number;
  y: number;
}

const TOOLBAR_OFFSET_Y = 8;

export function TextSelectionToolbar({ containerRef, entityId, enabled }: TextSelectionToolbarProps) {
  const [selectedText, setSelectedText] = useState('');
  const [position, setPosition] = useState<ToolbarPosition | null>(null);
  const toolbarRef = useRef<HTMLDivElement>(null);
  const addHighlight = useHighlightStore((s) => s.addHighlight);

  const checkSelection = useCallback(() => {
    if (!enabled || !containerRef.current) {
      setSelectedText('');
      setPosition(null);
      return;
    }

    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) {
      setSelectedText('');
      setPosition(null);
      return;
    }

    const text = selection.toString().trim();
    if (!text) {
      setSelectedText('');
      setPosition(null);
      return;
    }

    const anchorInContainer = containerRef.current.contains(selection.anchorNode);
    const focusInContainer = containerRef.current.contains(selection.focusNode);
    if (!anchorInContainer || !focusInContainer) {
      setSelectedText('');
      setPosition(null);
      return;
    }

    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();

    setSelectedText(text);
    setPosition({
      x: rect.left + rect.width / 2,
      y: rect.top - TOOLBAR_OFFSET_Y,
    });
  }, [containerRef, enabled]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !enabled) return;

    const handleMouseUp = () => {
      requestAnimationFrame(checkSelection);
    };

    const handleSelectionChange = () => {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed) {
        setSelectedText('');
        setPosition(null);
      }
    };

    container.addEventListener('mouseup', handleMouseUp);
    document.addEventListener('selectionchange', handleSelectionChange);

    return () => {
      container.removeEventListener('mouseup', handleMouseUp);
      document.removeEventListener('selectionchange', handleSelectionChange);
    };
  }, [containerRef, checkSelection, enabled]);

  useEffect(() => {
    if (enabled) return;
    window.getSelection()?.removeAllRanges();
    setSelectedText('');
    setPosition(null);
  }, [enabled]);

  // Dismiss when clicking outside the toolbar
  useEffect(() => {
    if (!position) return;

    const handlePointerDown = (e: PointerEvent) => {
      if (toolbarRef.current?.contains(e.target as Node)) return;
      // Let the mouseup handler on the container re-evaluate
    };

    document.addEventListener('pointerdown', handlePointerDown, true);
    return () => document.removeEventListener('pointerdown', handlePointerDown, true);
  }, [position]);

  const handleHighlight = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    if (!selectedText) return;

    addHighlight(entityId, selectedText);
    window.getSelection()?.removeAllRanges();
    setSelectedText('');
    setPosition(null);
  }, [entityId, selectedText, addHighlight]);

  if (!enabled || !position || !selectedText) return null;

  const toolbarStyle: React.CSSProperties = {
    position: 'fixed',
    left: position.x,
    top: position.y,
    transform: 'translate(-50%, -100%)',
    zIndex: 10000,
  };

  return createPortal(
    <div
      ref={toolbarRef}
      className="text-selection-toolbar"
      style={toolbarStyle}
      onMouseDown={(e) => e.stopPropagation()}
    >
      <button
        className="text-selection-toolbar-btn"
        onClick={handleHighlight}
        title="Highlight selected text"
        type="button"
      >
        <HighlightIcon />
      </button>
    </div>,
    document.body,
  );
}

function HighlightIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
    </svg>
  );
}
