import { describe, it, expect } from 'vitest';
import { suggestSkills } from '../src/client/SkillSuggester.js';

describe('SkillSuggester', () => {
  it('suggests test-related skills for test keyword', () => {
    const result = suggestSkills('write unit tests for payment module', 'code-tester');
    expect(result.length).toBeGreaterThanOrEqual(1);
    expect(result.some(s => s.name.includes('test'))).toBe(true);
  });

  it('suggests deploy-related skills', () => {
    const result = suggestSkills('deploy to production', 'jenkins-cicd');
    expect(result.length).toBeGreaterThanOrEqual(1);
    expect(result.some(s => s.name.includes('deploy'))).toBe(true);
  });

  it('suggests debug skills for error keyword', () => {
    const result = suggestSkills('getting an error in auth module', 'auto-pilot');
    expect(result.length).toBeGreaterThanOrEqual(1);
  });

  it('returns max 3 suggestions', () => {
    // 'test' + 'debug' + 'fix' + 'error' = many possible skills
    const result = suggestSkills('test debug fix error coverage', 'auto-pilot');
    expect(result.length).toBeLessThanOrEqual(3);
  });

  it('skips when already invoking a skill', () => {
    const result = suggestSkills('/auto-pilot:debug', 'auto-pilot');
    expect(result).toEqual([]);
  });

  it('returns empty for no keyword match', () => {
    const result = suggestSkills('hello world', 'auto-pilot');
    expect(result).toEqual([]);
  });

  it('formats commands with agent prefix', () => {
    const result = suggestSkills('review the code', 'code-reviewer');
    expect(result.length).toBeGreaterThanOrEqual(1);
    expect(result[0].command).toMatch(/^\/code-reviewer:/);
  });

  it('suggests jira skills for ticket keyword', () => {
    const result = suggestSkills('read the ticket details', 'jira-ops');
    expect(result.some(s => s.name.includes('ticket'))).toBe(true);
  });
});
