/**
 * Slash Command Router — parses input and dispatches to the correct handler.
 */

import { SLASH_REGISTRY } from './registry.js';
import type { SlashContext, SlashResult } from './registry.js';

// Import handler modules to trigger registration side-effects
import './handlers/nav.js';
import './handlers/session.js';
import './handlers/agents.js';
import './handlers/ops.js';
import './handlers/config.js';

/**
 * Dispatch a slash command string (e.g. "/help" or "/agent auto-pilot").
 * Returns a SlashResult describing what the caller should do next.
 */
export async function dispatchSlash(input: string, ctx: SlashContext): Promise<SlashResult> {
  const trimmed = input.trim();
  if (!trimmed.startsWith('/')) {
    return { action: 'continue', output: 'Not a slash command' };
  }

  const spaceIdx = trimmed.indexOf(' ');
  const command = spaceIdx === -1 ? trimmed.slice(1) : trimmed.slice(1, spaceIdx);
  const arg = spaceIdx === -1 ? '' : trimmed.slice(spaceIdx + 1).trim();

  const entry = SLASH_REGISTRY.get(command);
  if (!entry) {
    return { action: 'continue', output: `Unknown command: /${command}. Type /help for available commands.` };
  }

  return entry.handler(arg, ctx);
}
