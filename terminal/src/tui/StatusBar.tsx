/**
 * StatusBar — Bottom bar showing mode, agent, tokens, elapsed time.
 */

import React from 'react';
import { Box, Text } from 'ink';

interface Props {
  mode: 'chat' | 'plan' | 'edit';
  agent: string;
  tokenCount: number;
  elapsed?: number;
  serverAlive: boolean;
}

const MODE_COLORS: Record<string, string> = {
  chat: 'green',
  plan: 'blue',
  edit: 'yellow',
};

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export function StatusBar({ mode, agent, tokenCount, elapsed, serverAlive }: Props) {
  return (
    <Box borderStyle="single" borderColor="gray" paddingX={1} justifyContent="space-between">
      <Box gap={2}>
        <Text bold inverse color={MODE_COLORS[mode] || 'white'}>
          {' '}{mode.toUpperCase()}{' '}
        </Text>
        <Text color="cyan">{agent}</Text>
        <Text color={serverAlive ? 'green' : 'red'}>
          {serverAlive ? '●' : '○'}
        </Text>
      </Box>
      <Box gap={2}>
        {elapsed !== undefined && (
          <Text color="gray">{elapsed.toFixed(1)}s</Text>
        )}
        <Text color="gray">{formatTokens(tokenCount)} tokens</Text>
      </Box>
    </Box>
  );
}
