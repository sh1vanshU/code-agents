/**
 * useChat — Main chat logic hook.
 *
 * Manages the send -> stream -> receive cycle, integrating the store,
 * streaming hook, agentic loop, delegation, skills, orchestrator,
 * complexity detection, skill suggestions, context trimming, and
 * background task management.
 */

import { useCallback, useRef } from 'react';
import type { ApiClient } from '../../client/ApiClient.js';
import type { ChatMessage } from '../../client/types.js';
import { useChatStore } from '../../state/store.js';
import { useStreaming } from './useStreaming.js';
import { useAgenticLoop } from './useAgenticLoop.js';
import { extractDelegations, extractSkills, extractRememberTags, stripTags } from '../../client/TagParser.js';
import { analyzeRequest } from '../../client/Orchestrator.js';
import { loadSkill, buildSkillMessage } from '../../client/SkillLoader.js';
import { scoreResponse } from '../../client/ConfidenceScorer.js';
import { estimateComplexity } from '../../client/ComplexityDetector.js';
import { suggestSkills } from '../../client/SkillSuggester.js';
import { trimContext } from '../../client/ContextTrimmer.js';
import { getBackgroundManager } from '../../client/BackgroundTasks.js';
import { Scratchpad } from '../../state/Scratchpad.js';

const MAX_DELEGATION_DEPTH = 3;

export interface UseChatReturn {
  sendMessage: (text: string) => Promise<void>;
  isStreaming: boolean;
  streamingContent: string;
  cancelStream: () => void;
  loopState: ReturnType<typeof useAgenticLoop>['loopState'];
  pendingCommands: string[];
  approveCommands: (cmds: string[]) => void;
  rejectCommands: () => void;
  backgroundToForeground: (taskId: number) => Promise<void>;
}

export function useChat(client: ApiClient): UseChatReturn {
  const agent = useChatStore((s) => s.agent);
  const sessionId = useChatStore((s) => s.sessionId);
  const repoPath = useChatStore((s) => s.repoPath);
  const messages = useChatStore((s) => s.messages);
  const addMessage = useChatStore((s) => s.addMessage);
  const setBusy = useChatStore((s) => s.setBusy);
  const setSessionId = useChatStore((s) => s.setSessionId);
  const setAgent = useChatStore((s) => s.setAgent);
  const updateTokens = useChatStore((s) => s.updateTokens);

  const streaming = useStreaming(client);
  const agenticLoop = useAgenticLoop();
  const delegationDepth = useRef(0);
  const scratchpad = useRef<Scratchpad | null>(null);

  // System notice — rendered through Ink, never stdout.write (which breaks the input)
  const notice = useCallback((msg: string) => {
    addMessage({ role: 'system', content: msg });
  }, [addMessage]);

  // Ensure scratchpad is initialized
  const getScratchpad = useCallback(() => {
    const sid = useChatStore.getState().sessionId;
    if (sid && (!scratchpad.current || (scratchpad.current as any)._sessionId !== sid)) {
      scratchpad.current = new Scratchpad(sid);
    }
    return scratchpad.current;
  }, []);

  // ── Core stream + process ──────────────────────────────────────────

  const streamAgent = useCallback(async (
    targetAgent: string,
    msgs: ChatMessage[],
  ): Promise<string> => {
    const doneEvent = await streaming.start(targetAgent, msgs, {
      sessionId: sessionId ?? undefined,
      cwd: repoPath,
    });

    if (doneEvent?.type === 'done') {
      if (doneEvent.sessionId) setSessionId(doneEvent.sessionId);
      if (doneEvent.usage) {
        updateTokens({
          input: doneEvent.usage.prompt_tokens,
          output: doneEvent.usage.completion_tokens,
          cached: doneEvent.usage.cached_tokens,
        });
      }
      return doneEvent.fullContent || '';
    }
    return '';
  }, [sessionId, repoPath, streaming, setSessionId, updateTokens]);

  // ── Post-response processing (delegation, skills, remember) ────────

  const processResponse = useCallback(async (
    fullContent: string,
    currentAgent: string,
    allMessages: ChatMessage[],
  ): Promise<string> => {
    let result = fullContent;

    // Extract [REMEMBER:key=value] → write to scratchpad
    const remembers = extractRememberTags(result);
    if (remembers.length > 0) {
      const sp = getScratchpad();
      if (sp) {
        for (const { key, value } of remembers) {
          sp.set(key, value);
        }
      }
    }

    // Round-trip delegation: delegate executes as tool, result returns to source
    if (delegationDepth.current < MAX_DELEGATION_DEPTH) {
      const delegations = extractDelegations(result);
      for (const { agent: delegateAgent, prompt } of delegations) {
        notice(`> Agent(${delegateAgent})  ${prompt.slice(0, 60)}`);

        delegationDepth.current++;

        // Execute delegate
        const delegateMsgs: ChatMessage[] = [
          ...allMessages,
          { role: 'user', content: prompt },
        ];
        const delegateResult = await streamAgent(delegateAgent, delegateMsgs);

        delegationDepth.current--;

        if (!delegateResult) {
          notice('(no result)');
          continue;
        }

        // Extract delegate's [REMEMBER:] tags
        const delRemembers = extractRememberTags(delegateResult);
        if (delRemembers.length > 0) {
          const sp = getScratchpad();
          if (sp) {
            for (const { key, value } of delRemembers) sp.set(key, value);
          }
        }

        // Show result preview
        const preview = stripTags(delegateResult).split('\n')[0].slice(0, 80);
        notice(`  Result: ${preview}`);

        // Feed result back to source agent for synthesis
        const roundtripMsg: ChatMessage = {
          role: 'user',
          content: `[Agent Result from ${delegateAgent}]\n${stripTags(delegateResult)}\n[End Agent Result]\n\nContinue with the above result. Synthesize and respond to the user.`,
        };

        notice(`Returning to ${currentAgent}...`);

        const continuation = await streamAgent(currentAgent, [
          ...allMessages,
          { role: 'assistant', content: result },
          roundtripMsg,
        ]);

        if (continuation) {
          result = continuation;
          addMessage({ role: 'assistant', content: stripTags(continuation) });
        }
      }
    }

    // Skill loading: [SKILL:name] → fetch body → feed back
    const skills = extractSkills(result);
    for (const skillRef of skills) {
      const skill = await loadSkill(client, skillRef, currentAgent);
      if (skill) {
        notice(`Loading skill: ${skill.name}`);
        const skillMsg = buildSkillMessage(skill);
        const skillResult = await streamAgent(currentAgent, [
          ...allMessages,
          { role: 'assistant', content: result },
          { role: 'user', content: skillMsg },
        ]);
        if (skillResult) {
          result = skillResult;
          addMessage({ role: 'assistant', content: stripTags(skillResult) });
        }
      }
    }

    return result;
  }, [client, addMessage, streamAgent, getScratchpad]);

  // ── Main send + stream + process cycle ─────────────────────────────

  const streamAndProcess = useCallback(async (allMessages: ChatMessage[], currentAgent: string) => {
    setBusy(true);
    agenticLoop.setLoopState('STREAMING');

    // Context trimming: keep conversation within window
    const { messages: trimmedMessages, trimmedCount } = trimContext(allMessages);
    if (trimmedCount > 0) {
      notice(`(trimmed ${trimmedCount} older messages to fit context window)`);
    }

    const fullContent = await streamAgent(currentAgent, trimmedMessages);

    if (fullContent) {
      addMessage({ role: 'assistant', content: stripTags(fullContent) });

      // Post-response: delegation, skills, scratchpad
      await processResponse(fullContent, currentAgent, trimmedMessages);

      // Confidence scoring
      const lastUser = trimmedMessages.filter(m => m.role === 'user').pop();
      if (lastUser) {
        const confidence = scoreResponse(currentAgent, lastUser.content, fullContent);
        if (confidence.shouldDelegate && confidence.suggestedAgent) {
          notice(`Low confidence (${confidence.score}/5). Try: /agent ${confidence.suggestedAgent}`);
        }
      }

      // Check for bash commands in response
      const commands = agenticLoop.extractCommands(fullContent);
      if (commands.length > 0) {
        agenticLoop.setLoopState('AWAITING_APPROVAL');
        return; // Stay busy, wait for approval
      }
    }

    agenticLoop.setLoopState('IDLE');
    setBusy(false);
  }, [streamAgent, agenticLoop, addMessage, setBusy, processResponse]);

  // ── Public sendMessage ─────────────────────────────────────────────

  const sendMessage = useCallback(async (text: string) => {
    const userMsg: ChatMessage = { role: 'user', content: text };
    addMessage(userMsg);
    agenticLoop.resetLoop();

    let currentAgent = useChatStore.getState().agent;

    // Smart orchestrator: auto-switch to specialist
    const analysis = analyzeRequest(text, currentAgent);
    const isRouting = currentAgent === 'auto-pilot' || currentAgent === '';
    if (analysis.shouldDelegate && analysis.bestAgent !== currentAgent) {
      if (isRouting || (analysis.score >= 2)) {
        notice(`→ ${analysis.bestAgent} specializes in this — auto-switching.`);
        setAgent(analysis.bestAgent);
        currentAgent = analysis.bestAgent;
      }
    }

    // Complexity detection: suggest plan mode for complex tasks
    const mode = useChatStore.getState().mode;
    if (mode === 'chat') {
      const complexity = estimateComplexity(text);
      if (complexity.shouldSuggestPlan) {
        const reasons = complexity.reasons.slice(0, 3).join(', ');
        notice(`This looks complex (score ${complexity.score}: ${reasons}). Consider /plan or Shift+Tab for a structured approach.`);
      }
    }

    // Skill suggestions: proactive hints based on keywords
    const suggestions = suggestSkills(text, currentAgent);
    if (suggestions.length > 0) {
      const cmds = suggestions.map(s => s.command).join(', ');
      notice(`Skills: ${cmds}`);
    }

    const allMessages = [...messages, userMsg];
    await streamAndProcess(allMessages, currentAgent);
  }, [messages, addMessage, streamAndProcess, agenticLoop, setAgent]);

  // ── Background task foreground ─────────────────────────────────────

  const backgroundToForeground = useCallback(async (taskId: number) => {
    const bgManager = getBackgroundManager();
    const task = bgManager.getTask(taskId);
    if (!task) {
      notice(`Task #${taskId} not found.`);
      return;
    }

    if (task.status === 'done' && task.fullResponse) {
      notice(`── Replaying ${task.displayName} ──`);
      addMessage({ role: 'user', content: task.userInput });
      addMessage({ role: 'assistant', content: stripTags(task.fullResponse) });
      bgManager.removeTask(taskId);
      notice(`✓ Task #${taskId} ${task.displayName} completed and merged.`);
    } else if (task.status === 'error') {
      notice(`✗ Task #${taskId} error: ${task.error}`);
      bgManager.removeTask(taskId);
    } else {
      notice(`Task #${taskId} is still running...`);
    }
  }, [addMessage, notice]);

  // ── Command approval (agentic loop) ────────────────────────────────

  const approveCommands = useCallback((cmds: string[]) => {
    if (!agenticLoop.canLoop()) {
      agenticLoop.setLoopState('IDLE');
      setBusy(false);
      return;
    }

    const output = agenticLoop.approveCommands(cmds);
    const feedbackMsg: ChatMessage = {
      role: 'user',
      content: `Command output:\n\`\`\`\n${output}\n\`\`\``,
    };
    addMessage(feedbackMsg);

    const currentAgent = useChatStore.getState().agent;
    const allMessages = [...useChatStore.getState().messages];
    streamAndProcess(allMessages, currentAgent);
  }, [agenticLoop, addMessage, streamAndProcess, setBusy]);

  const rejectCommands = useCallback(() => {
    agenticLoop.rejectCommands();
    setBusy(false);
  }, [agenticLoop, setBusy]);

  return {
    sendMessage,
    isStreaming: streaming.isStreaming,
    streamingContent: streaming.content,
    cancelStream: streaming.cancel,
    loopState: agenticLoop.loopState,
    pendingCommands: agenticLoop.pendingCommands,
    approveCommands,
    rejectCommands,
    backgroundToForeground,
  };
}
