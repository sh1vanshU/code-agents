// Code Agents — HTTP + SSE Streaming Client
// Security: buffer limits, stream timeouts, isDone atomicity, Content-Length typing

import * as http from 'http';
import * as https from 'https';
import type { Agent } from '../protocol';
import { logger } from './Logger';

const MAX_BUFFER_SIZE = 1024 * 1024; // 1MB — prevents DoS via unbounded streams
const STREAM_TIMEOUT_MS = 120_000;   // 2 min — prevents hanging on stalled servers

interface ChatMessage {
  role: string;
  content: string;
}

export class ApiClient {
  private serverUrl: string;
  private abortController: AbortController | null = null;

  constructor(serverUrl: string) {
    this.serverUrl = serverUrl;
    logger.debug('ApiClient', 'Initialized', { serverUrl });
  }

  setServerUrl(url: string): void {
    // Validate URL before accepting
    try {
      const parsed = new URL(url);
      if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
        logger.warn('ApiClient', 'Rejected non-HTTP server URL', { url });
        return;
      }
      this.serverUrl = url;
    } catch {
      logger.warn('ApiClient', 'Rejected invalid server URL', { url });
    }
  }

  /** Check if the server is reachable */
  async checkHealth(): Promise<boolean> {
    try {
      const res = await this.fetch('GET', '/health', undefined, 3000);
      return res.statusCode === 200;
    } catch {
      return false;
    }
  }

  /** Fetch list of agents from server */
  async getAgents(): Promise<Agent[]> {
    try {
      const res = await this.fetch('GET', '/v1/agents', undefined, 5000);
      if (res.statusCode !== 200) return [];
      const data = JSON.parse(res.body);
      return Array.isArray(data) ? data : (data.agents || []);
    } catch {
      return [];
    }
  }

  /** Stream chat completion via SSE. Calls onToken for each content delta. */
  async streamChat(
    agent: string,
    messages: ChatMessage[],
    onToken: (token: string) => void,
    onDone: (fullContent: string) => void,
    onError: (error: string) => void,
  ): Promise<void> {
    logger.info('ApiClient', 'Starting SSE stream', { agent, messageCount: messages.length });
    const url = new URL(this.serverUrl);
    const isHttps = url.protocol === 'https:';
    const lib = isHttps ? https : http;

    const body = JSON.stringify({
      model: agent,
      messages,
      stream: true,
    });

    return new Promise<void>((resolve) => {
      let resolved = false;
      let isDone = false;

      const finish = () => {
        if (!resolved) {
          resolved = true;
          this.abortController = null;
          resolve();
        }
      };

      const req = lib.request(
        {
          hostname: url.hostname,
          port: url.port || (isHttps ? 443 : 80),
          path: '/v1/chat/completions',
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Content-Length': String(Buffer.byteLength(body)),
          },
        },
        (res) => {
          if (res.statusCode !== 200) {
            let errBody = '';
            res.on('data', (chunk) => { errBody += chunk; });
            res.on('end', () => {
              logger.error('ApiClient', 'SSE server error', undefined, { status: res.statusCode, body: errBody.slice(0, 200) });
              onError(`Server error ${res.statusCode}: ${errBody}`);
              res.removeAllListeners();
              finish();
            });
            res.on('error', () => { res.removeAllListeners(); finish(); });
            return;
          }

          let buffer = '';
          let fullContent = '';

          res.setEncoding('utf8');
          res.on('data', (chunk: string) => {
            if (isDone) return;

            // Check buffer size BEFORE appending to prevent memory exhaustion
            if (buffer.length + chunk.length > MAX_BUFFER_SIZE) {
              logger.warn('ApiClient', 'SSE buffer overflow', { bufferSize: buffer.length + chunk.length });
              isDone = true;
              onError('Response stream too large');
              req.destroy();
              finish();
              return;
            }

            buffer += chunk;
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
              if (isDone) return;

              const trimmed = line.trim();
              if (!trimmed || !trimmed.startsWith('data: ')) continue;

              const payload = trimmed.slice(6);
              if (payload === '[DONE]') {
                isDone = true;
                onDone(fullContent);
                req.destroy();
                finish();
                return;
              }

              try {
                const json = JSON.parse(payload);
                const content = json?.choices?.[0]?.delta?.content;
                if (content) {
                  fullContent += content;
                  onToken(content);
                }
              } catch {
                // skip malformed JSON lines
              }
            }
          });

          res.on('end', () => {
            if (!isDone) {
              onDone(fullContent);
            }
            res.removeAllListeners();
            finish();
          });

          res.on('error', (err) => {
            if (!isDone) {
              onError(err.message);
            }
            res.removeAllListeners();
            finish();
          });
        },
      );

      // Stream timeout — prevents hanging forever on stalled servers
      req.setTimeout(STREAM_TIMEOUT_MS, () => {
        if (!isDone) {
          logger.warn('ApiClient', 'SSE stream timeout', { timeoutMs: STREAM_TIMEOUT_MS });
          isDone = true;
          onError('Stream timeout — server did not respond');
          req.destroy();
          finish();
        }
      });

      req.on('error', (err) => {
        onError(err.message);
        finish();
      });

      // Cancellation — one-time abort handler
      this.abortController = new AbortController();
      const abortHandler = () => {
        isDone = true;
        req.destroy();
        this.abortController?.signal.removeEventListener('abort', abortHandler);
        finish();
      };
      this.abortController.signal.addEventListener('abort', abortHandler);

      req.write(body);
      req.end();
    });
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

    try {
      const res = await this.fetch('POST', '/v1/chat/completions', body, 60000);
      if (res.statusCode !== 200) {
        throw new Error(`Server error ${res.statusCode}`);
      }
      const data = JSON.parse(res.body);
      return data?.choices?.[0]?.message?.content || '';
    } catch (err: any) {
      throw new Error(err.message || 'Request failed');
    }
  }

  /** Low-level fetch helper using Node.js http/https */
  private fetch(
    method: string,
    path: string,
    body?: string,
    timeout = 10000,
  ): Promise<{ statusCode: number; body: string }> {
    return new Promise((resolve, reject) => {
      const url = new URL(this.serverUrl);
      const isHttps = url.protocol === 'https:';
      const lib = isHttps ? https : http;

      const headers: Record<string, string> = {};
      if (body) {
        headers['Content-Type'] = 'application/json';
        headers['Content-Length'] = String(Buffer.byteLength(body));
      }

      const req = lib.request(
        {
          hostname: url.hostname,
          port: url.port || (isHttps ? 443 : 80),
          path,
          method,
          headers,
          timeout,
        },
        (res) => {
          let data = '';
          res.setEncoding('utf8');
          res.on('data', (chunk) => { data += chunk; });
          res.on('end', () => {
            resolve({ statusCode: res.statusCode || 0, body: data });
          });
        },
      );

      req.on('timeout', () => {
        req.destroy();
        reject(new Error('Request timeout'));
      });
      req.on('error', reject);

      if (body) req.write(body);
      req.end();
    });
  }
}
