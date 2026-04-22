/* ═══════════════════════════════════════════════════════════
   Code Agents — Frontend Application
   SPA with Chat, Agents, Pipeline, Dashboard views
   ═══════════════════════════════════════════════════════════ */

// ── Agent Color Map ────────────────────────────────────────
const AGENT_COLORS = {
    "code-reasoning":   "#06b6d4",
    "code-writer":      "#22c55e",
    "code-reviewer":    "#eab308",
    "code-tester":      "#06b6d4",
    "redash-query":     "#3b82f6",
    "git-ops":          "#d946ef",
    "test-coverage":    "#34d399",
    "jenkins-cicd":     "#ef4444",
    "argocd-verify":    "#c084fc",
    "qa-regression":    "#f87171",
    "auto-pilot":       "#e8eaf0",
    "jira-ops":         "#3b82f6",
    "security":         "#f59e0b",
};

// ── Pipeline Steps ─────────────────────────────────────────
const PIPELINE_STEPS = [
    { id: "connect",  label: "Connect",  icon: "⚡" },
    { id: "review",   label: "Review",   icon: "🔍" },
    { id: "build",    label: "Build",    icon: "🔨" },
    { id: "deploy",   label: "Deploy",   icon: "🚀" },
    { id: "verify",   label: "Verify",   icon: "✓" },
    { id: "rollback", label: "Rollback", icon: "↩" },
];

// ── State ──────────────────────────────────────────────────
let agents = [];
let currentAgent = "";
let conversationHistory = [];
let sessionId = crypto.randomUUID();
let isStreaming = false;
let currentView = "chat";
let dashboardDays = 1;
let cmdPaletteIndex = 0;

// ── DOM Refs ───────────────────────────────────────────────
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const dom = {
    agentSelect:    $("#agent-select"),
    agentList:      $("#agent-list"),
    messages:       $("#messages"),
    chatArea:       $("#chat-area"),
    userInput:      $("#user-input"),
    sendBtn:        $("#send-btn"),
    newChatBtn:     $("#new-chat-btn"),
    sidebarToggle:  $("#sidebar-toggle"),
    sidebar:        $("#sidebar"),
    scrollBtn:      $("#scroll-bottom"),
    charCount:      $("#char-count"),
    inputAgentPill: $("#input-agent-pill"),
    topbarTitle:    $("#topbar-title"),
    cmdPalette:     $("#cmd-palette"),
    cmdInput:       $("#cmd-input"),
    cmdResults:     $("#cmd-results"),
    cmdPaletteBtn:  $("#cmd-palette-btn"),
    serverStatus:   $("#server-status"),
    toastContainer: $("#toast-container"),
};

// ── Init ───────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", init);

async function init() {
    setupEventListeners();
    setupKeyboardShortcuts();
    buildPipelineVisual();
    await fetchAgents();
}

// ── Fetch Agents ───────────────────────────────────────────
async function fetchAgents(retries = 3) {
    setServerStatus("connecting", "Connecting...");

    for (let attempt = 1; attempt <= retries; attempt++) {
        try {
            const resp = await fetch("/v1/agents");
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            agents = data.data || data.agents || data || [];
            if (agents.length === 0) throw new Error("No agents returned");
            populateAgentUI();
            selectAgent(agents[0].name || agents[0]);
            setServerStatus("connected", `${agents.length} agents online`);
            return;
        } catch (err) {
            console.error(`Attempt ${attempt}/${retries}:`, err);
            if (attempt < retries) {
                setServerStatus("connecting", `Retry ${attempt}/${retries}...`);
                await new Promise(r => setTimeout(r, 2000));
            }
        }
    }

    setServerStatus("error", "Server offline");
    dom.messages.innerHTML = `
        <div class="welcome-screen">
            <div class="welcome-glow"></div>
            <h1 class="welcome-title" style="-webkit-text-fill-color: #ef4444; background: none;">Offline</h1>
            <p class="welcome-subtitle">Cannot reach the server at <code style="background:var(--bg-code);padding:2px 8px;border-radius:4px;font-family:var(--font-mono);font-size:13px">${window.location.origin}</code></p>
            <p class="welcome-subtitle" style="margin-top:12px">
                <button class="btn-primary" onclick="fetchAgents(3)">Retry Connection</button>
            </p>
            <p class="welcome-subtitle" style="margin-top:20px;font-size:13px;color:var(--text-ghost)">
                Run <code style="background:var(--bg-code);padding:2px 8px;border-radius:4px;font-family:var(--font-mono);font-size:12px">code-agents start</code> to start the server
            </p>
        </div>`;
}

function setServerStatus(state, msg) {
    const dot = dom.serverStatus.querySelector(".status-dot");
    const text = dom.serverStatus.querySelector(".status-text");
    dot.className = `status-dot ${state}`;
    text.textContent = msg;
}

// ── Populate Agent UI ──────────────────────────────────────
function populateAgentUI() {
    dom.agentSelect.innerHTML = "";
    dom.agentList.innerHTML = "";

    agents.forEach(a => {
        const name = a.name || a;
        const display = a.display_name || name;
        const color = AGENT_COLORS[name] || "#8b8fa4";

        // Dropdown
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        dom.agentSelect.appendChild(opt);

        // Sidebar
        const li = document.createElement("li");
        li.dataset.agent = name;
        li.innerHTML = `<span class="agent-dot" style="background:${color};color:${color}"></span><span class="agent-name">${name}</span>`;
        li.addEventListener("click", () => {
            selectAgent(name);
            switchView("chat");
        });
        dom.agentList.appendChild(li);
    });

    // Build agents grid
    buildAgentsGrid();
}

function selectAgent(name) {
    currentAgent = name;
    dom.agentSelect.value = name;
    const color = AGENT_COLORS[name] || "#8b8fa4";

    // Sidebar active
    $$('#agent-list li').forEach(li => {
        li.classList.toggle("active", li.dataset.agent === name);
    });

    // Agent pill
    dom.inputAgentPill.textContent = name;
    dom.inputAgentPill.style.borderColor = color;
    dom.inputAgentPill.style.color = color;

    // Select border
    dom.agentSelect.style.borderColor = color;
}

// ── View Switching ─────────────────────────────────────────
function switchView(viewId) {
    currentView = viewId;

    // Views
    $$(".view").forEach(v => v.classList.remove("active"));
    $(`#view-${viewId}`)?.classList.add("active");

    // Nav
    $$(".nav-item").forEach(n => n.classList.remove("active"));
    $(`.nav-item[data-view="${viewId}"]`)?.classList.add("active");

    // Title
    const titles = { chat: "Chat", agents: "Agents", pipeline: "Pipeline", dashboard: "Dashboard" };
    dom.topbarTitle.textContent = titles[viewId] || viewId;

    // Load data for view
    if (viewId === "dashboard") loadDashboard();
    if (viewId === "pipeline") loadPipeline();

    // Close sidebar on mobile
    if (window.innerWidth <= 768) dom.sidebar.classList.remove("open");
}

// ── Event Listeners ────────────────────────────────────────
function setupEventListeners() {
    // Send
    dom.sendBtn.addEventListener("click", sendMessage);
    dom.userInput.addEventListener("keydown", e => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-resize
    dom.userInput.addEventListener("input", () => {
        dom.userInput.style.height = "auto";
        dom.userInput.style.height = Math.min(dom.userInput.scrollHeight, 160) + "px";
        const len = dom.userInput.value.length;
        dom.charCount.textContent = len > 0 ? len : "";
    });

    // Agent select
    dom.agentSelect.addEventListener("change", () => selectAgent(dom.agentSelect.value));

    // New chat
    dom.newChatBtn.addEventListener("click", startNewChat);

    // Sidebar toggle
    dom.sidebarToggle.addEventListener("click", () => {
        if (window.innerWidth <= 768) {
            dom.sidebar.classList.toggle("open");
        } else {
            dom.sidebar.classList.toggle("collapsed");
        }
    });

    // Nav items
    $$(".nav-item").forEach(btn => {
        btn.addEventListener("click", () => switchView(btn.dataset.view));
    });

    // Welcome cards
    document.addEventListener("click", e => {
        const card = e.target.closest(".welcome-card");
        if (card) {
            dom.userInput.value = card.dataset.action;
            sendMessage();
        }
    });

    // Scroll-to-bottom
    dom.chatArea?.addEventListener("scroll", () => {
        const gap = dom.chatArea.scrollHeight - dom.chatArea.scrollTop - dom.chatArea.clientHeight;
        dom.scrollBtn.classList.toggle("visible", gap > 100);
    });
    dom.scrollBtn.addEventListener("click", () => { dom.chatArea.scrollTop = dom.chatArea.scrollHeight; });

    // Command palette
    dom.cmdPaletteBtn.addEventListener("click", openCmdPalette);
    dom.cmdPalette.querySelector(".cmd-overlay").addEventListener("click", closeCmdPalette);
    dom.cmdInput.addEventListener("input", filterCmdPalette);
    dom.cmdInput.addEventListener("keydown", handleCmdNav);

    // Time filters
    $$(".tf-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            $$(".tf-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            dashboardDays = parseInt(btn.dataset.days);
            loadDashboard();
        });
    });

    // Start pipeline button
    $("#start-pipeline-btn")?.addEventListener("click", startPipeline);
}

// ── Keyboard Shortcuts ─────────────────────────────────────
function setupKeyboardShortcuts() {
    document.addEventListener("keydown", e => {
        // Ctrl+K — Command Palette
        if ((e.metaKey || e.ctrlKey) && e.key === "k") {
            e.preventDefault();
            toggleCmdPalette();
            return;
        }

        // Ctrl+B — Toggle sidebar
        if ((e.metaKey || e.ctrlKey) && e.key === "b") {
            e.preventDefault();
            dom.sidebar.classList.toggle("collapsed");
            return;
        }

        // Ctrl+N — New chat
        if ((e.metaKey || e.ctrlKey) && e.key === "n") {
            e.preventDefault();
            startNewChat();
            return;
        }

        // Ctrl+1-4 — Switch views
        if ((e.metaKey || e.ctrlKey) && e.key >= "1" && e.key <= "4") {
            e.preventDefault();
            const views = ["chat", "agents", "pipeline", "dashboard"];
            switchView(views[parseInt(e.key) - 1]);
            return;
        }

        // Escape — Close palette, focus input
        if (e.key === "Escape") {
            if (!dom.cmdPalette.classList.contains("hidden")) {
                closeCmdPalette();
            }
        }
    });
}

// ── Command Palette ────────────────────────────────────────
const CMD_ACTIONS = [
    { title: "New Chat",           desc: "Start a new conversation",    kbd: "Ctrl+N", action: () => { startNewChat(); switchView("chat"); } },
    { title: "Switch to Chat",     desc: "Open the chat view",          kbd: "Ctrl+1", action: () => switchView("chat") },
    { title: "Switch to Agents",   desc: "View all agents",             kbd: "Ctrl+2", action: () => switchView("agents") },
    { title: "Switch to Pipeline", desc: "CI/CD pipeline view",         kbd: "Ctrl+3", action: () => switchView("pipeline") },
    { title: "Switch to Dashboard",desc: "Analytics & telemetry",       kbd: "Ctrl+4", action: () => switchView("dashboard") },
    { title: "Toggle Sidebar",     desc: "Show/hide the sidebar",       kbd: "Ctrl+B", action: () => dom.sidebar.classList.toggle("collapsed") },
];

function buildCmdItems(filter = "") {
    const lower = filter.toLowerCase();

    // Static actions + dynamic agent switching
    let items = [...CMD_ACTIONS];
    agents.forEach(a => {
        const name = a.name || a;
        items.push({
            title: `Switch to ${name}`,
            desc: `Select the ${name} agent`,
            kbd: "",
            action: () => { selectAgent(name); switchView("chat"); },
        });
    });

    if (filter) {
        items = items.filter(i =>
            i.title.toLowerCase().includes(lower) || i.desc.toLowerCase().includes(lower)
        );
    }

    return items;
}

function renderCmdItems(items) {
    dom.cmdResults.innerHTML = "";
    cmdPaletteIndex = 0;

    items.forEach((item, i) => {
        const div = document.createElement("div");
        div.className = `cmd-item${i === 0 ? " active" : ""}`;
        div.innerHTML = `
            <div class="cmd-item-icon">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
            </div>
            <div class="cmd-item-text">
                <div class="cmd-item-title">${item.title}</div>
                <div class="cmd-item-desc">${item.desc}</div>
            </div>
            ${item.kbd ? `<span class="cmd-item-kbd">${item.kbd}</span>` : ""}
        `;
        div.addEventListener("click", () => { item.action(); closeCmdPalette(); });
        div.addEventListener("mouseenter", () => {
            $$(".cmd-item").forEach(c => c.classList.remove("active"));
            div.classList.add("active");
            cmdPaletteIndex = i;
        });
        dom.cmdResults.appendChild(div);
    });
}

function openCmdPalette() {
    dom.cmdPalette.classList.remove("hidden");
    dom.cmdInput.value = "";
    renderCmdItems(buildCmdItems());
    requestAnimationFrame(() => dom.cmdInput.focus());
}

function closeCmdPalette() {
    dom.cmdPalette.classList.add("hidden");
    dom.cmdInput.value = "";
}

function toggleCmdPalette() {
    dom.cmdPalette.classList.contains("hidden") ? openCmdPalette() : closeCmdPalette();
}

function filterCmdPalette() {
    renderCmdItems(buildCmdItems(dom.cmdInput.value));
}

function handleCmdNav(e) {
    const items = $$(".cmd-item");
    if (!items.length) return;

    if (e.key === "ArrowDown") {
        e.preventDefault();
        items[cmdPaletteIndex]?.classList.remove("active");
        cmdPaletteIndex = (cmdPaletteIndex + 1) % items.length;
        items[cmdPaletteIndex]?.classList.add("active");
        items[cmdPaletteIndex]?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "ArrowUp") {
        e.preventDefault();
        items[cmdPaletteIndex]?.classList.remove("active");
        cmdPaletteIndex = (cmdPaletteIndex - 1 + items.length) % items.length;
        items[cmdPaletteIndex]?.classList.add("active");
        items[cmdPaletteIndex]?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
        e.preventDefault();
        items[cmdPaletteIndex]?.click();
    } else if (e.key === "Escape") {
        closeCmdPalette();
    }
}

// ── Chat ───────────────────────────────────────────────────
function startNewChat() {
    conversationHistory = [];
    sessionId = crypto.randomUUID();
    dom.messages.innerHTML = `
        <div class="welcome-screen">
            <div class="welcome-glow"></div>
            <h1 class="welcome-title">Code Agents</h1>
            <p class="welcome-subtitle">AI-powered code intelligence. Select an agent and start building.</p>
            <div class="welcome-grid">
                <button class="welcome-card" data-action="Review the latest changes and provide feedback">
                    <div class="wc-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg></div>
                    <div class="wc-label">Review Code</div>
                    <div class="wc-desc">Analyze recent changes</div>
                </button>
                <button class="welcome-card" data-action="Run the test suite and report results">
                    <div class="wc-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg></div>
                    <div class="wc-label">Run Tests</div>
                    <div class="wc-desc">Execute test suite</div>
                </button>
                <button class="welcome-card" data-action="Show git status, recent commits, and branch info">
                    <div class="wc-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><line x1="1.05" y1="12" x2="7" y2="12"/><line x1="17.01" y1="12" x2="22.96" y2="12"/></svg></div>
                    <div class="wc-label">Git Status</div>
                    <div class="wc-desc">Branch & commit info</div>
                </button>
                <button class="welcome-card" data-action="Check deployment health and ArgoCD sync status">
                    <div class="wc-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg></div>
                    <div class="wc-label">Check Deploy</div>
                    <div class="wc-desc">Health & sync status</div>
                </button>
            </div>
            <div class="welcome-hint">
                <kbd>Ctrl</kbd><span>+</span><kbd>K</kbd> command palette
                <span class="hint-sep">|</span>
                <kbd>Enter</kbd> send message
                <span class="hint-sep">|</span>
                <kbd>Shift</kbd><span>+</span><kbd>Enter</kbd> new line
            </div>
        </div>`;
    showToast("New chat started", "info");
}

async function sendMessage() {
    const text = dom.userInput.value.trim();
    if (!text || isStreaming || !currentAgent) return;

    // Clear welcome
    const welcome = dom.messages.querySelector(".welcome-screen");
    if (welcome) welcome.remove();

    // Show user message
    appendMessage("user", text);
    conversationHistory.push({ role: "user", content: text });

    dom.userInput.value = "";
    dom.userInput.style.height = "auto";
    dom.charCount.textContent = "";
    dom.sendBtn.disabled = true;
    isStreaming = true;

    const spinnerId = showSpinner();

    try {
        await streamResponse(text, spinnerId);
    } catch (err) {
        removeSpinner(spinnerId);
        appendMessage("agent", `Error: ${err.message}`, { isError: true });
        showToast(`Error: ${err.message}`, "error");
    }

    isStreaming = false;
    dom.sendBtn.disabled = false;
    dom.userInput.focus();
}

async function streamResponse(text, spinnerId) {
    const body = {
        model: currentAgent,
        messages: conversationHistory,
        stream: true,
    };

    const resp = await fetch(`/v1/agents/${currentAgent}/chat/completions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });

    if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.error?.message || `HTTP ${resp.status}`);
    }

    removeSpinner(spinnerId);

    const msgEl = appendMessage("agent", "", { streaming: true });
    const bubbleEl = msgEl.querySelector(".message-bubble");
    const metaEl = msgEl.querySelector(".message-meta");

    bubbleEl.classList.add("streaming-cursor");

    let fullText = "";
    let usage = null;
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();

        for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const payload = line.slice(6).trim();
            if (payload === "[DONE]") continue;

            try {
                const chunk = JSON.parse(payload);
                const delta = chunk.choices?.[0]?.delta;
                if (delta?.content) {
                    fullText += delta.content;
                    bubbleEl.innerHTML = renderMarkdown(fullText);
                    bubbleEl.classList.add("streaming-cursor");
                    scrollToBottom();
                }
                if (chunk.usage) usage = chunk.usage;
            } catch (e) { /* skip */ }
        }
    }

    bubbleEl.classList.remove("streaming-cursor");
    conversationHistory.push({ role: "assistant", content: fullText });

    if (usage) {
        const parts = [];
        if (usage.prompt_tokens) parts.push(`in: ${fmt(usage.prompt_tokens)}`);
        if (usage.completion_tokens) parts.push(`out: ${fmt(usage.completion_tokens)}`);
        if (usage.total_tokens) parts.push(`total: ${fmt(usage.total_tokens)}`);
        if (parts.length) metaEl.textContent = parts.join(" · ");
    }

    bubbleEl.innerHTML = renderMarkdown(fullText);
    addCopyButtons(bubbleEl);
    scrollToBottom();
}

// ── Chat UI Helpers ────────────────────────────────────────
function appendMessage(role, text, opts = {}) {
    const name = role === "agent" ? currentAgent : "You";
    const color = role === "agent" ? (AGENT_COLORS[currentAgent] || "#8b8fa4") : "";

    const div = document.createElement("div");
    div.className = `message ${role}`;

    const labelStyle = role === "agent" && color ? `style="color:${color}"` : "";

    div.innerHTML = `
        <div class="message-label" ${labelStyle}>${name}</div>
        <div class="message-bubble">${role === "user" ? escapeHtml(text) : renderMarkdown(text)}</div>
        <div class="message-meta"></div>
    `;

    if (opts.isError) {
        const bubble = div.querySelector(".message-bubble");
        bubble.style.borderColor = "var(--error)";
        bubble.style.color = "#f87171";
    }

    dom.messages.appendChild(div);
    scrollToBottom();
    return div;
}

function showSpinner() {
    const id = "spinner-" + Date.now();
    const div = document.createElement("div");
    div.id = id;
    div.className = "message agent";
    const color = AGENT_COLORS[currentAgent] || "#8b8fa4";
    div.innerHTML = `
        <div class="message-label" style="color:${color}">${currentAgent}</div>
        <div class="spinner-container">
            <div class="spinner" style="border-top-color:${color}"></div>
            <span class="spinner-text">Thinking...</span>
        </div>
    `;
    dom.messages.appendChild(div);
    scrollToBottom();
    return id;
}

function removeSpinner(id) {
    document.getElementById(id)?.remove();
}

function scrollToBottom() {
    if (!dom.chatArea) return;
    const gap = dom.chatArea.scrollHeight - dom.chatArea.scrollTop - dom.chatArea.clientHeight;
    if (gap < 200 || isStreaming) {
        dom.chatArea.scrollTop = dom.chatArea.scrollHeight;
    }
}

// ── Markdown Renderer ──────────────────────────────────────
function escapeHtml(str) {
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
}

function renderMarkdown(text) {
    if (!text) return "";
    let html = escapeHtml(text);

    // Code blocks
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
        const langLabel = lang ? `<span class="lang-label">${lang}</span>` : "";
        return `<div class="code-block-wrapper">${langLabel}<pre><code class="language-${lang || "text"}">${code.trim()}</code></pre></div>`;
    });

    // Inline code
    html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");

    // Headers
    html = html.replace(/^#### (.+)$/gm, "<h4>$1</h4>");
    html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
    html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
    html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");

    // Bold & italic
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");

    // Blockquotes
    html = html.replace(/^&gt; (.+)$/gm, "<blockquote>$1</blockquote>");

    // Lists
    html = html.replace(/^- (.+)$/gm, "<li>$1</li>");
    html = html.replace(/(<li>.*<\/li>\n?)+/g, "<ul>$&</ul>");

    // Paragraphs & breaks
    html = html.replace(/\n\n/g, "</p><p>");
    html = html.replace(/\n/g, "<br>");

    if (!html.startsWith("<")) html = "<p>" + html + "</p>";

    return html;
}

function addCopyButtons(container) {
    container.querySelectorAll(".code-block-wrapper").forEach(wrapper => {
        if (wrapper.querySelector(".copy-btn")) return;
        const btn = document.createElement("button");
        btn.className = "copy-btn";
        btn.textContent = "Copy";
        btn.addEventListener("click", () => {
            const code = wrapper.querySelector("code").textContent;
            navigator.clipboard.writeText(code).then(() => {
                btn.textContent = "Copied!";
                setTimeout(() => { btn.textContent = "Copy"; }, 1500);
            });
        });
        wrapper.appendChild(btn);
    });
}

// ── Agents Grid ────────────────────────────────────────────
function buildAgentsGrid() {
    const grid = $("#agents-grid");
    if (!grid) return;
    grid.innerHTML = "";

    agents.forEach(a => {
        const name = a.name || a;
        const display = a.display_name || name;
        const backend = a.backend || "cursor";
        const model = a.model || "default";
        const color = AGENT_COLORS[name] || "#8b8fa4";

        const card = document.createElement("div");
        card.className = "agent-card";
        card.style.setProperty("--agent-color", color);
        card.innerHTML = `
            <div class="agent-card-header">
                <div class="agent-card-dot"></div>
                <div class="agent-card-name">${name}</div>
            </div>
            <div class="agent-card-meta">
                <div class="agent-card-row">
                    <span class="agent-card-key">Backend</span>
                    <span class="agent-card-value">${truncate(backend, 20)}</span>
                </div>
                <div class="agent-card-row">
                    <span class="agent-card-key">Model</span>
                    <span class="agent-card-value">${truncate(model, 20)}</span>
                </div>
            </div>
            <div class="agent-card-actions">
                <button class="agent-card-btn primary" data-agent="${name}">Chat</button>
                <button class="agent-card-btn" data-agent="${name}" data-detail="true">Details</button>
            </div>
        `;

        card.querySelector(".agent-card-btn.primary").addEventListener("click", e => {
            e.stopPropagation();
            selectAgent(name);
            switchView("chat");
        });

        card.querySelector(".agent-card-btn:not(.primary)").addEventListener("click", e => {
            e.stopPropagation();
            showToast(`${display} — Backend: ${backend}, Model: ${model}`, "info");
        });

        grid.appendChild(card);
    });
}

// ── Pipeline ───────────────────────────────────────────────
function buildPipelineVisual() {
    const container = $("#pipeline-visual");
    if (!container) return;
    container.innerHTML = "";

    PIPELINE_STEPS.forEach((step, i) => {
        if (i > 0) {
            const conn = document.createElement("div");
            conn.className = "pipeline-connector";
            conn.dataset.step = i;
            container.appendChild(conn);
        }

        const el = document.createElement("div");
        el.className = "pipeline-step";
        el.dataset.step = step.id;
        el.innerHTML = `
            <div class="pipeline-step-icon">${step.icon}</div>
            <div class="pipeline-step-label">${step.label}</div>
        `;
        container.appendChild(el);
    });
}

async function loadPipeline() {
    // Load Jenkins status
    try {
        const resp = await fetch("/jenkins/jobs");
        if (resp.ok) {
            const data = await resp.json();
            const jobs = data.jobs || data || [];
            const list = $("#jenkins-list");
            const count = $("#jenkins-count");
            count.textContent = jobs.length;
            if (jobs.length === 0) {
                list.innerHTML = '<div class="panel-empty">No Jenkins jobs found</div>';
            } else {
                list.innerHTML = jobs.slice(0, 8).map(j => `
                    <div class="panel-row">
                        <span class="panel-row-name">${j.name || j}</span>
                        <span class="status-pill ${getStatusClass(j.color || j.status)}">${j.color || j.status || "unknown"}</span>
                    </div>
                `).join("");
            }
        }
    } catch (e) {
        $("#jenkins-list").innerHTML = '<div class="panel-empty">Jenkins not connected</div>';
    }

    // Load ArgoCD status
    try {
        const resp = await fetch("/argocd/apps");
        if (resp.ok) {
            const data = await resp.json();
            const apps = data.apps || data.items || data || [];
            const list = $("#argocd-list");
            const count = $("#argocd-count");
            count.textContent = apps.length;
            if (apps.length === 0) {
                list.innerHTML = '<div class="panel-empty">No ArgoCD apps found</div>';
            } else {
                list.innerHTML = apps.slice(0, 8).map(a => {
                    const name = a.metadata?.name || a.name || a;
                    const health = a.status?.health?.status || "Unknown";
                    return `
                        <div class="panel-row">
                            <span class="panel-row-name">${name}</span>
                            <span class="status-pill ${getHealthClass(health)}">${health}</span>
                        </div>
                    `;
                }).join("");
            }
        }
    } catch (e) {
        $("#argocd-list").innerHTML = '<div class="panel-empty">ArgoCD not connected</div>';
    }
}

async function startPipeline() {
    try {
        const resp = await fetch("/pipeline/start", { method: "POST", headers: { "Content-Type": "application/json" } });
        if (resp.ok) {
            showToast("Pipeline started!", "success");
            loadPipeline();
        } else {
            showToast("Failed to start pipeline", "error");
        }
    } catch (e) {
        showToast("Pipeline API unavailable", "warning");
    }
}

// ── Dashboard ──────────────────────────────────────────────
async function loadDashboard() {
    // Summary
    try {
        const resp = await fetch(`/telemetry/summary?days=${dashboardDays}`);
        if (resp.ok) {
            const d = await resp.json();
            $("#stat-sessions").textContent = fmt(d.sessions || 0);
            $("#stat-messages").textContent = fmt(d.messages || 0);
            $("#stat-tokens").textContent = fmtK(d.total_tokens || d.tokens_in + d.tokens_out || 0);
            $("#stat-cost").textContent = "$" + (d.estimated_cost || 0).toFixed(2);
            $("#stat-errors").textContent = fmt(d.errors || 0);
        }
    } catch (e) {
        console.warn("Telemetry unavailable:", e);
    }

    // Agent usage
    try {
        const resp = await fetch(`/telemetry/agents?days=${dashboardDays}`);
        if (resp.ok) {
            const data = await resp.json();
            const items = data.agents || data || [];
            const chart = $("#agent-usage-chart");
            const maxVal = Math.max(...items.map(i => i.messages || i.count || 0), 1);
            chart.innerHTML = items.length ? items.map(i => {
                const name = i.agent || i.name;
                const val = i.messages || i.count || 0;
                const color = AGENT_COLORS[name] || "#8b8fa4";
                const pct = (val / maxVal * 100).toFixed(1);
                return `<div class="bar-row">
                    <span class="bar-label">${name}</span>
                    <div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${color}"></div></div>
                    <span class="bar-value">${fmt(val)}</span>
                </div>`;
            }).join("") : '<div class="panel-empty">No usage data</div>';
        }
    } catch (e) { /* skip */ }

    // Top commands
    try {
        const resp = await fetch(`/telemetry/commands?days=${dashboardDays}`);
        if (resp.ok) {
            const data = await resp.json();
            const cmds = data.commands || data || [];
            const el = $("#top-commands");
            el.innerHTML = cmds.length ? cmds.slice(0, 8).map(c => `
                <div class="panel-row">
                    <span class="panel-row-name">${c.command || c.name}</span>
                    <span class="panel-row-value">${fmt(c.count || 0)}x</span>
                </div>
            `).join("") : '<div class="panel-empty">No commands recorded</div>';
        }
    } catch (e) { /* skip */ }

    // Errors
    try {
        const resp = await fetch(`/telemetry/errors?days=${dashboardDays}`);
        if (resp.ok) {
            const data = await resp.json();
            const errs = data.errors || data || [];
            const el = $("#recent-errors");
            el.innerHTML = errs.length ? errs.slice(0, 8).map(e => `
                <div class="panel-row">
                    <span class="panel-row-name" style="color:var(--error)">${e.agent || "system"}</span>
                    <span class="panel-row-value">${e.message || e.error || "Unknown"}</span>
                </div>
            `).join("") : '<div class="panel-empty" style="color:var(--success)">No errors</div>';
        }
    } catch (e) { /* skip */ }
}

// ── Toast ──────────────────────────────────────────────────
function showToast(msg, type = "info") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    dom.toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = "toastOut 0.3s ease forwards";
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ── Utilities ──────────────────────────────────────────────
function fmt(n) {
    if (n === undefined || n === null) return "—";
    return n.toLocaleString();
}

function fmtK(n) {
    if (n === undefined || n === null) return "—";
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
    if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
    return n.toString();
}

function truncate(s, max) {
    if (!s) return "—";
    return s.length > max ? s.slice(0, max) + "…" : s;
}

function getStatusClass(status) {
    if (!status) return "pending";
    const s = status.toLowerCase();
    if (s.includes("blue") || s.includes("success") || s.includes("stable")) return "success";
    if (s.includes("red") || s.includes("fail") || s.includes("error")) return "error";
    if (s.includes("yellow") || s.includes("unstable")) return "warning";
    if (s.includes("running") || s.includes("building")) return "info";
    return "pending";
}

function getHealthClass(health) {
    if (!health) return "pending";
    const h = health.toLowerCase();
    if (h === "healthy") return "success";
    if (h === "degraded") return "warning";
    if (h === "missing" || h === "unknown") return "pending";
    return "error";
}
