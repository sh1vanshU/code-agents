// Code Agents — Approval Card Component
// Renders approve/deny/auto-run inline cards for agent command execution

import { store, type ApprovalRequest } from '../state';
import { respondApproval } from '../api';
import { escapeHtml } from '../markdown/renderer';

export class ApprovalCard {
  private el: HTMLElement;

  constructor(private request: ApprovalRequest) {
    this.el = document.createElement('div');
    this.el.className = 'approval-card animate-in';
    this.render();
  }

  private render(): void {
    this.el.innerHTML = `
      <div class="approval-card-title">
        <span>&#9888;</span>
        <span>${escapeHtml(this.request.agent)} wants to run</span>
      </div>
      <div class="approval-card-command">${escapeHtml(this.request.command)}</div>
      <div class="approval-card-actions">
        <button class="btn btn-success btn-approve" data-id="${this.request.id}">&#10003; Approve</button>
        <button class="btn btn-danger btn-deny" data-id="${this.request.id}">&#10007; Deny</button>
        <button class="btn btn-ghost btn-autorun" data-id="${this.request.id}">&#9679; Auto-run all</button>
      </div>
    `;

    // Approve
    this.el.querySelector('.btn-approve')?.addEventListener('click', () => {
      respondApproval(this.request.id, true);
      this.markResolved('approved');
    });

    // Deny
    this.el.querySelector('.btn-deny')?.addEventListener('click', () => {
      respondApproval(this.request.id, false);
      this.markResolved('denied');
    });

    // Auto-run (approve + enable auto-run for future)
    this.el.querySelector('.btn-autorun')?.addEventListener('click', () => {
      respondApproval(this.request.id, true);
      store.updateSettings({ autoRun: true });
      this.markResolved('auto-run enabled');
    });
  }

  private markResolved(status: string): void {
    store.update({ pendingApproval: null });
    this.el.innerHTML = `
      <div class="approval-card" style="opacity:0.6;border-color:var(--ca-border)">
        <div style="font-size:var(--ca-font-size-sm);color:var(--ca-text-muted)">
          &#10003; ${escapeHtml(status)} — ${escapeHtml(this.request.command)}
        </div>
      </div>
    `;
  }

  getElement(): HTMLElement {
    return this.el;
  }
}
