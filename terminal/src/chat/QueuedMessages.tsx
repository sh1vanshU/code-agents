/**
 * QueuedMessages — Inline display of pending queued messages above the input.
 *
 * Matches Claude Code's queue UI: shows first N queued messages with a `>`
 * prefix and a "+ M more" hint if the queue is long. Keeps the screen usable
 * even with hundreds of queued messages.
 */

import React from 'react';
import { Box, Text } from 'ink';
import { useChatStore, MAX_QUEUE_SIZE } from '../state/store.js';

const MAX_LINE = 100;

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max - 1) + '…' : s;
}

export function QueuedMessages() {
  const queue = useChatStore((s) => s.messageQueue);

  if (queue.length === 0) return null;

  const isFull = queue.length >= MAX_QUEUE_SIZE;

  return (
    <Box flexDirection="column" marginBottom={1}>
      {queue.map((msg, i) => (
        <Box key={i}>
          <Text color="gray" dimColor>{'> '}</Text>
          <Text color="gray" dimColor>{truncate(msg, MAX_LINE)}</Text>
        </Box>
      ))}
      <Box marginTop={0}>
        <Text color={isFull ? 'red' : 'gray'} dimColor italic>
          {'  '}
          {isFull
            ? `Queue full (${queue.length}/${MAX_QUEUE_SIZE}) — wait for agent to process before adding more`
            : `${queue.length}/${MAX_QUEUE_SIZE} queued — agent will process in order`}
        </Text>
      </Box>
    </Box>
  );
}
