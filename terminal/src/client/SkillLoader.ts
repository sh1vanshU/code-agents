/**
 * SkillLoader — fetch skill body from server when agent emits [SKILL:name] tags.
 *
 * Skills are markdown workflow files stored in agents/<name>/skills/*.md.
 * The server serves them via GET /v1/agents/{agent}/skills/{name}.
 */

import type { ApiClient } from './ApiClient.js';

export interface SkillBody {
  name: string;
  agent: string;
  body: string;
}

/**
 * Fetch a skill body from the server.
 *
 * @param skillRef - "name" (current agent) or "agent:name" (cross-agent)
 * @param currentAgent - current agent name (used when skillRef has no agent prefix)
 */
export async function loadSkill(
  client: ApiClient,
  skillRef: string,
  currentAgent: string,
): Promise<SkillBody | null> {
  let agent: string;
  let name: string;

  if (skillRef.includes(':')) {
    const parts = skillRef.split(':');
    agent = parts[0];
    name = parts.slice(1).join(':');
  } else {
    agent = currentAgent;
    name = skillRef;
  }

  try {
    const url = client.getServerUrl();
    const resp = await fetch(`${url}/v1/agents/${agent}/skills/${name}`);
    if (!resp.ok) return null;
    const data = await resp.json() as { name: string; body: string };
    return { name: data.name, agent, body: data.body };
  } catch {
    return null;
  }
}

/**
 * Build the follow-up message to inject a loaded skill into the conversation.
 */
export function buildSkillMessage(skill: SkillBody): string {
  return (
    `[Skill loaded: ${skill.name}]\n\n` +
    `${skill.body}\n\n` +
    `Now proceed with this workflow. Output the first \`\`\`bash command to begin.`
  );
}
