/**
 * StreamingResponse — Live SSE token display with spinner and elapsed timer.
 */

import React, { useState, useEffect, useRef } from 'react';
import { Box, Text } from 'ink';
import Spinner from 'ink-spinner';
import { MarkdownRenderer } from './MarkdownRenderer.js';

interface Props {
  content: string;
  isStreaming: boolean;
}

export function StreamingResponse({ content, isStreaming }: Props) {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef<number>(Date.now());

  useEffect(() => {
    if (!isStreaming) {
      setElapsed(0);
      startRef.current = Date.now();
      return;
    }

    startRef.current = Date.now();
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startRef.current) / 1000));
    }, 1000);

    return () => clearInterval(interval);
  }, [isStreaming]);

  if (!isStreaming) {
    return null;
  }

  // Before first token — show thinking spinner
  if (!content) {
    return (
      <Box marginBottom={1}>
        <Text color="yellow">
          <Spinner type="dots" />
        </Text>
        <Text color="yellow"> Thinking...</Text>
        <Text color="gray"> ({elapsed}s)</Text>
      </Box>
    );
  }

  // Streaming content
  return (
    <Box flexDirection="column" marginBottom={1}>
      <Box>
        <Text color="cyan">
          <Spinner type="dots" />
        </Text>
        <Text color="gray"> streaming ({elapsed}s)</Text>
      </Box>
      <Box marginTop={1}>
        <MarkdownRenderer content={content} />
      </Box>
    </Box>
  );
}
