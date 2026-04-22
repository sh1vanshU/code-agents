/**
 * usePlan — Plan state machine hook.
 *
 * Lifecycle: DRAFT -> PROPOSED -> APPROVED -> EXECUTING -> COMPLETED
 * Also supports REJECTED as a terminal state from PROPOSED.
 */

import { useState, useCallback } from 'react';
import type { PlanStep } from '../chat/PlanMode.js';

export type PlanPhase = 'IDLE' | 'DRAFT' | 'PROPOSED' | 'APPROVED' | 'EXECUTING' | 'COMPLETED' | 'REJECTED';

export interface PlanState {
  phase: PlanPhase;
  title: string;
  steps: PlanStep[];
}

const INITIAL_STATE: PlanState = {
  phase: 'IDLE',
  title: '',
  steps: [],
};

// Valid transitions
const TRANSITIONS: Record<PlanPhase, PlanPhase[]> = {
  IDLE: ['DRAFT'],
  DRAFT: ['PROPOSED', 'IDLE'],
  PROPOSED: ['APPROVED', 'REJECTED', 'IDLE'],
  APPROVED: ['EXECUTING'],
  EXECUTING: ['COMPLETED', 'IDLE'],
  COMPLETED: ['IDLE'],
  REJECTED: ['IDLE', 'DRAFT'],
};

export function usePlan() {
  const [plan, setPlan] = useState<PlanState>(INITIAL_STATE);

  const transition = useCallback((nextPhase: PlanPhase) => {
    setPlan(prev => {
      const allowed = TRANSITIONS[prev.phase];
      if (!allowed?.includes(nextPhase)) {
        return prev; // invalid transition — no-op
      }
      return { ...prev, phase: nextPhase };
    });
  }, []);

  const draft = useCallback((title: string, steps: PlanStep[]) => {
    setPlan({ phase: 'DRAFT', title, steps });
  }, []);

  const propose = useCallback(() => transition('PROPOSED'), [transition]);
  const approve = useCallback(() => transition('APPROVED'), [transition]);
  const reject = useCallback(() => transition('REJECTED'), [transition]);
  const execute = useCallback(() => transition('EXECUTING'), [transition]);

  const complete = useCallback(() => {
    setPlan(prev => ({
      ...prev,
      phase: 'COMPLETED',
      steps: prev.steps.map(s => ({ ...s, status: s.status === 'running' ? 'done' : s.status })),
    }));
  }, []);

  const updateStep = useCallback((stepId: string, status: PlanStep['status']) => {
    setPlan(prev => ({
      ...prev,
      steps: prev.steps.map(s => (s.id === stepId ? { ...s, status } : s)),
    }));
  }, []);

  const reset = useCallback(() => setPlan(INITIAL_STATE), []);

  return {
    plan,
    draft,
    propose,
    approve,
    reject,
    execute,
    complete,
    updateStep,
    reset,
  };
}
