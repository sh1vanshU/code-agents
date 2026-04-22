// Code Agents — Side Panel Chat Logic

(() => {
  // ---- State ----
  let serverUrl = 'http://localhost:8000';
  let currentAgent = DEFAULT_AGENT;
  let conversationHistory = []; // [{role, content}]
  let isStreaming = false;
  let statusInterval = null;

  // ---- DOM refs ----
  const agentSelector = document.getElementById('agent-selector');
  const statusDot = document.getElementById('status-dot');
  const messagesEl = document.getElementById('messages');
  const welcomeEl = document.getElementById('welcome');
  const streamingIndicator = document.getElementById('streaming-indicator');
  const chatInput = document.getElementById('chat-input');
  const btnSend = document.getElementById('btn-send');
  const btnClear = document.getElementById('btn-clear');

  // ---- Init ----
  async function init() {
    await loadSettings();
    populateAgentSelector();
    await updateServerStatus();

    // Poll server status every 15 seconds
    statusInterval = setInterval(updateServerStatus, 15000);

    // Check for pending context (from context menu or content scripts)
    await consumePendingContext();

    // Listen for new context arriving while panel is open
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area === 'session' && changes.pendingContext) {
        consumePendingContext();
      }
    });
  }

  async function loadSettings() {
    try {
      const data = await chrome.storage.sync.get(['serverUrl', 'defaultAgent']);
      if (data.serverUrl) serverUrl = data.serverUrl;
      if (data.defaultAgent) currentAgent = data.defaultAgent;
    } catch { /* use defaults */ }
  }

  function populateAgentSelector() {
    agentSelector.innerHTML = '';
    for (const agent of AGENTS) {
      const opt = document.createElement('option');
      opt.value = agent.name;
      opt.textContent = agentLabel(agent);
      if (agent.name === currentAgent) opt.selected = true;
      agentSelector.appendChild(opt);
    }
  }

  async function updateServerStatus() {
    const ok = await checkServer(serverUrl);
    statusDot.classList.toggle('connected', ok);
    statusDot.classList.toggle('disconnected', !ok);
    statusDot.title = ok ? 'Server connected' : 'Server disconnected';
  }

  async function consumePendingContext() {
    try {
      const data = await chrome.storage.session.get('pendingContext');
      if (!data.pendingContext) return;

      const ctx = data.pendingContext;
      // Clear it so we don't re-consume
      await chrome.storage.session.remove('pendingContext');

      let text = '';
      if (ctx.type === 'selected-text') {
        text = ctx.text;
      } else if (ctx.type === 'page-context' && ctx.data) {
        const d = ctx.data;
        const parts = [];
        if (d.type) parts.push(`[${ctx.source}/${d.type}]`);
        if (d.title) parts.push(d.title);
        if (d.description) parts.push(d.description);
        if (d.labels) parts.push(`Labels: ${d.labels}`);
        if (d.files) parts.push(`Files: ${d.files}`);
        text = parts.join('\n');
      }

      if (text) {
        chatInput.value = text;
        chatInput.focus();
        autoResizeInput();
      }
    } catch { /* ignore */ }
  }

  // ---- Send message ----
  async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text || isStreaming) return;

    // Hide welcome
    if (welcomeEl) welcomeEl.style.display = 'none';

    // Add user message
    appendMessage('user', text);
    conversationHistory.push({ role: 'user', content: text });

    chatInput.value = '';
    autoResizeInput();
    setStreaming(true);

    // Create assistant message element for streaming
    const assistantEl = appendMessage('assistant', '');
    let fullContent = '';

    try {
      const agentName = agentSelector.value || currentAgent;
      const gen = streamChat(serverUrl, agentName, conversationHistory);

      for await (const token of gen) {
        fullContent += token;
        assistantEl.innerHTML = renderMarkdown(fullContent);
        scrollToBottom();
      }

      if (!fullContent) {
        assistantEl.innerHTML = '<em>No response received.</em>';
      }

      conversationHistory.push({ role: 'assistant', content: fullContent });
    } catch (err) {
      console.error('Chat error:', err);
      if (!fullContent) {
        assistantEl.remove();
      }
      appendMessage('error', `Error: ${err.message}`);
    } finally {
      setStreaming(false);
      scrollToBottom();
    }
  }

  // ---- UI helpers ----
  function appendMessage(role, content) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    if (content) {
      div.innerHTML = role === 'user' ? escapeHtml(content) : renderMarkdown(content);
    }
    messagesEl.appendChild(div);
    scrollToBottom();
    return div;
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    });
  }

  function setStreaming(active) {
    isStreaming = active;
    streamingIndicator.classList.toggle('hidden', !active);
    btnSend.disabled = active;
    chatInput.disabled = active;
    if (!active) chatInput.focus();
  }

  function clearChat() {
    conversationHistory = [];
    messagesEl.innerHTML = '';
    if (welcomeEl) {
      messagesEl.appendChild(welcomeEl);
      welcomeEl.style.display = '';
    }
    chatInput.value = '';
    autoResizeInput();
    chatInput.focus();
  }

  function autoResizeInput() {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
  }

  // ---- Markdown rendering ----
  function renderMarkdown(text) {
    if (!text) return '';

    let html = escapeHtml(text);

    // Fenced code blocks: ```lang\n...\n```
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
      const cls = lang ? ` class="language-${lang}"` : '';
      return `<pre><code${cls}>${code}</code></pre>`;
    });

    // Inline code
    html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');

    // Bold
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // Italic
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

    // Headings (## before #)
    html = html.replace(/^## (.+)$/gm, '<h4>$1</h4>');
    html = html.replace(/^# (.+)$/gm, '<h3>$1</h3>');

    // Blockquotes
    html = html.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');

    // Unordered list items — group consecutive lines
    html = html.replace(/(?:^- (.+)$\n?)+/gm, (match) => {
      const items = match.trim().split('\n')
        .map((line) => `<li>${line.replace(/^- /, '')}</li>`)
        .join('');
      return `<ul>${items}</ul>`;
    });

    // Links: [text](url)
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

    // Line breaks (preserve newlines outside of pre blocks)
    html = html.replace(/\n/g, '<br>');

    // Clean up double <br> around block elements
    html = html.replace(/<br>\s*(<(?:pre|ul|ol|h[34]|blockquote))/g, '$1');
    html = html.replace(/(<\/(?:pre|ul|ol|h[34]|blockquote)>)\s*<br>/g, '$1');

    return html;
  }

  function escapeHtml(text) {
    const el = document.createElement('span');
    el.textContent = text;
    return el.innerHTML;
  }

  // ---- Event listeners ----
  agentSelector.addEventListener('change', () => {
    currentAgent = agentSelector.value;
    chrome.storage.sync.set({ defaultAgent: currentAgent });
  });

  btnSend.addEventListener('click', sendMessage);
  btnClear.addEventListener('click', clearChat);

  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  chatInput.addEventListener('input', autoResizeInput);

  // ---- Boot ----
  init();
})();
