/**
 * CLI Command: status — show server health, current config, and agent count.
 */

import { Command, Flags } from '@oclif/core';
import { ApiClient } from '../client/ApiClient.js';

export default class Status extends Command {
  static override description = 'Show server health, config, and agent count';

  static override flags = {
    server: Flags.string({
      char: 's',
      description: 'Server URL',
      default: 'http://localhost:8000',
    }),
  };

  async run(): Promise<void> {
    const { flags } = await this.parse(Status);
    const client = new ApiClient(flags.server);

    // Health check
    const alive = await client.checkHealth();
    this.log(`Server:  ${flags.server}`);
    this.log(`Health:  ${alive ? 'OK' : 'UNREACHABLE'}`);

    if (!alive) {
      this.log('\nServer is not running. Start with: code-agents start');
      return;
    }

    // Config
    try {
      const res = await fetch(`${flags.server}/v1/config`, { signal: AbortSignal.timeout(5000) });
      if (res.ok) {
        const config = await res.json() as Record<string, unknown>;
        this.log(`Backend: ${config.backend ?? '(default)'}`);
        this.log(`Model:   ${config.model ?? '(default)'}`);
      }
    } catch {
      this.log('Config:  (could not fetch)');
    }

    // Agents
    const agents = await client.getAgents();
    this.log(`Agents:  ${agents.length} loaded`);
  }
}
