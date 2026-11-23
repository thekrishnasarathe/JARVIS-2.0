// STARK INDUSTRIES // J.A.R.V.I.S. 2.0 Web Client

// ─── API Base URL Resolution ──────────────────────────────────────────
const getApiBaseUrl = () => {
  const urlParams = new URLSearchParams(window.location.search);
  const paramApi = urlParams.get('api');
  if (paramApi) {
    localStorage.setItem('JARVIS_API_URL', paramApi);
    return paramApi;
  }
  const storedApi = localStorage.getItem('JARVIS_API_URL');
  if (storedApi) return storedApi;

  if (window.__JARVIS_API_URL__) return window.__JARVIS_API_URL__;

  const loc = window.location;
  if (loc.hostname === 'localhost' || loc.hostname === '127.0.0.1') {
    return 'http://localhost:8000';
  }
  return loc.origin;
};

const API_BASE = getApiBaseUrl().replace(/\/+$/, '');
console.log('[JARVIS] Initialized API Base:', API_BASE);

// ─── State ────────────────────────────────────────────────────────────
let audioEnabled = true;
let isRecognizing = false;

// ─── DOM References ───────────────────────────────────────────────────
const clockEl = document.getElementById('live-clock');
const apiLabelEl = document.getElementById('active-api-url');
const statusIndicatorEl = document.getElementById('system-status-indicator');
const cpuValEl = document.getElementById('cpu-val');
const cpuBarEl = document.getElementById('cpu-bar');
const ramValEl = document.getElementById('ram-val');
const ramBarEl = document.getElementById('ram-bar');
const pluginValEl = document.getElementById('plugin-val');
const memValEl = document.getElementById('mem-val');
const chatFeedEl = document.getElementById('chat-feed');
const thinkingEl = document.getElementById('thinking-indicator');
const commandForm = document.getElementById('command-form');
const commandInput = document.getElementById('command-input');
const audioToggleBtn = document.getElementById('audio-toggle');
const arcReactor = document.getElementById('arc-reactor');
const coreStateLabel = document.getElementById('core-state-label');
const clearLogBtn = document.getElementById('clear-log-btn');
const errorToast = document.getElementById('error-boundary-toast');
const errorMsg = document.getElementById('error-toast-msg');
const dismissErrorBtn = document.getElementById('dismiss-error');

if (apiLabelEl) {
  apiLabelEl.textContent = API_BASE;
}

// ─── Clock Update ─────────────────────────────────────────────────────
function updateClock() {
  const now = new Date();
  clockEl.textContent = now.toTimeString().split(' ')[0];
}
setInterval(updateClock, 1000);
updateClock();

// ─── Error Boundary Toast ─────────────────────────────────────────────
function showError(msg) {
  if (!errorToast) return;
  errorMsg.textContent = msg;
  errorToast.classList.remove('hidden');
  setTimeout(() => {
    errorToast.classList.add('hidden');
  }, 6000);
}

dismissErrorBtn?.addEventListener('click', () => {
  errorToast.classList.add('hidden');
});

// ─── Speech Synthesis ─────────────────────────────────────────────────
function speakResponse(text) {
  if (!audioEnabled || !('speechSynthesis' in window)) return;
  try {
    window.speechSynthesis.cancel();
    // Clean emojis and symbols for speech
    const cleanText = text.replace(/[\u{1F600}-\u{1F6FF}|[\u{2600}-\u{26FF}]/gu, '');
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.rate = 1.05;
    utterance.pitch = 0.95;
    const voices = window.speechSynthesis.getVoices();
    const englishVoice = voices.find(v => v.lang.startsWith('en') && (v.name.includes('David') || v.name.includes('Male') || v.name.includes('Google')));
    if (englishVoice) utterance.voice = englishVoice;
    window.speechSynthesis.speak(utterance);
  } catch (err) {
    console.warn('[Audio] TTS warning:', err);
  }
}

// ─── Audio Toggle ─────────────────────────────────────────────────────
audioToggleBtn?.addEventListener('click', () => {
  audioEnabled = !audioEnabled;
  audioToggleBtn.textContent = audioEnabled ? '🔊 AUDIO ON' : '🔇 AUDIO OFF';
  audioToggleBtn.style.borderColor = audioEnabled ? 'var(--primary-orange)' : 'var(--text-dim)';
  audioToggleBtn.style.color = audioEnabled ? 'var(--primary-orange)' : 'var(--text-dim)';
  if (!audioEnabled && 'speechSynthesis' in window) {
    window.speechSynthesis.cancel();
  }
});

// ─── Append Chat Message ──────────────────────────────────────────────
function appendMessage(sender, text, severity = 'info') {
  const msgEl = document.createElement('div');
  msgEl.className = `chat-message ${sender.toLowerCase()}`;
  
  const timeStr = new Date().toTimeString().split(' ')[0];
  const badgeClass = severity === 'error' ? 'badge-error' : (severity === 'success' ? 'badge-success' : 'badge-info');
  const badgeText = severity.toUpperCase();

  msgEl.innerHTML = `
    <div class="msg-header">
      <span class="msg-author">${sender.toUpperCase()}</span>
      <span class="msg-time">${timeStr}</span>
      <span class="badge ${badgeClass}">${badgeText}</span>
    </div>
    <div class="msg-body">${escapeHtml(text)}</div>
  `;

  chatFeedEl.appendChild(msgEl);
  chatFeedEl.scrollTop = chatFeedEl.scrollHeight;

  if (sender.toLowerCase() === 'jarvis') {
    speakResponse(text);
  }
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ─── Transmit Command ─────────────────────────────────────────────────
async function transmitCommand(query) {
  if (!query || !query.trim()) return;
  const command = query.trim();

  // Add User Message
  appendMessage('USER', command, 'info');
  commandInput.value = '';
  thinkingEl.classList.remove('hidden');
  coreStateLabel.textContent = 'NEURAL PROCESSING';
  coreStateLabel.style.color = 'var(--primary-orange)';

  try {
    const res = await fetch(`${API_BASE}/api/command`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ command }),
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || `Server responded with ${res.status}`);
    }

    const data = await res.json();
    thinkingEl.classList.add('hidden');
    coreStateLabel.textContent = 'CORE READY';
    coreStateLabel.style.color = 'var(--text-dim)';

    appendMessage('JARVIS', data.text, data.severity || 'info');
  } catch (err) {
    console.error('[JARVIS] Command execution error:', err);
    thinkingEl.classList.add('hidden');
    coreStateLabel.textContent = 'COMM ERROR';
    coreStateLabel.style.color = 'var(--deep-red)';

    const fallbackMsg = `Transmission failed: ${err.message}. If running remotely, please ensure the backend is active at ${API_BASE}.`;
    appendMessage('JARVIS', fallbackMsg, 'error');
    showError(err.message);
  }
}

// ─── Form Submission ──────────────────────────────────────────────────
commandForm?.addEventListener('submit', (e) => {
  e.preventDefault();
  transmitCommand(commandInput.value);
});

// ─── Quick Shortcuts ──────────────────────────────────────────────────
document.querySelectorAll('.chip-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    const cmd = btn.getAttribute('data-cmd');
    if (cmd) transmitCommand(cmd);
  });
});

// ─── Clear Log ────────────────────────────────────────────────────────
clearLogBtn?.addEventListener('click', () => {
  chatFeedEl.innerHTML = '';
  appendMessage('JARVIS', 'Tactical log buffer purged. Ready for new input.', 'info');
});

// ─── Arc Reactor Speech Input ─────────────────────────────────────────
if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = 'en-US';

  recognition.onstart = () => {
    isRecognizing = true;
    coreStateLabel.textContent = 'LISTENING...';
    coreStateLabel.style.color = '#00FF66';
    arcReactor.style.transform = 'scale(1.15)';
  };

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    console.log('[STT] Recognized:', transcript);
    commandInput.value = transcript;
    transmitCommand(transcript);
  };

  recognition.onerror = (event) => {
    console.warn('[STT] Speech error:', event.error);
    isRecognizing = false;
    coreStateLabel.textContent = 'CORE READY';
    coreStateLabel.style.color = 'var(--text-dim)';
    arcReactor.style.transform = '';
  };

  recognition.onend = () => {
    isRecognizing = false;
    coreStateLabel.textContent = 'CORE READY';
    coreStateLabel.style.color = 'var(--text-dim)';
    arcReactor.style.transform = '';
  };

  arcReactor?.addEventListener('click', () => {
    if (isRecognizing) {
      recognition.stop();
    } else {
      try {
        recognition.start();
      } catch (e) {
        console.warn(e);
      }
    }
  });
} else {
  arcReactor?.addEventListener('click', () => {
    transmitCommand('system status');
  });
}

// ─── Telemetry Polling ────────────────────────────────────────────────
async function fetchTelemetry() {
  try {
    const res = await fetch(`${API_BASE}/api/status`, { method: 'GET' });
    if (!res.ok) return;
    const data = await res.json();

    if (cpuValEl && data.cpu_percent !== undefined) {
      cpuValEl.textContent = `${Math.round(data.cpu_percent)}%`;
      cpuBarEl.style.width = `${Math.min(100, Math.max(5, data.cpu_percent))}%`;
    }
    if (ramValEl && data.ram_percent !== undefined) {
      ramValEl.textContent = `${Math.round(data.ram_percent)}%`;
      ramBarEl.style.width = `${Math.min(100, Math.max(5, data.ram_percent))}%`;
    }
    if (pluginValEl && data.active_plugins !== undefined) {
      pluginValEl.textContent = `${data.active_plugins} LOADED`;
    }
    if (memValEl && data.memory_stats) {
      memValEl.textContent = `${data.memory_stats.total_memories || 0} NODES`;
    }
    if (statusIndicatorEl) {
      statusIndicatorEl.textContent = 'ONLINE';
      statusIndicatorEl.className = 'pill-value status-online';
    }
  } catch (err) {
    // Graceful fallback for telemetry offline
    if (statusIndicatorEl) {
      statusIndicatorEl.textContent = 'STANDALONE';
      statusIndicatorEl.className = 'pill-value';
    }
  }
}

setInterval(fetchTelemetry, 10000);
fetchTelemetry();
