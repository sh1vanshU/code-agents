/**
 * Config slash commands: /model, /backend, /theme
 */

import { registerSlash } from '../registry.js';
import type { SlashContext, SlashResult } from '../registry.js';

// ── /model ───────────────────────────────────────────────────────────

registerSlash('model', {
  help: 'Show or switch the current model',
  group: 'config',
  handler: async (arg: string, ctx: SlashContext): Promise<SlashResult> => {
    if (!arg) {
      try {
        const res = await fetch(`${ctx.client.getServerUrl()}/v1/config`, { signal: AbortSignal.timeout(5000) });
        if (res.ok) {
          const data = await res.json() as { model?: string };
          return { action: 'continue', output: `Current model: ${data.model ?? '(default)'}` };
        }
      } catch { /* fall through */ }
      return { action: 'continue', output: 'Usage: /model <model-name>' };
    }

    try {
      const res = await fetch(`${ctx.client.getServerUrl()}/v1/config`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: arg }),
        signal: AbortSignal.timeout(5000),
      });
      if (res.ok) {
        return { action: 'continue', output: `Model set to: ${arg}` };
      }
      return { action: 'continue', output: 'Failed to update model on server.' };
    } catch {
      return { action: 'continue', output: 'Could not reach server to update model.' };
    }
  },
});

// ── /backend ─────────────────────────────────────────────────────────

registerSlash('backend', {
  help: 'Show or switch the backend (cursor/claude/claude-cli)',
  group: 'config',
  handler: async (arg: string, ctx: SlashContext): Promise<SlashResult> => {
    if (!arg) {
      try {
        const res = await fetch(`${ctx.client.getServerUrl()}/v1/config`, { signal: AbortSignal.timeout(5000) });
        if (res.ok) {
          const data = await res.json() as { backend?: string };
          return { action: 'continue', output: `Current backend: ${data.backend ?? '(default)'}` };
        }
      } catch { /* fall through */ }
      return { action: 'continue', output: 'Usage: /backend <cursor|claude|claude-cli>' };
    }

    const valid = ['cursor', 'claude', 'claude-cli'];
    if (!valid.includes(arg)) {
      return { action: 'continue', output: `Invalid backend. Choose from: ${valid.join(', ')}` };
    }

    try {
      const res = await fetch(`${ctx.client.getServerUrl()}/v1/config`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ backend: arg }),
        signal: AbortSignal.timeout(5000),
      });
      if (res.ok) {
        return { action: 'continue', output: `Backend set to: ${arg}` };
      }
      return { action: 'continue', output: 'Failed to update backend on server.' };
    } catch {
      return { action: 'continue', output: 'Could not reach server to update backend.' };
    }
  },
});

// ── /theme ───────────────────────────────────────────────────────────

registerSlash('theme', {
  help: 'Switch color theme (dark/light/monokai/solarized)',
  group: 'config',
  handler: async (arg: string): Promise<SlashResult> => {
    const themes = ['dark', 'light', 'monokai', 'solarized'];
    if (!arg) {
      return { action: 'continue', output: `Available themes: ${themes.join(', ')}` };
    }
    if (!themes.includes(arg)) {
      return { action: 'continue', output: `Unknown theme "${arg}". Available: ${themes.join(', ')}` };
    }
    // Theme is client-side only; store in env for this session
    process.env.CODE_AGENTS_THEME = arg;
    return { action: 'continue', output: `Theme set to: ${arg}` };
  },
});
