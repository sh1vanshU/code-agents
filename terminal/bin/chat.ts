#!/usr/bin/env tsx
/**
 * Direct chat entry point — bypasses oclif for zero-build launches.
 *
 * Usage: npx tsx terminal/bin/chat.ts [--agent auto-pilot] [--server http://localhost:8000]
 */

import React from 'react';
import { render } from 'ink';
import { ApiClient } from '../src/client/ApiClient.js';
import { AgentService } from '../src/client/AgentService.js';
import { ServerMonitor } from '../src/client/ServerMonitor.js';
import { ChatApp } from '../src/chat/ChatApp.js';

// Parse simple flags
const args = process.argv.slice(2);
let agent = 'auto-pilot';
let server = process.env['CODE_AGENTS_SERVER'] || 'http://localhost:8000';

for (let i = 0; i < args.length; i++) {
  if ((args[i] === '--agent' || args[i] === '-a') && args[i + 1]) {
    agent = args[++i];
  } else if ((args[i] === '--server' || args[i] === '-s') && args[i + 1]) {
    server = args[++i];
  } else if (!args[i].startsWith('-')) {
    // Positional arg = agent name
    agent = args[i];
  }
}

const client = new ApiClient(server);
const agentService = new AgentService(client);
const monitor = new ServerMonitor(client);

// Check server health
const alive = await client.checkHealth();
if (!alive) {
  console.log(`  Server not running at ${server}`);
  console.log('  Start with: code-agents start');
  process.exit(1);
}

// Fetch agents
await agentService.refresh();
agentService.setAgent(agent);

const { waitUntilExit } = render(
  React.createElement(ChatApp, {
    client,
    agentService,
    monitor,
  }),
);

await waitUntilExit();
monitor.dispose();
