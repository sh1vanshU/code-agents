/**
 * CLI Command: start — spawn the Python server as a background process and wait until healthy.
 */

import { Command, Flags } from '@oclif/core';
import { ApiClient } from '../client/ApiClient.js';
import { ServerMonitor } from '../client/ServerMonitor.js';

export default class Start extends Command {
  static override description = 'Start the code-agents Python server in the background';

  static override flags = {
    server: Flags.string({
      char: 's',
      description: 'Server URL',
      default: 'http://localhost:8000',
    }),
    dir: Flags.string({
      char: 'd',
      description: 'Path to the code-agents installation',
      default: process.env.HOME + '/.code-agents',
    }),
    timeout: Flags.integer({
      char: 't',
      description: 'Startup timeout in seconds',
      default: 30,
    }),
  };

  async run(): Promise<void> {
    const { flags } = await this.parse(Start);

    const client = new ApiClient(flags.server);

    // Check if already running
    const alive = await client.checkHealth();
    if (alive) {
      this.log('Server is already running at ' + flags.server);
      return;
    }

    this.log('Starting code-agents server...');
    const monitor = new ServerMonitor(client);
    monitor.spawnServer(flags.dir);

    const ready = await monitor.waitForServer(flags.timeout * 1000);
    monitor.dispose();

    if (ready) {
      this.log('Server started and healthy at ' + flags.server);
    } else {
      this.error(`Server did not become healthy within ${flags.timeout}s. Check logs.`);
    }
  }
}
