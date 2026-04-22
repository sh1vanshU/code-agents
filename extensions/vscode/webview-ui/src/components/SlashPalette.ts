// Code Agents — Slash Command Palette (with keyboard navigation)

import { store } from '../state';

export interface SlashCommand {
  command: string;
  description: string;
  category: string;
}

export const SLASH_COMMANDS: SlashCommand[] = [
  // Navigation & Help
  { command: 'help', description: 'Show all commands', category: 'Navigation' },
  { command: 'open', description: 'Open related resource', category: 'Navigation' },
  { command: 'setup', description: 'Run setup wizard', category: 'Navigation' },
  { command: 'restart', description: 'Restart chat', category: 'Navigation' },
  { command: 'quit', description: 'Exit chat', category: 'Navigation' },

  // Session
  { command: 'clear', description: 'Clear session, start fresh', category: 'Session' },
  { command: 'history', description: 'List saved sessions', category: 'Session' },
  { command: 'resume', description: 'Resume a saved session', category: 'Session' },
  { command: 'export', description: 'Export conversation', category: 'Session' },
  { command: 'session', description: 'Show session ID', category: 'Session' },
  { command: 'delete-chat', description: 'Delete a saved session', category: 'Session' },

  // Agent & Skills
  { command: 'agent', description: 'Switch to another agent', category: 'Agent' },
  { command: 'agents', description: 'List all agents', category: 'Agent' },
  { command: 'skills', description: 'List agent skills', category: 'Agent' },
  { command: 'rules', description: 'Show active rules', category: 'Agent' },
  { command: 'memory', description: 'Show agent memory', category: 'Agent' },
  { command: 'tokens', description: 'Token usage stats', category: 'Agent' },

  // Code Analysis
  { command: 'review', description: 'Code review current file', category: 'Code' },
  { command: 'refactor', description: 'Refactoring suggestions', category: 'Code' },
  { command: 'blame', description: 'Deep git blame story', category: 'Code' },
  { command: 'deps', description: 'Dependency tree', category: 'Code' },
  { command: 'impact', description: 'Impact analysis', category: 'Code' },
  { command: 'solve', description: 'Problem decomposition', category: 'Code' },
  { command: 'generate-tests', description: 'Generate tests for file', category: 'Code' },
  { command: 'pr-preview', description: 'Preview PR before opening', category: 'Code' },
  { command: 'review-reply', description: 'Reply to PR review', category: 'Code' },
  { command: 'investigate', description: 'Search Kibana logs', category: 'Code' },

  // DevOps
  { command: 'run', description: 'Execute shell command', category: 'DevOps' },
  { command: 'bash', description: 'Direct shell execution', category: 'DevOps' },
  { command: 'flags', description: 'Feature flags analysis', category: 'DevOps' },
  { command: 'config-diff', description: 'Compare configs', category: 'DevOps' },

  // Config
  { command: 'model', description: 'Switch model', category: 'Config' },
  { command: 'backend', description: 'Switch backend', category: 'Config' },
  { command: 'theme', description: 'Switch color theme', category: 'Config' },

  // Runtime
  { command: 'plan', description: 'Create execution plan', category: 'Runtime' },
  { command: 'confirm', description: 'Toggle confirmation gate', category: 'Runtime' },
  { command: 'superpower', description: 'Auto-execute commands', category: 'Runtime' },
  { command: 'sandbox', description: 'Restrict writes to project', category: 'Runtime' },
  { command: 'verify', description: 'Auto-verify with reviewer', category: 'Runtime' },
  { command: 'pair', description: 'Pair programming mode', category: 'Runtime' },
  { command: 'mcp', description: 'MCP servers & tools', category: 'Runtime' },
  { command: 'bg', description: 'Background tasks', category: 'Runtime' },
  { command: 'repo', description: 'Switch repository', category: 'Runtime' },
  { command: 'btw', description: 'Side message to agent', category: 'Runtime' },

  // Testing
  { command: 'qa-suite', description: 'QA regression suite', category: 'Testing' },
  { command: 'coverage-boost', description: 'Auto-boost coverage', category: 'Testing' },
  { command: 'mutate', description: 'Mutation testing', category: 'Testing' },
  { command: 'testdata', description: 'Generate test fixtures', category: 'Testing' },
];

export class SlashPalette {
  private el: HTMLElement;
  private selectedIndex = 0;
  private filteredCommands: SlashCommand[] = [];
  private keydownHandler: ((e: KeyboardEvent) => void) | null = null;

  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'slash-palette hidden';
    this.el.id = 'slash-palette';

    // Single click delegation — prevents listener accumulation on re-render
    this.el.addEventListener('click', (e) => {
      const item = (e.target as HTMLElement).closest('.slash-item') as HTMLElement | null;
      if (item?.dataset.cmd) {
        this.selectCommand(item.dataset.cmd);
      }
    });

    store.subscribe((state) => {
      if (state.showSlashPalette) {
        this.show(state.slashFilter);
      } else {
        this.hide();
      }
    });
  }

  mount(parent: HTMLElement): void {
    parent.appendChild(this.el);
  }

  private show(filter: string): void {
    this.el.classList.remove('hidden');
    this.selectedIndex = 0;
    this.renderList(filter);
    this.attachKeyboard();
  }

  private hide(): void {
    this.el.classList.add('hidden');
    this.detachKeyboard();
  }

  /** Attach keyboard navigation to the document */
  private attachKeyboard(): void {
    this.detachKeyboard();
    this.keydownHandler = (e: KeyboardEvent) => {
      if (!store.getState().showSlashPalette) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        this.selectedIndex = Math.min(this.selectedIndex + 1, this.filteredCommands.length - 1);
        this.updateSelection();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        this.selectedIndex = Math.max(this.selectedIndex - 1, 0);
        this.updateSelection();
      } else if (e.key === 'Enter' && this.filteredCommands.length > 0) {
        e.preventDefault();
        this.selectCommand(this.filteredCommands[this.selectedIndex].command);
      } else if (e.key === 'Tab' && this.filteredCommands.length > 0) {
        e.preventDefault();
        this.selectCommand(this.filteredCommands[this.selectedIndex].command);
      }
    };
    document.addEventListener('keydown', this.keydownHandler, true);
  }

  private detachKeyboard(): void {
    if (this.keydownHandler) {
      document.removeEventListener('keydown', this.keydownHandler, true);
      this.keydownHandler = null;
    }
  }

  /** Update visual selection without full re-render */
  private updateSelection(): void {
    this.el.querySelectorAll('.slash-item').forEach((item, i) => {
      item.classList.toggle('selected', i === this.selectedIndex);
    });
    // Scroll selected into view
    const selected = this.el.querySelector('.slash-item.selected');
    selected?.scrollIntoView({ block: 'nearest' });
  }

  private renderList(filter: string): void {
    this.filteredCommands = SLASH_COMMANDS.filter(cmd =>
      cmd.command.includes(filter.toLowerCase()) ||
      cmd.description.toLowerCase().includes(filter.toLowerCase())
    );

    // Group by category
    const groups: Record<string, SlashCommand[]> = {};
    for (const cmd of this.filteredCommands) {
      if (!groups[cmd.category]) groups[cmd.category] = [];
      groups[cmd.category].push(cmd);
    }

    let html = '';
    let idx = 0;
    for (const [category, commands] of Object.entries(groups)) {
      html += `<div class="slash-category">${category}</div>`;
      for (const cmd of commands) {
        html += `<div class="slash-item ${idx === this.selectedIndex ? 'selected' : ''}" data-cmd="${cmd.command}" data-idx="${idx}">
          <span class="slash-item-cmd">/${cmd.command}</span>
          <span class="slash-item-desc">${cmd.description}</span>
        </div>`;
        idx++;
      }
    }

    if (this.filteredCommands.length === 0) {
      html = `<div class="palette-empty">No commands found</div>`;
    }

    this.el.innerHTML = `<div class="slash-palette-list">${html}</div>`;
    // Click handling delegated in constructor — no per-render listeners needed
  }

  private selectCommand(cmd: string): void {
    store.update({ showSlashPalette: false });
    const textarea = document.getElementById('chat-textarea') as HTMLTextAreaElement;
    if (textarea) {
      textarea.value = `/${cmd} `;
      textarea.focus();
    }
  }

  getElement(): HTMLElement {
    return this.el;
  }
}
