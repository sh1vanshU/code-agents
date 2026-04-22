/**
 * ChatInput — Bordered input box with placeholder + queue indicator.
 *
 * Always active — user can type while agent is streaming.
 * Messages are queued and processed in order when agent finishes.
 */

import React, { useState } from 'react';
import { Box, Text } from 'ink';
import TextInput from 'ink-text-input';
import { useChatStore, MAX_QUEUE_SIZE } from '../state/store.js';

interface Props {
  onSubmit: (value: string) => void;
  disabled?: boolean; // kept for API compat
}

export function ChatInput({ onSubmit }: Props) {
  const [value, setValue] = useState('');
  const isBusy = useChatStore((s) => s.isBusy);
  const tokenUsage = useChatStore((s) => s.tokenUsage);
  const queueLength = useChatStore((s) => s.messageQueue.length);

  const totalTokens = tokenUsage.input + tokenUsage.output;

  const handleSubmit = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setValue('');
    onSubmit(trimmed);
  };

  const queueFull = queueLength >= MAX_QUEUE_SIZE;
  const queueHint = isBusy && queueLength > 0
    ? queueFull
      ? ` (queue full ${queueLength}/${MAX_QUEUE_SIZE})`
      : ` (${queueLength}/${MAX_QUEUE_SIZE} queued)`
    : '';

  const placeholder = queueFull
    ? 'Queue full — wait for agent to process…'
    : isBusy
      ? 'Type to queue…'
      : 'Type a message…';

  return (
    <Box
      borderStyle="round"
      borderColor={queueFull ? 'red' : 'cyan'}
      paddingX={1}
      width="100%"
    >
      <Text color={queueFull ? 'red' : 'cyan'} bold>{'> '}</Text>
      <TextInput
        value={value}
        onChange={setValue}
        onSubmit={handleSubmit}
        placeholder={placeholder}
      />
      <Box flexGrow={1} />
      <Text color="gray" dimColor>
        {queueHint}
        {totalTokens > 0 ? ` ${totalTokens} tokens` : ''}
      </Text>
    </Box>
  );
}
