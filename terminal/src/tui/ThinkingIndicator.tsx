/**
 * ThinkingIndicator — Animated spinner with elapsed time during streaming.
 */

import React, { useState, useEffect } from 'react';
import { Box, Text } from 'ink';
import Spinner from 'ink-spinner';

interface Props {
  label?: string;
}

export function ThinkingIndicator({ label = 'Thinking' }: Props) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const start = Date.now();
    const timer = setInterval(() => {
      setElapsed((Date.now() - start) / 1000);
    }, 100);
    return () => clearInterval(timer);
  }, []);

  return (
    <Box>
      <Text color="yellow">
        <Spinner type="dots" />
      </Text>
      <Text color="yellow"> {label}...</Text>
      <Text color="gray"> {elapsed.toFixed(1)}s</Text>
    </Box>
  );
}
