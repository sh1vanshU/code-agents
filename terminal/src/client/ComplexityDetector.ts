/**
 * ComplexityDetector — auto-detect complex tasks and suggest plan mode.
 *
 * Ported from code_agents/chat/chat_complexity.py.
 * Scores user input against weighted regex patterns to determine
 * if a structured plan should be suggested before execution.
 */

export interface ComplexityResult {
  score: number;
  shouldSuggestPlan: boolean;
  reasons: string[];
}

const COMPLEXITY_THRESHOLD = 4;

const COMPLEXITY_PATTERNS: Array<[RegExp, number]> = [
  // Multi-file / large-scope keywords
  [/\brefactor\b/i, 3],
  [/\bmigrat(?:e|ion)\b/i, 3],
  [/\brewrite\b/i, 3],
  [/\bredesign\b/i, 3],
  [/\brearchitect\b/i, 4],
  [/\boverhaul\b/i, 3],
  [/\bconvert all\b/i, 3],
  [/\bimplement(?:\s+all|\s+the\s+following|\s+these)\b/i, 3],
  [/\badd support for\b/i, 2],
  [/\bupgrade\b/i, 2],
  [/\breplace\b.*\bwith\b/i, 2],
  // Multi-step indicators
  [/\bsteps?\s*[:\d]/i, 2],
  [/\b(?:first|then|next|finally|after that)\b/i, 1],
  [/\band\s+(?:also|then)\b/i, 1],
  // Scope indicators
  [/\bacross\s+(?:all|the|every)\b/i, 2],
  [/\bevery\s+(?:file|module|component|test|endpoint)\b/i, 2],
  [/\ball\s+(?:files|modules|components|tests|endpoints|agents)\b/i, 2],
  [/\bmultiple\s+(?:files|modules|components)\b/i, 2],
  // Explicit complexity markers
  [/\bcomplete\s+(?:rewrite|overhaul|redesign)\b/i, 4],
  [/\bfull\s+(?:rewrite|pipeline|stack|implementation)\b/i, 3],
  [/\bend.to.end\b/i, 2],
  [/\bfrom\s+scratch\b/i, 3],
  // CI/CD multi-step pipelines
  [/\bbuild\s+and\s+deploy\b/i, 4],
  [/\bdeploy\b.*\bverify\b/i, 4],
  [/\bbuild.*deploy.*verify\b/i, 5],
  [/\bbuild.*deploy.*argocd\b/i, 5],
  [/\bpipeline\b/i, 2],
  [/\brollback\b/i, 2],
  // File count mentions
  [/\b\d{2,}\s+files?\b/i, 2],
];

export function estimateComplexity(userInput: string): ComplexityResult {
  let score = 0;
  const reasons: string[] = [];

  for (const [pattern, weight] of COMPLEXITY_PATTERNS) {
    const m = pattern.exec(userInput);
    if (m) {
      score += weight;
      reasons.push(m[0]);
    }
  }

  // Long messages get a bonus
  if (userInput.length > 300) score += 1;
  if (userInput.length > 600) score += 1;

  return {
    score,
    shouldSuggestPlan: score >= COMPLEXITY_THRESHOLD,
    reasons,
  };
}
