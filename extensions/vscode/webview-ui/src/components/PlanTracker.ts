// Code Agents — Plan Mode Tracker Component

import { store, type PlanState } from '../state';
import { escapeHtml } from '../markdown/renderer';

const STEP_ICONS: Record<string, string> = {
  completed: '&#10003;',
  current: '&#9654;',
  pending: '&#9675;',
  failed: '&#10007;',
};

export class PlanTracker {
  private el: HTMLElement;

  constructor() {
    this.el = document.createElement('div');
    this.el.id = 'plan-tracker';

    store.subscribe((state) => {
      if (state.plan && state.mode === 'plan') {
        this.renderPlan(state.plan);
        this.el.style.display = 'block';
      } else {
        this.el.style.display = 'none';
      }
    });
  }

  mount(parent: HTMLElement): void {
    parent.appendChild(this.el);
  }

  private renderPlan(plan: PlanState): void {
    const completedCount = plan.steps.filter(s => s.status === 'completed').length;
    const totalSteps = plan.steps.length;
    const progress = totalSteps > 0 ? (completedCount / totalSteps) * 100 : 0;

    this.el.innerHTML = `
      <div class="plan-tracker">
        <div class="plan-header">
          <span class="plan-title">${escapeHtml(plan.title)}</span>
          <span class="plan-status ${plan.status}">${plan.status.toUpperCase()}</span>
        </div>

        <div class="plan-progress">
          <div class="plan-progress-bar">
            <div class="plan-progress-fill" style="width:${progress}%"></div>
          </div>
          <span class="plan-progress-text">${completedCount}/${totalSteps}</span>
        </div>

        <div class="plan-steps">
          ${plan.steps.map((step, i) => `
            <div class="plan-step ${step.status === 'current' ? 'current' : ''}">
              <span class="plan-step-icon ${step.status}">${STEP_ICONS[step.status]}</span>
              <span class="plan-step-text">${i + 1}. ${escapeHtml(step.text)}</span>
              ${step.status === 'current' ? '<span class="plan-step-indicator">current</span>' : ''}
            </div>
          `).join('')}
        </div>

        ${plan.status === 'executing' || plan.status === 'proposed' ? `
          <div class="plan-actions">
            ${plan.status === 'proposed' ? `
              <button class="btn btn-success btn-approve-plan">Approve</button>
              <button class="btn btn-danger btn-reject-plan">Reject</button>
              <button class="btn btn-edit-plan">Edit</button>
            ` : `
              <button class="btn btn-pause-plan">Pause</button>
              <button class="btn btn-danger btn-cancel-plan">Cancel</button>
            `}
          </div>
        ` : ''}
      </div>
    `;
  }

  getElement(): HTMLElement {
    return this.el;
  }
}
