import React, { ReactNode } from 'react';
import type { TextHighlight } from '@/stores/highlightStore';

/**
 * Recursively walk a React children tree and wrap substrings that match
 * any highlight entry in `<mark>` elements. Designed to be used inside
 * ReactMarkdown custom component renderers.
 */
export function highlightTextChildren(
  children: ReactNode,
  highlights: TextHighlight[],
): ReactNode {
  if (highlights.length === 0) return children;

  return React.Children.map(children, (child) => {
    if (typeof child === 'string') {
      return applyHighlightsToString(child, highlights);
    }

    if (React.isValidElement(child) && child.props.children) {
      return React.cloneElement(
        child,
        undefined,
        highlightTextChildren(child.props.children, highlights),
      );
    }

    return child;
  });
}

function applyHighlightsToString(
  text: string,
  highlights: TextHighlight[],
): ReactNode[] {
  const sortedHighlights = [...highlights].sort(
    (a, b) => b.text.length - a.text.length,
  );

  const pattern = sortedHighlights
    .map((h) => escapeRegex(h.text))
    .join('|');

  if (!pattern) return [text];

  const regex = new RegExp(`(${pattern})`, 'gi');
  const parts = text.split(regex);

  if (parts.length === 1) return [text];

  const colorMap = new Map(
    sortedHighlights.map((h) => [h.text.toLowerCase(), h.color]),
  );

  return parts.map((part, i) => {
    const color = colorMap.get(part.toLowerCase());
    if (color) {
      return (
        <mark
          key={`hl-${i}`}
          className="text-highlight"
          style={{ backgroundColor: color }}
        >
          {part}
        </mark>
      );
    }
    return part;
  });
}

function escapeRegex(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
