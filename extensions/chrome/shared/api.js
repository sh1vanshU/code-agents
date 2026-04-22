// Code Agents — API client with SSE streaming

/**
 * Check if the Code Agents server is reachable.
 * @param {string} serverUrl - Base server URL (e.g. http://localhost:8000)
 * @returns {Promise<boolean>}
 */
async function checkServer(serverUrl) {
  try {
    const res = await fetch(`${serverUrl}/health`, {
      method: 'GET',
      signal: AbortSignal.timeout(3000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Fetch the list of available agents from the server.
 * Falls back to the local AGENTS list on failure.
 * @param {string} serverUrl
 * @returns {Promise<Array>}
 */
async function getAgents(serverUrl) {
  try {
    const res = await fetch(`${serverUrl}/v1/agents`, {
      method: 'GET',
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return AGENTS;
    const data = await res.json();
    return Array.isArray(data) ? data : (data.agents || AGENTS);
  } catch {
    return AGENTS;
  }
}

/**
 * Stream a chat completion via SSE. Yields individual content tokens.
 * @param {string} serverUrl
 * @param {string} agent - Agent name (used as model)
 * @param {Array} messages - OpenAI-format messages [{role, content}]
 * @yields {string} content tokens
 */
async function* streamChat(serverUrl, agent, messages) {
  const res = await fetch(`${serverUrl}/v1/chat/completions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: agent,
      messages,
      stream: true,
    }),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`Server error ${res.status}: ${text}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop(); // keep incomplete last line in buffer

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || !trimmed.startsWith('data: ')) continue;

      const payload = trimmed.slice(6); // strip "data: "
      if (payload === '[DONE]') return;

      try {
        const json = JSON.parse(payload);
        const content = json?.choices?.[0]?.delta?.content;
        if (content) yield content;
      } catch {
        // skip malformed JSON lines
      }
    }
  }
}

/**
 * Non-streaming chat completion. Returns the full assistant message.
 * @param {string} serverUrl
 * @param {string} agent
 * @param {Array} messages
 * @returns {Promise<string>}
 */
async function sendChat(serverUrl, agent, messages) {
  const res = await fetch(`${serverUrl}/v1/chat/completions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: agent,
      messages,
      stream: false,
    }),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`Server error ${res.status}: ${text}`);
  }

  const data = await res.json();
  return data?.choices?.[0]?.message?.content || '';
}
