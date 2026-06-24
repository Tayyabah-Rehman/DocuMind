/* ── DocuMind — frontend JS ─────────────────────────────── */

'use strict';

// ── DOM refs ──────────────────────────────────────────────────
const messages      = document.getElementById('messages');
const questionInput = document.getElementById('questionInput');
const sendBtn       = document.getElementById('sendBtn');
const docList       = document.getElementById('docList');
const clearBtn      = document.getElementById('clearBtn');
const dropZone      = document.getElementById('dropZone');
const uploadStatus  = document.getElementById('uploadStatus');

// ── State ─────────────────────────────────────────────────────
let isBusy = false;

// ── Init ──────────────────────────────────────────────────────
(async function init() {
  await refreshDocList();
})();

// ── Key handler ───────────────────────────────────────────────
function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendQuestion();
  }
}

// ── Auto-resize textarea ──────────────────────────────────────
function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 140) + 'px';
}

// ── Drag-and-drop ─────────────────────────────────────────────
function handleDrop(e) {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) uploadFile(file);
}

// ── Upload ────────────────────────────────────────────────────
async function uploadFile(file) {
  if (!file) return;

  showStatus('loading', `⏳ Uploading "${file.name}"…`);

  const fd = new FormData();
  fd.append('file', file);

  try {
    const res  = await fetch('/api/upload', { method: 'POST', body: fd });
    const data = await res.json();

    if (!res.ok) {
      showStatus('error', `❌ ${data.error || 'Upload failed.'}`);
      return;
    }

    showStatus('success', `✅ ${data.message} (${data.chunks} chunks)`);
    await refreshDocList();

    // Reset file input so the same file can be re-selected
    document.getElementById('fileInput').value = '';
  } catch (err) {
    showStatus('error', `❌ Network error: ${err.message}`);
  }
}

function showStatus(type, text) {
  uploadStatus.className = `upload-status ${type}`;
  uploadStatus.textContent = text;
  if (type === 'success') {
    setTimeout(() => { uploadStatus.className = 'upload-status hidden'; }, 4000);
  }
}

// ── Refresh document list ─────────────────────────────────────
async function refreshDocList() {
  try {
    const res  = await fetch('/api/docs');
    const data = await res.json();
    renderDocList(data.docs || []);
  } catch (_) { /* silently ignore */ }
}

function renderDocList(docs) {
  if (!docs.length) {
    docList.innerHTML = '<li class="doc-empty">No documents yet</li>';
    clearBtn.style.display = 'none';
    return;
  }

  clearBtn.style.display = '';
  docList.innerHTML = docs.map(d => `
    <li class="doc-item">
      <span class="doc-name">📄 ${escHtml(d.name)}</span>
      <span class="doc-meta">
        <span class="doc-badge">${d.chunks} chunks</span>
        &nbsp;${formatDate(d.uploaded_at)}
      </span>
    </li>
  `).join('');
}

// ── Clear docs ────────────────────────────────────────────────
async function clearDocs() {
  if (!confirm('Remove all documents from this session?')) return;
  await fetch('/api/clear', { method: 'POST' });
  await refreshDocList();
  appendMessage('assistant', '🗑 Documents cleared. Upload a new document to get started.');
}

// ── Send question ─────────────────────────────────────────────
async function sendQuestion() {
  const q = questionInput.value.trim();
  if (!q || isBusy) return;

  isBusy = true;
  sendBtn.disabled = true;
  questionInput.value = '';
  questionInput.style.height = 'auto';

  appendMessage('user', q);
  const typingId = appendTyping();

  try {
    const res  = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q }),
    });
    const data = await res.json();

    removeTyping(typingId);

    if (!res.ok) {
      appendMessage('assistant', `❌ ${data.error || 'Something went wrong.'}`);
    } else {
      appendAnswer(data.answer, data.sources || [], data.tokens_used);
    }
  } catch (err) {
    removeTyping(typingId);
    appendMessage('assistant', `❌ Network error: ${err.message}`);
  } finally {
    isBusy = false;
    sendBtn.disabled = false;
    questionInput.focus();
  }
}

// ── DOM helpers ───────────────────────────────────────────────
function appendMessage(role, html) {
  const row = document.createElement('div');
  row.className = `msg-row ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = role === 'user' ? '🧑' : '🤖';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.innerHTML = escHtml(html).replace(/\n/g, '<br>');

  row.appendChild(avatar);
  row.appendChild(bubble);
  messages.appendChild(row);
  scrollBottom();
  return row;
}

function appendAnswer(answerText, sources, tokensUsed) {
  const row = document.createElement('div');
  row.className = 'msg-row assistant';

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = '🤖';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.innerHTML = escHtml(answerText).replace(/\n/g, '<br>');

  if (sources.length) {
    const bar = document.createElement('div');
    bar.className = 'sources-bar';
    bar.innerHTML = '📎 ' + sources.map(s =>
      `<span class="src-chip">${escHtml(s)}</span>`
    ).join(' ');
    if (tokensUsed) {
      const tok = document.createElement('span');
      tok.style.cssText = 'margin-left:auto;font-size:10.5px;';
      tok.textContent = `${tokensUsed} tokens`;
      bar.appendChild(tok);
    }
    bubble.appendChild(bar);
  }

  row.appendChild(avatar);
  row.appendChild(bubble);
  messages.appendChild(row);
  scrollBottom();
}

function appendTyping() {
  const id = 'typing_' + Date.now();
  const row = document.createElement('div');
  row.className = 'msg-row assistant';
  row.id = id;

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = '🤖';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';

  row.appendChild(avatar);
  row.appendChild(bubble);
  messages.appendChild(row);
  scrollBottom();
  return id;
}

function removeTyping(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function scrollBottom() {
  messages.scrollTop = messages.scrollHeight;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatDate(iso) {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch (_) { return ''; }
}
