import { describe, it, expect } from 'vitest';
import { estimateComplexity } from '../src/client/ComplexityDetector.js';

describe('ComplexityDetector', () => {
  it('detects refactor as complex', () => {
    const result = estimateComplexity('refactor the payment service to use async/await');
    expect(result.score).toBeGreaterThanOrEqual(3);
    expect(result.reasons).toContain('refactor');
  });

  it('detects migration as complex', () => {
    const result = estimateComplexity('migrate all endpoints from Express to FastAPI');
    expect(result.shouldSuggestPlan).toBe(true);
    expect(result.score).toBeGreaterThanOrEqual(4);
  });

  it('detects multi-step CI/CD as complex', () => {
    const result = estimateComplexity('build and deploy pg-acquiring-biz to dev, then verify');
    expect(result.shouldSuggestPlan).toBe(true);
    expect(result.score).toBeGreaterThanOrEqual(4);
  });

  it('flags build deploy verify pipeline', () => {
    const result = estimateComplexity('build, deploy and verify the release branch');
    expect(result.shouldSuggestPlan).toBe(true);
  });

  it('detects complete rewrite as highly complex', () => {
    const result = estimateComplexity('complete rewrite of the auth module from scratch');
    expect(result.score).toBeGreaterThanOrEqual(7);
  });

  it('gives bonus for long messages', () => {
    const short = estimateComplexity('refactor');
    const long = estimateComplexity('refactor ' + 'x'.repeat(350));
    expect(long.score).toBeGreaterThan(short.score);
  });

  it('returns low score for simple messages', () => {
    const result = estimateComplexity('fix the typo in README');
    expect(result.shouldSuggestPlan).toBe(false);
    expect(result.score).toBeLessThan(4);
  });

  it('simple question is not complex', () => {
    const result = estimateComplexity('how does the auth module work?');
    expect(result.shouldSuggestPlan).toBe(false);
    expect(result.score).toBe(0);
  });

  it('returns matched reasons', () => {
    const result = estimateComplexity('rewrite all files from scratch');
    expect(result.reasons.length).toBeGreaterThanOrEqual(2);
  });

  it('detects file count mentions', () => {
    const result = estimateComplexity('update 25 files to use the new API');
    expect(result.reasons.some(r => r.includes('25 files'))).toBe(true);
  });
});
