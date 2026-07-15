import { prepare, layout, type PreparedText } from '@chenglou/pretext';
import type { GraphNode, EntityRecord } from '@/types/graph';
import { normalizeMarkdownInput } from './markdownTextUtils';

// Default sizes
export const DEFAULT_TEXT_NODE_WIDTH = 400;
export const DEFAULT_TEXT_NODE_HEIGHT = 300;
export const MIN_TEXT_NODE_HEIGHT = 150;
export const MAX_TEXT_NODE_HEIGHT = 1500;
export const DEFAULT_IMAGE_NODE_WIDTH = 300;
export const DEFAULT_IMAGE_NODE_HEIGHT = 450;
export const DEFAULT_VISUAL_NODE_WIDTH = 400;
export const DEFAULT_VISUAL_NODE_HEIGHT = 300;
// Visual nodes include non-chart UI chrome (header, controls, wrappers, padding).
// Keep these offsets in sync with EntityPanel.css / EntityPanelContent layout.
export const VISUAL_NODE_HORIZONTAL_CHROME = 48;
export const VISUAL_NODE_VERTICAL_CHROME = 156;

// Horizontal padding: content-wrapper (10×2) + panel-content (12×2)
const TEXT_NODE_HORIZONTAL_CHROME = 44;
// Fixed vertical padding that doesn't scale with font:
// content-wrapper padding (10×2) + panel-content padding (12×2) + borders/gaps
const FIXED_VERTICAL_PADDING = 50;
// Chrome lines that scale with font: ID, display_name, "Type: text" header
const CHROME_LINE_COUNT = 3;
// Extra per-chrome-line spacing (margins between header elements)
const CHROME_LINE_MARGIN = 6;

// Base font for Pretext measurement (0.85rem ≈ 13.6px)
const BASE_FONT_PX = 13.6;
const BASE_LINE_HEIGHT = 20; // 13.6 * 1.45
const BASE_FONT_STR = `400 ${BASE_FONT_PX}px "Geist Mono", "SF Mono", "Fira Code", monospace`;

// Optimal font size bounds
const MIN_FONT_PX = 10;
const MAX_FONT_PX = 26;
// Keep a small gutter for occasional scrollbar appearance without over-wrapping
// during measurement.
const SCROLLBAR_WIDTH_ESTIMATE_PX = 6;
// Tiny safety room for sub-pixel differences.
const TEXT_FIT_HEIGHT_SAFETY_PX = 2;

// Keep multiplier neutral; extra buffer here tends to create visible bottom gaps.
const MARKDOWN_HEIGHT_BUFFER = 1.0;

// Cache prepared text to avoid repeated DOM measurement
const preparedTextCache = new Map<string, PreparedText>();

function stripMarkdown(text: string): string {
  return text
    .replace(/^#{1,6}\s+/gm, '')        // headings
    .replace(/(\*{1,3}|_{1,3})(.*?)\1/g, '$2') // bold/italic
    .replace(/`{1,3}[^`]*`{1,3}/g, (m) => m.replace(/`/g, '')) // inline code
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')  // links
    .replace(/^[-*+]\s+/gm, '• ')       // unordered lists
    .replace(/^\d+\.\s+/gm, '  ')       // ordered lists
    .replace(/^>\s?/gm, '')             // blockquotes
    .replace(/!\[.*?\]\(.*?\)/g, '');   // images
}

function getPreparedTextFromNormalizedText(normalizedText: string): PreparedText {
  const plain = stripMarkdown(normalizedText);
  // Use full normalized+stripped text in the key to avoid collisions from
  // truncated prefixes. Include measurement config for future-proofing.
  const cacheKey = `v2|font=${BASE_FONT_STR}|ws=pre-wrap|text=${plain}`;

  let prepared = preparedTextCache.get(cacheKey);
  if (!prepared) {
    // Use pre-wrap so newlines are preserved as forced line breaks,
    // matching how ReactMarkdown renders paragraphs with white-space: pre-wrap
    prepared = prepare(plain, BASE_FONT_STR, { whiteSpace: 'pre-wrap' });
    preparedTextCache.set(cacheKey, prepared);
    if (preparedTextCache.size > 500) {
      const firstKey = preparedTextCache.keys().next().value;
      if (firstKey !== undefined) preparedTextCache.delete(firstKey);
    }
  }
  return prepared;
}

function measureTextHeightAtFont(
  prepared: PreparedText,
  availableWidth: number,
  fontPx: number,
): number {
  // For monospace: scaling font by S scales all char widths by S.
  // Instead of re-preparing at each font size, we measure at base font
  // with inversely-scaled width, then scale the result.
  const scale = fontPx / BASE_FONT_PX;
  const scaledWidth = availableWidth / scale;
  const { height } = layout(prepared, scaledWidth, BASE_LINE_HEIGHT);
  return height * scale * MARKDOWN_HEIGHT_BUFFER;
}

// Tags are absolutely positioned at top: 8px, overlaying content.
// Each chip row is ~22px tall with 4px gap. They reduce visible content area.
const TAGS_TOP_OFFSET = 8;   // CSS top: 8px
const TAGS_ROW_HEIGHT = 26;  // one row of tag chips (~22px + 4px gap)
const TAGS_PER_ROW = 5;      // approximate chips per row at default width
const TAGS_BOTTOM_CLEARANCE = 4; // visual gap between tags and title/content

// Adjacent paragraph margins collapse in CSS, so each markdown paragraph break
// contributes roughly one side of our 0.35em paragraph margin.
const PARAGRAPH_MARGIN_EM = 0.35;

function countParagraphBreaks(text: string): number {
  const matches = text.match(/\n\s*\n/g);
  return matches ? matches.length : 0;
}

function estimateTagsOverlayHeight(tagCount: number): number {
  if (tagCount === 0) return 0;
  const rows = Math.ceil(tagCount / TAGS_PER_ROW);
  return TAGS_TOP_OFFSET + rows * TAGS_ROW_HEIGHT + TAGS_BOTTOM_CLEARANCE;
}

export function getTagOverlayOffset(tagCount: number): number {
  return estimateTagsOverlayHeight(tagCount);
}

/**
 * Compute the largest font size (px) where the full text content fits
 * within the given node dimensions, accounting for header chrome, tags, and paragraphs.
 */
export function computeOptimalFontSize(
  text: string,
  nodeWidth: number,
  nodeHeight: number,
  tagCount: number = 0,
): number {
  const normalizedText = normalizeMarkdownInput(text);
  const prepared = getPreparedTextFromNormalizedText(normalizedText);
  const textAreaWidth = Math.max(
    nodeWidth - TEXT_NODE_HORIZONTAL_CHROME - SCROLLBAR_WIDTH_ESTIMATE_PX,
    1,
  );
  const paragraphBreaks = countParagraphBreaks(normalizedText);
  const tagsHeight = estimateTagsOverlayHeight(tagCount);

  let lo = MIN_FONT_PX;
  let hi = MAX_FONT_PX;

  for (let i = 0; i < 10; i++) {
    const mid = (lo + hi) / 2;
    const lineHeight = mid * 1.45;
    // Chrome height: fixed padding + scaled header lines + tags
    const chromeHeight = FIXED_VERTICAL_PADDING
      + CHROME_LINE_COUNT * (lineHeight + CHROME_LINE_MARGIN)
      + tagsHeight;
    const availableHeight = nodeHeight - chromeHeight - TEXT_FIT_HEIGHT_SAFETY_PX;

    if (availableHeight <= 0) {
      hi = mid;
      continue;
    }

    const textHeight = measureTextHeightAtFont(prepared, textAreaWidth, mid);
    // Add paragraph margin gaps that Pretext doesn't model
    const paragraphGaps = paragraphBreaks * PARAGRAPH_MARGIN_EM * mid;
    if (textHeight + paragraphGaps <= availableHeight) {
      lo = mid;
    } else {
      hi = mid;
    }
  }

  // `lo` is the last known fitting value. Never round it up, or it can exceed
  // the fitting boundary and reintroduce tiny scrollbars.
  return Math.max(MIN_FONT_PX, Math.floor(lo * 10) / 10);
}

function measureTextHeight(text: string, availableWidth: number): number {
  const normalizedText = normalizeMarkdownInput(text);
  const prepared = getPreparedTextFromNormalizedText(normalizedText);
  const { height } = layout(prepared, availableWidth, BASE_LINE_HEIGHT);
  const paragraphGaps = countParagraphBreaks(normalizedText) * PARAGRAPH_MARGIN_EM * BASE_FONT_PX;
  return Math.ceil(height * MARKDOWN_HEIGHT_BUFFER + paragraphGaps);
}

type VegaSpecDimensionValue =
  | number
  | {
      step?: number;
    }
  | string
  | undefined;

interface VegaSpecLike {
  width?: VegaSpecDimensionValue;
  height?: VegaSpecDimensionValue;
  config?: {
    width?: VegaSpecDimensionValue;
    height?: VegaSpecDimensionValue;
  };
}

function toPositiveNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
    ? value
    : null;
}

function resolveDimension(value: VegaSpecDimensionValue): number | null {
  if (typeof value === 'number') return toPositiveNumber(value);
  if (value && typeof value === 'object') {
    const stepValue = (value as { step?: unknown }).step;
    return toPositiveNumber(stepValue);
  }
  return null;
}

/**
 * Extract dimensions from Vega-Lite spec
 * For visual charts, uses actual spec dimensions without bounds - no minimum size constraints
 */
export const getVegaSpecDimensions = (spec: unknown): { width: number; height: number } => {
  if (!spec || typeof spec !== 'object') {
    return { width: DEFAULT_VISUAL_NODE_WIDTH, height: DEFAULT_VISUAL_NODE_HEIGHT };
  }

  const typedSpec = spec as VegaSpecLike;

  // Vega-Lite specs can have width/height at top level or in config
  const specWidth = resolveDimension(typedSpec.width) ?? resolveDimension(typedSpec.config?.width);
  const specHeight = resolveDimension(typedSpec.height) ?? resolveDimension(typedSpec.config?.height);

  const fallbackChartWidth = Math.max(DEFAULT_VISUAL_NODE_WIDTH - VISUAL_NODE_HORIZONTAL_CHROME, 200);
  const fallbackChartHeight = Math.max(DEFAULT_VISUAL_NODE_HEIGHT - VISUAL_NODE_VERTICAL_CHROME, 140);

  // If at least one dimension is provided, preserve that axis and infer the other.
  if (specWidth !== null || specHeight !== null) {
    const chartWidth = Math.max(specWidth ?? fallbackChartWidth, 200);
    const chartHeight = Math.max(specHeight ?? fallbackChartHeight, 140);
    return {
      width: Math.max(chartWidth + VISUAL_NODE_HORIZONTAL_CHROME, DEFAULT_VISUAL_NODE_WIDTH),
      height: Math.max(chartHeight + VISUAL_NODE_VERTICAL_CHROME, DEFAULT_VISUAL_NODE_HEIGHT),
    };
  }

  // Fallback to defaults only if spec doesn't specify dimensions
  return {
    width: DEFAULT_VISUAL_NODE_WIDTH,
    height: DEFAULT_VISUAL_NODE_HEIGHT,
  };
};

/**
 * Helper to find an entity in the list by matching various ID fields
 */
export const findEntityById = (
  entities: EntityRecord[],
  idOrNode: string | GraphNode
): EntityRecord | undefined => {
  if (!entities) return undefined;
  
  const searchId = typeof idOrNode === 'string' ? idOrNode : idOrNode.id;
  // We also need to handle the case where the input is a node object with entity_id
  const entityId = typeof idOrNode === 'object' ? idOrNode.entity_id : undefined;

  return entities.find((e) => {
    // Match against primary ID
    if (e.id === searchId) return true;
    // Match against entity_id
    if (e.entity_id === searchId) return true;
    
    // If we have a secondary ID from the input node, check that too
    if (entityId) {
      if (e.id === entityId) return true;
      if (e.entity_id === entityId) return true;
    }
    
    return false;
  });
};

/**
 * Get node dimensions based on entity type and content
 */
export const getNodeDimensions = (
  node: GraphNode,
  currentEntities: EntityRecord[]
): { width: number; height: number } => {
  // If the backend explicitly set dimensions (resize/maximize), use those
  if (node.nodeWidth != null && node.nodeHeight != null) {
    return { width: node.nodeWidth, height: node.nodeHeight };
  }

  // Lookup original entity data
  const originalEntity = findEntityById(currentEntities, node);
  const rawData = originalEntity || node;

  const content_type = rawData.type || 'unknown';
  const content_value = rawData.value;

  if (content_type === 'visual' && content_value && typeof content_value === 'object') {
    return getVegaSpecDimensions(content_value);
  }

  if (content_type === 'image') {
    return {
      width: DEFAULT_IMAGE_NODE_WIDTH,
      height: DEFAULT_IMAGE_NODE_HEIGHT,
    };
  }

  // Measure text content to determine height
  if (content_type === 'text' && content_value) {
    const textStr = String(content_value);
    const availableWidth = Math.max(
      DEFAULT_TEXT_NODE_WIDTH - TEXT_NODE_HORIZONTAL_CHROME - SCROLLBAR_WIDTH_ESTIMATE_PX,
      1,
    );
    const textHeight = measureTextHeight(textStr, availableWidth);
    const totalHeight = textHeight + FIXED_VERTICAL_PADDING
      + CHROME_LINE_COUNT * (BASE_LINE_HEIGHT + CHROME_LINE_MARGIN);
    return {
      width: DEFAULT_TEXT_NODE_WIDTH,
      height: Math.min(Math.max(totalHeight, MIN_TEXT_NODE_HEIGHT), MAX_TEXT_NODE_HEIGHT),
    };
  }

  // Default size for unknown types
  return {
    width: DEFAULT_TEXT_NODE_WIDTH,
    height: DEFAULT_TEXT_NODE_HEIGHT,
  };
};
