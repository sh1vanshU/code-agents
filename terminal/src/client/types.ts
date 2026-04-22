import { z } from 'zod';

// --- Agent ---
export const AgentSchema = z.object({
  name: z.string(),
  description: z.string().optional(),
  model: z.string().optional(),
  backend: z.string().optional(),
});
export type Agent = z.infer<typeof AgentSchema>;

// --- Chat Messages ---
export const ChatMessageSchema = z.object({
  role: z.enum(['system', 'user', 'assistant']),
  content: z.string(),
  timestamp: z.string().optional(),
});
export type ChatMessage = z.infer<typeof ChatMessageSchema>;

// --- Completion Request ---
export const CompletionRequestSchema = z.object({
  model: z.string(),
  messages: z.array(ChatMessageSchema),
  stream: z.boolean().default(true),
  session_id: z.string().optional(),
  cwd: z.string().optional(),
  include_session: z.boolean().optional(),
  stream_tool_activity: z.boolean().optional(),
});
export type CompletionRequest = z.infer<typeof CompletionRequestSchema>;

// --- SSE Events ---
export const SSEDeltaSchema = z.object({
  content: z.string().optional(),
  reasoning: z.string().optional(),
});

export const SSEChoiceSchema = z.object({
  delta: SSEDeltaSchema.optional(),
  message: z.object({ role: z.string(), content: z.string() }).optional(),
  finish_reason: z.string().nullable().optional(),
});

export const SSEChunkSchema = z.object({
  choices: z.array(SSEChoiceSchema),
  usage: z.object({
    prompt_tokens: z.number(),
    completion_tokens: z.number(),
    cached_tokens: z.number().optional(),
  }).optional(),
  duration_ms: z.number().optional(),
  session_id: z.string().optional(),
});
export type SSEChunk = z.infer<typeof SSEChunkSchema>;

// --- Typed SSE stream events ---
export type StreamEvent =
  | { type: 'token'; content: string }
  | { type: 'reasoning'; content: string }
  | { type: 'done'; fullContent: string; usage?: SSEChunk['usage']; durationMs?: number; sessionId?: string }
  | { type: 'error'; message: string };

// --- Session ---
export const SessionSchema = z.object({
  id: z.string(),
  agent: z.string(),
  repo_path: z.string(),
  title: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  messages: z.array(ChatMessageSchema),
});
export type Session = z.infer<typeof SessionSchema>;

// --- Health ---
export const HealthSchema = z.object({
  status: z.string(),
});
