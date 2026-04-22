import { describe, it, expect } from 'vitest';
import { trimContext, estimateTokens } from '../src/client/ContextTrimmer.js';
import type { ChatMessage } from '../src/client/types.js';

describe('ContextTrimmer', () => {
  const msg = (role: 'user' | 'assistant', content: string): ChatMessage => ({ role, content });

  it('returns unchanged for small conversations', () => {
    const msgs = [msg('user', 'hello'), msg('assistant', 'hi')];
    const result = trimContext(msgs, 5);
    expect(result.messages).toEqual(msgs);
    expect(result.trimmedCount).toBe(0);
  });

  it('trims older messages beyond window', () => {
    // 6 user-assistant pairs + system = 13 messages, window=3
    const msgs: ChatMessage[] = [msg('user', 'system prompt')];
    for (let i = 1; i <= 6; i++) {
      msgs.push(msg('user', `question ${i}`));
      msgs.push(msg('assistant', `answer ${i}`));
    }

    const result = trimContext(msgs, 3);
    expect(result.trimmedCount).toBeGreaterThan(0);
    // Should keep first message + last 3 pairs
    expect(result.messages[0].content).toBe('system prompt');
    expect(result.messages[result.messages.length - 1].content).toBe('answer 6');
  });

  it('preserves messages with code blocks', () => {
    const msgs: ChatMessage[] = [
      msg('user', 'system'),
      msg('user', 'q1'),
      msg('assistant', 'here is code:\n```bash\necho hi\n```'),
      msg('user', 'q2'),
      msg('assistant', 'a2'),
      msg('user', 'q3'),
      msg('assistant', 'a3'),
      msg('user', 'q4'),
      msg('assistant', 'a4'),
      msg('user', 'q5'),
      msg('assistant', 'a5'),
    ];

    const result = trimContext(msgs, 2);
    // Code block message should be preserved even though it's old
    const hasCodeBlock = result.messages.some(m => m.content.includes('```bash'));
    expect(hasCodeBlock).toBe(true);
  });

  it('always preserves first message', () => {
    const msgs: ChatMessage[] = [msg('user', 'SYSTEM')];
    for (let i = 0; i < 20; i++) {
      msgs.push(msg('user', `q${i}`));
      msgs.push(msg('assistant', `a${i}`));
    }

    const result = trimContext(msgs, 2);
    expect(result.messages[0].content).toBe('SYSTEM');
  });

  it('no-ops when within window', () => {
    const msgs: ChatMessage[] = [
      msg('user', 'q1'), msg('assistant', 'a1'),
      msg('user', 'q2'), msg('assistant', 'a2'),
    ];
    const result = trimContext(msgs, 5);
    expect(result.trimmedCount).toBe(0);
  });
});

describe('estimateTokens', () => {
  it('estimates roughly 1 token per 4 chars', () => {
    const msgs = [{ role: 'user' as const, content: 'a'.repeat(400) }];
    expect(estimateTokens(msgs)).toBe(100);
  });

  it('returns 0 for empty messages', () => {
    expect(estimateTokens([])).toBe(0);
  });
});
