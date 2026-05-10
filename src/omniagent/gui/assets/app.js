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
    currentAgent: '',
    conversations: [],
    activeConversationId: null,
};

// ── Agent Identity Map ─────────────────────────────────────────────
const AGENT_MAP = {
    'general-agent':      { name: 'General',    emoji: '🤖', color: 'agent-general' },
    'code-gen-agent':     { name: 'CodeGen',    emoji: '💻', color: 'agent-codegen' },
    'code-review-agent':  { name: 'Review',     emoji: '🔍', color: 'agent-review' },
    'doc-writer-agent':   { name: 'DocWriter',  emoji: '📝', color: 'agent-doc' },
    'test-agent':         { name: 'Test',       emoji: '🧪', color: 'agent-test' },
};

function getAgentInfo(agentId) {
    if (!agentId) return { name: 'Agent', emoji: '🎯', color: '' };
    const key = agentId.toLowerCase().replace(/[_\s]+/g, '-');
    return AGENT_MAP[key] || { name: agentId, emoji: '🎯', color: '' };
}

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

    // Tables
    s = s.replace(/^(\|.+\|)\n(\|[-| :]+\|)\n((?:\|.+\|\n?)+)/gm, (_, header, sep, body) => {
        const ths = header.split('|').filter(c => c.trim()).map(c => `<th>${c.trim()}</th>`).join('');
        const rows = body.trim().split('\n').map(row => {
            const tds = row.split('|').filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`).join('');
            return `<tr>${tds}</tr>`;
        }).join('');
        return `<table class="md-table"><thead><tr>${ths}</tr></thead><tbody>${rows}</tbody></table>`;
    });

    // Horizontal rules
    s = s.replace(/^---+$/gm, '<hr class="md-hr">');

    // Blockquotes
    s = s.replace(/^> (.+)$/gm, '<blockquote class="md-blockquote">$1</blockquote>');
    s = s.replace(/(<blockquote class="md-blockquote">.*<\/blockquote>\n?)+/g, '<div class="md-blockquotes">$&</div>');

    // Headings (h1-h3)
    s = s.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    s = s.replace(/^## (.+)$/gm, '<h3>$1</h3>');
    s = s.replace(/^# (.+)$/gm, '<h2>$1</h2>');

    // Inline code
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Bold
    s = s.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Italic
    s = s.replace(/(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');
    // Links
    s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" style="color:var(--ac)">$1</a>');
    // Ordered lists
    s = s.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
    // Unordered lists
    s = s.replace(/^- (.+)$/gm, '<li>$1</li>');
    s = s.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
    // Paragraphs
    s = s.replace(/\n\n/g, '</p><p>');
    s = s.replace(/\n/g, '<br>');

    return `<p>${s}</p>`;
}

function isLongFormMarkdown(text) {
    if (!text || text.length < 200) return false;
    return /^#{1,3} |^\|.*\|.*\|/m.test(text) || text.includes('```') || text.split('\n').length > 8;
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

function addAssistantMessage(text, agentName, emoji, agentId) {
    const container = document.getElementById('messages');
    const info = getAgentInfo(agentId);
    const displayName = agentName || info.name;
    const displayEmoji = emoji || info.emoji;

    // Agent transition divider
    if (agentId && agentId !== state.currentAgent && state.currentAgent !== '') {
        const trans = document.createElement('div');
        trans.className = 'agent-transition';
        trans.innerHTML = `<span class="agent-transition-badge ${info.color}">${displayEmoji} ${escapeHtml(displayName)}</span>`;
        container.appendChild(trans);
    }
    if (agentId) state.currentAgent = agentId;

    const div = document.createElement('div');
    div.className = `message assistant${info.color ? ' ' + info.color : ''}`;
    const longForm = isLongFormMarkdown(text);
    const bubbleClass = longForm ? 'bubble doc-bubble' : 'bubble';
    div.innerHTML = `
        <div class="avatar ${info.color}">${displayEmoji}</div>
        <div class="body" ${longForm ? 'style="max-width:100%;flex:1"' : ''}>
            <div class="source">${escapeHtml(displayName)}</div>
            <div class="${bubbleClass}">${renderMarkdown(text)}</div>
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
    const iconMap = { read: '📖', write: '✏️', edit: '✏️', glob: '📂', grep: '🔍', web_search: '🔍', web_fetch: '🌐', git_status: '📋', git_diff: '📋', git_log: '📋', git_branch: '📋' };
    const icon = iconMap[tool] || '⚙️';
    const preview = typeof args === 'object' ? (args.path || args.query || args.url || args.pattern || '') : '';
    div.innerHTML = `
        <div class="tool-call-header" onclick="this.parentElement.classList.toggle('open')">
            <span class="tool-icon">${icon}</span>
            <span class="tool-name">${escapeHtml(tool)}</span>
            ${preview ? `<span class="tool-preview">${escapeHtml(String(preview).slice(0, 60))}</span>` : ''}
            <span class="tool-status ${isError ? 'error' : 'success'}">${isError ? '✗' : '✓'}</span>
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
                        addAssistantMessage(e.message, (e.source || 'system').toUpperCase(), emoji, e.agent_id || '');
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
    state.currentAgent = '';
    // Auto-save conversation on task complete
    if (state.activeConversationId) {
        saveCurrentConversation().then(() => loadConversations());
    }
}

// ── Task Submission ────────────────────────────────────────────────
async function submitTask(text) {
    if (!text || !text.trim() || state.running) return;
    const input = document.getElementById('user-input');
    input.value = '';
    input.style.height = 'auto';

    // Auto-create conversation if none active
    if (!state.activeConversationId && !text.trim().startsWith('/')) {
        try {
            const r = await api('create_conversation', text.trim().slice(0, 50));
            if (r.status === 'ok') state.activeConversationId = r.id;
        } catch (e) { /* ignore */ }
    }

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
    loadSkills();
    loadAudit();
    loadUsers();
    loadMarketplace();
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

// ── Skills Panel ────────────────────────────────────────────────────
async function loadSkills() {
    try {
        const skills = await api('get_skills');
        const list = document.getElementById('skill-list');
        if (!Array.isArray(skills) || skills.length === 0) {
            list.innerHTML = '<div class="empty-hint">No skills installed. Install from a Git URL above.</div>';
            return;
        }
        list.innerHTML = skills.map(s => `
            <div class="skill-row">
                <div class="skill-header">
                    <span class="skill-name">${escapeHtml(s.name || s.id)}</span>
                    <span class="skill-version">v${escapeHtml(s.version || '?')}</span>
                    <label class="toggle-switch">
                        <input type="checkbox" ${s.enabled !== false ? 'checked' : ''} onchange="toggleSkill('${s.id}', this.checked)">
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                <div class="skill-desc">${escapeHtml(s.description || '')}</div>
                <div class="skill-meta">
                    ${(s.capabilities || []).map(c => `<span class="cap-tag">${escapeHtml(c)}</span>`).join('')}
                    ${(s.tags || []).map(t => `<span class="tag-pill">${escapeHtml(t)}</span>`).join('')}
                </div>
                <div class="skill-actions">
                    <button class="btn-danger-sm" onclick="uninstallSkill('${s.id}')">Uninstall</button>
                </div>
            </div>`).join('');
    } catch (e) {
        document.getElementById('skill-list').innerHTML = `<div class="empty-hint" style="color:var(--er)">${e.message}</div>`;
    }
}

async function installSkill() {
    const input = document.getElementById('skill-git-url');
    const url = input.value.trim();
    if (!url) return;
    try {
        const r = await api('install_skill', url);
        if (r.status === 'ok') {
            input.value = '';
            loadSkills();
        } else {
            alert(r.message || 'Install failed');
        }
    } catch (e) { alert('Install failed: ' + e.message); }
}

async function uninstallSkill(id) {
    if (!confirm(`Uninstall skill "${id}"?`)) return;
    try {
        await api('uninstall_skill', id);
        loadSkills();
    } catch (e) { /* ignore */ }
}

async function toggleSkill(id, enabled) {
    try { await api('toggle_skill', id, enabled); } catch (e) { /* ignore */ }
}

// ── Audit Panel ─────────────────────────────────────────────────────
async function loadAudit() {
    try {
        const stats = await api('get_audit_stats');
        document.getElementById('audit-stats').innerHTML = `
            <span class="stat-item"><strong>${stats.total_entries || 0}</strong> entries</span>
            <span class="stat-item"><strong>${stats.total_errors || 0}</strong> errors</span>
            <span class="stat-item">${((stats.error_rate || 0) * 100).toFixed(1)}% error rate</span>
            ${(stats.top_tools || []).slice(0, 3).map(t =>
                `<span class="stat-item">${escapeHtml(t.tool)}: ${t.count}</span>`
            ).join('')}`;
    } catch (e) { /* ignore */ }

    try {
        const timeFilter = document.getElementById('audit-time-filter').value;
        const toolFilter = document.getElementById('audit-tool-filter').value.trim();
        const errorOnly = document.getElementById('audit-error-filter').checked;
        const now = Date.now() / 1000;
        const filters = {};
        if (timeFilter === 'today') filters.start_time = now - 86400;
        else if (timeFilter === 'week') filters.start_time = now - 604800;
        else if (timeFilter === 'month') filters.start_time = now - 2592000;
        if (toolFilter) filters.tool_name = toolFilter;
        if (errorOnly) filters.is_error = true;

        const entries = await api('query_audit', JSON.stringify(filters));
        const log = document.getElementById('audit-log');
        if (!Array.isArray(entries) || entries.length === 0) {
            log.innerHTML = '<div class="empty-hint">No audit entries found.</div>';
            return;
        }
        log.innerHTML = `<table class="audit-table">
            <thead><tr><th>Time</th><th>Tool</th><th>Agent</th><th>User</th><th>Duration</th><th>Status</th></tr></thead>
            <tbody>${entries.map(e => `
                <tr class="${e.is_error ? 'audit-error' : ''}">
                    <td>${new Date(e.timestamp * 1000).toLocaleString()}</td>
                    <td><code>${escapeHtml(e.tool_name)}</code></td>
                    <td>${escapeHtml(e.agent_id)}</td>
                    <td>${escapeHtml(e.user_id || '-')}</td>
                    <td>${e.duration_ms.toFixed(1)}ms</td>
                    <td>${e.is_error ? '<span class="status-err">Error</span>' : '<span class="status-ok">OK</span>'}</td>
                </tr>`).join('')}</tbody></table>`;
    } catch (e) {
        document.getElementById('audit-log').innerHTML = `<div class="empty-hint" style="color:var(--er)">${e.message}</div>`;
    }
}

async function purgeAudit() {
    const days = prompt('Purge entries older than how many days?', '30');
    if (!days) return;
    const ts = (Date.now() / 1000) - (parseInt(days) * 86400);
    try {
        const r = await api('purge_audit', ts);
        if (r.status === 'ok') {
            alert(`Purged ${r.deleted} entries`);
            loadAudit();
        }
    } catch (e) { alert('Purge failed: ' + e.message); }
}

// ── Users Panel ─────────────────────────────────────────────────────
async function loadUsers() {
    try {
        const users = await api('get_users');
        const list = document.getElementById('user-list');
        if (!Array.isArray(users) || users.length === 0) {
            list.innerHTML = '<div class="empty-hint">No users configured. Click "Add User" to create one.</div>';
            return;
        }
        const roleColors = { admin: 'var(--er)', developer: 'var(--ac)', viewer: 'var(--tx3)' };
        list.innerHTML = users.map(u => `
            <div class="user-row">
                <div class="user-info">
                    <span class="user-name">${escapeHtml(u.display_name || u.username)}</span>
                    <span class="role-badge" style="background:${roleColors[u.role] || 'var(--tx3)'}">${escapeHtml(u.role)}</span>
                    <span class="user-email">${escapeHtml(u.email || '')}</span>
                </div>
                <div class="user-actions">
                    <select class="toolbar-select-sm" onchange="updateUserRole('${u.id}', this.value)">
                        <option value="admin" ${u.role === 'admin' ? 'selected' : ''}>Admin</option>
                        <option value="developer" ${u.role === 'developer' ? 'selected' : ''}>Developer</option>
                        <option value="viewer" ${u.role === 'viewer' ? 'selected' : ''}>Viewer</option>
                    </select>
                    <button class="btn-danger-sm" onclick="deactivateUser('${u.id}')">Deactivate</button>
                </div>
            </div>`).join('');
    } catch (e) {
        document.getElementById('user-list').innerHTML = `<div class="empty-hint" style="color:var(--er)">${e.message}</div>`;
    }
}

function showCreateUser() {
    document.getElementById('create-user-form').classList.remove('hidden');
}

function hideCreateUser() {
    document.getElementById('create-user-form').classList.add('hidden');
}

async function createUser() {
    const username = document.getElementById('cu-username').value.trim();
    const display = document.getElementById('cu-display').value.trim();
    const email = document.getElementById('cu-email').value.trim();
    const role = document.getElementById('cu-role').value;
    if (!username) { alert('Username required'); return; }
    try {
        const r = await api('create_user', username, display || username, email, role);
        if (r.status === 'ok') {
            hideCreateUser();
            document.getElementById('cu-username').value = '';
            document.getElementById('cu-display').value = '';
            document.getElementById('cu-email').value = '';
            loadUsers();
        } else { alert(r.message || 'Create failed'); }
    } catch (e) { alert('Create failed: ' + e.message); }
}

async function updateUserRole(userId, newRole) {
    try { await api('update_user_role', userId, newRole); } catch (e) { /* ignore */ }
}

async function deactivateUser(userId) {
    if (!confirm('Deactivate this user?')) return;
    try {
        await api('deactivate_user', userId);
        loadUsers();
    } catch (e) { /* ignore */ }
}

// ── Marketplace Panel ───────────────────────────────────────────────
async function loadMarketplace() {
    try {
        const query = document.getElementById('mp-query')?.value?.trim() || '';
        const itemType = document.getElementById('mp-type-filter')?.value || '';
        const entries = await api('search_marketplace', query, itemType);
        const list = document.getElementById('marketplace-list');
        if (!Array.isArray(entries) || entries.length === 0) {
            list.innerHTML = '<div class="empty-hint">No marketplace items found.</div>';
            return;
        }
        const statusColors = { active: 'var(--ok)', pending_review: 'var(--wn)', rejected: 'var(--er)' };
        list.innerHTML = entries.map(e => `
            <div class="mp-card">
                <div class="mp-header">
                    <span class="mp-name">${escapeHtml(e.name)}</span>
                    <span class="mp-type-badge">${escapeHtml(e.item_type)}</span>
                    <span class="mp-version">v${escapeHtml(e.version)}</span>
                    <span class="mp-status" style="color:${statusColors[e.status] || 'var(--tx3)'}">${escapeHtml(e.status)}</span>
                </div>
                <div class="mp-desc">${escapeHtml(e.description || '')}</div>
                <div class="mp-meta">
                    <span>by ${escapeHtml(e.author || '?')}</span>
                    <span>${e.install_count} installs</span>
                    ${(e.capabilities || []).map(c => `<span class="cap-tag">${escapeHtml(c)}</span>`).join('')}
                </div>
                ${e.status === 'active' ? `<div class="mp-actions">
                    <button class="btn-secondary-sm" onclick="mpSubmitReview('${e.item_id}', '${e.item_type}')">Submit for Review</button>
                </div>` : ''}
                ${e.status === 'pending_review' ? `<div class="mp-actions">
                    <button class="btn-primary-sm" onclick="mpApprove('${e.item_id}', '${e.item_type}')">Approve</button>
                    <button class="btn-danger-sm" onclick="mpReject('${e.item_id}', '${e.item_type}')">Reject</button>
                </div>` : ''}
            </div>`).join('');
    } catch (e) {
        document.getElementById('marketplace-list').innerHTML = `<div class="empty-hint" style="color:var(--er)">${e.message}</div>`;
    }
}

async function mpSubmitReview(itemId, itemType) {
    try {
        await api('marketplace_submit_review', itemId, itemType, 'user');
        loadMarketplace();
    } catch (e) { /* ignore */ }
}

async function mpApprove(itemId, itemType) {
    try {
        await api('marketplace_approve', itemId, itemType, 'admin');
        loadMarketplace();
    } catch (e) { /* ignore */ }
}

async function mpReject(itemId, itemType) {
    const reason = prompt('Rejection reason:', '');
    if (reason === null) return;
    try {
        await api('marketplace_reject', itemId, itemType, 'admin', reason);
        loadMarketplace();
    } catch (e) { /* ignore */ }
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

// ── Conversations Panel ────────────────────────────────────────────
async function loadConversations() {
    try {
        const convs = await api('get_conversations_list');
        state.conversations = Array.isArray(convs) ? convs : [];
        renderConversationList();
    } catch (e) { /* ignore */ }
}

function renderConversationList() {
    const list = document.getElementById('conversation-list');
    if (!list) return;
    if (state.conversations.length === 0) {
        list.innerHTML = '<div class="empty-hint">No conversations yet.</div>';
        return;
    }
    list.innerHTML = state.conversations.map(c => {
        const active = c.id === state.activeConversationId ? ' active' : '';
        const date = new Date(c.created_at * 1000).toLocaleDateString();
        return `<div class="conv-item${active}" onclick="switchConversation('${c.id}')">
            <div class="conv-title">${escapeHtml(c.title)}</div>
            <div class="conv-date">${date}</div>
            <button class="conv-delete" onclick="event.stopPropagation(); deleteConversation('${c.id}')" title="Delete">&times;</button>
        </div>`;
    }).join('');
}

async function createConversation() {
    try {
        const r = await api('create_conversation', 'New Chat');
        if (r.status === 'ok') {
            state.activeConversationId = r.id;
            document.getElementById('messages').innerHTML = '';
            state.pipelineCreated = false;
            await loadConversations();
            switchPanel('chat');
        }
    } catch (e) { /* ignore */ }
}

async function switchConversation(id) {
    // Save current conversation messages
    await saveCurrentConversation();
    state.activeConversationId = id;
    const conv = state.conversations.find(c => c.id === id);
    if (!conv) return;

    // Restore messages
    const container = document.getElementById('messages');
    container.innerHTML = '';
    state.pipelineCreated = false;
    state.currentAgent = '';

    for (const m of (conv.messages || [])) {
        if (m.role === 'user') {
            addUserMessage(m.content);
        } else if (m.role === 'assistant') {
            addAssistantMessage(m.content, m.agent, m.emoji, m.agent_id);
        }
    }
    renderConversationList();
    switchPanel('chat');
}

async function saveCurrentConversation() {
    if (!state.activeConversationId) return;
    const msgEls = document.querySelectorAll('#messages > .message');
    const messages = [];
    for (const el of msgEls) {
        if (el.classList.contains('user')) {
            const bubble = el.querySelector('.bubble');
            if (bubble) messages.push({ role: 'user', content: bubble.textContent });
        } else if (el.classList.contains('assistant')) {
            const bubble = el.querySelector('.bubble');
            const source = el.querySelector('.source');
            if (bubble) messages.push({
                role: 'assistant',
                content: bubble.textContent,
                agent: source ? source.textContent : '',
            });
        }
    }
    // Auto-title from first user message
    let title = '';
    const firstUser = messages.find(m => m.role === 'user');
    if (firstUser) title = firstUser.content.slice(0, 50);

    try {
        await api('save_conversation', state.activeConversationId, JSON.stringify(messages), title);
    } catch (e) { /* ignore */ }
}

async function deleteConversation(id) {
    try {
        await api('delete_conversation', id);
        if (state.activeConversationId === id) {
            state.activeConversationId = null;
            document.getElementById('messages').innerHTML = '';
        }
        await loadConversations();
    } catch (e) { /* ignore */ }
}

// ── Workspace Panel ────────────────────────────────────────────────
async function loadWorkspace() {
    try {
        const r = await api('list_workspace_files');
        if (r.status !== 'ok') return;
        document.getElementById('workspace-root').textContent = r.root || '';
        const tree = document.getElementById('file-tree');
        tree.innerHTML = renderFileTree(r.files || [], '');
    } catch (e) { /* ignore */ }
}

function renderFileTree(items, prefix) {
    return items.map(item => {
        if (item.is_dir) {
            const children = item.children || [];
            return `<div class="tree-dir">
                <div class="tree-item" onclick="this.parentElement.classList.toggle('open')">
                    <span class="tree-icon">📁</span>
                    <span class="tree-name">${escapeHtml(item.name)}</span>
                </div>
                <div class="tree-children">${renderFileTree(children, prefix + item.name + '/')}</div>
            </div>`;
        }
        const iconMap = { '.py': '🐍', '.js': '📜', '.ts': '📘', '.html': '🌐', '.css': '🎨', '.md': '📝', '.json': '📋', '.toml': '📋', '.yaml': '📋', '.yml': '📋', '.txt': '📄', '.sh': '💻', '.bat': '💻' };
        const icon = iconMap[item.ext] || '📄';
        const path = item.path;
        return `<div class="tree-item tree-file" onclick="openFile('${escapeHtml(path)}')">
            <span class="tree-icon">${icon}</span>
            <span class="tree-name">${escapeHtml(item.name)}</span>
        </div>`;
    }).join('');
}

async function openFile(relPath) {
    try {
        const r = await api('read_file_content', relPath);
        if (r.status !== 'ok') return;
        document.getElementById('file-viewer-name').textContent = relPath;
        document.getElementById('file-viewer-content').textContent = r.content;
        document.getElementById('file-viewer').classList.remove('hidden');
    } catch (e) { /* ignore */ }
}

function closeFileViewer() {
    document.getElementById('file-viewer').classList.add('hidden');
}

function refreshWorkspace() {
    loadWorkspace();
}

// ── Panel Switching ────────────────────────────────────────────────
function switchPanel(panel) {
    // Toggle sidebar active state
    document.querySelectorAll('.sidebar-item').forEach(item => {
        item.classList.toggle('active', item.dataset.panel === panel);
    });
    // Toggle panels
    document.getElementById('conversations-panel').classList.toggle('hidden', panel !== 'conversations');
    document.getElementById('workspace-panel').classList.toggle('hidden', panel !== 'workspace');
    // Chat is always visible (main area)
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

    // Sidebar panel switching
    document.getElementById('conversations-btn').addEventListener('click', () => {
        const panel = document.getElementById('conversations-panel');
        const isHidden = panel.classList.contains('hidden');
        switchPanel(isHidden ? 'conversations' : 'chat');
        if (isHidden) loadConversations();
    });
    document.getElementById('workspace-btn').addEventListener('click', () => {
        const panel = document.getElementById('workspace-panel');
        const isHidden = panel.classList.contains('hidden');
        switchPanel(isHidden ? 'workspace' : 'chat');
        if (isHidden) loadWorkspace();
    });

    document.querySelectorAll('.modal-tab').forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    setTimeout(() => {
        loadModels();
        loadAgents();
        loadTools();
        refreshStatus();
        loadConversations();
        setStatus('Ready', false);
    }, 300);
});
