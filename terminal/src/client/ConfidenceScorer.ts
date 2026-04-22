/**
 * ConfidenceScorer — rate response confidence and suggest specialist agents.
 *
 * Ported from code_agents/core/confidence_scorer.py.
 */

export interface ConfidenceResult {
  score: number; // 1-5
  shouldDelegate: boolean;
  suggestedAgent: string | null;
  reason: string;
}

// Hedging phrases that indicate low confidence
const HEDGING_PHRASES = [
  "i'm not sure", "i am not sure", "i don't know", "i cannot",
  "i'm unable", "unfortunately", "i apologize", "sorry",
  "beyond my capabilities", "outside my scope", "not my area",
  "you might want to", "consider using", "you should try",
  "i would recommend switching", "better suited for",
];

// Agent specialization hints
const SPECIALIST_HINTS: Record<string, string[]> = {
  'code-tester': ['test', 'testing', 'debug', 'fixture', 'mock', 'assert'],
  'code-reviewer': ['review', 'security', 'vulnerability', 'code quality'],
  'jenkins-cicd': ['build', 'deploy', 'pipeline', 'jenkins', 'ci/cd'],
  'git-ops': ['git', 'branch', 'merge', 'commit', 'push'],
  'redash-query': ['sql', 'query', 'database', 'schema'],
  'argocd-verify': ['argocd', 'kubernetes', 'pods', 'deployment'],
  'jira-ops': ['jira', 'ticket', 'sprint', 'confluence'],
};

export function scoreResponse(
  agent: string,
  userInput: string,
  response: string,
): ConfidenceResult {
  const lower = response.toLowerCase();
  let score = 5;

  // Check for hedging phrases
  let hedgeCount = 0;
  for (const phrase of HEDGING_PHRASES) {
    if (lower.includes(phrase)) hedgeCount++;
  }
  if (hedgeCount >= 3) score = 1;
  else if (hedgeCount >= 2) score = 2;
  else if (hedgeCount >= 1) score = 3;

  // Check if response suggests another agent
  let suggestedAgent: string | null = null;
  if (score <= 3) {
    for (const [specialist, hints] of Object.entries(SPECIALIST_HINTS)) {
      if (specialist === agent) continue;
      const matchCount = hints.filter(h => lower.includes(h)).length;
      if (matchCount >= 2) {
        suggestedAgent = specialist;
        break;
      }
    }
  }

  return {
    score,
    shouldDelegate: score <= 2 && suggestedAgent !== null,
    suggestedAgent,
    reason: hedgeCount > 0 ? `${hedgeCount} hedging phrase(s) detected` : 'confident',
  };
}
