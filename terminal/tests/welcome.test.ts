import { describe, it, expect } from 'vitest';
import { AGENT_ROLES } from '../src/chat/WelcomeMessage.js';

describe('WelcomeMessage AGENT_ROLES', () => {
  it('has 19 agent roles', () => {
    expect(Object.keys(AGENT_ROLES).length).toBe(19);
  });

  it('includes core agents', () => {
    expect(AGENT_ROLES['auto-pilot']).toBeDefined();
    expect(AGENT_ROLES['jenkins-cicd']).toBeDefined();
    expect(AGENT_ROLES['code-writer']).toBeDefined();
    expect(AGENT_ROLES['code-reviewer']).toBeDefined();
    expect(AGENT_ROLES['code-tester']).toBeDefined();
    expect(AGENT_ROLES['debug-agent']).toBeDefined();
  });

  it('includes newer agents', () => {
    expect(AGENT_ROLES['github-actions']).toBeDefined();
    expect(AGENT_ROLES['db-ops']).toBeDefined();
    expect(AGENT_ROLES['pr-review']).toBeDefined();
    expect(AGENT_ROLES['terraform-ops']).toBeDefined();
    expect(AGENT_ROLES['grafana-ops']).toBeDefined();
  });

  it('all roles are non-empty strings', () => {
    for (const [name, role] of Object.entries(AGENT_ROLES)) {
      expect(typeof role).toBe('string');
      expect(role.length).toBeGreaterThan(5);
    }
  });
});
