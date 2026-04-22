/**
 * Code Agents — Token Usage Tracker
 *
 * Tracks cumulative input / output / cached tokens per session with
 * human-friendly formatting and optional max-session-token limit
 * (via CODE_AGENTS_MAX_SESSION_TOKENS env var).
 */

export interface TokenUsage {
  input: number;
  output: number;
  cached?: number;
}

export class TokenTracker {
  private input = 0;
  private output = 0;
  private cached = 0;
  private readonly maxTokens: number | null;

  constructor() {
    const envMax = process.env['CODE_AGENTS_MAX_SESSION_TOKENS'];
    this.maxTokens = envMax ? parseInt(envMax, 10) : null;
    if (this.maxTokens !== null && isNaN(this.maxTokens)) {
      this.maxTokens = null;
    }
  }

  /** Record token usage from a single completion response */
  record(usage: TokenUsage): void {
    this.input += usage.input;
    this.output += usage.output;
    this.cached += usage.cached ?? 0;
  }

  /** Get cumulative totals */
  getTotal(): { input: number; output: number; cached: number; total: number } {
    const total = this.input + this.output;
    return { input: this.input, output: this.output, cached: this.cached, total };
  }

  /** Human-friendly summary, e.g. "3.2k tokens" */
  format(): string {
    const { total } = this.getTotal();
    if (total === 0) return '0 tokens';
    if (total < 1000) return `${total} tokens`;
    return `${(total / 1000).toFixed(1)}k tokens`;
  }

  /** Detailed breakdown */
  formatDetailed(): string {
    const fmt = (n: number): string => {
      if (n < 1000) return String(n);
      return `${(n / 1000).toFixed(1)}k`;
    };
    const parts = [`in: ${fmt(this.input)}`, `out: ${fmt(this.output)}`];
    if (this.cached > 0) {
      parts.push(`cached: ${fmt(this.cached)}`);
    }
    return parts.join(' · ');
  }

  /** Check if the session has exceeded the configured max token limit */
  isLimitExceeded(): boolean {
    if (this.maxTokens === null) return false;
    return this.getTotal().total >= this.maxTokens;
  }

  /** Get the configured max, or null if unlimited */
  getMaxTokens(): number | null {
    return this.maxTokens;
  }

  /** Reset counters */
  reset(): void {
    this.input = 0;
    this.output = 0;
    this.cached = 0;
  }
}
