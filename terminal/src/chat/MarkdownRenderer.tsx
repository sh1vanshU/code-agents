/**
 * MarkdownRenderer — Rich terminal markdown via marked + marked-terminal.
 *
 * Converts markdown to ANSI-styled terminal output using chalk coloring.
 * Memoized: re-renders only when content actually changes, avoiding
 * expensive marked.parse() calls on every streaming token.
 */

import React, { useMemo } from 'react';
import { Text } from 'ink';
import { marked } from 'marked';
import { markedTerminal } from 'marked-terminal';

// Configure marked with the terminal renderer once
marked.use(markedTerminal({ tab: 2 }) as any);

interface Props {
  content: string;
}

function MarkdownRendererImpl({ content }: Props) {
  const rendered = useMemo(() => {
    if (!content) return '';
    try {
      return (marked.parse(content) as string).trimEnd();
    } catch {
      return content;
    }
  }, [content]);

  if (!rendered) return null;
  return <Text>{rendered}</Text>;
}

// Memo: only re-render when content changes (not on parent re-renders)
export const MarkdownRenderer = React.memo(
  MarkdownRendererImpl,
  (prev, next) => prev.content === next.content,
);
