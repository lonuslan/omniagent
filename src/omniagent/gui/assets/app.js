/* ═══════════════════════════════════════════════════════════════════
   OmniAgent Studio — Frontend Logic
   ═══════════════════════════════════════════════════════════════════ */

// ── State ──────────────────────────────────────────────────────────
const state = {
    mode: 'agent',
    activeModel: '',
    allModels: [],
    running: false,
    pollTimer: null,
    pipelineCreated: false,
    pollErrors: 0,
    maxPollErrors: 5,
};

// ── API Wrapper ────────────────────────────────────────────────────
async function api(method, ...args) {
    try {
        const result = await pywebview.api[method](...args);
        return JSON.parse(result);
    } catch (e) {
        console.error(`API error: ${method}`, e);
        return { status: 'error', message: e.message };
    }
}

// ── Markdown Renderer ──────────────────────────────────────────────
function renderMarkdown(text) {
    if (!text) return '';
    let s = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    // Code blocks
    s = s.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
        const langLabel = lang || 'code';
        const blockId = 'cb-' + Math.random().toString(36).slice(2, 8);
        return `<div class="code-block"><div class="code-header"><span>${langLabel}</span><button class="copy-btn" onclick="copyCode('${blockId}')">Copy</button></div><pre><code id="${blockId}">${code.trimEnd()}</code></pre></div>`;
    });

    // Inline code
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Bold
    s = s.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Italic
    s = s.replace(/(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');
    // Links
    s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" style="color:var(--ac)">$1</a>');
    // Lists
    s = s.replace(/^- (.+)$/gm, '<li>$1</li>');
    s = s.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
    // Paragraphs
    s = s.replace(/\n\n/g, '</p><p>');
    s = s.replace(/\n/g, '<br>');

    return `<p>${s}</p>`;
}

function copyCode(id) {
    const el = document.getElementById(id);
    if (!el) return;
    navigator.clipboard.writeText(el.textContent).then(() => {
        const btn = el.closest('.code-block').querySelector('.copy-btn');
        btn.textContent = 'Copied!';
        setTimeout(() => btn.textContent = 'Copy', 1500);
    });
}

// ── Message Rendering ──────────────────────────────────────────────
function addUserMessage(text) {
    removeWelcome();
    const container = document.getElementById('messages');
    const div = document.createElement('div');
    div.className = 'message user';
    div.innerHTML = `
        <div class="avatar">U</div>
        <div class="body">
            <div class="source">You</div>
            <div class="bubble">${escapeHtml(text)}</div>
        </div>`;
    container.appendChild(div);
    scrollToBottom();
}

function addAssistantMessage(text, agentName, emoji) {
    const container = document.getElementById('messages');
    const div = document.createElement('div');
    div.className = 'message assistant';
    div.innerHTML = `
        <div class="avatar">${emoji || '🎯'}</div>
        <div class="body">
            <div class="source">${escapeHtml(agentName || 'Agent')}</div>
            <div class="bubble">${renderMarkdown(text)}</div>
        </div>`;
    container.appendChild(div);
    scrollToBottom();
}

function addSystemMessage(text, level) {
    const container = document.getElementById('messages');
    const div = document.createElement('div');
    div.className = 'message system';
    const icon = { info: 'ℹ️', success: '✅', warning: '⚠️', error: '❌', thinking: '🔍', system: '🤖' }[level] || 'ℹ️';
    div.innerHTML = `
        <div class="avatar">${icon}</div>
        <div class="body">
            <div class="source">System</div>
            <div class="bubble">${renderMarkdown(text)}</div>
        </div>`;
    container.appendChild(div);
    scrollToBottom();
}

function addToolCallCard(tool, args, result, isError) {
    const container = document.getElementById('messages');
    const div = document.createElement('div');
    div.className = 'tool-call';
    const argsStr = typeof args === 'object' ? JSON.stringify(args, null, 2) : String(args);
    div.innerHTML = `
        <div class="tool-call-header" onclick="this.parentElement.classList.toggle('open')">
            <span class="tool-icon">🔧</span>
            <span class="tool-name">${escapeHtml(tool)}</span>
            <span class="tool-status ${isError ? 'error' : 'success'}">${isError ? 'Error' : 'OK'}</span>
            <span class="chevron">▶</span>
        </div>
        <div class="tool-call-body">
            <div class="tool-args"><strong>Args:</strong> ${escapeHtml(argsStr)}</div>
            <div class="tool-result"><strong>Result:</strong> ${escapeHtml(String(result || ''))}</div>
        </div>`;
    container.appendChild(div);
    scrollToBottom();
}

function addApprovalCard(approval) {
    const container = document.getElementById('messages');
    const div = document.createElement('div');
    div.className = 'approval-card';
    div.id = `approval-${approval.id}`;
    div.innerHTML = `
        <div class="approval-title">审批请求 — ${escapeHtml(approval.agent)}</div>
        <div class="approval-desc">${escapeHtml(approval.action)}: ${escapeHtml(approval.description || '')}</div>
        <div class="approval-actions">
            <button class="btn-approve" onclick="handleApproval('${approval.id}', true)">批准</button>
            <button class="btn-deny" onclick="handleApproval('${approval.id}', false)">拒绝</button>
        </div>`;
    container.appendChild(div);
    scrollToBottom();
}

function addPipeline(stages) {
    const container = document.getElementById('messages');
    const div = document.createElement('div');
    div.className = 'message system';
    div.innerHTML = `
        <div class="avatar">🔄</div>
        <div class="body" style="max-width:100%;flex:1">
            <div class="source">Pipeline</div>
            <div class="pipeline" id="pipeline-container">
                ${stages.map((s, i) => `
                    <div class="pipeline-stage" id="stage-${i}">
                        <span class="stage-status">⬜</span>
                        <span class="stage-emoji">${s.emoji || '▶️'}</span>
                        <span class="stage-name">${escapeHtml(s.name)}</span>
                        <span class="stage-agent" id="stage-agent-${i}"></span>
                    </div>`).join('')}
            </div>
        </div>`;
    container.appendChild(div);
    state.pipelineCreated = true;
    scrollToBottom();
}

function updateStage(index, status, agent) {
    const el = document.getElementById(`stage-${index}`);
    if (!el) return;
    el.className = `pipeline-stage ${status}`;
    const statusIcon = { pending: '⬜', running: '⚡', completed: '✅', failed: '❌' }[status] || '⬜';
    el.querySelector('.stage-status').innerHTML = statusIcon;
    if (agent) {
        const agentEl = document.getElementById(`stage-agent-${index}`);
        if (agentEl) agentEl.textContent = agent.replace('Agent', '').replace('-', ' ').trim();
    }
    const completed = document.querySelectorAll('.pipeline-stage.completed').length;
    const total = document.querySelectorAll('.pipeline-stage').length;
    if (total > 0) {
        document.getElementById('status-text').textContent = `Stage ${completed + 1}/${total}`;
    }
}

// ── Approval Handling ──────────────────────────────────────────────
async function handleApproval(id, approved) {
    const card = document.getElementById(`approval-${id}`);
    if (card) {
        card.style.opacity = '0.5';
        card.querySelector('.approval-actions').innerHTML =
            `<span style="font-size:11px;color:var(--tx3)">${approved ? '已批准' : '已拒绝'}</span>`;
    }
    if (approved) {
        await api('approve_tool', id);
    } else {
        await api('deny_tool', id);
    }
}

// ── Event Polling ──────────────────────────────────────────────────
function startPolling() {
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollErrors = 0;
    state.pollTimer = setInterval(async () => {
        try {
            const events = await api('poll_events');
            if (!Array.isArray(events)) {
                state.pollErrors++;
                if (state.pollErrors >= state.maxPollErrors) stopPolling('Error');
                return;
            }
            state.pollErrors = 0;
            for (const e of events) {
                if (e.type === 'event') {
                    if (e.source === 'approval_request') {
                        try {
                            const approval = JSON.parse(e.message);
                            addApprovalCard(approval);
                        } catch (_) {
                            addAssistantMessage(e.message, 'SYSTEM', '⚠️');
                        }
                    } else {
                        const emoji = { system: '🤖', thinking: '🔍', success: '✅', warning: '⚠️', error: '❌', info: 'ℹ️' }[e.level] || '🎯';
                        addAssistantMessage(e.message, (e.source || 'system').toUpperCase(), emoji);
                    }
                } else if (e.type === 'action') {
                    if (e.action === 'init_pipeline' && !state.pipelineCreated) {
                        addPipeline(e.stages || []);
                    } else if (e.action === 'stage_update') {
                        updateStage(e.index, e.status, e.agent);
                        updateAgentDot(e.agent, e.status);
                    } else if (e.action === 'task_complete' || e.action === 'demo_complete') {
                        stopPolling('Complete');
                    } else if (e.action === 'clear') {
                        document.getElementById('messages').innerHTML = '';
                        state.pipelineCreated = false;
                        stopPolling('Ready');
                    }
                } else if (e.type === 'tool_call') {
                    addToolCallCard(e.tool, e.args, e.result, e.error);
                }
            }
        } catch (e) {
            state.pollErrors++;
            if (state.pollErrors >= state.maxPollErrors) {
                stopPolling('Poll error');
            }
        }
    }, 200);
}

function stopPolling(msg) {
    if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
    setStatus(msg || 'Ready', false);
    document.getElementById('send-btn').disabled = false;
    document.getElementById('stop-btn').classList.remove('visible');
    state.running = false;
    state.pipelineCreated = false;
}

// ── Task Submission ────────────────────────────────────────────────
async function submitTask(text) {
    if (!text || !text.trim() || state.running) return;
    const input = document.getElementById('user-input');
    input.value = '';
    input.style.height = 'auto';

    // Show user message (unless it's a command)
    if (!text.trim().startsWith('/')) {
        addUserMessage(text.trim());
    }

    setStatus('Analyzing...', true);
    document.getElementById('send-btn').disabled = true;
    document.getElementById('stop-btn').classList.add('visible');
    state.running = true;

    try {
        const r = await api('execute_task', text.trim());
        if (r.status === 'started') {
            if (r.mode === 'command') {
                // Commands resolve immediately, poll once
                setTimeout(async () => {
                    const events = await api('poll_events');
                    if (Array.isArray(events)) {
                        for (const e of events) {
                            if (e.type === 'event') {
                                const emoji = { info: 'ℹ️', warning: '⚠️', success: '✅' }[e.level] || 'ℹ️';
                                addAssistantMessage(e.message, 'SYSTEM', emoji);
                            } else if (e.type === 'action' && e.action === 'clear') {
                                document.getElementById('messages').innerHTML = '';
                            }
                        }
                    }
                    stopPolling('Ready');
                }, 100);
            } else {
                const modeLabel = r.mode === 'llm' ? 'LLM' : 'Demo';
                addAssistantMessage(`Task received (${modeLabel} mode)`, 'ORCHESTRATOR', '🎯');
                startPolling();
            }
        } else if (r.status === 'error') {
            addAssistantMessage(`Error: ${r.message}`, 'SYSTEM', '❌');
            stopPolling('Error');
        }
    } catch (e) {
        addAssistantMessage(`Error: ${e.message}`, 'ORCHESTRATOR', '❌');
        stopPolling('Error');
    }
}

async function stopTask() {
    try {
        await api('stop_task');
        addAssistantMessage('正在取消任务…', 'SYSTEM', '⚠️');
    } catch (e) { /* ignore */ }
}

// ── Mode Selector ──────────────────────────────────────────────────
function setMode(mode) {
    state.mode = mode;
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
    });
    try { api('set_mode', mode); } catch (e) { /* ignore */ }
}

// ── Settings Modal ─────────────────────────────────────────────────
function openSettings() {
    document.getElementById('settings-modal').classList.remove('hidden');
    loadModels();
    loadAgents();
    loadTools();
}

function closeSettings() {
    document.getElementById('settings-modal').classList.add('hidden');
}

function switchTab(tab) {
    document.querySelectorAll('.modal-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === `tab-${tab}`));
}

// ── Model Management ───────────────────────────────────────────────
async function loadModels() {
    try {
        const d = await api('get_models');
        state.allModels = d.models || [];
        state.activeModel = d.active_model || '';
        renderModelTags();
    } catch (e) {
        document.getElementById('model-tags').innerHTML = `<span style="color:var(--er);font-size:11px">Load failed: ${e.message}</span>`;
    }
}

function renderModelTags() {
    document.getElementById('model-tags').innerHTML = state.allModels.map(m =>
        `<span class="model-tag${m.active ? ' active-model' : ''}${state.activeModel === m.id ? ' selected' : ''}"
              onclick="selectModel('${m.id}')" id="mtag-${m.id}">${m.name}${state.activeModel === m.id ? ' ⚡' : ''}</span>`
    ).join('');
}

async function selectModel(id) {
    try {
        const d = await api('get_model_defaults', id);
        const cfg = document.getElementById('model-config');
        cfg.innerHTML = `
            <div class="config-form">
                <div class="model-info">
                    <span class="model-name">${d.name}</span>
                    <span class="model-provider">${d.provider}</span>
                    <span class="model-meta">${d.api_format} | ${d.context}</span>
                    <a href="${d.doc_url}" class="model-doc" target="_blank">Docs</a>
                </div>
                <label>API Key</label>
                <input type="password" id="cfg-key" value="${d.api_key || ''}" placeholder="sk-...">
                <label>Base URL</label>
                <input type="text" id="cfg-url" value="${d.base_url_override || d.base_url}" placeholder="${d.base_url}">
                <div class="form-row">
                    <div><label>Max Tokens</label><input type="number" id="cfg-mt" value="${d.max_tokens || d.default_max_tokens}"></div>
                    <div><label>Temperature</label><input type="number" id="cfg-temp" value="${d.temperature || d.default_temperature}" step="0.1" min="0" max="2"></div>
                </div>
                <label>Extra Config</label>
                <textarea id="cfg-extra" placeholder="# Extra config">${d.extra_headers || ''}</textarea>
                <div class="form-actions">
                    <button class="btn-primary" onclick="saveModel('${d.id}')">Save</button>
                    <button class="btn-secondary" onclick="testModel('${d.id}')">Test</button>
                    ${state.activeModel === d.id
                        ? '<button class="btn-success" disabled>Active</button>'
                        : `<button class="btn-success" onclick="activateModel('${d.id}')">Activate</button>`}
                </div>
                <div id="cfg-result-${d.id}"></div>
            </div>`;
        document.getElementById('model-tags').querySelectorAll('.model-tag').forEach(t => t.classList.remove('selected'));
        document.getElementById(`mtag-${id}`).classList.add('selected');
    } catch (e) {
        document.getElementById('model-config').innerHTML = `<div style="color:var(--er);font-size:11px">${e.message}</div>`;
    }
}

async function saveModel(id) {
    const cfg = {
        api_key: document.getElementById('cfg-key').value.trim(),
        base_url: document.getElementById('cfg-url').value.trim(),
        max_tokens: parseInt(document.getElementById('cfg-mt').value) || 4096,
        temperature: parseFloat(document.getElementById('cfg-temp').value) || 0.7,
    };
    if (!cfg.api_key) { showCfgResult(id, 'Please enter API Key', 'err'); return; }
    try {
        await api('save_model_config', id, JSON.stringify(cfg));
        showCfgResult(id, 'Saved', 'ok');
        loadModels();
    } catch (e) { showCfgResult(id, 'Save failed', 'err'); }
}

async function testModel(id) {
    showCfgResult(id, 'Testing...', '');
    try {
        const r = await api('test_model_connection', id);
        const latency = r.latency_ms ? `[${r.latency_ms}ms] ` : '';
        showCfgResult(id, latency + r.message, r.status);
    } catch (e) { showCfgResult(id, `Test failed: ${e.message}`, 'err'); }
}

async function activateModel(id) {
    try {
        const r = await api('select_model', id);
        if (r.status === 'ok') {
            showCfgResult(id, 'Model activated', 'ok');
            state.activeModel = id;
            renderModelTags();
            loadModels();
            refreshStatus();
        }
    } catch (e) { showCfgResult(id, 'Activation failed', 'err'); }
}

function showCfgResult(id, msg, cls) {
    const el = document.getElementById(`cfg-result-${id}`);
    if (el) el.innerHTML = `<div class="result-msg ${cls}">${msg}</div>`;
}

// ── Agent & Tool Lists ─────────────────────────────────────────────
async function loadAgents() {
    try {
        const agents = await api('get_agents');
        document.getElementById('agent-list').innerHTML = agents.map(a =>
            `<div class="agent-row" id="ar-${a.id}">
                <div class="agent-dot" id="ard-${a.id}"></div>
                <div class="agent-info">
                    <div class="agent-name">${escapeHtml(a.name)}</div>
                    <div class="agent-caps">${(a.capabilities || []).slice(0, 3).join(', ')}</div>
                </div>
            </div>`
        ).join('');
    } catch (e) { /* ignore */ }
}

async function loadTools() {
    try {
        const tools = await api('get_tools');
        const cats = { file: '📁', shell: '💻', web: '🌐' };
        document.getElementById('tool-list').innerHTML = tools.map(t =>
            `<div class="tool-row">
                <span class="tool-name-display">${escapeHtml(t.name)}</span>
                <span class="tool-badge">${cats[t.category] || ''}${t.requires_approval ? ' 🔒' : ''}</span>
                <div class="tool-desc">${escapeHtml(t.description)}</div>
            </div>`
        ).join('');
    } catch (e) { /* ignore */ }
}

function updateAgentDot(agentId, status) {
    const dot = document.getElementById(`ard-${agentId}`);
    if (dot) dot.className = `agent-dot${status === 'running' ? ' running' : ''}`;
}

// ── Status Bar ─────────────────────────────────────────────────────
function setStatus(text, busy) {
    document.getElementById('status-text').textContent = text;
    document.getElementById('status-dot').className = busy ? 'status-dot busy' : 'status-dot';
}

async function refreshStatus() {
    try {
        const s = await api('get_llm_status');
        document.getElementById('model-status').textContent = s.active_model ? `LLM: ${s.active_model}` : 'No LLM configured';
    } catch (e) { /* ignore */ }
    try {
        const info = await api('get_system_info');
        document.getElementById('agent-count').textContent = `${info.agents} agents | ${info.tools} tools`;
    } catch (e) { /* ignore */ }
}

// ── Utilities ──────────────────────────────────────────────────────
function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}

function removeWelcome() {
    const w = document.getElementById('welcome');
    if (w) w.remove();
}

function scrollToBottom() {
    const area = document.getElementById('chat-area');
    area.scrollTop = area.scrollHeight;
}

// ── Event Listeners ────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('user-input');
    input.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 120) + 'px';
    });

    input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submitTask(this.value);
        }
    });

    document.getElementById('send-btn').addEventListener('click', () => {
        submitTask(input.value);
    });

    document.getElementById('stop-btn').addEventListener('click', stopTask);

    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.addEventListener('click', () => setMode(btn.dataset.mode));
    });

    document.getElementById('settings-btn').addEventListener('click', openSettings);
    document.getElementById('settings-close').addEventListener('click', closeSettings);
    document.querySelector('.modal-backdrop')?.addEventListener('click', closeSettings);

    document.querySelectorAll('.modal-tab').forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    setTimeout(() => {
        loadModels();
        loadAgents();
        loadTools();
        refreshStatus();
        setStatus('Ready', false);
    }, 300);
});
