/**
 * BackgroundTasks — push agent tasks to background, continue working.
 *
 * Ported from code_agents/chat/chat_background.py.
 * Manages concurrent background streaming tasks with output buffering,
 * result capture, and foreground replay.
 */

import type { ChatMessage } from './types.js';

export interface BackgroundTask {
  id: number;
  displayName: string;
  agentName: string;
  userInput: string;
  status: 'running' | 'done' | 'error';
  startedAt: number;
  outputBuffer: string[];
  fullResponse: string | null;
  error: string | null;
  resultSummary: string;
  messages: ChatMessage[];
  abortFn: (() => void) | null;
}

const MAX_CONCURRENT = parseInt(process.env['CODE_AGENTS_MAX_BACKGROUND'] || '3', 10);

/**
 * Generate a readable task name from agent + prompt.
 */
function generateTaskName(agentName: string, userInput: string): string {
  const lower = userInput.toLowerCase();
  let action = 'task';
  for (const word of ['build', 'deploy', 'review', 'test', 'analyze', 'check',
                       'run', 'investigate', 'search', 'create', 'fix', 'debug']) {
    if (lower.includes(word)) { action = word; break; }
  }

  const words = userInput.split(/\s+/);
  let target = '';
  for (const w of words) {
    if (w.includes('-') && w.length > 5) {
      target = w.replace(/[.,;:"'()\[\]]/g, '');
      break;
    }
    if (w.includes('/') && !w.includes('http')) {
      target = w.split('/').pop()?.replace(/[.,;:"'()\[\]]/g, '') || '';
      break;
    }
  }

  return target ? `${action}:${target}` : `${action}:${agentName}`;
}

function formatElapsed(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${String(s).padStart(2, '0')}s`;
}

export class BackgroundTaskManager {
  private tasks = new Map<number, BackgroundTask>();
  private nextId = 1;

  createTask(
    agentName: string,
    userInput: string,
    messages: ChatMessage[],
  ): BackgroundTask {
    const task: BackgroundTask = {
      id: this.nextId++,
      displayName: generateTaskName(agentName, userInput),
      agentName,
      userInput,
      status: 'running',
      startedAt: Date.now(),
      outputBuffer: [],
      fullResponse: null,
      error: null,
      resultSummary: '',
      messages: [...messages],
      abortFn: null,
    };
    this.tasks.set(task.id, task);
    return task;
  }

  getTask(id: number): BackgroundTask | undefined {
    return this.tasks.get(id);
  }

  listTasks(): BackgroundTask[] {
    return [...this.tasks.values()];
  }

  removeTask(id: number): void {
    this.tasks.delete(id);
  }

  activeCount(): number {
    let count = 0;
    for (const t of this.tasks.values()) {
      if (t.status === 'running') count++;
    }
    return count;
  }

  canCreate(): boolean {
    return this.activeCount() < MAX_CONCURRENT;
  }

  doneTasks(): BackgroundTask[] {
    return this.listTasks().filter(t => t.status === 'done' || t.status === 'error');
  }

  completeTask(
    id: number,
    fullResponse: string | null,
    error: string | null,
  ): void {
    const task = this.tasks.get(id);
    if (!task) return;

    if (error) {
      task.status = 'error';
      task.error = error;
    } else if (fullResponse) {
      task.status = 'done';
      task.fullResponse = fullResponse;
      // Extract summary from response
      for (const line of fullResponse.split('\n')) {
        const trimmed = line.trim();
        if (['SUCCESS', 'FAILED', 'ERROR', 'BUILD #', 'DEPLOYED'].some(
          kw => trimmed.toUpperCase().includes(kw)
        )) {
          task.resultSummary = trimmed.slice(0, 80);
          break;
        }
      }
      if (!task.resultSummary) {
        task.resultSummary = fullResponse.slice(0, 60).replace(/\n/g, ' ');
      }
    } else {
      task.status = 'error';
      task.error = 'No response received';
    }
  }

  formatTaskList(): string {
    const tasks = this.listTasks();
    if (tasks.length === 0) return '  No background tasks.';

    return tasks.map(t => {
      const elapsed = formatElapsed(Date.now() - t.startedAt);
      const icon = t.status === 'running' ? '⟳' : t.status === 'done' ? '✓' : '✗';
      const summary = t.resultSummary || t.userInput.slice(0, 40);
      return `  #${t.id} ${t.displayName} (${t.status}, ${elapsed}) ${icon} — ${summary}`;
    }).join('\n');
  }
}

// Singleton
let _manager: BackgroundTaskManager | null = null;

export function getBackgroundManager(): BackgroundTaskManager {
  if (!_manager) _manager = new BackgroundTaskManager();
  return _manager;
}
