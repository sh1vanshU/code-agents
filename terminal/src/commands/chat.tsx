import { Command, Flags } from '@oclif/core';
import React from 'react';
import { render } from 'ink';
import { ApiClient } from '../client/ApiClient.js';
import { AgentService } from '../client/AgentService.js';
import { ServerMonitor } from '../client/ServerMonitor.js';
import { ChatApp } from '../chat/ChatApp.js';

export default class Chat extends Command {
  static override description = 'Start an interactive chat session with a code agent';

  static override flags = {
    agent: Flags.string({
      char: 'a',
      description: 'Agent to chat with',
      default: 'auto-pilot',
    }),
    server: Flags.string({
      char: 's',
      description: 'Server URL',
      default: 'http://localhost:8000',
    }),
  };

  async run(): Promise<void> {
    const { flags } = await this.parse(Chat);

    const client = new ApiClient(flags.server);
    const agentService = new AgentService(client);
    const monitor = new ServerMonitor(client);

    // Check server health
    const alive = await client.checkHealth();
    if (!alive) {
      this.log('Server not running at ' + flags.server);
      this.log('Start with: code-agents start');
      this.exit(1);
    }

    // Fetch agents
    await agentService.refresh();
    agentService.setAgent(flags.agent);

    const { waitUntilExit } = render(
      React.createElement(ChatApp, {
        client,
        agentService,
        monitor,
      }),
    );

    await waitUntilExit();
    monitor.dispose();
  }
}
