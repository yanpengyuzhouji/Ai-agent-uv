/**
 * 张雪峰视角 AI 对话 - 前端逻辑
 * ========================================
 * 功能：
 *   - 多轮对话（通过 session_id）
 *   - SSE 流式输出，逐字显示
 *   - 会话管理（新建、切换、删除）
 *   - 预设问题卡片
 *   - 简易 Markdown 渲染
 */

// 动态获取 API 根地址，避免硬编码 localhost
const API_BASE = window.location.origin;
// ============================================================
// 状态管理
// ============================================================

const state = {
    currentSessionId: localStorage.getItem('currentSessionId') || null,
    sessions: new Map(), // sessionId -> { messages: [], title: '' }
    isStreaming: false,
    serverOnline: false,
    uploadedContext: '', // 保存已上传解析的文本
    attachedFile: null,  // { filename, fileUrl, markdown } 当前会话的附件
};

// ============================================================
// DOM 元素引用
// ============================================================

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const dom = {
    welcomeScreen: $('#welcomeScreen'),
    chatMessages: $('#chatMessages'),
    messageInput: $('#messageInput'),
    sendBtn: $('#sendBtn'),
    newChatBtn: $('#newChatBtn'),
    sessionsList: $('#sessionsList'),
    modelInfo: $('#modelInfo'),
    sidebar: $('#sidebar'),
    menuBtn: $('#menuBtn'),
    filePreview: $('#filePreview'),
    fileUploadInput: $('#fileUploadInput'),
};

// ============================================================
// API 调用
// ============================================================

async function checkServerStatus() {
    try {
        const resp = await fetch(`${API_BASE}/`);
        const data = await resp.json();
        state.serverOnline = true;

        const dot = dom.modelInfo.querySelector('.status-dot');
        dot.classList.add('online');
        dom.modelInfo.querySelector('span').textContent =
            `${data.backend} / ${data.model}`;

        return data;
    } catch {
        state.serverOnline = false;
        dom.modelInfo.querySelector('span').textContent = '服务未连接';
        return null;
    }
}

async function sendMessageStream(message, sessionId) {
    const resp = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            message,
            session_id: sessionId || undefined,
            stream: true,
        }),
    });

    if (!resp.ok) {
        throw new Error(`API 错误: ${resp.status}`);
    }

    return resp.body;
}

async function deleteSessionAPI(sessionId) {
    try {
        await fetch(`${API_BASE}/sessions/${sessionId}`, { method: 'DELETE' });
    } catch {
        // 忽略
    }
}

async function loadSessionsListAPI() {
    try {
        const resp = await fetch(`${API_BASE}/sessions`);
        if (resp.ok) {
            const list = await resp.json();
            list.forEach(s => {
                if (!state.sessions.has(s.session_id)) {
                    state.sessions.set(s.session_id, {
                        messages: [],
                        title: s.last_message || '旧会话'
                    });
                }
            });
        }
    } catch {}
}

async function loadSessionDetailAPI(sessionId) {
    try {
        const resp = await fetch(`${API_BASE}/sessions/${sessionId}`);
        if (resp.ok) {
            const detail = await resp.json();
            const session = state.sessions.get(sessionId) || { title: '会话' };
            session.messages = detail.messages;
            state.sessions.set(sessionId, session);
        }
    } catch {}
}

// ============================================================
// 消息渲染
// ============================================================

function renderMarkdown(text) {
    // 简易 Markdown → HTML
    let html = text
        // 转义 HTML
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        // 加粗 **text**
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        // 行内代码
        .replace(/`(.*?)`/g, '<code>$1</code>')
        // 引用 > text
        .replace(/^&gt;\s*(.+)$/gm, '<blockquote>$1</blockquote>')
        // 无序列表
        .replace(/^[-*]\s+(.+)$/gm, '<li>$1</li>')
        // 段落（双换行）
        .replace(/\n\n/g, '</p><p>')
        // 单换行
        .replace(/\n/g, '<br>');

    // 包裹 li 标签
    html = html.replace(/(<li>.*?<\/li>)/gs, '<ul>$1</ul>');
    // 合并相邻 ul
    html = html.replace(/<\/ul>\s*<ul>/g, '');

    return `<p>${html}</p>`;
}

function createMessageElement(role, content) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    const avatarText = role === 'ai' ? '峰' : '👤';
    div.innerHTML = `
        <div class="message-avatar">${avatarText}</div>
        <div class="message-content">
            <div class="message-bubble">
                ${role === 'ai' ? renderMarkdown(content) : escapeHtml(content)}
            </div>
        </div>
    `;
    return div;
}

// 创建包含原始 HTML 的消息气泡（用来展示带链接的用户消息）
function createMessageElementRaw(role, innerHtml) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    const avatarText = role === 'ai' ? '峰' : '👤';
    div.innerHTML = `
        <div class="message-avatar">${avatarText}</div>
        <div class="message-content">
            <div class="message-bubble">${innerHtml}</div>
        </div>
    `;
    return div;
}

function createTypingIndicator() {
    const div = document.createElement('div');
    div.className = 'message ai';
    div.id = 'typingMessage';
    div.innerHTML = `
        <div class="message-avatar">峰</div>
        <div class="message-content">
            <div class="message-bubble">
                <div class="typing-indicator">
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                </div>
            </div>
        </div>
    `;
    return div;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function scrollToBottom() {
    requestAnimationFrame(() => {
        dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
    });
}

// ============================================================
// 对话逻辑
// ============================================================

async function sendMessage(text) {
    if (!text.trim() && !state.uploadedContext) return;
    if (state.isStreaming) return;

    let message = text.trim();
    let displayHtml = escapeHtml(message) || '';

    // 如果有附带文档：解析内容暗中注入给 AI，但用户看到的只是一个链接徽章
    if (state.uploadedContext && state.attachedFile) {
        message = state.uploadedContext + "【基于以上资料，我要问的是】：\n" + (text.trim() || '请分析此文件');
        const linkHtml = `<a href="${state.attachedFile.fileUrl}" target="_blank" style="color:#4a9eff; text-decoration:none; display:inline-flex; align-items:center; gap:3px; background:rgba(74,158,255,0.1); padding:2px 8px; border-radius:4px; font-size:13px; margin-bottom:4px;">📎 ${escapeHtml(state.attachedFile.filename)}</a>`;
        displayHtml = linkHtml + (text.trim() ? '<br>' + escapeHtml(text.trim()) : '');
        clearUploadedFile(); // 发送后清除输入框旁的附件徽标
    } else if (state.uploadedContext) {
        message = state.uploadedContext + "【基于以上资料，我要问的是】：\n" + (text.trim() || '请分析此文件');
        clearUploadedFile();
    }

    if (!message) return;

    dom.messageInput.value = '';
    autoResizeTextarea();
    updateSendButton();

    // 切到聊天视图
    showChatView();

    // 创建新会话或使用现有会话
    if (!state.currentSessionId) {
        const newId = generateId();
        state.currentSessionId = newId;
        
        dom.chatMessages.innerHTML = '';
        localStorage.setItem('currentSessionId', newId);

        const titleText = text.trim() || (state.attachedFile ? state.attachedFile.filename : '新对话');
        state.sessions.set(newId, {
            messages: [],
            title: titleText.substring(0, 20) + (titleText.length > 20 ? '...' : ''),
            createdAt: Date.now(),
        });
        renderSessionsList();
    }

    const session = state.sessions.get(state.currentSessionId);

    // 添加用户消息（存储完整内容，显示简洁版）
    session.messages.push({ role: 'user', content: message });
    const userMsg = createMessageElementRaw('user', displayHtml);
    dom.chatMessages.appendChild(userMsg);
    scrollToBottom();

    // 显示打字指示器
    const typing = createTypingIndicator();
    dom.chatMessages.appendChild(typing);
    scrollToBottom();

    // 开始流式接收
    state.isStreaming = true;
    updateSendButton();

    let fullResponse = '';

    try {
        const body = await sendMessageStream(message, state.currentSessionId);
        const reader = body.getReader();
        const decoder = new TextDecoder();

        // 替换打字指示器为实际消息
        let aiMsgEl = null;
        let bubbleEl = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;

                try {
                    const data = JSON.parse(line.slice(6));

                    if (data.type === 'session') {
                        // 更新 session_id（服务端可能返回新的）
                        const oldId = state.currentSessionId;
                        if (data.session_id && data.session_id !== oldId) {
                            const sessionData = state.sessions.get(oldId);
                            state.sessions.delete(oldId);
                            state.currentSessionId = data.session_id;
                            state.sessions.set(data.session_id, sessionData);
                            renderSessionsList();
                        }
                    } else if (data.type === 'content') {
                        if (!aiMsgEl) {
                            // 移除打字指示器，创建 AI 消息
                            typing.remove();
                            aiMsgEl = createMessageElement('ai', '');
                            bubbleEl = aiMsgEl.querySelector('.message-bubble');
                            dom.chatMessages.appendChild(aiMsgEl);
                        }

                        fullResponse += data.text;
                        bubbleEl.innerHTML = renderMarkdown(fullResponse);
                        scrollToBottom();
                    } else if (data.type === 'error') {
                        typing.remove();
                        showError(data.message);
                    } else if (data.type === 'done') {
                        // 完成
                    }
                } catch {
                    // 忽略解析错误
                }
            }
        }

        // 如果没收到任何内容
        if (!aiMsgEl) {
            typing.remove();
        }

        // 保存 AI 回复
        if (fullResponse) {
            session.messages.push({ role: 'ai', content: fullResponse });
        }

    } catch (error) {
        typing.remove();
        showError(`连接失败: ${error.message}`);
    }

    state.isStreaming = false;
    updateSendButton();
    scrollToBottom();
}

function showError(msg) {
    const div = document.createElement('div');
    div.className = 'message ai';
    div.innerHTML = `
        <div class="message-avatar">⚠</div>
        <div class="message-content">
            <div class="message-bubble" style="border-color: rgba(255,107,107,0.3); color: #ff6b6b;">
                ${escapeHtml(msg)}
            </div>
        </div>
    `;
    dom.chatMessages.appendChild(div);
    scrollToBottom();
}

// ============================================================
// 视图管理
// ============================================================

function showWelcomeView() {
    dom.welcomeScreen.style.display = 'flex';
    dom.chatMessages.classList.remove('active');
    state.currentSessionId = null;
    localStorage.removeItem('currentSessionId');
    renderSessionsList();
}

function showChatView() {
    dom.welcomeScreen.style.display = 'none';
    dom.chatMessages.classList.add('active');
}

async function loadSession(sessionId) {
    let session = state.sessions.get(sessionId);
    if (!session || (!session.messages || session.messages.length === 0)) {
        await loadSessionDetailAPI(sessionId);
        session = state.sessions.get(sessionId);
    }
    
    if (!session) return;

    state.currentSessionId = sessionId;
    localStorage.setItem('currentSessionId', sessionId);
    showChatView();

    // 渲染历史消息
    dom.chatMessages.innerHTML = '';
    for (const msg of session.messages) {
        const el = createMessageElement(msg.role, msg.content);
        dom.chatMessages.appendChild(el);
    }

    renderSessionsList();
    scrollToBottom();
}

// ============================================================
// 会话管理 UI
// ============================================================

function renderSessionsList() {
    dom.sessionsList.innerHTML = '';

    const sorted = [...state.sessions.entries()]
        .sort((a, b) => (b[1].createdAt || 0) - (a[1].createdAt || 0));

    for (const [id, session] of sorted) {
        const div = document.createElement('div');
        div.className = `session-item${id === state.currentSessionId ? ' active' : ''}`;

        div.innerHTML = `
            <div class="session-icon">💬</div>
            <div class="session-info">
                <div class="session-title">${escapeHtml(session.title || '新对话')}</div>
                <div class="session-meta">${session.messages ? session.messages.length : 0} 条消息</div>
            </div>
            <button class="session-delete delete-btn" title="删除会话">
                <svg class="delete-btn" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="pointer-events: none;">
                    <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
            </button>
        `;

        div.addEventListener('click', (e) => {
            if (!e.target.classList.contains('delete-btn')) {
                loadSession(id);
                if (window.innerWidth <= 768) closeSidebar();
            }
        });

        div.querySelector('.delete-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            state.sessions.delete(id);
            deleteSessionAPI(id);
            if (id === state.currentSessionId) {
                showWelcomeView();
            }
            renderSessionsList();
        });

        dom.sessionsList.appendChild(div);
    }
}

// ============================================================
// 输入处理
// ============================================================

function autoResizeTextarea() {
    const ta = dom.messageInput;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
}

function updateSendButton() {
    const hasText = dom.messageInput.value.trim().length > 0;
    const hasFile = state.uploadedContext.length > 0;
    dom.sendBtn.disabled = (!hasText && !hasFile) || state.isStreaming;
}

// 渲染持久化的附件徽标（始终贴在输入框旁）
function renderFileBadge() {
    if (!state.attachedFile) {
        dom.filePreview.style.display = 'none';
        return;
    }
    const f = state.attachedFile;
    dom.filePreview.style.display = 'flex';
    dom.filePreview.innerHTML = `
        <a href="${f.fileUrl}" target="_blank" style="color:inherit; text-decoration:none; display:flex; align-items:center; gap:4px;">
            📄 <span style="text-decoration:underline;">${f.filename}</span>
        </a>
        <button style="background:none; border:none; color:#888; cursor:pointer; margin-left:6px; font-size:14px;" onclick="clearUploadedFile()">✖</button>
    `;
}

// 暴露全局清除函数
window.clearUploadedFile = function() {
    state.uploadedContext = '';
    state.attachedFile = null;
    dom.filePreview.style.display = 'none';
    updateSendButton();
};

// ============================================================
// 工具函数
// ============================================================

function generateId() {
    return Math.random().toString(36).substring(2, 10);
}

function closeSidebar() {
    dom.sidebar.classList.remove('open');
    const overlay = document.querySelector('.sidebar-overlay');
    if (overlay) overlay.classList.remove('active');
}

// ============================================================
// 初始化
// ============================================================

async function init() {
    // 检查服务器
    checkServerStatus();
    setInterval(checkServerStatus, 15000);

    // 获取远程历史记录
    await loadSessionsListAPI();
    if (state.currentSessionId && state.sessions.has(state.currentSessionId)) {
        await loadSession(state.currentSessionId);
    } else {
        renderSessionsList();
    }

    // 输入框事件
    dom.messageInput.addEventListener('input', () => {
        autoResizeTextarea();
        updateSendButton();
    });

    dom.messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage(dom.messageInput.value);
        }
    });

    // 发送按钮
    dom.sendBtn.addEventListener('click', () => {
        sendMessage(dom.messageInput.value);
    });

    // 新建对话
    dom.newChatBtn.addEventListener('click', () => {
        showWelcomeView();
        closeSidebar();
    });

    // 附件处理逻辑
    dom.fileUploadInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        dom.filePreview.style.display = 'flex';
        dom.filePreview.innerHTML = `<span>⏳ 正在全自动读取解析 ${file.name}...</span>`;
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const res = await fetch(`${API_BASE}/upload`, {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            if (res.ok && data.markdown) {
                state.uploadedContext = `【以下为用户提供的附件资料：${data.filename}】\n---\n` + data.markdown + `\n---\n\n`;
                state.attachedFile = {
                    filename: data.filename,
                    fileUrl: data.file_url || '#',
                    markdown: data.markdown,
                };
                renderFileBadge();
                updateSendButton();
            } else {
                dom.filePreview.innerHTML = `<span>❌ 解析被拒: ${data.detail || '格式暂不支持'}</span> <button style="background:none; border:none; color:inherit; cursor:pointer;" onclick="clearUploadedFile()">✖</button>`;
            }
        } catch(err) {
            dom.filePreview.innerHTML = `<span>❌ 网络故障: ${err.message}</span> <button style="background:none; border:none; color:inherit; cursor:pointer;" onclick="clearUploadedFile()">✖</button>`;
        }
        dom.fileUploadInput.value = '';
    });

    // 预设问题卡片
    $$('.welcome-card').forEach((card) => {
        card.addEventListener('click', () => {
            const question = card.dataset.question;
            if (question) {
                sendMessage(question);
            }
        });
    });

    // 移动端菜单
    dom.menuBtn.addEventListener('click', () => {
        dom.sidebar.classList.toggle('open');
        // 创建遮罩
        let overlay = document.querySelector('.sidebar-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.className = 'sidebar-overlay';
            overlay.addEventListener('click', closeSidebar);
            document.body.appendChild(overlay);
        }
        overlay.classList.toggle('active');
    });

    // 初始化输入框状态
    updateSendButton();
}

// 启动
document.addEventListener('DOMContentLoaded', init);
