/**
 * Questionnaire — multi-choice interactive forms using ink SelectInput.
 *
 * Presents questions one at a time with arrow-key selection.
 * Calls onComplete with all answers once finished.
 */

import React, { useState, useCallback } from 'react';
import { Box, Text } from 'ink';
import { Select } from '@inkjs/ui';

export interface Question {
  key: string;
  label: string;
  options: string[];
  defaultValue?: string;
}

interface Props {
  questions: Question[];
  onComplete: (answers: Record<string, string>) => void;
}

export function Questionnaire({ questions, onComplete }: Props) {
  const [currentIdx, setCurrentIdx] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});

  const question = questions[currentIdx];

  const handleSelect = useCallback((value: string) => {
    const updated = { ...answers, [question.key]: value };
    setAnswers(updated);

    if (currentIdx + 1 < questions.length) {
      setCurrentIdx(currentIdx + 1);
    } else {
      onComplete(updated);
    }
  }, [answers, question, currentIdx, questions, onComplete]);

  if (!question) return null;

  const items = question.options.map(opt => ({ label: opt, value: opt }));

  return (
    <Box flexDirection="column" paddingX={1}>
      <Box marginBottom={1}>
        <Text bold color="cyan">
          Question {currentIdx + 1}/{questions.length}
        </Text>
      </Box>

      <Box marginBottom={1}>
        <Text>{question.label}</Text>
      </Box>

      <Select options={items} onChange={handleSelect} />

      {Object.keys(answers).length > 0 && (
        <Box marginTop={1} flexDirection="column">
          <Text color="gray" dimColor>Answered:</Text>
          {Object.entries(answers).map(([k, v]) => (
            <Text key={k} color="gray" dimColor>  {k}: {v}</Text>
          ))}
        </Box>
      )}
    </Box>
  );
}
