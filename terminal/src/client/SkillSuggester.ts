/**
 * SkillSuggester — proactive skill suggestions based on user input keywords.
 *
 * Ported from code_agents/chat/chat_context.py _suggest_skills().
 * Maps input keywords to relevant skill names and returns formatted suggestions.
 */

const KEYWORD_SKILL_MAP: Record<string, string[]> = {
  test: ['test-and-report', 'test-fix-loop', 'testing-strategy', 'write-and-test'],
  build: ['local-build', 'build', 'deploy-checklist'],
  review: ['code-review', 'design-review', 'security-review'],
  debug: ['debug'],
  deploy: ['deploy', 'deploy-checklist', 'kibana-logs'],
  jira: ['read-ticket', 'create-ticket', 'update-status'],
  ticket: ['read-ticket', 'create-ticket', 'update-status'],
  analyze: ['system-analysis', 'impact-analysis', 'architecture'],
  analysis: ['system-analysis', 'impact-analysis'],
  incident: ['incident-response'],
  standup: ['standup'],
  doc: ['documentation'],
  security: ['security-review', 'negative-testing'],
  refactor: ['tech-debt'],
  design: ['system-design', 'design-review'],
  api: ['api-testing', 'negative-testing'],
  log: ['kibana-logs', 'log-analysis', 'debug'],
  error: ['kibana-logs', 'log-analysis', 'debug'],
  coverage: ['test-and-report', 'testing-strategy'],
  plan: ['full-sdlc', 'system-design'],
  performance: ['testing-strategy', 'architecture'],
  implement: ['write-and-test', 'write-from-jira'],
  fix: ['debug', 'test-fix-loop'],
  write: ['write-and-test', 'write-from-jira'],
  java: ['java-spring'],
  spring: ['java-spring'],
};

export interface SkillSuggestion {
  command: string; // e.g. "/auto-pilot:debug"
  name: string;    // e.g. "debug"
}

/**
 * Suggest skills based on keywords in the user's message.
 * Returns up to 3 skill suggestions.
 */
export function suggestSkills(
  userInput: string,
  agentName: string,
): SkillSuggestion[] {
  // Skip if already invoking a skill
  const trimmed = userInput.trim();
  if (trimmed.startsWith('/') && trimmed.includes(':')) return [];

  const inputLower = userInput.toLowerCase();
  const matched: SkillSuggestion[] = [];
  const seen = new Set<string>();

  for (const [keyword, skillNames] of Object.entries(KEYWORD_SKILL_MAP)) {
    if (!inputLower.includes(keyword)) continue;

    for (const skillName of skillNames) {
      if (seen.has(skillName)) continue;
      seen.add(skillName);

      matched.push({
        command: `/${agentName}:${skillName}`,
        name: skillName,
      });

      if (matched.length >= 3) return matched;
    }
  }

  return matched;
}
