/**
 * ContextTrimmer — manage conversation context window to prevent token overflow.
 *
 * Keeps the most recent N message pairs while always preserving system prompts
 * and messages containing code blocks (which are likely important context).
 */

import type { ChatMessage } from './types.js';

const DEFAULT_WINDOW = parseInt(process.env['CODE_AGENTS_CONTEXT_WINDOW'] || '10', 10);

export interface TrimResult {
  messages: ChatMessage[];
  trimmedCount: number;
}

/**
 * Trim messages to fit within the configured context window.
 *
 * Preserves:
 * - The first message (usually system prompt)
 * - Messages containing code blocks (``` markers)
 * - The most recent `window` user-assistant pairs
 *
 * @param messages  Full message array
 * @param window    Number of user-assistant pairs to keep (default from env)
 */
export function trimContext(
  messages: ChatMessage[],
  window: number = DEFAULT_WINDOW,
): TrimResult {
  if (messages.length <= 2) {
    return { messages, trimmedCount: 0 };
  }

  // Count user messages (each user msg + its assistant reply = 1 pair)
  const userIndices: number[] = [];
  for (let i = 0; i < messages.length; i++) {
    if (messages[i].role === 'user') userIndices.push(i);
  }

  // If within window, no trimming needed
  if (userIndices.length <= window) {
    return { messages, trimmedCount: 0 };
  }

  // Determine the cutoff: keep the last `window` user messages and everything after
  const cutoffUserIdx = userIndices[userIndices.length - window];
  const keep = new Set<number>();

  // Always keep index 0 (system prompt or first message)
  keep.add(0);

  // Keep everything from cutoff onward
  for (let i = cutoffUserIdx; i < messages.length; i++) {
    keep.add(i);
  }

  // Also keep messages with code blocks in the trimmed region
  for (let i = 1; i < cutoffUserIdx; i++) {
    if (messages[i].content.includes('```')) {
      keep.add(i);
    }
  }

  const result: ChatMessage[] = [];
  let trimmedCount = 0;

  for (let i = 0; i < messages.length; i++) {
    if (keep.has(i)) {
      result.push(messages[i]);
    } else {
      trimmedCount++;
    }
  }

  return { messages: result, trimmedCount };
}

/**
 * Estimate token count for a message array (rough: 1 token ≈ 4 chars).
 */
export function estimateTokens(messages: ChatMessage[]): number {
  let chars = 0;
  for (const msg of messages) {
    chars += msg.content.length;
  }
  return Math.ceil(chars / 4);
}
