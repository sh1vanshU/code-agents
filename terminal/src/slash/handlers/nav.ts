/**
 * Navigation slash commands: /help, /quit, /clear, /open
 */

import { registerSlash, SLASH_REGISTRY } from '../registry.js';
import type { SlashContext, SlashResult } from '../registry.js';

// ── /help ────────────────────────────────────────────────────────────

registerSlash('help', {
  help: 'Show all available slash commands',
  group: 'nav',
  aliases: ['?', 'commands'],
  handler: async (_arg: string, _ctx: SlashContext): Promise<SlashResult> => {
    const groups = new Map<string, string[]>();
    const seen = new Set<string>();

    for (const [name, entry] of SLASH_REGISTRY) {
      // Skip aliases — only show primary name
      if (seen.has(entry.help + entry.group)) continue;
      seen.add(entry.help + entry.group);

      const list = groups.get(entry.group) ?? [];
      const aliasStr = entry.aliases?.length ? ` (${entry.aliases.map(a => '/' + a).join(', ')})` : '';
      list.push(`  /${name}${aliasStr} — ${entry.help}`);
      groups.set(entry.group, list);
    }

    const lines: string[] = ['\n── Slash Commands ──\n'];
    const groupOrder: string[] = ['nav', 'session', 'agent', 'ops', 'config', 'analysis', 'tools'];
    for (const g of groupOrder) {
      const cmds = groups.get(g);
      if (!cmds) continue;
      lines.push(`[${g}]`);
      lines.push(...cmds.sort());
      lines.push('');
    }

    return { action: 'continue', output: lines.join('\n') };
  },
});

// ── /quit ────────────────────────────────────────────────────────────

registerSlash('quit', {
  help: 'Exit the chat session',
  group: 'nav',
  aliases: ['exit', 'q'],
  handler: async (): Promise<SlashResult> => {
    return { action: 'quit' };
  },
});

// ── /clear ───────────────────────────────────────────────────────────

registerSlash('clear', {
  help: 'Clear chat history',
  group: 'nav',
  handler: async (_arg: string, ctx: SlashContext): Promise<SlashResult> => {
    ctx.store.reset();
    return { action: 'continue', output: 'Chat history cleared.' };
  },
});

// ── /setup ──────────────────────────────────────────────────────────

registerSlash('setup', {
  help: 'Configure integrations (jenkins, argocd, redash, testing)',
  group: 'nav',
  handler: async (arg: string): Promise<SlashResult> => {
    const sections = ['jenkins', 'argocd', 'redash', 'testing'];
    if (!arg) {
      return { action: 'continue', output: `Usage: /setup <section>\nSections: ${sections.join(', ')}` };
    }
    if (!sections.includes(arg.toLowerCase())) {
      return { action: 'continue', output: `Unknown section "${arg}". Available: ${sections.join(', ')}` };
    }
    // Delegate to server-side setup
    return { action: 'send', message: `/setup ${arg}` };
  },
});

// ── /delete-chat ────────────────────────────────────────────────────

registerSlash('delete-chat', {
  help: 'Delete a saved chat session by ID',
  group: 'nav',
  handler: async (arg: string): Promise<SlashResult> => {
    if (!arg) {
      return { action: 'continue', output: 'Usage: /delete-chat <session-id>' };
    }
    try {
      const { remove } = await import('../../state/SessionHistory.js');
      remove(arg);
      return { action: 'continue', output: `Deleted session: ${arg}` };
    } catch {
      return { action: 'continue', output: `Failed to delete session: ${arg}` };
    }
  },
});

// ── /open ────────────────────────────────────────────────────────────

registerSlash('open', {
  help: 'Open a file or URL in default application',
  group: 'nav',
  handler: async (arg: string): Promise<SlashResult> => {
    if (!arg) {
      return { action: 'continue', output: 'Usage: /open <path-or-url>' };
    }

    const { execFile } = await import('node:child_process');
    const cmd = process.platform === 'darwin' ? 'open' : process.platform === 'win32' ? 'start' : 'xdg-open';
    // Security: use execFile with array args to prevent shell injection
    execFile(cmd, [arg], (err) => {
      if (err) { /* silently fail — user already saw the output message */ }
    });
    return { action: 'continue', output: `Opening ${arg}` };
  },
});
