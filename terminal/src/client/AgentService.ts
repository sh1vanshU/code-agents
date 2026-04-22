/**
 * Agent discovery and selection service.
 */

import type { Agent } from './types.js';
import { ApiClient } from './ApiClient.js';

const DEFAULT_AGENT = 'auto-pilot';

export class AgentService {
  private client: ApiClient;
  private agents: Agent[] = [];
  private _currentAgent: string = DEFAULT_AGENT;

  constructor(client: ApiClient) {
    this.client = client;
  }

  get currentAgent(): string {
    return this._currentAgent;
  }

  /** Fetch the agent list from the server */
  async refresh(): Promise<Agent[]> {
    this.agents = await this.client.getAgents();
    return this.agents;
  }

  /** Get cached agent list */
  getAgents(): Agent[] {
    return this.agents;
  }

  /** Get agent names only */
  getAgentNames(): string[] {
    return this.agents.map(a => a.name);
  }

  /** Switch to a different agent. Returns true if valid. */
  setAgent(name: string): boolean {
    if (this.agents.length > 0 && !this.agents.some(a => a.name === name)) {
      return false;
    }
    this._currentAgent = name;
    return true;
  }

  /** Find an agent by name */
  findAgent(name: string): Agent | undefined {
    return this.agents.find(a => a.name === name);
  }
}
