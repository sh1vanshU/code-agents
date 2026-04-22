import { describe, it, expect } from 'vitest';
import { analyzeRequest } from '../src/client/Orchestrator.js';

describe('Orchestrator', () => {
  it('routes build/deploy to jenkins-cicd', () => {
    const result = analyzeRequest('trigger jenkins build and deploy pipeline');
    expect(result.shouldDelegate).toBe(true);
    expect(result.bestAgent).toBe('jenkins-cicd');
    expect(result.score).toBeGreaterThanOrEqual(2);
  });

  it('routes test requests to code-tester', () => {
    const result = analyzeRequest('write unit tests for the payment module');
    expect(result.shouldDelegate).toBe(true);
    expect(result.bestAgent).toBe('code-tester');
  });

  it('routes git operations to git-ops', () => {
    const result = analyzeRequest('create a new branch from main and push');
    expect(result.shouldDelegate).toBe(true);
    expect(result.bestAgent).toBe('git-ops');
  });

  it('routes code review to code-reviewer', () => {
    const result = analyzeRequest('review the pull request for security vulnerabilities');
    expect(result.shouldDelegate).toBe(true);
    expect(result.bestAgent).toBe('code-reviewer');
  });

  it('routes SQL queries to redash-query', () => {
    const result = analyzeRequest('run a SQL query to check the orders table');
    expect(result.shouldDelegate).toBe(true);
    expect(result.bestAgent).toBe('redash-query');
  });

  it('skips conversational patterns', () => {
    const result = analyzeRequest('yes');
    expect(result.shouldDelegate).toBe(false);
  });

  it('skips for "ok"', () => {
    const result = analyzeRequest('ok');
    expect(result.shouldDelegate).toBe(false);
  });

  it('returns auto-pilot for ambiguous requests', () => {
    const result = analyzeRequest('help me with something');
    expect(result.shouldDelegate).toBe(false);
  });

  it('multi-word keywords score higher', () => {
    const result = analyzeRequest('trigger build');
    expect(result.bestAgent).toBe('jenkins-cicd');
    expect(result.score).toBeGreaterThanOrEqual(2);
  });

  it('preserves current agent for conversational', () => {
    const result = analyzeRequest('proceed', 'jenkins-cicd');
    expect(result.bestAgent).toBe('jenkins-cicd');
    expect(result.shouldDelegate).toBe(false);
  });
});
