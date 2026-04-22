/**
 * Code Agents — Session History (interoperable with Python chat_history)
 *
 * Reads and writes the same JSON format used by the Python CLI so sessions
 * are seamlessly portable between the TypeScript terminal and `code-agents chat`.
 *
 * Storage: ~/.code-agents/chat_history/{id}.json
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';
import * as crypto from 'node:crypto';
import type { ChatMessage } from '../client/types.js';

export interface Session {
  id: string;
  agent: string;
  repo_path: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
}

export interface SessionSummary {
  id: string;
  agent: string;
  repo_path: string;
  title: string;
  created_at: string;
  updated_at: string;
  messageCount: number;
}

const HISTORY_DIR = path.join(os.homedir(), '.code-agents', 'chat_history');

function ensureDir(): void {
  if (!fs.existsSync(HISTORY_DIR)) {
    fs.mkdirSync(HISTORY_DIR, { recursive: true });
  }
}

/** Validate and resolve session file path. Rejects path traversal attempts. */
function sessionPath(id: string): string {
  // Sanitise id to prevent path traversal
  const safe = id.replace(/[^a-zA-Z0-9_-]/g, '');
  if (!safe || safe.length < 4) {
    throw new Error(`Invalid session ID: ${id}`);
  }
  const resolved = path.join(HISTORY_DIR, `${safe}.json`);
  // Ensure resolved path is still inside HISTORY_DIR
  if (!resolved.startsWith(HISTORY_DIR)) {
    throw new Error(`Path traversal detected: ${id}`);
  }
  return resolved;
}

export function generateSessionId(): string {
  return crypto.randomUUID();
}

export function save(session: Session): void {
  ensureDir();
  const data: Session = {
    ...session,
    updated_at: new Date().toISOString(),
  };
  fs.writeFileSync(sessionPath(session.id), JSON.stringify(data, null, 2), 'utf-8');
}

export function load(id: string): Session | null {
  const p = sessionPath(id);
  if (!fs.existsSync(p)) return null;
  try {
    const raw = fs.readFileSync(p, 'utf-8');
    return JSON.parse(raw) as Session;
  } catch {
    return null;
  }
}

export function list(): SessionSummary[] {
  ensureDir();
  const files = fs.readdirSync(HISTORY_DIR).filter((f) => f.endsWith('.json'));
  const summaries: SessionSummary[] = [];

  for (const file of files) {
    try {
      const raw = fs.readFileSync(path.join(HISTORY_DIR, file), 'utf-8');
      const data = JSON.parse(raw) as Session;
      summaries.push({
        id: data.id,
        agent: data.agent,
        repo_path: data.repo_path,
        title: data.title,
        created_at: data.created_at,
        updated_at: data.updated_at,
        messageCount: data.messages?.length ?? 0,
      });
    } catch {
      // skip corrupt files
    }
  }

  // Most recent first
  summaries.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  return summaries;
}

export function findByRepo(repoPath: string): SessionSummary[] {
  return list().filter((s) => s.repo_path === repoPath);
}

export function remove(id: string): boolean {
  const p = sessionPath(id);
  if (!fs.existsSync(p)) return false;
  fs.unlinkSync(p);
  return true;
}

/** Create a new empty session */
export function create(agent: string, repoPath: string, title?: string): Session {
  const now = new Date().toISOString();
  return {
    id: generateSessionId(),
    agent,
    repo_path: repoPath,
    title: title ?? `Session ${now}`,
    created_at: now,
    updated_at: now,
    messages: [],
  };
}
