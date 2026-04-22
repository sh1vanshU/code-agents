/**
 * StatusBar — Compact mode hint line below the input box.
 *
 * Mirrors Claude Code's layout:
 *   ⏵⏵ accept edits on (shift+tab to cycle)
 */

import React from 'react';
import { Box, Text } from 'ink';

const MODE_LABELS: Record<string, { icon: string; label: string; color: string }> = {
  chat: { icon: '💬', label: 'chat', color: 'green' },
  plan: { icon: '📋', label: 'plan mode', color: 'blue' },
  edit: { icon: '⏵⏵', label: 'accept edits on', color: 'magenta' },
};

interface Props {
  mode: 'chat' | 'plan' | 'edit';
  isStreaming: boolean;
}

export function StatusBar({ mode, isStreaming }: Props) {
  const modeInfo = MODE_LABELS[mode] || MODE_LABELS.chat;

  return (
    <Box paddingX={1}>
      <Text color={modeInfo.color as any} bold>
        {modeInfo.icon} {modeInfo.label}
      </Text>
      <Text color="gray" dimColor>
        {' '}(shift+tab to cycle)
      </Text>
      {isStreaming && (
        <>
          <Text color="gray" dimColor> · </Text>
          <Text color="red" dimColor>esc to interrupt</Text>
        </>
      )}
    </Box>
  );
}
