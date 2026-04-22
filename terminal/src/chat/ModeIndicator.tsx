/**
 * ModeIndicator — Colored badge showing current chat mode.
 *
 * green = Chat, blue = Plan, yellow = Edit
 */

import React from 'react';
import { Box, Text } from 'ink';

const MODE_COLORS: Record<string, string> = {
  chat: 'green',
  plan: 'blue',
  edit: 'yellow',
};

interface Props {
  mode: 'chat' | 'plan' | 'edit';
}

export function ModeIndicator({ mode }: Props) {
  const color = MODE_COLORS[mode] ?? 'white';
  const label = mode.charAt(0).toUpperCase() + mode.slice(1);

  return (
    <Box>
      <Text color={color} bold inverse>{` ${label} `}</Text>
    </Box>
  );
}
