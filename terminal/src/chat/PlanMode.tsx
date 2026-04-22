/**
 * PlanMode — displays a plan lifecycle with step checkmarks and approval prompt.
 *
 * Shows plan steps with status indicators (pending/running/done/failed),
 * and an approval prompt when the plan is in PROPOSED state.
 */

import React from 'react';
import { Box, Text } from 'ink';
import type { PlanState } from '../hooks/usePlan.js';

export interface PlanStep {
  id: string;
  label: string;
  status: 'pending' | 'running' | 'done' | 'failed';
}

interface Props {
  plan: PlanState;
  onApprove: () => void;
  onReject: () => void;
}

const STATUS_ICON: Record<PlanStep['status'], string> = {
  pending: '○',
  running: '◑',
  done: '●',
  failed: '✗',
};

const STATUS_COLOR: Record<PlanStep['status'], string> = {
  pending: 'gray',
  running: 'yellow',
  done: 'green',
  failed: 'red',
};

export function PlanMode({ plan, onApprove, onReject }: Props) {
  return (
    <Box flexDirection="column" paddingX={1}>
      <Box marginBottom={1}>
        <Text bold color="magenta">Plan</Text>
        <Text color="gray"> — </Text>
        <Text color="cyan">{plan.phase}</Text>
        {plan.title && <Text color="gray"> — {plan.title}</Text>}
      </Box>

      {plan.steps.map((step, i) => (
        <Box key={step.id || i}>
          <Text color={STATUS_COLOR[step.status]}>
            {' '}{STATUS_ICON[step.status]} {step.label}
          </Text>
        </Box>
      ))}

      {plan.phase === 'PROPOSED' && (
        <Box marginTop={1}>
          <Text color="yellow">
            Approve this plan? Press [y] to approve, [n] to reject.
          </Text>
        </Box>
      )}

      {plan.phase === 'COMPLETED' && (
        <Box marginTop={1}>
          <Text color="green">Plan completed.</Text>
        </Box>
      )}
    </Box>
  );
}
