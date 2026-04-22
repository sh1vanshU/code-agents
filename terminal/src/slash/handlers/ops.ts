/**
 * Operations slash commands: /run, /bash, /superpower, /plan, /repo
 */

import { registerSlash } from '../registry.js';
import type { SlashContext, SlashResult } from '../registry.js';

// ── /run ─────────────────────────────────────────────────────────────

registerSlash('run', {
  help: 'Run a shell command and show output',
  group: 'ops',
  aliases: ['!'],
  handler: async (arg: string, ctx: SlashContext): Promise<SlashResult> => {
    if (!arg) {
      return { action: 'continue', output: 'Usage: /run <command>' };
    }
    if (!ctx.store.superpower) {
      return { action: 'continue', output: 'Superpower mode is off. Use /superpower to enable shell commands.' };
    }

    const { execFileSync } = await import('node:child_process');
    try {
      // Security: use execFileSync with bash -c to avoid direct shell string expansion
      const output = execFileSync('/bin/bash', ['-c', arg], {
        cwd: ctx.store.repoPath || process.cwd(),
        timeout: 30_000,
        maxBuffer: 1024 * 1024,
        encoding: 'utf-8',
      });
      return { action: 'continue', output: output.trim() || '(no output)' };
    } catch (err: any) {
      return { action: 'continue', output: `Command failed: ${err.stderr || err.message}` };
    }
  },
});

// ── /bash ────────────────────────────────────────────────────────────

registerSlash('bash', {
  help: 'Run a bash command (alias for /run)',
  group: 'ops',
  handler: async (arg: string, ctx: SlashContext): Promise<SlashResult> => {
    if (!arg) {
      return { action: 'continue', output: 'Usage: /bash <command>' };
    }
    if (!ctx.store.superpower) {
      return { action: 'continue', output: 'Superpower mode is off. Use /superpower to enable shell commands.' };
    }

    const { execFileSync } = await import('node:child_process');
    try {
      const output = execFileSync('/bin/bash', ['-c', arg], {
        cwd: ctx.store.repoPath || process.cwd(),
        timeout: 30_000,
        maxBuffer: 1024 * 1024,
        encoding: 'utf-8',
      });
      return { action: 'continue', output: output.trim() || '(no output)' };
    } catch (err: any) {
      return { action: 'continue', output: `Command failed: ${err.stderr || err.message}` };
    }
  },
});

// ── /superpower ──────────────────────────────────────────────────────

registerSlash('superpower', {
  help: 'Toggle superpower mode (enables /run, /bash)',
  group: 'ops',
  handler: async (_arg: string, ctx: SlashContext): Promise<SlashResult> => {
    const next = !ctx.store.superpower;
    // Zustand doesn't expose a generic setter, so we toggle via the store's internal set
    // We access the underlying set by using the store API
    (ctx.store as any).setState?.({ superpower: next });
    // Fallback: if setState is not available, the store object itself may be mutable
    (ctx.store as any).superpower = next;
    const label = next ? 'ON' : 'OFF';
    return { action: 'continue', output: `Superpower mode: ${label}` };
  },
});

// ── /plan ────────────────────────────────────────────────────────────

registerSlash('plan', {
  help: 'Enter plan mode — propose a plan before execution',
  group: 'ops',
  handler: async (arg: string, ctx: SlashContext): Promise<SlashResult> => {
    if (!arg) {
      ctx.store.cycleMode();
      return { action: 'continue', output: `Mode switched to: ${ctx.store.mode}` };
    }
    // If an argument is provided, send it as a plan request to the agent
    return { action: 'send', message: `[PLAN] ${arg}` };
  },
});

// ── /btw ────────────────────────────────────────────────────────────

registerSlash('btw', {
  help: 'Inject a side message into agent context (or show/clear)',
  group: 'ops',
  handler: async (arg: string, ctx: SlashContext): Promise<SlashResult> => {
    const store = ctx.store as any;
    if (!store._btwMessages) store._btwMessages = [];

    if (!arg) {
      if (!store._btwMessages.length) {
        return { action: 'continue', output: 'No side messages. Usage: /btw <message> or /btw clear' };
      }
      return { action: 'continue', output: '── Side Messages ──\n' + store._btwMessages.map((m: string, i: number) => `  ${i + 1}. ${m}`).join('\n') };
    }
    if (arg === 'clear') {
      store._btwMessages = [];
      return { action: 'continue', output: 'Side messages cleared.' };
    }
    store._btwMessages.push(arg);
    return { action: 'continue', output: `Side message added: "${arg}"` };
  },
});

// ── /endpoints ──────────────────────────────────────────────────────

registerSlash('endpoints', {
  help: 'Show discovered API endpoints',
  group: 'ops',
  handler: async (arg: string, ctx: SlashContext): Promise<SlashResult> => {
    try {
      const subCmd = arg || 'list';
      const res = await fetch(
        `${ctx.client.getServerUrl()}/v1/endpoints?action=${subCmd}`,
        { signal: AbortSignal.timeout(10000) },
      );
      if (!res.ok) return { action: 'continue', output: 'Could not fetch endpoints.' };
      const data = await res.json();
      if (Array.isArray(data.endpoints) && data.endpoints.length === 0) {
        return { action: 'continue', output: 'No endpoints discovered yet. Run /endpoints scan to discover.' };
      }
      const lines = data.endpoints?.map((e: any) => `  ${e.method} ${e.path}`).join('\n') || JSON.stringify(data, null, 2);
      return { action: 'continue', output: `── Endpoints ──\n${lines}` };
    } catch {
      return { action: 'continue', output: 'Could not fetch endpoints from server.' };
    }
  },
});

// ── /repo ────────────────────────────────────────────────────────────

registerSlash('repo', {
  help: 'Show current repo path',
  group: 'ops',
  handler: async (_arg: string, ctx: SlashContext): Promise<SlashResult> => {
    return { action: 'continue', output: `Repo: ${ctx.store.repoPath}` };
  },
});

// ── /tasks ──────────────────────────────────────────────────────────

registerSlash('tasks', {
  help: 'List background tasks',
  group: 'ops',
  handler: async (_arg: string): Promise<SlashResult> => {
    const { getBackgroundManager } = await import('../../client/BackgroundTasks.js');
    const mgr = getBackgroundManager();
    return { action: 'continue', output: mgr.formatTaskList() };
  },
});

// ── /fg ─────────────────────────────────────────────────────────────

registerSlash('fg', {
  help: 'Bring a background task to foreground — /fg <id>',
  group: 'ops',
  handler: async (arg: string): Promise<SlashResult> => {
    const { getBackgroundManager } = await import('../../client/BackgroundTasks.js');
    const mgr = getBackgroundManager();
    const id = parseInt(arg, 10);
    if (isNaN(id)) {
      const list = mgr.formatTaskList();
      return { action: 'continue', output: `Usage: /fg <task_id>\n\n${list}` };
    }
    const task = mgr.getTask(id);
    if (!task) return { action: 'continue', output: `Task #${id} not found.` };

    if (task.status === 'done' && task.fullResponse) {
      const summary = task.fullResponse.slice(0, 500);
      mgr.removeTask(id);
      return { action: 'continue', output: `── ${task.displayName} ──\n${summary}\n\n✓ Merged.` };
    }
    if (task.status === 'error') {
      mgr.removeTask(id);
      return { action: 'continue', output: `✗ Task #${id} error: ${task.error}` };
    }
    return { action: 'continue', output: `Task #${id} is still running...` };
  },
});
