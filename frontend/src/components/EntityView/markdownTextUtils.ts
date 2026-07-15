/**
 * Normalize incoming markdown-like text so rendering and measurement paths
 * operate on the same newline semantics.
 */
export function normalizeMarkdownInput(content: string): string {
  const normalized = content.replace(/\r\n/g, '\n');
  // If no real newlines exist, interpret literal \n sequences as newlines.
  const withNormalizedBreaks = normalized.includes('\n')
    ? normalized
    : normalized.replace(/\\n/g, '\n');
  // ReactMarkdown generally collapses trailing blank lines in output; keep
  // measurement/rendering aligned by trimming only trailing whitespace.
  return withNormalizedBreaks.trimEnd();
}
