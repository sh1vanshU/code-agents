/**
 * CommandPanel — arrow-key option selector using ink SelectInput.
 *
 * Generic reusable panel for picking from a list of options.
 * Used by /model, /backend, /theme, /agent when no argument is given.
 */

import React from 'react';
import { Box, Text } from 'ink';
import { Select } from '@inkjs/ui';

interface Props {
  title: string;
  options: string[];
  onSelect: (value: string) => void;
}

export function CommandPanel({ title, options, onSelect }: Props) {
  const items = options.map(opt => ({ label: opt, value: opt }));

  return (
    <Box flexDirection="column" paddingX={1}>
      <Box marginBottom={1}>
        <Text bold color="yellow">{title}</Text>
      </Box>

      <Select options={items} onChange={onSelect} />
    </Box>
  );
}
