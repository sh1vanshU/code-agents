/**
 * ChatApp — Root Ink app component for the terminal chat REPL.
 *
 * Composes all sub-components: WelcomeMessage, ChatOutput,
 * StreamingResponse, CommandApproval, and ChatInput. Wires up
 * useChat hook for main logic and useKeyBindings for shortcuts.
 */

import React, { useState, useCallback, useEffect } from 'react';
import { Box, useApp } from 'ink';
import type { ApiClient } from '../client/ApiClient.js';
import type { AgentService } from '../client/AgentService.js';
import type { ServerMonitor } from '../client/ServerMonitor.js';
import { useChatStore } from '../state/store.js';
import { WelcomeMessage } from './WelcomeMessage.js';
import { ChatOutput } from './ChatOutput.js';
import { StreamingResponse } from './StreamingResponse.js';
import { CommandApproval } from './CommandApproval.js';
import { ChatInput } from './ChatInput.js';
import { QueuedMessages } from './QueuedMessages.js';
import { StatusBar } from './StatusBar.js';
import { useChat } from './hooks/useChat.js';
import { useKeyBindings } from './hooks/useKeyBindings.js';
import { useMessageQueue } from './hooks/useMessageQueue.js';

interface Props {
  client: ApiClient;
  agentService: AgentService;
  monitor: ServerMonitor;
}

export function ChatApp({ client, agentService }: Props) {
  const { exit } = useApp();
  const [inputCleared, setInputCleared] = useState(0);

  const agent = useChatStore((s) => s.agent);
  const mode = useChatStore((s) => s.mode);
  const messages = useChatStore((s) => s.messages);
  const isBusy = useChatStore((s) => s.isBusy);
  const setAgent = useChatStore((s) => s.setAgent);
  const addMessage = useChatStore((s) => s.addMessage);

  // Sync agent from AgentService on mount
  useEffect(() => {
    setAgent(agentService.currentAgent);
  }, [agentService.currentAgent, setAgent]);

  // Find agent description
  const agentInfo = agentService.findAgent(agent);

  const chat = useChat(client);

  const handleSend = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;

    // Built-in quit commands
    if (trimmed === '/quit' || trimmed === '/exit') {
      exit();
      return;
    }

    // Agent switching: /agent <name>
    if (trimmed.startsWith('/agent ')) {
      const name = trimmed.slice(7).trim();
      if (agentService.setAgent(name)) {
        setAgent(name);
      }
      return;
    }

    await chat.sendMessage(trimmed);
  }, [chat, exit, agentService, setAgent]);

  // Message queue — auto-send queued messages when agent finishes
  const { enqueue } = useMessageQueue({ onDequeue: handleSend });

  const handleSubmit = useCallback((text: string) => {
    if (isBusy) {
      const accepted = enqueue(text);
      if (!accepted) {
        addMessage({
          role: 'system',
          content: 'Queue is full (max 5). Wait for the agent to process some messages before queuing more.',
        });
      }
    } else {
      handleSend(text);
    }
  }, [isBusy, enqueue, handleSend, addMessage]);

  // Keyboard shortcuts
  useKeyBindings({
    isStreaming: chat.isStreaming,
    cancelStream: chat.cancelStream,
    clearInput: () => setInputCleared((c) => c + 1),
  });

  const showApproval = chat.loopState === 'AWAITING_APPROVAL' && chat.pendingCommands.length > 0;

  return (
    <Box flexDirection="column" padding={1}>
      <WelcomeMessage agent={agent} description={agentInfo?.description} />

      <ChatOutput messages={messages} agent={agent} />

      <StreamingResponse
        content={chat.streamingContent}
        isStreaming={chat.isStreaming}
      />

      {showApproval && (
        <CommandApproval
          commands={chat.pendingCommands}
          onApprove={chat.approveCommands}
          onReject={chat.rejectCommands}
        />
      )}

      <QueuedMessages />

      <ChatInput
        key={inputCleared}
        onSubmit={handleSubmit}
      />

      <StatusBar mode={mode} isStreaming={chat.isStreaming} />
    </Box>
  );
}
