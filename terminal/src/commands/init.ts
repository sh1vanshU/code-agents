/**
 * CLI Command: init — initialize code-agents for the current repository.
 *
 * Thin wrapper that delegates to the Python CLI's init command.
 */

import { Command, Flags } from '@oclif/core';
import { execSync } from 'node:child_process';

export default class Init extends Command {
  static override description = 'Initialize code-agents for the current repository';

  static override flags = {
    dir: Flags.string({
      char: 'd',
      description: 'Path to the code-agents installation',
      default: process.env.HOME + '/.code-agents',
    }),
  };

  async run(): Promise<void> {
    const { flags } = await this.parse(Init);

    this.log('Initializing code-agents for ' + process.cwd() + '...\n');

    try {
      const output = execSync('poetry run code-agents init', {
        cwd: flags.dir,
        encoding: 'utf-8',
        timeout: 60_000,
        maxBuffer: 1024 * 1024,
        env: { ...process.env, TARGET_REPO_PATH: process.cwd() },
        stdio: ['inherit', 'pipe', 'pipe'],
      });
      if (output) this.log(output);
      this.log('Initialization complete.');
    } catch (err: any) {
      if (err.stdout) this.log(err.stdout);
      if (err.stderr) this.warn(err.stderr);
      if (!err.stdout && !err.stderr) {
        this.error('Failed to run init. Is code-agents installed at ' + flags.dir + '?');
      }
    }
  }
}
