/**
 * Agent slash commands: /agent, /agents, /rules, /skills, /tokens, /memory
 */

import { registerSlash } from '../registry.js';
import type { SlashContext, SlashResult } from '../registry.js';

// ── /agent ───────────────────────────────────────────────────────────

registerSlash('agent', {
  help: 'Switch to a different agent',
  group: 'agent',
  handler: async (arg: string, ctx: SlashContext): Promise<SlashResult> => {
    if (!arg) {
      return { action: 'continue', output: `Current agent: ${ctx.agentService.currentAgent}. Usage: /agent <name>` };
    }
    const ok = ctx.agentService.setAgent(arg);
    if (!ok) {
      const names = ctx.agentService.getAgentNames().join(', ');
      return { action: 'continue', output: `Unknown agent "${arg}". Available: ${names}` };
    }
    ctx.store.setAgent(arg);
    return { action: 'switch_agent', agent: arg };
  },
});

// ── /agents ──────────────────────────────────────────────────────────

registerSlash('agents', {
  help: 'List all available agents',
  group: 'agent',
  handler: async (_arg: string, ctx: SlashContext): Promise<SlashResult> => {
    const agents = ctx.agentService.getAgents();
    if (!agents.length) {
      return { action: 'continue', output: 'No agents loaded. Is the server running?' };
    }
    const lines = ['\n── Agents ──'];
    for (const a of agents) {
      const marker = a.name === ctx.agentService.currentAgent ? ' *' : '';
      lines.push(`  ${a.name.padEnd(20)} ${a.description ?? ''}${marker}`);
    }
    return { action: 'continue', output: lines.join('\n') };
  },
});

// ── /rules ───────────────────────────────────────────────────────────

registerSlash('rules', {
  help: 'Show active rules for current agent',
  group: 'agent',
  handler: async (_arg: string, ctx: SlashContext): Promise<SlashResult> => {
    try {
      const res = await fetch(
        `${ctx.client.getServerUrl()}/v1/agents/${ctx.agentService.currentAgent}/rules`,
        { signal: AbortSignal.timeout(5000) },
      );
      if (!res.ok) return { action: 'continue', output: 'Could not fetch rules.' };
      const data = await res.json() as { rules: string[] };
      if (!data.rules?.length) return { action: 'continue', output: 'No rules active.' };
      return { action: 'continue', output: '\n── Rules ──\n' + data.rules.map(r => `  • ${r}`).join('\n') };
    } catch {
      return { action: 'continue', output: 'Could not fetch rules from server.' };
    }
  },
});

// ── /skills ──────────────────────────────────────────────────────────

registerSlash('skills', {
  help: 'List skills for current agent',
  group: 'agent',
  handler: async (_arg: string, ctx: SlashContext): Promise<SlashResult> => {
    try {
      const res = await fetch(
        `${ctx.client.getServerUrl()}/v1/agents/${ctx.agentService.currentAgent}/skills`,
        { signal: AbortSignal.timeout(5000) },
      );
      if (!res.ok) return { action: 'continue', output: 'Could not fetch skills.' };
      const data = await res.json() as { skills: string[] };
      if (!data.skills?.length) return { action: 'continue', output: 'No skills found.' };
      return { action: 'continue', output: '\n── Skills ──\n' + data.skills.map(s => `  • ${s}`).join('\n') };
    } catch {
      return { action: 'continue', output: 'Could not fetch skills from server.' };
    }
  },
});

// ── /tokens ──────────────────────────────────────────────────────────

registerSlash('tokens', {
  help: 'Show token usage for this session',
  group: 'agent',
  handler: async (_arg: string, ctx: SlashContext): Promise<SlashResult> => {
    const { input, output, cached } = ctx.store.tokenUsage;
    const total = input + output;
    return {
      action: 'continue',
      output: `Tokens — Input: ${input} | Output: ${output} | Cached: ${cached} | Total: ${total}`,
    };
  },
});

// ── /memory ──────────────────────────────────────────────────────────

registerSlash('memory', {
  help: 'Show/clear/list agent memory (persistent learnings)',
  group: 'agent',
  handler: async (arg: string, ctx: SlashContext): Promise<SlashResult> => {
    const subCmd = arg?.trim().toLowerCase();
    const serverUrl = ctx.client.getServerUrl();
    const currentAgent = ctx.agentService.currentAgent;

    try {
      if (subCmd === 'clear') {
        const res = await fetch(
          `${serverUrl}/v1/agents/${currentAgent}/memory`,
          { method: 'DELETE', signal: AbortSignal.timeout(5000) },
        );
        if (!res.ok) return { action: 'continue', output: 'Could not clear memory.' };
        return { action: 'continue', output: `Memory cleared for ${currentAgent}.` };
      }

      if (subCmd === 'list') {
        const res = await fetch(`${serverUrl}/v1/agents`, { signal: AbortSignal.timeout(5000) });
        if (!res.ok) return { action: 'continue', output: 'Could not fetch agents.' };
        const data = await res.json() as { agents: Array<{ name: string }> };
        const lines = ['── Agents with Memory ──'];
        for (const a of data.agents) {
          try {
            const mRes = await fetch(`${serverUrl}/v1/agents/${a.name}/memory`, { signal: AbortSignal.timeout(3000) });
            if (mRes.ok) {
              const mData = await mRes.json() as { memory: string };
              if (mData.memory) lines.push(`  ${a.name} — ${mData.memory.split('\n').length} lines`);
            }
          } catch { /* skip */ }
        }
        if (lines.length === 1) lines.push('  No agents have stored memories.');
        return { action: 'continue', output: lines.join('\n') };
      }

      // Default: show memory for current agent
      const res = await fetch(
        `${serverUrl}/v1/agents/${currentAgent}/memory`,
        { signal: AbortSignal.timeout(5000) },
      );
      if (!res.ok) return { action: 'continue', output: 'Could not fetch agent memory.' };
      const data = await res.json() as { memory: string };
      if (!data.memory) return { action: 'continue', output: 'No agent memory stored.' };
      return { action: 'continue', output: '\n── Agent Memory ──\n' + data.memory };
    } catch {
      return { action: 'continue', output: 'Could not fetch agent memory from server.' };
    }
  },
});
