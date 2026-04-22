/**
 * TokenBudgetBar — Visual token usage gauge.
 */

import React from 'react';
import { Box, Text } from 'ink';

interface Props {
  used: number;
  limit: number;
  width?: number;
}

export function TokenBudgetBar({ used, limit, width = 30 }: Props) {
  const pct = Math.min(used / limit, 1);
  const filled = Math.round(pct * width);
  const empty = width - filled;
  const color = pct > 0.9 ? 'red' : pct > 0.7 ? 'yellow' : 'green';

  const formatNum = (n: number) => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
    return String(n);
  };

  return (
    <Box gap={1}>
      <Text color="gray">Tokens:</Text>
      <Text color={color}>{'█'.repeat(filled)}</Text>
      <Text color="gray">{'░'.repeat(empty)}</Text>
      <Text color={color}>{formatNum(used)}</Text>
      <Text color="gray">/ {formatNum(limit)}</Text>
      <Text color={color}> ({(pct * 100).toFixed(0)}%)</Text>
    </Box>
  );
}
