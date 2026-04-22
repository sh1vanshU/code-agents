/**
 * CLI Command: doctor — run health diagnostics.
 *
 * Delegates to the Python CLI's doctor command for now, printing the result.
 */

import { Command } from '@oclif/core';
import { execSync } from 'node:child_process';

export default class Doctor extends Command {
  static override description = 'Run health diagnostics on the code-agents environment';

  async run(): Promise<void> {
    this.log('Running code-agents doctor...\n');

    try {
      const output = execSync('poetry run code-agents doctor', {
        cwd: process.env.HOME + '/.code-agents',
        encoding: 'utf-8',
        timeout: 30_000,
        maxBuffer: 1024 * 1024,
      });
      this.log(output);
    } catch (err: any) {
      if (err.stdout) {
        this.log(err.stdout);
      }
      if (err.stderr) {
        this.warn(err.stderr);
      }
      if (!err.stdout && !err.stderr) {
        this.error('Failed to run doctor. Is code-agents installed at ~/.code-agents?');
      }
    }
  }
}
