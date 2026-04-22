/**
 * CLI Command: stop — find the running server process and kill it gracefully.
 */

import { Command, Flags } from '@oclif/core';
import { execSync } from 'node:child_process';

export default class Stop extends Command {
  static override description = 'Stop the running code-agents server';

  static override flags = {
    port: Flags.integer({
      char: 'p',
      description: 'Server port to find process for',
      default: 8000,
    }),
  };

  async run(): Promise<void> {
    const { flags } = await this.parse(Stop);

    try {
      // Find PIDs listening on the server port
      const output = execSync(`lsof -ti :${flags.port}`, { encoding: 'utf-8' }).trim();
      if (!output) {
        this.log('No server process found on port ' + flags.port);
        return;
      }

      const pids = output.split('\n').map(p => p.trim()).filter(Boolean);
      for (const pid of pids) {
        try {
          process.kill(Number(pid), 'SIGTERM');
          this.log(`Sent SIGTERM to PID ${pid}`);
        } catch {
          this.warn(`Could not kill PID ${pid}`);
        }
      }

      this.log('Server stopped.');
    } catch {
      this.log('No server process found on port ' + flags.port);
    }
  }
}
