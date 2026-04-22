/**
 * AgentSelector — interactive agent picker with arrow-key navigation.
 */

import React, { useState } from 'react';
import { Box, Text, useInput } from 'ink';

export interface AgentOption {
  name: string;
  description: string;
}

interface Props {
  agents: AgentOption[];
  onSelect: (agent: string) => void;
  onCancel: () => void;
}

export function AgentSelector({ agents, onSelect, onCancel }: Props) {
  const [cursor, setCursor] = useState(0);
  const total = agents.length + 1; // +1 for Cancel

  useInput((input, key) => {
    if (key.escape) { onCancel(); return; }
    if (key.return) {
      if (cursor === agents.length) { onCancel(); return; }
      onSelect(agents[cursor].name);
      return;
    }
    if (key.downArrow) setCursor((c) => Math.min(c + 1, total - 1));
    if (key.upArrow) setCursor((c) => Math.max(c - 1, 0));
    // Number keys for direct selection
    const num = parseInt(input, 10);
    if (num >= 1 && num <= agents.length) {
      onSelect(agents[num - 1].name);
    }
    if (input === '0') onCancel();
  });

  return (
    <Box flexDirection="column" paddingLeft={2}>
      <Text bold>Select an agent:</Text>
      <Text> </Text>
      {agents.map((a, i) => (
        <Text key={a.name}>
          {'  '}
          {i === cursor ? '❯ ' : '  '}
          <Text bold={i === cursor}>{`${i + 1}. ${a.name.padEnd(22)}`}</Text>
          <Text dimColor>{a.description}</Text>
        </Text>
      ))}
      <Text>
        {'  '}
        {cursor === agents.length ? '❯ ' : '  '}
        <Text bold={cursor === agents.length}>0. Cancel</Text>
      </Text>
      <Text dimColor>  ↑↓ navigate · Enter select · Esc cancel</Text>
    </Box>
  );
}
