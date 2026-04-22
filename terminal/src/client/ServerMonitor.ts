/**
 * Server health monitor — polls the Python server and manages startup.
 */

import { spawn, type ChildProcess } from 'node:child_process';
import { ApiClient } from './ApiClient.js';

const POLL_INTERVAL_MS = 1000;
const STARTUP_TIMEOUT_MS = 15_000;

export class ServerMonitor {
  private client: ApiClient;
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private _isAlive = false;
  private listeners: Array<(alive: boolean) => void> = [];

  constructor(client: ApiClient) {
    this.client = client;
  }

  get isAlive(): boolean {
    return this._isAlive;
  }

  /** Start polling the server health endpoint */
  startPolling(intervalMs = POLL_INTERVAL_MS): void {
    this.stopPolling();
    this.pollTimer = setInterval(async () => {
      const alive = await this.client.checkHealth();
      if (alive !== this._isAlive) {
        this._isAlive = alive;
        this.listeners.forEach(fn => fn(alive));
      }
    }, intervalMs);
    // Immediately check
    this.client.checkHealth().then(alive => {
      this._isAlive = alive;
      this.listeners.forEach(fn => fn(alive));
    });
  }

  stopPolling(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  /** Subscribe to health changes */
  onChange(fn: (alive: boolean) => void): () => void {
    this.listeners.push(fn);
    return () => {
      this.listeners = this.listeners.filter(l => l !== fn);
    };
  }

  /**
   * Spawn the Python server as a detached background process.
   * Returns the child process (already unref'd).
   */
  spawnServer(codeAgentsDir: string): ChildProcess {
    // Security: only propagate necessary env vars to the Python server
    const safeEnv: Record<string, string> = {
      PATH: process.env['PATH'] ?? '',
      HOME: process.env['HOME'] ?? '',
      USER: process.env['USER'] ?? '',
      SHELL: process.env['SHELL'] ?? '',
      LANG: process.env['LANG'] ?? 'en_US.UTF-8',
      HOST: '0.0.0.0',
      PORT: '8000',
    };
    // Propagate code-agents specific vars
    for (const [key, val] of Object.entries(process.env)) {
      if (key.startsWith('CODE_AGENTS_') || key.startsWith('CURSOR_') || key.startsWith('ANTHROPIC_') ||
          key.startsWith('JENKINS_') || key.startsWith('ARGOCD_') || key.startsWith('JIRA_') ||
          key.startsWith('ELASTICSEARCH_') || key.startsWith('KIBANA_') || key.startsWith('GRAFANA_') ||
          key.startsWith('REDASH_') || key.startsWith('SLACK_') || key === 'TARGET_REPO_PATH') {
        if (val !== undefined) safeEnv[key] = val;
      }
    }
    const server = spawn('poetry', ['run', 'python', '-m', 'code_agents.core.main'], {
      cwd: codeAgentsDir,
      env: safeEnv,
      detached: true,
      stdio: 'ignore',
    });
    server.unref();
    return server;
  }

  /**
   * Wait for the server to become healthy, up to timeoutMs.
   * Returns true if healthy, false if timed out.
   */
  async waitForServer(timeoutMs = STARTUP_TIMEOUT_MS): Promise<boolean> {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      if (await this.client.checkHealth()) {
        this._isAlive = true;
        return true;
      }
      await new Promise(r => setTimeout(r, 500));
    }
    return false;
  }

  dispose(): void {
    this.stopPolling();
    this.listeners = [];
  }
}
