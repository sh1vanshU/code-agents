/**
 * CLI Command: agents — list all available agents with descriptions.
 */

import { Command, Flags } from '@oclif/core';
import { ApiClient } from '../client/ApiClient.js';

export default class Agents extends Command {
  static override description = 'List all available code agents';

  static override flags = {
    server: Flags.string({
      char: 's',
      description: 'Server URL',
      default: 'http://localhost:8000',
    }),
  };

  async run(): Promise<void> {
    const { flags } = await this.parse(Agents);
    const client = new ApiClient(flags.server);

    const alive = await client.checkHealth();
    if (!alive) {
      this.error('Server not running at ' + flags.server + '. Start with: code-agents start');
    }

    const agents = await client.getAgents();
    if (!agents.length) {
      this.log('No agents found.');
      return;
    }

    this.log(`\n  ${'Agent'.padEnd(22)} Description`);
    this.log(`  ${'─'.repeat(22)} ${'─'.repeat(50)}`);
    for (const a of agents) {
      this.log(`  ${a.name.padEnd(22)} ${a.description ?? ''}`);
    }
    this.log(`\n  ${agents.length} agents available.\n`);
  }
}
