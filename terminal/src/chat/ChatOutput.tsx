/**
 * ChatOutput — Scrollable message history display.
 *
 * User messages get a green `>` prefix, assistant messages render
 * inside a bordered ResponseBox with markdown. Each message is memoized
 * so adding a new message doesn't re-parse markdown for old ones.
 */

import React from 'react';
import { Box, Text } from 'ink';
import type { ChatMessage } from '../client/types.js';
import { ResponseBox } from './ResponseBox.js';

interface Props {
  messages: ChatMessage[];
  agent: string;
}

interface MessageRowProps {
  msg: ChatMessage;
  agent: string;
}

function MessageRowImpl({ msg, agent }: MessageRowProps) {
  if (msg.role === 'user') {
    return (
      <Box marginBottom={1}>
        <Text color="green" bold>{'> '}</Text>
        <Text color="green">{msg.content}</Text>
      </Box>
    );
  }

  if (msg.role === 'assistant') {
    return <ResponseBox agent={agent} content={msg.content} />;
  }

  // System messages — render dimmed
  return (
    <Box marginBottom={1}>
      <Text color="gray" dimColor>{msg.content}</Text>
    </Box>
  );
}

// Memo: message rows only re-render when their specific msg changes
const MessageRow = React.memo(
  MessageRowImpl,
  (prev, next) =>
    prev.msg === next.msg &&
    prev.msg.content === next.msg.content &&
    prev.agent === next.agent,
);

export function ChatOutput({ messages, agent }: Props) {
  if (messages.length === 0) {
    return null;
  }

  return (
    <Box flexDirection="column">
      {messages.map((msg, i) => (
        <MessageRow key={i} msg={msg} agent={agent} />
      ))}
    </Box>
  );
}
