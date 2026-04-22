/**
 * Code Agents — Session Scratchpad
 *
 * Persists discovered facts as key-value pairs in
 * /tmp/code-agents/{sessionId}/state.json
 *
 * Interoperable with the Python session_scratchpad.py module which
 * uses the same path and JSON format.
 */

import * as fs from 'node:fs';
import * as path from 'node:path';

const BASE_DIR = '/tmp/code-agents';

export class Scratchpad {
  private readonly dir: string;
  private readonly filePath: string;

  constructor(sessionId: string) {
    // Sanitise session ID to prevent path traversal
    const safe = sessionId.replace(/[^a-zA-Z0-9_-]/g, '');
    if (!safe || safe.length < 4) {
      throw new Error(`Invalid session ID: ${sessionId}`);
    }
    this.dir = path.join(BASE_DIR, safe);
    // Ensure resolved path stays inside BASE_DIR
    if (!this.dir.startsWith(BASE_DIR)) {
      throw new Error(`Path traversal detected: ${sessionId}`);
    }
    this.filePath = path.join(this.dir, 'state.json');
  }

  /** Set a key-value pair */
  set(key: string, value: string): void {
    const data = this.readFile();
    data[key] = value;
    this.writeFile(data);
  }

  /** Get a value by key, or null if not found */
  get(key: string): string | null {
    const data = this.readFile();
    return data[key] ?? null;
  }

  /** Get all stored key-value pairs */
  getAll(): Record<string, string> {
    return this.readFile();
  }

  /** Remove all stored data */
  clear(): void {
    this.writeFile({});
  }

  /** Delete a single key */
  delete(key: string): boolean {
    const data = this.readFile();
    if (!(key in data)) return false;
    delete data[key];
    this.writeFile(data);
    return true;
  }

  // --- internals ---

  private ensureDir(): void {
    if (!fs.existsSync(this.dir)) {
      fs.mkdirSync(this.dir, { recursive: true });
    }
  }

  private readFile(): Record<string, string> {
    if (!fs.existsSync(this.filePath)) return {};
    try {
      const raw = fs.readFileSync(this.filePath, 'utf-8');
      return JSON.parse(raw) as Record<string, string>;
    } catch {
      return {};
    }
  }

  private writeFile(data: Record<string, string>): void {
    this.ensureDir();
    fs.writeFileSync(this.filePath, JSON.stringify(data, null, 2), 'utf-8');
  }
}
