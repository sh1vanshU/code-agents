/**
 * Code Agents — Client-side Config Loader
 *
 * Two-tier config merge (same precedence as Python env_loader.py):
 *   1. Global:   ~/.code-agents/config.env
 *   2. Per-repo: <cwd>/.env.code-agents  (overrides global)
 *
 * Reads dotenv-style KEY=VALUE files. Does NOT modify process.env.
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';

const GLOBAL_CONFIG = path.join(os.homedir(), '.code-agents', 'config.env');
const REPO_CONFIG_NAME = '.env.code-agents';

/** Parse a dotenv-style file into a plain object */
function parseDotenv(filePath: string): Record<string, string> {
  if (!fs.existsSync(filePath)) return {};
  const result: Record<string, string> = {};

  const content = fs.readFileSync(filePath, 'utf-8');
  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    // Skip empty lines and comments
    if (!trimmed || trimmed.startsWith('#')) continue;

    const eqIdx = trimmed.indexOf('=');
    if (eqIdx === -1) continue;

    const key = trimmed.slice(0, eqIdx).trim();
    let value = trimmed.slice(eqIdx + 1).trim();

    // Strip surrounding quotes (single or double)
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    if (key) {
      result[key] = value;
    }
  }
  return result;
}

let _cache: Record<string, string> | null = null;

/** Load merged config (global + per-repo). Cached after first call. */
export function loadConfig(cwd?: string): Record<string, string> {
  if (_cache) return _cache;

  const global = parseDotenv(GLOBAL_CONFIG);
  const repoPath = path.join(cwd ?? process.cwd(), REPO_CONFIG_NAME);
  const repo = parseDotenv(repoPath);

  // Repo overrides global
  _cache = { ...global, ...repo };
  return _cache;
}

/** Invalidate config cache (useful after config changes or in tests) */
export function reloadConfig(cwd?: string): Record<string, string> {
  _cache = null;
  return loadConfig(cwd);
}

/** Get a single config value by key. Falls back to process.env. */
export function getConfigValue(key: string): string | undefined {
  const config = loadConfig();
  return config[key] ?? process.env[key];
}

/** Derive the server URL from config or defaults (localhost:8000) */
export function getServerUrl(): string {
  const config = loadConfig();
  const host = config['HOST'] ?? process.env['HOST'] ?? '0.0.0.0';
  const port = config['PORT'] ?? process.env['PORT'] ?? '8000';
  // 0.0.0.0 is not reachable from a client; map to localhost
  const resolvedHost = host === '0.0.0.0' ? 'localhost' : host;
  return `http://${resolvedHost}:${port}`;
}
