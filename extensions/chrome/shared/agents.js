// Code Agents — Agent definitions

const AGENTS = [
  { name: 'auto-pilot',    description: 'Full SDLC orchestration' },
  { name: 'jenkins-cicd',  description: 'Build, deploy, ArgoCD verification' },
  { name: 'code-reasoning', description: 'Code analysis and exploration' },
  { name: 'code-writer',   description: 'Generate and modify code' },
  { name: 'code-reviewer', description: 'Code review for bugs and security' },
  { name: 'code-tester',   description: 'Write tests, debug failures' },
  { name: 'test-coverage', description: 'Coverage analysis, autonomous boost' },
  { name: 'qa-regression', description: 'Full regression test suites' },
  { name: 'git-ops',       description: 'Git workflows and release management' },
  { name: 'argocd-verify', description: 'Advanced ArgoCD: rollback, canary' },
  { name: 'jira-ops',      description: 'Jira tickets and Confluence' },
  { name: 'redash-query',  description: 'SQL queries via Redash' },
  { name: 'security',      description: 'OWASP scanning, CVE audit' },
];

const DEFAULT_AGENT = 'auto-pilot';

/**
 * Get the display label for an agent (name + short description).
 */
function agentLabel(agent) {
  return `${agent.name} — ${agent.description}`;
}

/**
 * Find an agent by name (case-insensitive).
 */
function findAgent(name) {
  const lower = (name || '').toLowerCase();
  return AGENTS.find((a) => a.name.toLowerCase() === lower) || null;
}
