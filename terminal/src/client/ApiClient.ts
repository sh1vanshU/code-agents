/**
 * Code Agents — HTTP + SSE Streaming Client (pure Node.js, no vscode dependency)
 * Adapted from extensions/vscode/src/services/ApiClient.ts
 *
 * Security: buffer limits (1MB), stream timeouts (120s), URL validation, cancellation
 */

import type { Agent, ChatMessage, CompletionRequest, SSEChunk, StreamEvent } from './types.js';

const MAX_BUFFER_SIZE = 1024 * 1024; // 1MB — prevents DoS via unbounded streams
const STREAM_TIMEOUT_MS = 120_000;   // 2 min — prevents hanging on stalled servers
const DEFAULT_TIMEOUT_MS = 10_000;

export class ApiClient {
  private serverUrl: string;
  private abortController: AbortController | null = null;

  constructor(serverUrl: string) {
    this.serverUrl = serverUrl;
  }

  setServerUrl(url: string): void {
    try {
      const parsed = new URL(url);
      if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return;
      this.serverUrl = url;
    } catch {
      // reject invalid URL silently
    }
  }

  getServerUrl(): string {
    return this.serverUrl;
  }

  /** Check if the server is reachable */
  async checkHealth(): Promise<boolean> {
    try {
      const res = await this.fetchJSON<{ status: string }>('GET', '/health', undefined, 3000);
      return res.status === 'ok';
    } catch {
      return false;
    }
  }

  /** Fetch list of agents from server */
  async getAgents(): Promise<Agent[]> {
    try {
      const data = await this.fetchJSON<Agent[] | { agents: Agent[] }>('GET', '/v1/agents', undefined, 5000);
      return Array.isArray(data) ? data : (data.agents || []);
    } catch {
      return [];
    }
  }

  /**
   * Stream chat completion via SSE as an async generator.
   * Yields typed StreamEvent objects for each SSE event.
   */
  async *streamChat(
    agent: string,
    messages: ChatMessage[],
    options?: { sessionId?: string; cwd?: string },
  ): AsyncGenerator<StreamEvent> {
    const body: CompletionRequest = {
      model: agent,
      messages,
      stream: true,
      session_id: options?.sessionId,
      cwd: options?.cwd,
    };

    this.abortController = new AbortController();
    const { signal } = this.abortController;

    let response: Response;
    try {
      response = await fetch(`${this.serverUrl}/v1/chat/completions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal,
      });
    } catch (err: any) {
      yield { type: 'error', message: err.message || 'Connection failed' };
      return;
    }

    if (!response.ok || !response.body) {
      const errBody = await response.text().catch(() => '');
      yield { type: 'error', message: `Server error ${response.status}: ${errBody.slice(0, 200)}` };
      return;
    }

    // Set up stream timeout
    const timeout = setTimeout(() => {
      this.abortController?.abort();
    }, STREAM_TIMEOUT_MS);

    let buffer = '';
    let fullContent = '';
    let totalBytes = 0;

    try {
      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        totalBytes += chunk.length;

        if (totalBytes > MAX_BUFFER_SIZE) {
          yield { type: 'error', message: 'Response stream too large' };
          reader.cancel();
          break;
        }

        buffer += chunk;
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || !trimmed.startsWith('data: ')) continue;

          const payload = trimmed.slice(6);
          if (payload === '[DONE]') {
            yield { type: 'done', fullContent };
            return;
          }

          try {
            const json: SSEChunk = JSON.parse(payload);
            const choice = json.choices?.[0];

            if (choice?.delta?.content) {
              fullContent += choice.delta.content;
              yield { type: 'token', content: choice.delta.content };
            }
            if (choice?.delta?.reasoning) {
              yield { type: 'reasoning', content: choice.delta.reasoning };
            }
            if (choice?.finish_reason === 'stop' || json.usage) {
              yield {
                type: 'done',
                fullContent,
                usage: json.usage,
                durationMs: json.duration_ms,
                sessionId: json.session_id,
              };
              return;
            }
          } catch {
            // skip malformed JSON lines
          }
        }
      }

      // Stream ended without [DONE] or finish_reason
      if (fullContent) {
        yield { type: 'done', fullContent };
      }
    } catch (err: any) {
      if (signal.aborted) {
        yield { type: 'error', message: 'Stream cancelled' };
      } else {
        yield { type: 'error', message: err.message || 'Stream error' };
      }
    } finally {
      clearTimeout(timeout);
      this.abortController = null;
    }
  }

  /** Cancel any in-flight streaming request */
  cancelStream(): void {
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
  }

  /** Non-streaming chat */
  async sendChat(agent: string, messages: ChatMessage[]): Promise<string> {
    const body = JSON.stringify({
      model: agent,
      messages,
      stream: false,
    });

    const data = await this.fetchJSON<{ choices: Array<{ message: { content: string } }> }>(
      'POST', '/v1/chat/completions', body, 60_000,
    );
    return data.choices?.[0]?.message?.content || '';
  }

  /** Generic JSON fetch helper using native fetch */
  private async fetchJSON<T>(
    method: string,
    path: string,
    body?: string,
    timeout = DEFAULT_TIMEOUT_MS,
  ): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);

    try {
      const headers: Record<string, string> = {};
      if (body) headers['Content-Type'] = 'application/json';

      const res = await fetch(`${this.serverUrl}${path}`, {
        method,
        headers,
        body,
        signal: controller.signal,
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      return await res.json() as T;
    } finally {
      clearTimeout(timer);
    }
  }
}
