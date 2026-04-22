/**
 * Session slash commands: /session, /history, /resume, /export
 */

import { registerSlash } from '../registry.js';
import type { SlashContext, SlashResult } from '../registry.js';

// ── /session ─────────────────────────────────────────────────────────

registerSlash('session', {
  help: 'Show current session info',
  group: 'session',
  handler: async (_arg: string, ctx: SlashContext): Promise<SlashResult> => {
    const { agent, sessionId, repoPath, mode, messages, tokenUsage } = ctx.store;
    const lines = [
      '\n── Session Info ──',
      `  Agent:    ${agent}`,
      `  Session:  ${sessionId ?? '(none)'}`,
      `  Repo:     ${repoPath}`,
      `  Mode:     ${mode}`,
      `  Messages: ${messages.length}`,
      `  Tokens:   ${tokenUsage.input} in / ${tokenUsage.output} out / ${tokenUsage.cached} cached`,
    ];
    return { action: 'continue', output: lines.join('\n') };
  },
});

// ── /history ─────────────────────────────────────────────────────────

registerSlash('history', {
  help: 'List recent chat sessions',
  group: 'session',
  aliases: ['sessions'],
  handler: async (_arg: string, ctx: SlashContext): Promise<SlashResult> => {
    try {
      const res = await fetch(`${ctx.client.getServerUrl()}/v1/sessions`, { signal: AbortSignal.timeout(5000) });
      if (!res.ok) return { action: 'continue', output: 'Could not fetch session history.' };
      const data = await res.json() as Array<{ id: string; agent: string; title: string; updated_at: string }>;
      if (!data.length) return { action: 'continue', output: 'No sessions found.' };

      const lines = ['\n── Recent Sessions ──'];
      for (const s of data.slice(0, 15)) {
        lines.push(`  ${s.id.slice(0, 8)} | ${s.agent.padEnd(14)} | ${s.title || '(untitled)'} | ${s.updated_at}`);
      }
      return { action: 'continue', output: lines.join('\n') };
    } catch {
      return { action: 'continue', output: 'Could not fetch session history.' };
    }
  },
});

// ── /resume ──────────────────────────────────────────────────────────

registerSlash('resume', {
  help: 'Resume a previous session by ID',
  group: 'session',
  handler: async (arg: string, ctx: SlashContext): Promise<SlashResult> => {
    if (!arg) {
      return { action: 'continue', output: 'Usage: /resume <session-id>' };
    }
    // Security: validate session ID format (alphanumeric, hyphens, underscores only)
    const safeId = arg.replace(/[^a-zA-Z0-9_-]/g, '');
    if (!safeId || safeId.length < 4 || safeId !== arg) {
      return { action: 'continue', output: `Invalid session ID format: ${arg}` };
    }
    ctx.store.setSessionId(safeId);
    return { action: 'continue', output: `Resumed session ${safeId}. Next message will continue that session.` };
  },
});

// ── /export ──────────────────────────────────────────────────────────

registerSlash('export', {
  help: 'Export current conversation as JSON',
  group: 'session',
  handler: async (_arg: string, ctx: SlashContext): Promise<SlashResult> => {
    const { writeFile } = await import('node:fs/promises');
    const path = await import('node:path');

    const payload = {
      agent: ctx.store.agent,
      sessionId: ctx.store.sessionId,
      messages: ctx.store.messages,
      tokenUsage: ctx.store.tokenUsage,
      exportedAt: new Date().toISOString(),
    };

    const filename = `code-agents-export-${Date.now()}.json`;
    const filepath = path.join(process.cwd(), filename);
    await writeFile(filepath, JSON.stringify(payload, null, 2));
    return { action: 'continue', output: `Exported ${ctx.store.messages.length} messages to ${filepath}` };
  },
});
