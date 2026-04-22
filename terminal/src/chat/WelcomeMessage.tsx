/**
 * WelcomeMessage — Agent welcome box with roles, capabilities, examples, and keyboard shortcuts.
 *
 * Ported from code_agents/chat/chat_welcome.py AGENT_ROLES + AGENT_WELCOME.
 */

import React from 'react';
import { Box, Text } from 'ink';

/** Agent role descriptions (extracted from YAML system prompts) */
export const AGENT_ROLES: Record<string, string> = {
  'code-reasoning': 'Analyze code, explain architecture, trace flows (read-only)',
  'code-writer': 'Generate and modify code, refactor, implement features',
  'code-reviewer': 'Review code for bugs, security issues, style violations',
  'code-tester': 'Write tests, debug issues, optimize code quality',
  'redash-query': 'Write SQL, query databases, explore schemas via Redash',
  'git-ops': 'Git operations: branches, diffs, logs, push',
  'test-coverage': 'Run test suites, generate coverage reports, find gaps',
  'jenkins-cicd': 'Build and deploy via Jenkins — end-to-end CI/CD',
  'argocd-verify': 'Verify ArgoCD deployments, scan pod logs, rollback',
  'qa-regression': 'Run regression suites, write missing tests, eliminate manual QA',
  'auto-pilot': 'Autonomous orchestrator — delegates to sub-agents, runs full workflows',
  'jira-ops': 'Read Jira tickets, Confluence pages, update ticket status',
  'security': 'Security audit: OWASP scan, CVE check, secrets detection',
  'grafana-ops': 'Grafana Ops: query metrics, investigate alerts, correlate deploys',
  'terraform-ops': 'Terraform/IaC: plan, review, apply infrastructure changes',
  'github-actions': 'GitHub Actions: trigger, monitor, retry, and debug workflows',
  'db-ops': 'Postgres/DB: safe queries, explain plans, migrations, schema inspection',
  'pr-review': 'PR Review Bot: auto-review PRs, post inline comments, enforce quality',
  'debug-agent': 'Autonomous debugging: reproduce, trace, root-cause, fix, verify',
};

/** Agent welcome data: [title, capabilities, examples] */
const AGENT_WELCOME: Record<string, { title: string; capabilities: string[]; examples: string[] }> = {
  'auto-pilot': {
    title: 'Auto-Pilot — Full Autonomy · Sarathi (सारथी)',
    capabilities: [
      'Execute multi-step workflows end-to-end autonomously',
      'Delegate to 18 specialist agents',
      'Build → Deploy → Verify pipelines without manual switching',
      'Run code reviews, apply fixes, and re-verify automatically',
    ],
    examples: [
      'Build and deploy {repo} to dev',
      'Review the latest changes, fix issues, and run tests',
      'Run the full CI/CD pipeline for release branch',
    ],
  },
  'jenkins-cicd': {
    title: 'Jenkins CI/CD — Build & Deploy · Nirmata (निर्माता)',
    capabilities: [
      'Git pre-check: detect branch, status, uncommitted changes',
      'Build a service (trigger, poll, extract version)',
      'Deploy using the build version',
      'Full git → plan → build → deploy → verify workflow',
    ],
    examples: [
      'Build {repo}',
      'Build and deploy {repo}',
      'Deploy the latest build',
    ],
  },
  'code-writer': {
    title: 'Code Writer — Generate & Modify Code · Rachnakar (रचनाकार)',
    capabilities: [
      'Write new files, modules, and functions',
      'Refactor existing code for clarity',
      'Implement features from requirements',
    ],
    examples: [
      'Add input validation to the login function',
      'Refactor the UserService to use dependency injection',
    ],
  },
  'code-reviewer': {
    title: 'Code Reviewer — Critical Review · Parikshak (परीक्षक)',
    capabilities: [
      'Identify bugs and security vulnerabilities',
      'Suggest performance improvements',
      'Flag style violations and anti-patterns',
    ],
    examples: [
      'Review the auth module for security issues',
      'Review the last 3 commits for quality',
    ],
  },
  'code-tester': {
    title: 'Code Tester — Testing & Debugging · Nirikshak (निरीक्षक)',
    capabilities: [
      'Write unit tests, integration tests, and fixtures',
      'Debug failing tests and trace issues',
      'Optimize code quality and readability',
    ],
    examples: [
      'Write unit tests for the PaymentService class',
      'Debug why test_auth_flow is failing',
    ],
  },
  'debug-agent': {
    title: 'Debug Agent — Autonomous Debugging · Khojak (खोजक)',
    capabilities: [
      'Reproduce bugs by running failing tests/commands',
      'Trace errors through code to find root cause',
      'Auto-fix bugs and verify with tests',
    ],
    examples: [
      'Debug tests/test_auth.py::test_login',
      'Fix the AttributeError in the payment module',
    ],
  },
  'security': {
    title: 'Security Agent — Cybersecurity Audit · Surakshak (सुरक्षक)',
    capabilities: [
      'OWASP Top 10 static analysis',
      'Dependency audit: CVEs, outdated packages',
      'Secrets detection: hardcoded API keys, tokens',
    ],
    examples: [
      'Run a full security audit on this repo',
      'Scan for hardcoded secrets and API keys',
    ],
  },
};

interface Props {
  agent: string;
  description?: string;
}

export function WelcomeMessage({ agent, description }: Props) {
  const welcome = AGENT_WELCOME[agent];
  const role = AGENT_ROLES[agent] || description;

  // Substitute {repo} with cwd basename
  const repoName = process.cwd().split('/').pop() || 'my-project';
  const substituteRepo = (s: string) => s.replace(/\{repo\}/g, repoName);

  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor="yellow"
      paddingX={2}
      paddingY={1}
      marginBottom={1}
    >
      <Box>
        <Text bold color="yellow">Code Agents</Text>
        <Text color="gray"> v0.1.0</Text>
      </Box>

      <Box marginTop={1}>
        <Text color="cyan" bold>
          {welcome ? welcome.title : agent}
        </Text>
      </Box>

      {role && !welcome && (
        <Box>
          <Text color="gray">{role}</Text>
        </Box>
      )}

      {welcome && (
        <>
          <Box marginTop={1} flexDirection="column">
            <Text color="gray" dimColor>Capabilities:</Text>
            {welcome.capabilities.map((cap, i) => (
              <Text key={i} color="gray" dimColor>  • {cap}</Text>
            ))}
          </Box>

          <Box marginTop={1} flexDirection="column">
            <Text color="gray" dimColor>Try:</Text>
            {welcome.examples.map((ex, i) => (
              <Text key={i} color="green" dimColor>  {substituteRepo(ex)}</Text>
            ))}
          </Box>
        </>
      )}

      <Box marginTop={1} flexDirection="column">
        <Text color="gray" dimColor>Keyboard shortcuts:</Text>
        <Text color="gray" dimColor>  Shift+Tab  cycle mode (Chat / Plan / Edit)</Text>
        <Text color="gray" dimColor>  Ctrl+C     cancel stream or exit</Text>
        <Text color="gray" dimColor>  Escape     clear input</Text>
        <Text color="gray" dimColor>  /quit      exit the session</Text>
      </Box>
    </Box>
  );
}
