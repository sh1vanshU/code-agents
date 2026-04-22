/**
 * Slash Command Registry — central map of all slash commands.
 *
 * Each entry has a help string, group tag, handler function, and optional aliases.
 */

import type { ChatStore } from '../state/store.js';
import type { ApiClient } from '../client/ApiClient.js';
import type { AgentService } from '../client/AgentService.js';

// ── Types ────────────────────────────────────────────────────────────

export interface SlashEntry {
  help: string;
  group: 'nav' | 'session' | 'agent' | 'ops' | 'config' | 'analysis' | 'tools';
  handler: (arg: string, ctx: SlashContext) => Promise<SlashResult>;
  aliases?: string[];
}

export interface SlashContext {
  store: ChatStore;
  client: ApiClient;
  agentService: AgentService;
}

export type SlashResult =
  | { action: 'continue'; output?: string }
  | { action: 'quit' }
  | { action: 'send'; message: string }
  | { action: 'switch_agent'; agent: string };

// ── Registry ─────────────────────────────────────────────────────────

export const SLASH_REGISTRY: Map<string, SlashEntry> = new Map();

/**
 * Helper to register a command (called by handler modules on import).
 */
export function registerSlash(name: string, entry: SlashEntry): void {
  SLASH_REGISTRY.set(name, entry);
  if (entry.aliases) {
    for (const alias of entry.aliases) {
      SLASH_REGISTRY.set(alias, entry);
    }
  }
}
