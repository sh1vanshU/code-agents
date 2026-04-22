var E=Object.defineProperty;var L=(o,e,t)=>e in o?E(o,e,{enumerable:!0,configurable:!0,writable:!0,value:t}):o[e]=t;var c=(o,e,t)=>L(o,typeof e!="symbol"?e+"":e,t);(function(){const e=document.createElement("link").relList;if(e&&e.supports&&e.supports("modulepreload"))return;for(const n of document.querySelectorAll('link[rel="modulepreload"]'))s(n);new MutationObserver(n=>{for(const i of n)if(i.type==="childList")for(const l of i.addedNodes)l.tagName==="LINK"&&l.rel==="modulepreload"&&s(l)}).observe(document,{childList:!0,subtree:!0});function t(n){const i={};return n.integrity&&(i.integrity=n.integrity),n.referrerPolicy&&(i.referrerPolicy=n.referrerPolicy),n.crossOrigin==="use-credentials"?i.credentials="include":n.crossOrigin==="anonymous"?i.credentials="omit":i.credentials="same-origin",i}function s(n){if(n.ep)return;n.ep=!0;const i=t(n);fetch(n.href,i)}})();const M=[{name:"auto-pilot",description:"Full SDLC orchestration"},{name:"code-writer",description:"Generate & modify code"},{name:"code-reviewer",description:"Review, bugs, security"},{name:"code-reasoning",description:"Analysis & exploration"},{name:"code-tester",description:"Write tests, debug"},{name:"test-coverage",description:"Coverage analysis"},{name:"qa-regression",description:"Full regression suites"},{name:"jenkins-cicd",description:"Build & deploy"},{name:"argocd-verify",description:"Deployment verification"},{name:"git-ops",description:"Git workflows"},{name:"jira-ops",description:"Jira & Confluence"},{name:"redash-query",description:"SQL via Redash"},{name:"security",description:"OWASP scanning"}],A={connected:!1,serverUrl:"http://localhost:8000",agents:M,currentAgent:"auto-pilot",currentModel:"",mode:"chat",messages:[],isStreaming:!1,streamingContent:"",view:"chat",showSlashPalette:!1,showMentionPicker:!1,showAgentPicker:!1,slashFilter:"",mentionFilter:"",contextFiles:[],plan:null,pendingApproval:null,sessionTokens:0,maxSessionTokens:1e5,settings:{theme:"auto",autoRun:!0,requireConfirm:!0,dryRun:!1,superpower:!1,contextWindow:5,autoStartServer:!1}};class T{constructor(){c(this,"state");c(this,"listeners",new Set);this.state={...A}}getState(){return{...this.state}}update(e){this.state={...this.state,...e},this.notify()}updateSettings(e){this.state={...this.state,settings:{...this.state.settings,...e}},this.notify()}addMessage(e){this.state={...this.state,messages:[...this.state.messages,e]},this.notify()}updateLastMessage(e){const t=[...this.state.messages];t.length>0&&(t[t.length-1]={...t[t.length-1],content:e}),this.state={...this.state,messages:t},this.notify()}clearMessages(){this.state={...this.state,messages:[],plan:null,pendingApproval:null},this.notify()}addContextFile(e,t){this.state.contextFiles.some(n=>n.path===e)||(this.state={...this.state,contextFiles:[...this.state.contextFiles,{path:e,lines:t}]},this.notify())}removeContextFile(e){this.state={...this.state,contextFiles:this.state.contextFiles.filter(t=>t.path!==e)},this.notify()}subscribe(e){return this.listeners.add(e),()=>this.listeners.delete(e)}notify(){for(const e of this.listeners)e(this.state)}static msgId(){return Date.now().toString(36)+Math.random().toString(36).slice(2,6)}}const a=new T;function q(){let o=null;function e(t){o&&window.removeEventListener("message",o),o=s=>t(s.data),window.addEventListener("message",o)}if(typeof acquireVsCodeApi=="function"){const t=acquireVsCodeApi();return{postMessage:s=>t.postMessage(s),onMessage:s=>e(s),getState:()=>t.getState()||{},setState:s=>t.setState(s),platform:"vscode"}}return window.ideBridge?{postMessage:t=>{try{window.ideBridge&&window.ideBridge.send(JSON.stringify(t))}catch(s){console.error("[CodeAgents] Failed to send message:",s)}},onMessage:t=>{window._ideCallback=t},getState:()=>{try{return JSON.parse(localStorage.getItem("ca-state")||"{}")}catch{return{}}},setState:t=>{try{localStorage.setItem("ca-state",JSON.stringify(t))}catch{}},platform:"intellij"}:{postMessage:t=>console.log("[IDE.postMessage]",t),onMessage:t=>{e(t),window.__ideCallback=t},getState:()=>{try{return JSON.parse(localStorage.getItem("ca-state")||"{}")}catch{return{}}},setState:t=>{try{localStorage.setItem("ca-state",JSON.stringify(t))}catch{}},platform:"browser"}}const u=q();window.IDE=u;function x(o,e){u.postMessage({type:"sendMessage",text:o,agent:e})}function k(o){u.postMessage({type:"changeAgent",agent:o})}function D(o){u.postMessage({type:"changeMode",mode:o})}function R(){u.postMessage({type:"cancelStream"})}function P(o,e){u.postMessage({type:"slashCommand",command:o,args:e})}function v(o,e){u.postMessage({type:"approvalResponse",id:o,approved:e})}function S(o,e){u.postMessage({type:"applyDiff",filePath:o,diff:e})}function N(o,e){u.postMessage({type:"openFile",filePath:o,line:e})}function H(o){u.postMessage({type:"saveSettings",settings:o})}function B(){u.postMessage({type:"loadHistory"})}function I(o){u.postMessage({type:"resumeSession",sessionId:o})}function F(o){u.postMessage({type:"exportChat",format:o})}const O={debug:"color: #7a7a94",info:"color: #6366f1",warn:"color: #fbbf24",error:"color: #f87171; font-weight: bold"};class j{constructor(){c(this,"enabled",!0)}enable(){this.enabled=!0}disable(){this.enabled=!1}debug(e,t,s){this.log("debug",e,t,s)}info(e,t,s){this.log("info",e,t,s)}warn(e,t,s){this.log("warn",e,t,s)}error(e,t,s){this.log("error",e,t,s)}stateChange(e,t,s){this.log("debug",e,`State: ${t}`,s)}message(e,t,s){const n=e==="send"?"→":"←";this.log("debug","Protocol",`${n} ${t}`,s)}log(e,t,s,n){if(!this.enabled)return;const l=`%c[${new Date().toISOString().slice(11,23)}] [${t}]`,r=O[e];n!==void 0?console[e](l,r,s,n):console[e](l,r,s)}}const V=new j,W=[{pattern:/(\/\/.*$|#.*$)/gm,className:"hl-comment"},{pattern:/("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)/g,className:"hl-string"},{pattern:/\b(\d+\.?\d*(?:e[+-]?\d+)?|0x[0-9a-f]+|0b[01]+)\b/gi,className:"hl-number"},{pattern:/\b(function|const|let|var|if|else|return|import|export|from|class|def|self|async|await|try|catch|finally|throw|new|for|while|do|switch|case|break|continue|in|of|type|interface|enum|struct|impl|fn|pub|mod|use|package|public|private|protected|static|final|void|int|string|boolean|true|false|null|undefined|None|True|False|yield|lambda|raise|except|pass|with|as|is|not|and|or|extends|implements|abstract|override|super|this|val|var|when|companion|object|data|sealed|suspend|lateinit|lazy|open|internal)\b/g,className:"hl-keyword"},{pattern:/\b([A-Z][a-zA-Z0-9_]*(?:<[^>]*>)?)\b/g,className:"hl-type"},{pattern:/\b([a-zA-Z_]\w*)\s*\(/g,className:"hl-function"},{pattern:/(@\w+)/g,className:"hl-decorator"},{pattern:/(=>|->|&&|\|\||===?|!==?|<=?|>=?|\+=?|-=?|\*=?|\/=?|%=?|\.\.\.|::)/g,className:"hl-operator"}];function z(o,e){if(!o||["text","plain","output","log","diff"].includes(e.toLowerCase()))return o;let s=o;const n=[];for(const r of W){const d=new RegExp(r.pattern.source,r.pattern.flags);let h;for(;(h=d.exec(o))!==null;){const g=h[1]||h[0],m=h.index+h[0].indexOf(g);n.push({start:m,end:m+g.length,cls:r.className})}}n.sort((r,d)=>d.start-r.start);const i=new Set,l=n.filter(r=>{for(let d=r.start;d<r.end;d++)if(i.has(d))return!1;for(let d=r.start;d<r.end;d++)i.add(d);return!0});l.sort((r,d)=>d.start-r.start);for(const r of l){const d=s.slice(0,r.start),h=s.slice(r.start,r.end),g=s.slice(r.end);s=`${d}<span class="${r.cls}">${h}</span>${g}`}return s}function p(o){const e=document.createElement("span");return e.textContent=o,e.innerHTML}function C(o){if(!o)return"";let e=p(o);return e=e.replace(/```(\w*)\s*\n([\s\S]*?)\n```/g,(t,s,n)=>{const i=s||"code",l=s?` class="language-${s}"`:"";return`<div class="code-block-wrapper">
      <div class="code-block-header">
        <span class="code-block-lang">${p(i)}</span>
        <div class="code-block-actions">
          <button class="btn-icon btn-copy" data-code="${f(n)}" title="Copy">📋</button>
          <button class="btn-icon btn-apply" data-code="${f(n)}" title="Apply to editor">✓</button>
        </div>
      </div>
      <div class="code-block-content"><code${l}>${s?z(n,s):n}</code></div>
    </div>`}),e=e.replace(/`([^`\n]+)`/g,"<code>$1</code>"),e=e.replace(/\*\*([^*]+)\*\*/g,"<strong>$1</strong>"),e=e.replace(new RegExp("(?<!\\*)\\*([^*]+)\\*(?!\\*)","g"),"<em>$1</em>"),e=e.replace(/^### (.+)$/gm,"<h4>$1</h4>"),e=e.replace(/^## (.+)$/gm,"<h3>$1</h3>"),e=e.replace(/^# (.+)$/gm,'<h3 style="font-size:16px">$1</h3>'),e=e.replace(/(?:^&gt; (.+)$\n?)+/gm,t=>`<blockquote>${t.trim().split(`
`).map(n=>n.replace(/^&gt; /,"")).join("<br>")}</blockquote>`),e=e.replace(/(?:^- (.+)$\n?)+/gm,t=>`<ul>${t.trim().split(`
`).map(n=>`<li>${n.replace(/^- /,"")}</li>`).join("")}</ul>`),e=e.replace(/(?:^\d+\. (.+)$\n?)+/gm,t=>`<ol>${t.trim().split(`
`).map(n=>`<li>${n.replace(/^\d+\. /,"")}</li>`).join("")}</ol>`),e=e.replace(/\[([^\]]+)\]\(([^)]+)\)/g,(t,s,n)=>{const i=n.trim();return i.startsWith("javascript:")||i.startsWith("data:")||i.startsWith("vbscript:")?s:`<a href="${f(i)}" target="_blank" rel="noopener">${s}</a>`}),e=e.replace(/^---$/gm,'<hr class="md-hr">'),e=e.replace(/\n/g,"<br>"),e=e.replace(/<br>\s*(<(?:div|pre|ul|ol|h[34]|blockquote|hr))/g,"$1"),e=e.replace(/(<\/(?:div|pre|ul|ol|h[34]|blockquote)>)\s*<br>/g,"$1"),e}function f(o){return o.replace(/&/g,"&amp;").replace(/"/g,"&quot;").replace(/'/g,"&#39;").replace(/</g,"&lt;").replace(/>/g,"&gt;")}class U{constructor(e){c(this,"el");this.request=e,this.el=document.createElement("div"),this.el.className="approval-card animate-in",this.render()}render(){var e,t,s;this.el.innerHTML=`
      <div class="approval-card-title">
        <span>&#9888;</span>
        <span>${p(this.request.agent)} wants to run</span>
      </div>
      <div class="approval-card-command">${p(this.request.command)}</div>
      <div class="approval-card-actions">
        <button class="btn btn-success btn-approve" data-id="${this.request.id}">&#10003; Approve</button>
        <button class="btn btn-danger btn-deny" data-id="${this.request.id}">&#10007; Deny</button>
        <button class="btn btn-ghost btn-autorun" data-id="${this.request.id}">&#9679; Auto-run all</button>
      </div>
    `,(e=this.el.querySelector(".btn-approve"))==null||e.addEventListener("click",()=>{v(this.request.id,!0),this.markResolved("approved")}),(t=this.el.querySelector(".btn-deny"))==null||t.addEventListener("click",()=>{v(this.request.id,!1),this.markResolved("denied")}),(s=this.el.querySelector(".btn-autorun"))==null||s.addEventListener("click",()=>{v(this.request.id,!0),a.updateSettings({autoRun:!0}),this.markResolved("auto-run enabled")})}markResolved(e){a.update({pendingApproval:null}),this.el.innerHTML=`
      <div class="approval-card" style="opacity:0.6;border-color:var(--ca-border)">
        <div style="font-size:var(--ca-font-size-sm);color:var(--ca-text-muted)">
          &#10003; ${p(e)} — ${p(this.request.command)}
        </div>
      </div>
    `}getElement(){return this.el}}class _{constructor(){c(this,"el");this.el=document.createElement("div"),this.el.className="toolbar",this.render(),a.subscribe(()=>this.updateStatus())}mount(e){e.appendChild(this.el)}render(){const e=a.getState();this.el.innerHTML=`
      <div class="toolbar-left">
        <div class="mode-selector">
          <button class="mode-tab ${e.mode==="chat"?"active":""}" data-mode="chat">Chat</button>
          <button class="mode-tab ${e.mode==="plan"?"active":""}" data-mode="plan">Plan</button>
          <button class="mode-tab ${e.mode==="agent"?"active":""}" data-mode="agent">Agent</button>
        </div>
        <div class="agent-select-wrapper" data-agent="${e.currentAgent}">
          <span class="agent-dot"></span>
          <select class="select agent-selector" title="Select agent">
            ${this.renderAgentOptions(e.currentAgent)}
          </select>
        </div>
      </div>
      <div class="toolbar-right">
        <span class="status-dot ${e.connected?"connected":"disconnected"}"
              title="${e.connected?"Server connected":"Server disconnected"}"></span>
        <button class="btn-icon btn-history" title="Chat history">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
        </button>
        <button class="btn-icon btn-settings-toggle" title="Settings">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        </button>
        <button class="btn-icon btn-new-chat" title="New chat">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        </button>
      </div>
    `,this.bindEvents()}renderAgentOptions(e){return a.getState().agents.map(s=>`<option value="${s.name}" ${s.name===e?"selected":""}>${s.name}</option>`).join("")}bindEvents(){this.el.onclick=t=>{const s=t.target,n=s.closest(".mode-tab");if(n!=null&&n.dataset.mode){const i=n.dataset.mode;a.update({mode:i}),D(i),this.el.querySelectorAll(".mode-tab").forEach(l=>l.classList.toggle("active",l===n));return}if(s.closest(".btn-settings-toggle")){a.update({view:"settings"});return}if(s.closest(".btn-history")){a.update({view:"history"});return}if(s.closest(".btn-new-chat")){a.clearMessages(),a.update({view:"chat"});return}};const e=this.el.querySelector(".agent-selector");e&&(e.onchange=()=>{const t=e.value;a.update({currentAgent:t}),k(t);const s=this.el.querySelector(".agent-select-wrapper");s&&(s.dataset.agent=t)})}updateStatus(){const e=a.getState(),t=this.el.querySelector(".status-dot");t&&(t.className=`status-dot ${e.connected?"connected":"disconnected"}`,t.setAttribute("title",e.connected?"Server connected":"Server disconnected"))}}class y{constructor(e){c(this,"el");this.message=e,this.el=document.createElement("div"),this.el.className=`message ${e.role} animate-in`,e.agent&&(this.el.dataset.agent=e.agent),this.render()}render(){const e=this.message;if(e.role==="error"){this.el.innerHTML=p(e.content);return}if(e.role==="system"){this.el.innerHTML=p(e.content);return}let t="";if(e.role==="assistant"&&e.agent){const s=new Date(e.timestamp).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});t+=`<div class="message-header">
        <span class="message-sender">${p(e.agent)}</span>
        <span class="message-time">${s}</span>
      </div>`}if(e.role==="user"){const s=new Date(e.timestamp).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});t+=`<div class="message-header">
        <span class="message-sender" style="color:var(--ca-text-secondary)">You</span>
        <span class="message-time">${s}</span>
      </div>`}if(e.filePath){const s=e.fileLines?`${e.filePath} (${e.fileLines})`:e.filePath;t+=`<div class="file-chip" data-path="${p(e.filePath)}">
        <span class="file-icon">📄</span>
        <span>${p(s)}</span>
      </div>`}t+='<div class="message-content">',e.role==="user"?t+=p(e.content).replace(/\n/g,"<br>"):t+=C(e.content),t+="</div>",e.role==="assistant"&&e.content&&(t+=`<div class="message-footer">
        <button class="btn-icon btn-reaction" data-reaction="up" title="Helpful">👍</button>
        <button class="btn-icon btn-reaction" data-reaction="down" title="Not helpful">👎</button>
        <button class="btn-icon btn-retry" title="Retry">↻</button>
        <button class="btn-icon btn-copy-msg" title="Copy message">📋</button>
        <button class="btn-icon btn-delegate" title="Delegate to another agent">→</button>
      </div>`),this.el.innerHTML=t,this.bindEvents()}bindEvents(){this.el.querySelectorAll(".file-chip").forEach(e=>{e.addEventListener("click",()=>{const t=e.dataset.path;t&&N(t)})}),this.el.querySelectorAll(".btn-copy").forEach(e=>{e.addEventListener("click",()=>{const t=e.dataset.code||"";navigator.clipboard.writeText(b(t)),e.textContent="✓",setTimeout(()=>{e.isConnected&&(e.textContent="📋")},1500)})}),this.el.querySelectorAll(".btn-apply").forEach(e=>{e.addEventListener("click",()=>{const t=e.dataset.code||"";S("",b(t)),e.textContent="✓ Applied"})}),this.el.querySelectorAll(".btn-apply-diff").forEach(e=>{e.addEventListener("click",()=>{const t=e.dataset.file||"",s=e.dataset.diff||"";S(t,b(s)),e.textContent="✓ Applied",e.classList.add("btn-ghost"),e.setAttribute("disabled","")})}),this.el.querySelectorAll(".btn-copy-msg").forEach(e=>{e.addEventListener("click",()=>{navigator.clipboard.writeText(this.message.content),e.textContent="✓",setTimeout(()=>{e.isConnected&&(e.textContent="📋")},1500)})})}getElement(){return this.el}}function b(o){return o.replace(/&amp;/g,"&").replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,"<").replace(/&gt;/g,">")}class K{constructor(){c(this,"el");c(this,"autoScroll",!0);c(this,"lastMessageCount",0);c(this,"lastStreamContent","");this.el=document.createElement("div"),this.el.className="messages",this.el.id="messages",this.el.addEventListener("scroll",()=>{const{scrollTop:e,scrollHeight:t,clientHeight:s}=this.el;this.autoScroll=t-e-s<60}),a.subscribe(e=>this.onStateChange(e))}mount(e){e.appendChild(this.el)}onStateChange(e){const t=e.messages;if(t.length!==this.lastMessageCount){if(t.length>this.lastMessageCount&&this.lastMessageCount>0)for(let s=this.lastMessageCount;s<t.length;s++){const n=new y(t[s]);this.el.appendChild(n.getElement())}else this.renderMessages(t);this.lastMessageCount=t.length,this.lastStreamContent=""}else if(e.isStreaming&&t.length>0){const s=e.streamingContent;if(s!==this.lastStreamContent){const n=this.el.lastElementChild;if(n){const i=n.querySelector(".message-content");if(i)i.innerHTML=C(s);else{const l=new y(t[t.length-1]);n.replaceWith(l.getElement())}}this.lastStreamContent=s}}this.autoScroll&&this.scrollToBottom()}renderMessages(e){this.el.innerHTML="";for(const t of e){const s=new y(t);this.el.appendChild(s.getElement())}}scrollToBottom(){requestAnimationFrame(()=>{this.el.scrollTop=this.el.scrollHeight})}getElement(){return this.el}}const $=[{command:"help",description:"Show all commands",category:"Navigation"},{command:"open",description:"Open related resource",category:"Navigation"},{command:"setup",description:"Run setup wizard",category:"Navigation"},{command:"restart",description:"Restart chat",category:"Navigation"},{command:"quit",description:"Exit chat",category:"Navigation"},{command:"clear",description:"Clear session, start fresh",category:"Session"},{command:"history",description:"List saved sessions",category:"Session"},{command:"resume",description:"Resume a saved session",category:"Session"},{command:"export",description:"Export conversation",category:"Session"},{command:"session",description:"Show session ID",category:"Session"},{command:"delete-chat",description:"Delete a saved session",category:"Session"},{command:"agent",description:"Switch to another agent",category:"Agent"},{command:"agents",description:"List all agents",category:"Agent"},{command:"skills",description:"List agent skills",category:"Agent"},{command:"rules",description:"Show active rules",category:"Agent"},{command:"memory",description:"Show agent memory",category:"Agent"},{command:"tokens",description:"Token usage stats",category:"Agent"},{command:"review",description:"Code review current file",category:"Code"},{command:"refactor",description:"Refactoring suggestions",category:"Code"},{command:"blame",description:"Deep git blame story",category:"Code"},{command:"deps",description:"Dependency tree",category:"Code"},{command:"impact",description:"Impact analysis",category:"Code"},{command:"solve",description:"Problem decomposition",category:"Code"},{command:"generate-tests",description:"Generate tests for file",category:"Code"},{command:"pr-preview",description:"Preview PR before opening",category:"Code"},{command:"review-reply",description:"Reply to PR review",category:"Code"},{command:"investigate",description:"Search Kibana logs",category:"Code"},{command:"run",description:"Execute shell command",category:"DevOps"},{command:"bash",description:"Direct shell execution",category:"DevOps"},{command:"flags",description:"Feature flags analysis",category:"DevOps"},{command:"config-diff",description:"Compare configs",category:"DevOps"},{command:"model",description:"Switch model",category:"Config"},{command:"backend",description:"Switch backend",category:"Config"},{command:"theme",description:"Switch color theme",category:"Config"},{command:"plan",description:"Create execution plan",category:"Runtime"},{command:"confirm",description:"Toggle confirmation gate",category:"Runtime"},{command:"superpower",description:"Auto-execute commands",category:"Runtime"},{command:"sandbox",description:"Restrict writes to project",category:"Runtime"},{command:"verify",description:"Auto-verify with reviewer",category:"Runtime"},{command:"pair",description:"Pair programming mode",category:"Runtime"},{command:"mcp",description:"MCP servers & tools",category:"Runtime"},{command:"bg",description:"Background tasks",category:"Runtime"},{command:"repo",description:"Switch repository",category:"Runtime"},{command:"btw",description:"Side message to agent",category:"Runtime"},{command:"qa-suite",description:"QA regression suite",category:"Testing"},{command:"coverage-boost",description:"Auto-boost coverage",category:"Testing"},{command:"mutate",description:"Mutation testing",category:"Testing"},{command:"testdata",description:"Generate test fixtures",category:"Testing"}];class J{constructor(){c(this,"el");c(this,"selectedIndex",0);c(this,"filteredCommands",[]);c(this,"keydownHandler",null);this.el=document.createElement("div"),this.el.className="slash-palette hidden",this.el.id="slash-palette",this.el.addEventListener("click",e=>{const t=e.target.closest(".slash-item");t!=null&&t.dataset.cmd&&this.selectCommand(t.dataset.cmd)}),a.subscribe(e=>{e.showSlashPalette?this.show(e.slashFilter):this.hide()})}mount(e){e.appendChild(this.el)}show(e){this.el.classList.remove("hidden"),this.selectedIndex=0,this.renderList(e),this.attachKeyboard()}hide(){this.el.classList.add("hidden"),this.detachKeyboard()}attachKeyboard(){this.detachKeyboard(),this.keydownHandler=e=>{a.getState().showSlashPalette&&(e.key==="ArrowDown"?(e.preventDefault(),this.selectedIndex=Math.min(this.selectedIndex+1,this.filteredCommands.length-1),this.updateSelection()):e.key==="ArrowUp"?(e.preventDefault(),this.selectedIndex=Math.max(this.selectedIndex-1,0),this.updateSelection()):e.key==="Enter"&&this.filteredCommands.length>0?(e.preventDefault(),this.selectCommand(this.filteredCommands[this.selectedIndex].command)):e.key==="Tab"&&this.filteredCommands.length>0&&(e.preventDefault(),this.selectCommand(this.filteredCommands[this.selectedIndex].command)))},document.addEventListener("keydown",this.keydownHandler,!0)}detachKeyboard(){this.keydownHandler&&(document.removeEventListener("keydown",this.keydownHandler,!0),this.keydownHandler=null)}updateSelection(){this.el.querySelectorAll(".slash-item").forEach((t,s)=>{t.classList.toggle("selected",s===this.selectedIndex)});const e=this.el.querySelector(".slash-item.selected");e==null||e.scrollIntoView({block:"nearest"})}renderList(e){this.filteredCommands=$.filter(i=>i.command.includes(e.toLowerCase())||i.description.toLowerCase().includes(e.toLowerCase()));const t={};for(const i of this.filteredCommands)t[i.category]||(t[i.category]=[]),t[i.category].push(i);let s="",n=0;for(const[i,l]of Object.entries(t)){s+=`<div class="slash-category">${i}</div>`;for(const r of l)s+=`<div class="slash-item ${n===this.selectedIndex?"selected":""}" data-cmd="${r.command}" data-idx="${n}">
          <span class="slash-item-cmd">/${r.command}</span>
          <span class="slash-item-desc">${r.description}</span>
        </div>`,n++}this.filteredCommands.length===0&&(s='<div class="palette-empty">No commands found</div>'),this.el.innerHTML=`<div class="slash-palette-list">${s}</div>`}selectCommand(e){a.update({showSlashPalette:!1});const t=document.getElementById("chat-textarea");t&&(t.value=`/${e} `,t.focus())}getElement(){return this.el}}class G{constructor(){c(this,"el");c(this,"textarea");c(this,"sendBtn");this.el=document.createElement("div"),this.el.className="input-area",this.render(),a.subscribe(e=>this.onStateChange(e))}mount(e){e.appendChild(this.el)}focus(){var e;(e=this.textarea)==null||e.focus()}setText(e){this.textarea&&(this.textarea.value=e,this.autoResize())}render(){const e=a.getState();this.el.innerHTML=`
      <div class="input-context" id="input-context"></div>
      <div class="input-toolbar">
        <button class="btn-icon btn-mention" title="Mention file or agent (@)">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-3.92 7.94"/></svg>
        </button>
        <button class="btn-icon btn-attach" title="Attach file context">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
        </button>
        <span class="slash-indicator" id="slash-trigger" title="Slash commands">/commands</span>
      </div>
      <div class="input-row" style="position:relative">
        <div id="slash-palette-mount"></div>
        <div id="mention-picker-mount"></div>
        <textarea
          class="chat-textarea"
          id="chat-textarea"
          placeholder="Ask anything... (Enter to send, Shift+Enter for newline)"
          rows="1"
          ${e.isStreaming?"disabled":""}
        ></textarea>
        <button class="btn-send ${e.isStreaming?"stop":""}" id="btn-send"
                title="${e.isStreaming?"Stop generation":"Send message"}">
          ${e.isStreaming?'<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>':'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13"/><path d="M22 2L15 22L11 13L2 9L22 2Z"/></svg>'}
        </button>
      </div>
      <div class="input-hint">
        <span>Enter to send, Shift+Enter for newline</span>
        <span class="token-counter" id="token-counter"></span>
      </div>
    `,this.textarea=this.el.querySelector("#chat-textarea"),this.sendBtn=this.el.querySelector("#btn-send"),this.bindEvents(),this.renderContext()}bindEvents(){var e,t;this.sendBtn.addEventListener("click",()=>{a.getState().isStreaming?R():this.handleSend()}),this.textarea.addEventListener("keydown",s=>{s.key==="Enter"&&!s.shiftKey&&(s.preventDefault(),this.handleSend()),s.key==="/"&&this.textarea.value===""&&a.update({showSlashPalette:!0,slashFilter:""}),s.key==="@"&&a.update({showMentionPicker:!0,mentionFilter:""}),s.key==="Escape"&&a.update({showSlashPalette:!1,showMentionPicker:!1})}),this.textarea.addEventListener("input",()=>{if(this.autoResize(),a.getState().showSlashPalette){const s=this.textarea.value;s.startsWith("/")?a.update({slashFilter:s.slice(1)}):a.update({showSlashPalette:!1})}if(a.getState().showMentionPicker){const s=this.textarea.value,n=s.lastIndexOf("@");n>=0?a.update({mentionFilter:s.slice(n+1)}):a.update({showMentionPicker:!1})}}),(e=this.el.querySelector("#slash-trigger"))==null||e.addEventListener("click",()=>{a.update({showSlashPalette:!a.getState().showSlashPalette}),this.textarea.focus()}),(t=this.el.querySelector(".btn-mention"))==null||t.addEventListener("click",()=>{const s=this.textarea.selectionStart,n=this.textarea.selectionEnd,i=this.textarea.value;this.textarea.value=i.slice(0,s)+"@"+i.slice(n),this.textarea.selectionStart=this.textarea.selectionEnd=s+1,this.textarea.focus(),a.update({showMentionPicker:!0,mentionFilter:""})})}handleSend(){var n,i;const e=this.textarea.value.trim();if(!e||a.getState().isStreaming)return;if(e.startsWith("/")){const l=e.split(" "),r=l[0].slice(1),d=l.slice(1).join(" ");if($.find(g=>g.command===r)){P(r,d),this.textarea.value="",this.autoResize(),a.update({showSlashPalette:!1});return}}const t=a.getState();let s=e;t.contextFiles.length>0&&(s=`${t.contextFiles.map(r=>r.lines?`File: ${r.path} (${r.lines})`:`File: ${r.path}`).join(`
`)}

${e}`),a.addMessage({id:Date.now().toString(36)+Math.random().toString(36).slice(2,6),role:"user",content:e,timestamp:Date.now(),filePath:(n=t.contextFiles[0])==null?void 0:n.path,fileLines:(i=t.contextFiles[0])==null?void 0:i.lines}),this.textarea.value="",this.autoResize(),a.update({contextFiles:[],showSlashPalette:!1,showMentionPicker:!1}),x(s,t.currentAgent)}autoResize(){this.textarea.style.height="0",this.textarea.style.height=Math.min(this.textarea.scrollHeight+2,150)+"px"}renderContext(){const e=this.el.querySelector("#input-context");if(!e)return;const t=a.getState();if(t.contextFiles.length===0){e.style.display="none";return}e.style.display="flex",e.innerHTML=t.contextFiles.map(s=>`
      <div class="file-chip">
        <span class="file-icon">📄</span>
        <span>${p(s.lines?`${s.path} (${s.lines})`:s.path)}</span>
        <span class="btn-remove" data-path="${p(s.path)}">&times;</span>
      </div>
    `).join(""),e.onclick=s=>{const n=s.target.closest(".btn-remove");n!=null&&n.dataset.path&&(a.removeContextFile(n.dataset.path),this.renderContext())}}onStateChange(e){this.sendBtn&&(this.sendBtn.className=`btn-send ${e.isStreaming?"stop":""}`,this.sendBtn.title=e.isStreaming?"Stop generation":"Send message",this.sendBtn.innerHTML=e.isStreaming?'<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>':'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13"/><path d="M22 2L15 22L11 13L2 9L22 2Z"/></svg>'),this.textarea&&(this.textarea.disabled=e.isStreaming,e.isStreaming||this.textarea.focus()),this.renderContext();const t=this.el.querySelector("#token-counter");t&&e.sessionTokens>0&&(t.textContent=`${e.sessionTokens.toLocaleString()} tokens`)}getElement(){return this.el}}const Z=[{icon:"&#128221;",label:"Review",agent:"code-reviewer",prompt:"Review the latest changes for bugs and security issues"},{icon:"&#129514;",label:"Test",agent:"code-tester",prompt:"Write comprehensive tests for the current file"},{icon:"&#128269;",label:"Explain",agent:"code-reasoning",prompt:"Explain the architecture and code flow of this project"},{icon:"&#128640;",label:"Deploy",agent:"jenkins-cicd",prompt:"Build and deploy the current project"},{icon:"&#128737;",label:"Secure",agent:"security",prompt:"Run a security audit (OWASP, CVE, secrets detection)"},{icon:"&#128295;",label:"Fix",agent:"code-writer",prompt:"Fix the bugs in the current file"}];class Y{constructor(){c(this,"el");this.el=document.createElement("div"),this.el.className="welcome",this.el.id="welcome",this.render()}mount(e){e.appendChild(this.el)}render(){this.el.innerHTML=`
      <div class="welcome-logo">Code Agents</div>
      <div class="welcome-subtitle">13 specialist agents at your service. Select an agent or use a quick action to get started.</div>
      <div class="quick-actions">
        ${Z.map(e=>`
          <button class="quick-action" data-agent="${e.agent}" data-prompt="${e.prompt}">
            <span class="qa-icon">${e.icon}</span>
            <span class="qa-label">${e.label}</span>
          </button>
        `).join("")}
      </div>
    `,this.el.querySelectorAll(".quick-action").forEach(e=>{e.addEventListener("click",()=>{const t=e.dataset.agent,s=e.dataset.prompt;a.update({currentAgent:t}),k(t),a.addMessage({id:Date.now().toString(36),role:"user",content:s,timestamp:Date.now()}),x(s,t),this.el.style.display="none"})})}show(){this.el.style.display=""}hide(){this.el.style.display="none"}getElement(){return this.el}}const Q={completed:"&#10003;",current:"&#9654;",pending:"&#9675;",failed:"&#10007;"};class X{constructor(){c(this,"el");this.el=document.createElement("div"),this.el.id="plan-tracker",a.subscribe(e=>{e.plan&&e.mode==="plan"?(this.renderPlan(e.plan),this.el.style.display="block"):this.el.style.display="none"})}mount(e){e.appendChild(this.el)}renderPlan(e){const t=e.steps.filter(i=>i.status==="completed").length,s=e.steps.length,n=s>0?t/s*100:0;this.el.innerHTML=`
      <div class="plan-tracker">
        <div class="plan-header">
          <span class="plan-title">${p(e.title)}</span>
          <span class="plan-status ${e.status}">${e.status.toUpperCase()}</span>
        </div>

        <div class="plan-progress">
          <div class="plan-progress-bar">
            <div class="plan-progress-fill" style="width:${n}%"></div>
          </div>
          <span class="plan-progress-text">${t}/${s}</span>
        </div>

        <div class="plan-steps">
          ${e.steps.map((i,l)=>`
            <div class="plan-step ${i.status==="current"?"current":""}">
              <span class="plan-step-icon ${i.status}">${Q[i.status]}</span>
              <span class="plan-step-text">${l+1}. ${p(i.text)}</span>
              ${i.status==="current"?'<span class="plan-step-indicator">current</span>':""}
            </div>
          `).join("")}
        </div>

        ${e.status==="executing"||e.status==="proposed"?`
          <div class="plan-actions">
            ${e.status==="proposed"?`
              <button class="btn btn-success btn-approve-plan">Approve</button>
              <button class="btn btn-danger btn-reject-plan">Reject</button>
              <button class="btn btn-edit-plan">Edit</button>
            `:`
              <button class="btn btn-pause-plan">Pause</button>
              <button class="btn btn-danger btn-cancel-plan">Cancel</button>
            `}
          </div>
        `:""}
      </div>
    `}getElement(){return this.el}}class ee{constructor(){c(this,"el");c(this,"toolbar");c(this,"messageList");c(this,"chatInput");c(this,"welcome");c(this,"planTracker");c(this,"slashPalette");c(this,"scrollBtn");this.el=document.createElement("div"),this.el.className="chat-view",this.el.style.cssText="display:flex;flex-direction:column;height:100%;position:relative",this.toolbar=new _,this.messageList=new K,this.chatInput=new G,this.welcome=new Y,this.planTracker=new X,this.slashPalette=new J,this.scrollBtn=document.createElement("button"),this.scrollBtn.className="scroll-bottom hidden",this.scrollBtn.innerHTML="&#8595;",this.scrollBtn.title="Scroll to bottom",this.scrollBtn.addEventListener("click",()=>{this.messageList.scrollToBottom()}),this.toolbar.mount(this.el);const e=document.createElement("div");e.style.cssText="flex:1;position:relative;overflow:hidden;display:flex;flex-direction:column",this.welcome.mount(e),this.messageList.mount(e),this.planTracker.mount(e),e.appendChild(this.scrollBtn),this.el.appendChild(e),this.chatInput.mount(this.el);const t=this.el.querySelector("#slash-palette-mount");t&&this.slashPalette.mount(t),a.subscribe(s=>{s.messages.length===0&&!s.isStreaming?(this.welcome.show(),this.messageList.getElement().style.display="none"):(this.welcome.hide(),this.messageList.getElement().style.display="");const n=this.messageList.getElement(),{scrollTop:i,scrollHeight:l,clientHeight:r}=n,d=l-i-r<60;this.scrollBtn.classList.toggle("hidden",d||s.messages.length===0)})}mount(e){e.appendChild(this.el)}show(){this.el.style.display="flex"}hide(){this.el.style.display="none"}focus(){this.chatInput.focus()}setInput(e){this.chatInput.setText(e)}getElement(){return this.el}}class te{constructor(){c(this,"el");this.el=document.createElement("div"),this.el.className="overlay overlay-enter",this.el.style.display="none",a.subscribe(e=>{e.view==="settings"?(this.render(),this.el.style.display=""):this.el.style.display="none"})}mount(e){e.appendChild(this.el)}render(){const e=a.getState(),t=e.settings;this.el.innerHTML=`
      <div class="overlay-header">
        <button class="btn-back" id="settings-back">&larr; Back</button>
        <span class="overlay-title">Settings</span>
      </div>
      <div class="overlay-body">

        <div class="settings-section">
          <div class="settings-section-title">Connection</div>
          <div class="settings-card">
            <div class="settings-row">
              <span class="settings-label">Server URL</span>
              <div class="settings-value">
                <input class="input" id="set-server-url" value="${e.serverUrl}" style="max-width:200px;text-align:right">
              </div>
            </div>
            <div class="settings-row">
              <span class="settings-label">Status</span>
              <div class="settings-value flex items-center gap-4" style="justify-content:flex-end">
                <span class="status-dot ${e.connected?"connected":"disconnected"}"></span>
                <span style="font-size:var(--ca-font-size-sm)">${e.connected?"Connected":"Disconnected"}</span>
              </div>
            </div>
            <div class="settings-row">
              <span class="settings-label">Auto-start server</span>
              <div class="settings-value">
                <button class="toggle ${t.autoStartServer?"on":""}" id="set-autostart"></button>
              </div>
            </div>
          </div>
        </div>

        <div class="settings-section">
          <div class="settings-section-title">Defaults</div>
          <div class="settings-card">
            <div class="settings-row">
              <span class="settings-label">Agent</span>
              <div class="settings-value">
                <select class="select" id="set-agent" style="max-width:160px;margin-left:auto">
                  ${e.agents.map(s=>`<option value="${s.name}" ${s.name===e.currentAgent?"selected":""}>${s.name}</option>`).join("")}
                </select>
              </div>
            </div>
            <div class="settings-row">
              <span class="settings-label">Context window</span>
              <div class="settings-value">
                <input class="input" id="set-context-window" type="number" min="1" max="20" value="${t.contextWindow}" style="max-width:80px;text-align:right">
              </div>
            </div>
          </div>
        </div>

        <div class="settings-section">
          <div class="settings-section-title">Behavior</div>
          <div class="settings-card">
            <div class="settings-row">
              <span class="settings-label">Auto-run commands</span>
              <div class="settings-value">
                <button class="toggle ${t.autoRun?"on":""}" id="set-autorun"></button>
              </div>
            </div>
            <div class="settings-row">
              <span class="settings-label">Require confirmation</span>
              <div class="settings-value">
                <button class="toggle ${t.requireConfirm?"on":""}" id="set-confirm"></button>
              </div>
            </div>
            <div class="settings-row">
              <span class="settings-label">Dry-run mode</span>
              <div class="settings-value">
                <button class="toggle ${t.dryRun?"on":""}" id="set-dryrun"></button>
              </div>
            </div>
            <div class="settings-row">
              <span class="settings-label">Superpower</span>
              <div class="settings-value">
                <button class="toggle ${t.superpower?"on":""}" id="set-superpower"></button>
              </div>
            </div>
          </div>
        </div>

        <div class="settings-section">
          <div class="settings-section-title">Theme</div>
          <div class="settings-card">
            <div class="settings-row">
              <span class="settings-label">Theme</span>
              <div class="settings-value flex gap-4" style="justify-content:flex-end">
                ${["auto","dark","light","high-contrast"].map(s=>`
                  <button class="btn btn-ghost ${t.theme===s?"btn-primary":""}" data-theme="${s}">${s.charAt(0).toUpperCase()+s.slice(1)}</button>
                `).join("")}
              </div>
            </div>
          </div>
        </div>

        <div class="settings-section">
          <div class="settings-section-title">Usage</div>
          <div class="settings-card">
            <div class="stats-bar">
              <div class="stats-bar-header">
                <span>Session tokens</span>
                <span>${e.sessionTokens.toLocaleString()} / ${e.maxSessionTokens.toLocaleString()}</span>
              </div>
              <div class="stats-bar-track">
                <div class="stats-bar-fill ${e.sessionTokens/e.maxSessionTokens>.8?"danger":""}"
                     style="width:${Math.min(100,e.sessionTokens/e.maxSessionTokens*100)}%"></div>
              </div>
            </div>
          </div>
        </div>

      </div>
      <div class="settings-footer">
        <button class="btn" id="settings-reset">Reset</button>
        <button class="btn btn-primary" id="settings-save">Save</button>
      </div>
    `,this.bindEvents()}bindEvents(){var s,n,i;(s=this.el.querySelector("#settings-back"))==null||s.addEventListener("click",()=>{a.update({view:"chat"})});const e=(l,r)=>{var d;(d=this.el.querySelector(`#${l}`))==null||d.addEventListener("click",h=>{const g=h.currentTarget;g.classList.toggle("on");const m=g.classList.contains("on");a.updateSettings({[r]:m})})};e("set-autostart","autoStartServer"),e("set-autorun","autoRun"),e("set-confirm","requireConfirm"),e("set-dryrun","dryRun"),e("set-superpower","superpower");const t=Array.from(this.el.querySelectorAll(".settings-row")).find(l=>l.querySelector("[data-theme]"));t&&(t.onclick=l=>{const r=l.target.closest("[data-theme]");if(!r)return;const d=r.dataset.theme;a.updateSettings({theme:d}),document.documentElement.dataset.theme=d,this.el.querySelectorAll("[data-theme]").forEach(h=>{h.classList.toggle("btn-primary",h.dataset.theme===d)})}),(n=this.el.querySelector("#settings-save"))==null||n.addEventListener("click",()=>{var h,g;const l=(h=this.el.querySelector("#set-server-url"))==null?void 0:h.value,r=parseInt(((g=this.el.querySelector("#set-context-window"))==null?void 0:g.value)||"5"),d=a.getState();a.update({serverUrl:l}),a.updateSettings({contextWindow:r}),H({...d.settings,serverUrl:l,contextWindow:r}),a.update({view:"chat"})}),(i=this.el.querySelector("#settings-reset"))==null||i.addEventListener("click",()=>{a.updateSettings({theme:"auto",autoRun:!0,requireConfirm:!0,dryRun:!1,superpower:!1,contextWindow:5,autoStartServer:!1}),document.documentElement.dataset.theme="auto",this.render()})}getElement(){return this.el}}class se{constructor(){c(this,"el");c(this,"sessions",[]);this.el=document.createElement("div"),this.el.className="overlay overlay-enter",this.el.style.display="none",a.subscribe(e=>{e.view==="history"?(this.el.style.display="",B()):this.el.style.display="none"})}mount(e){e.appendChild(this.el)}setSessions(e){this.sessions=e,this.render()}render(){const e=this.groupByDate(this.sessions);let t="";if(this.sessions.length===0)t='<div class="history-empty">No saved conversations yet.</div>';else for(const[s,n]of Object.entries(e)){t+=`<div class="history-group-label">${s}</div>`;for(const i of n){const l=new Date(i.timestamp).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});t+=`
            <div class="history-item" data-session-id="${i.id}" data-agent="${i.agent}">
              <div class="history-item-content">
                <div class="history-item-title">${this.escapeHtml(i.title)}</div>
                <div class="history-item-meta">${i.messageCount} messages &bull; ${l}</div>
              </div>
              <span class="history-item-agent">${i.agent}</span>
              <button class="btn-icon history-item-delete" title="Delete" data-session-id="${i.id}">&times;</button>
            </div>
          `}}this.el.innerHTML=`
      <div class="overlay-header">
        <button class="btn-back" id="history-back">&larr; Back</button>
        <span class="overlay-title">Chat History</span>
      </div>
      <div class="overlay-body">
        <div class="history-search">
          <input class="input" id="history-search-input" placeholder="Search conversations...">
        </div>
        <div id="history-list">${t}</div>
      </div>
      <div class="history-footer">
        <button class="btn" id="history-export">Export All</button>
      </div>
    `,this.bindEvents()}bindEvents(){var t,s,n;(t=this.el.querySelector("#history-back"))==null||t.addEventListener("click",()=>{a.update({view:"chat"})});const e=this.el.querySelector("#history-list");e&&e.addEventListener("click",i=>{const l=i.target;if(l.classList.contains("history-item-delete"))return;const r=l.closest(".history-item");r!=null&&r.dataset.sessionId&&(I(r.dataset.sessionId),a.update({view:"chat"}))}),(s=this.el.querySelector("#history-search-input"))==null||s.addEventListener("input",i=>{const l=i.target.value.toLowerCase();this.el.querySelectorAll(".history-item").forEach(r=>{var g,m,w;const d=((m=(g=r.querySelector(".history-item-title"))==null?void 0:g.textContent)==null?void 0:m.toLowerCase())||"",h=((w=r.dataset.agent)==null?void 0:w.toLowerCase())||"";r.style.display=d.includes(l)||h.includes(l)?"":"none"})}),(n=this.el.querySelector("#history-export"))==null||n.addEventListener("click",()=>{F("markdown")})}groupByDate(e){const t={},s=new Date,n=new Date(s.getFullYear(),s.getMonth(),s.getDate()).getTime(),i=n-864e5;for(const l of e){let r;l.timestamp>=n?r="Today":l.timestamp>=i?r="Yesterday":r=new Date(l.timestamp).toLocaleDateString(),t[r]||(t[r]=[]),t[r].push(l)}return t}escapeHtml(e){const t=document.createElement("span");return t.textContent=e,t.innerHTML}getElement(){return this.el}}class ne{constructor(e){c(this,"chatView");c(this,"settingsView");c(this,"historyView");this.chatView=new ee,this.settingsView=new te,this.historyView=new se,this.chatView.mount(e),this.settingsView.mount(e),this.historyView.mount(e),u.onMessage(n=>this.handleMessage(n));const t=u.getState();t&&t.messages&&a.update({messages:t.messages,currentAgent:t.currentAgent||"auto-pilot"}),a.subscribe(n=>{u.setState({messages:n.messages.slice(-50),currentAgent:n.currentAgent})});const s=a.getState().settings.theme;document.documentElement.dataset.theme=s}handleMessage(e){var t;if(!(!e||!e.type))switch(e.type!=="streamToken"&&V.message("recv",e.type,e.type==="streamEnd"?{contentLength:(t=e.fullContent)==null?void 0:t.length}:void 0),e.type){case"streamToken":{const s=a.getState();if(!s.isStreaming)a.update({isStreaming:!0,streamingContent:e.token}),a.addMessage({id:Date.now().toString(36)+Math.random().toString(36).slice(2,6),role:"assistant",content:e.token,agent:s.currentAgent,timestamp:Date.now()});else{const n=a.getState().streamingContent+e.token;a.update({streamingContent:n}),a.updateLastMessage(n)}break}case"streamEnd":{a.update({isStreaming:!1,streamingContent:""}),e.fullContent&&a.updateLastMessage(e.fullContent);break}case"streamError":{a.update({isStreaming:!1,streamingContent:""}),a.addMessage({id:Date.now().toString(36),role:"error",content:e.error||"An error occurred",timestamp:Date.now()});break}case"serverStatus":{a.update({connected:e.connected});break}case"setAgents":{Array.isArray(e.agents)&&e.agents.length>0&&a.update({agents:e.agents});break}case"injectContext":{e.agent&&a.update({currentAgent:e.agent}),e.filePath&&a.addContextFile(e.filePath,e.fileLines),e.text&&this.chatView.setInput(e.text),a.update({view:"chat"}),this.chatView.focus();break}case"planUpdate":{a.update({plan:e.plan,mode:"plan"});break}case"approvalRequest":{const s={id:e.id,command:e.command,agent:e.agent||a.getState().currentAgent};a.update({pendingApproval:s});const n=new U(s),i=document.getElementById("messages");i&&(i.appendChild(n.getElement()),i.scrollTop=i.scrollHeight);break}case"slashResult":{a.addMessage({id:Date.now().toString(36),role:"assistant",content:e.output,agent:a.getState().currentAgent,timestamp:Date.now()});break}case"themeChanged":{document.documentElement.dataset.theme=e.theme,a.updateSettings({theme:e.theme});break}case"restoreState":{if(e.state&&typeof e.state=="object"){const s=["messages","currentAgent","connected","serverUrl","agents","settings","mode"],n={};for(const i of s)i in e.state&&(n[i]=e.state[i]);a.update(n)}break}case"historySessions":{this.historyView.setSessions(e.sessions||[]);break}case"tokenUsage":{a.update({sessionTokens:e.sessionTokens||0,maxSessionTokens:e.maxSessionTokens||1e5});break}}}}document.addEventListener("DOMContentLoaded",()=>{const o=document.getElementById("app");o&&new ne(o)});
//# sourceMappingURL=index.js.map
