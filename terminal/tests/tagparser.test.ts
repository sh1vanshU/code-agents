import { describe, it, expect } from 'vitest';
import {
  extractDelegations,
  extractSkills,
  extractRememberTags,
  stripTags,
  maskSecrets,
} from '../src/client/TagParser.js';

describe('TagParser', () => {
  describe('extractDelegations', () => {
    it('extracts single delegation', () => {
      const text = '[DELEGATE:code-reviewer] Review this code for security issues';
      const result = extractDelegations(text);
      expect(result).toHaveLength(1);
      expect(result[0].agent).toBe('code-reviewer');
      expect(result[0].prompt).toBe('Review this code for security issues');
    });

    it('extracts multiple delegations', () => {
      const text = '[DELEGATE:code-tester] Write tests\n[DELEGATE:jenkins-cicd] Trigger build';
      const result = extractDelegations(text);
      expect(result).toHaveLength(2);
      expect(result[0].agent).toBe('code-tester');
      expect(result[1].agent).toBe('jenkins-cicd');
    });

    it('skips empty prompts', () => {
      const text = '[DELEGATE:code-reviewer]   ';
      const result = extractDelegations(text);
      expect(result).toHaveLength(0);
    });

    it('does not match mid-line', () => {
      const text = 'Use [DELEGATE:agent] in your response';
      const result = extractDelegations(text);
      expect(result).toHaveLength(0);
    });
  });

  describe('extractSkills', () => {
    it('extracts single skill', () => {
      const result = extractSkills('Loading [SKILL:build] now');
      expect(result).toEqual(['build']);
    });

    it('extracts cross-agent skill', () => {
      const result = extractSkills('[SKILL:jenkins-cicd:deploy]');
      expect(result).toEqual(['jenkins-cicd:deploy']);
    });

    it('returns empty for no skills', () => {
      expect(extractSkills('no skills here')).toEqual([]);
    });
  });

  describe('extractRememberTags', () => {
    it('extracts key-value pairs', () => {
      const text = '[REMEMBER:image_tag=924-grv] [REMEMBER:env=qa4]';
      const result = extractRememberTags(text);
      expect(result).toHaveLength(2);
      expect(result[0]).toEqual({ key: 'image_tag', value: '924-grv' });
      expect(result[1]).toEqual({ key: 'env', value: 'qa4' });
    });
  });

  describe('stripTags', () => {
    it('strips all internal tags', () => {
      const text = 'Hello [SKILL:build] world [DELEGATE:agent] [REMEMBER:k=v] [QUESTION:env]';
      const result = stripTags(text);
      expect(result).toBe('Hello  world');
    });
  });

  describe('maskSecrets', () => {
    it('masks Authorization Bearer header', () => {
      const cmd = `curl -H "Authorization: Bearer sk-abc123xyz"`;
      const masked = maskSecrets(cmd);
      expect(masked).toContain('●●●●●●');
      expect(masked).not.toContain('sk-abc123xyz');
    });

    it('masks --user credentials', () => {
      const cmd = 'curl --user admin:secretpass http://example.com';
      const masked = maskSecrets(cmd);
      expect(masked).toContain('●●●●●●');
      expect(masked).not.toContain('secretpass');
    });

    it('masks -u credentials', () => {
      const cmd = 'curl -u user:token123 http://example.com';
      const masked = maskSecrets(cmd);
      expect(masked).not.toContain('token123');
    });

    it('masks inline URL passwords', () => {
      const cmd = 'curl https://admin:secret123@jenkins.local/api';
      const masked = maskSecrets(cmd);
      expect(masked).not.toContain('secret123');
      expect(masked).toContain('●●●●●●');
    });
  });
});
