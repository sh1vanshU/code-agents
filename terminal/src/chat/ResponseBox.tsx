/**
 * ResponseBox — Bordered assistant response with agent name header.
 *
 * Memoized so finished messages don't re-render when new messages arrive.
 */

import React from 'react';
import { Box, Text } from 'ink';
import { MarkdownRenderer } from './MarkdownRenderer.js';

interface Props {
  agent: string;
  content: string;
}

function ResponseBoxImpl({ agent, content }: Props) {
  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor="cyan"
      paddingX={1}
      marginBottom={1}
    >
      <Box marginBottom={1}>
        <Text color="cyan" bold>{agent}</Text>
      </Box>
      <MarkdownRenderer content={content} />
    </Box>
  );
}

export const ResponseBox = React.memo(
  ResponseBoxImpl,
  (prev, next) => prev.content === next.content && prev.agent === next.agent,
);
