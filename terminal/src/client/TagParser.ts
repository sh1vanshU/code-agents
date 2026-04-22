/**
 * TagParser — extract [DELEGATE:], [SKILL:], [REMEMBER:] tags from agent responses.
 * Also masks secrets in bash commands for safe display.
 *
 * Ported from code_agents/chat/chat_commands.py (lines 24-68).
 */

// ── Tag extraction ─────────────────────────────────────────────────

/** [DELEGATE:agent-name] prompt — must be at start of line */
const DELEGATE_RE = /^\[DELEGATE:([a-z0-9_-]+)\]\s*(.+)$/gm;

/** [SKILL:name] or [SKILL:agent:name] */
const SKILL_RE = /\[SKILL:([a-z0-9_:-]+)\]/g;

/** [REMEMBER:key=value] */
const REMEMBER_RE = /\[REMEMBER:([a-zA-Z_][a-zA-Z0-9_]*)=([^\]]+)\]/g;

export interface Delegation {
  agent: string;
  prompt: string;
}

export interface RememberPair {
  key: string;
  value: string;
}

export function extractDelegations(text: string): Delegation[] {
  const results: Delegation[] = [];
  let match: RegExpExecArray | null;
  const re = new RegExp(DELEGATE_RE.source, DELEGATE_RE.flags);
  while ((match = re.exec(text)) !== null) {
    const prompt = match[2].trim();
    if (prompt) {
      results.push({ agent: match[1], prompt });
    }
  }
  return results;
}

export function extractSkills(text: string): string[] {
  const results: string[] = [];
  let match: RegExpExecArray | null;
  const re = new RegExp(SKILL_RE.source, SKILL_RE.flags);
  while ((match = re.exec(text)) !== null) {
    results.push(match[1]);
  }
  return results;
}

export function extractRememberTags(text: string): RememberPair[] {
  const results: RememberPair[] = [];
  let match: RegExpExecArray | null;
  const re = new RegExp(REMEMBER_RE.source, REMEMBER_RE.flags);
  while ((match = re.exec(text)) !== null) {
    results.push({ key: match[1], value: match[2].trim() });
  }
  return results;
}

/** Strip all internal tags from text for display */
export function stripTags(text: string): string {
  return text
    .replace(/\[SKILL:[a-z0-9_:-]+\]/g, '')
    .replace(/\[DELEGATE:[a-z0-9_-]+\]/g, '')
    .replace(/\[REMEMBER:[^\]]+\]/g, '')
    .replace(/\[QUESTION:[^\]]+\]/g, '')
    .trim();
}

// ── Secret masking ─────────────────────────────────────────────────

const SECRET_PATTERNS: Array<[RegExp, string]> = [
  // Authorization headers
  [/(-H\s+["']Authorization:\s*(?:Basic|Bearer)\s+)([^"']+)(["'])/g, '$1●●●●●●$3'],
  // Token headers
  [/(-H\s+["'](?:X-Api-Key|Private-Token|X-Auth-Token|JENKINS-CRUMB):\s*)([^"']+)(["'])/g, '$1●●●●●●$3'],
  // --user user:password
  [/(--user\s+\S+?:)(\S+)/g, '$1●●●●●●'],
  // -u user:password
  [/(-u\s+\S+?:)(\S+)/g, '$1●●●●●●'],
  // Inline passwords in URLs: https://user:password@host
  [/(https?:\/\/[^:]+:)([^@]+)(@)/g, '$1●●●●●●$3'],
  // Base64-ish tokens in headers
  [/(-H\s+["'][^"']*:\s*)([A-Za-z0-9+/=]{20,})(["'])/g, '$1●●●●●●$3'],
];

/** Mask auth tokens in a command for safe terminal display. */
export function maskSecrets(cmd: string): string {
  let masked = cmd;
  for (const [pattern, replacement] of SECRET_PATTERNS) {
    masked = masked.replace(new RegExp(pattern.source, pattern.flags), replacement);
  }
  return masked;
}
