/**
 * FullScreenApp — Full-screen Ink app layout with status bar.
 * Replaces the Python Textual TUI (tui/app.py) without needing bridge/proxy layers.
 */

import React from 'react';
import { Box } from 'ink';
import type { ApiClient } from '../client/ApiClient.js';
import type { AgentService } from '../client/AgentService.js';
import type { ServerMonitor } from '../client/ServerMonitor.js';
import { useChatStore } from '../state/store.js';
import { ChatApp } from '../chat/ChatApp.js';
import { StatusBar } from './StatusBar.js';

interface Props {
  client: ApiClient;
  agentService: AgentService;
  monitor: ServerMonitor;
}

export function FullScreenApp({ client, agentService, monitor }: Props) {
  const mode = useChatStore((s) => s.mode);
  const agent = useChatStore((s) => s.agent);
  const tokenUsage = useChatStore((s) => s.tokenUsage);

  return (
    <Box flexDirection="column" height="100%">
      <Box flexGrow={1} flexDirection="column">
        <ChatApp client={client} agentService={agentService} monitor={monitor} />
      </Box>
      <StatusBar
        mode={mode}
        agent={agent}
        tokenCount={tokenUsage.input + tokenUsage.output}
        serverAlive={monitor.isAlive}
      />
    </Box>
  );
}
