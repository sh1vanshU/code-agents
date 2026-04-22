/**
 * SmartOrchestrator — analyze user messages and auto-switch to specialist agent.
 *
 * Ported from code_agents/agent_system/smart_orchestrator.py.
 * Uses keyword scoring to find the best agent for a request.
 */

export interface AnalysisResult {
  bestAgent: string;
  score: number;
  shouldDelegate: boolean;
  description: string;
}

// Agent capabilities: agent → { keywords, description }
const AGENT_CAPABILITIES: Record<string, { keywords: string[]; description: string }> = {
  'code-reasoning': {
    keywords: ['explain code', 'how does', 'trace', 'architecture', 'flow', 'analyze code', 'understand code', 'read code', 'design pattern'],
    description: 'Read-only code analysis, architecture explanation, flow tracing',
  },
  'code-writer': {
    keywords: ['write', 'create', 'implement', 'add', 'refactor', 'modify', 'generate', 'new file', 'feature', 'update code', 'fix code'],
    description: 'Generate and modify code, implement features, refactor',
  },
  'code-reviewer': {
    keywords: ['review', 'pr', 'pull request', 'security', 'vulnerability', 'style', 'lint', 'code quality', 'bug', 'smell'],
    description: 'Code review for bugs, security, style violations',
  },
  'code-tester': {
    keywords: ['write test', 'test this', 'test', 'debug', 'unit test', 'integration test', 'mock', 'assert', 'tdd', 'fixture', 'pytest', 'junit', 'spec', 'write tests', 'run tests', 'test repository', 'test the code', 'lets test'],
    description: 'Write tests, run tests, debug failures, test strategy',
  },
  'git-ops': {
    keywords: ['git', 'branch', 'merge', 'checkout', 'push', 'pull', 'commit', 'rebase', 'stash', 'diff', 'log', 'cherry-pick'],
    description: 'Git operations: branches, diffs, logs, merge, push',
  },
  'jenkins-cicd': {
    keywords: ['build', 'jenkins', 'ci', 'cd', 'deploy', 'job', 'pipeline', 'artifact', 'trigger build'],
    description: 'Jenkins CI/CD: trigger builds, poll status, extract versions',
  },
  'argocd-verify': {
    keywords: ['argocd', 'argo', 'sync', 'pod', 'kubernetes', 'k8s', 'rollback', 'deployment status', 'container'],
    description: 'ArgoCD deployment verification, pod logs, rollback',
  },
  'redash-query': {
    keywords: ['sql', 'query', 'database', 'redash', 'schema', 'table', 'select', 'join', 'aggregate'],
    description: 'SQL queries via Redash, database exploration',
  },
  'qa-regression': {
    keywords: ['regression', 'regression test', 'qa', 'end to end test', 'e2e', 'test suite', 'smoke test', 'full test suite'],
    description: 'Regression suites, full test runs, eliminate manual QA',
  },
  'test-coverage': {
    keywords: ['test coverage', 'code coverage', 'coverage', 'coverage report', 'uncovered', 'coverage gap', 'branch coverage', 'line coverage'],
    description: 'Run test suites, generate coverage reports, find gaps',
  },
  'jira-ops': {
    keywords: ['jira', 'ticket', 'issue', 'confluence', 'sprint', 'story', 'epic', 'transition', 'assign'],
    description: 'Jira ticket management, Confluence pages, status transitions',
  },
};

// Conversational patterns that should never trigger routing
const CONVERSATIONAL = new Set([
  'yes', 'no', 'y', 'n', 'ok', 'okay', 'sure', 'proceed', 'go ahead',
  'go for it', 'do it', 'confirm', 'cancel', 'skip', 'continue',
  'retry', 'next', 'done', 'stop', 'quit', 'exit',
  '1', '2', '3', '4', '5', 'option a', 'option b', 'option c',
]);

function keywordMatches(keyword: string, text: string): boolean {
  if (keyword.length <= 3) {
    return new RegExp(`\\b${keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`).test(text);
  }
  if (keyword.includes(' ')) {
    return text.includes(keyword);
  }
  return new RegExp(`\\b${keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`).test(text);
}

export function analyzeRequest(userMessage: string, currentAgent?: string): AnalysisResult {
  const msg = userMessage.toLowerCase().trim();

  // Skip conversational follow-ups
  if (CONVERSATIONAL.has(msg)) {
    return { bestAgent: currentAgent || 'auto-pilot', score: 0, shouldDelegate: false, description: 'conversational follow-up' };
  }

  // Score each agent
  const scores: Record<string, number> = {};
  for (const [agent, caps] of Object.entries(AGENT_CAPABILITIES)) {
    if (agent === 'auto-pilot') continue;
    let score = 0;
    for (const kw of caps.keywords) {
      if (keywordMatches(kw, msg)) {
        score += kw.split(' ').length; // multi-word keywords score higher
      }
    }
    scores[agent] = score;
  }

  // Find best agent
  let bestAgent = 'auto-pilot';
  let bestScore = 0;
  for (const [agent, score] of Object.entries(scores)) {
    if (score > bestScore) {
      bestAgent = agent;
      bestScore = score;
    }
  }

  if (bestScore === 0) {
    return { bestAgent: currentAgent || 'auto-pilot', score: 0, shouldDelegate: false, description: 'general request' };
  }

  const caps = AGENT_CAPABILITIES[bestAgent];
  return {
    bestAgent,
    score: bestScore,
    shouldDelegate: true,
    description: caps?.description || `${bestAgent} task`,
  };
}
