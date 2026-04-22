/**
 * ProgressDashboard — Multi-step operation progress display.
 */

import React from 'react';
import { Box, Text } from 'ink';
import Spinner from 'ink-spinner';

interface Step {
  label: string;
  status: 'pending' | 'running' | 'done' | 'error' | 'skipped';
  detail?: string;
}

interface Props {
  title: string;
  steps: Step[];
}

const STATUS_ICON: Record<Step['status'], string> = {
  pending: '○',
  running: '',  // will use spinner
  done: '✓',
  error: '✗',
  skipped: '–',
};

const STATUS_COLOR: Record<Step['status'], string> = {
  pending: 'gray',
  running: 'yellow',
  done: 'green',
  error: 'red',
  skipped: 'gray',
};

export function ProgressDashboard({ title, steps }: Props) {
  const done = steps.filter(s => s.status === 'done').length;
  const total = steps.filter(s => s.status !== 'skipped').length;

  return (
    <Box flexDirection="column" borderStyle="single" borderColor="gray" paddingX={1}>
      <Box justifyContent="space-between">
        <Text bold>{title}</Text>
        <Text color="gray">{done}/{total}</Text>
      </Box>
      <Text color="gray">{'─'.repeat(40)}</Text>
      {steps.map((step, i) => (
        <Box key={i} gap={1}>
          {step.status === 'running' ? (
            <Text color="yellow"><Spinner type="dots" /></Text>
          ) : (
            <Text color={STATUS_COLOR[step.status]}>{STATUS_ICON[step.status]}</Text>
          )}
          <Text color={STATUS_COLOR[step.status]}>{step.label}</Text>
          {step.detail && <Text color="gray"> — {step.detail}</Text>}
        </Box>
      ))}
    </Box>
  );
}
