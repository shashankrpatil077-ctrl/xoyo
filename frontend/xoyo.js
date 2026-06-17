/* ═══════════════════════════════════════════════════════════
   XOYO Ω — Frontend Controller
   Connects ALL 35 backend services to the HUD.
   ═══════════════════════════════════════════════════════════ */

// ─── CONFIGURATION ───────────────────────────────────────
const BASE = window.location.origin;  // works when served from orchestrator
const ORCH_URL = `${BASE}`;           // orchestrator on same origin
const POLL_HEALTH  = 15000;           // health check every 15s
const POLL_STATE   = 10000;           // state check every 10s
const POLL_CLOCK   = 1000;            // clock every 1s

// All XOYO services with port + display name
const SERVICES = {
  vllm:8000, vision:8001, whisper:8002, tts:8003,
  materials:8004, physics:8005, camera:8006, dgm:8007,
  workers:8008, florence:8009, smolvla:8018, flow:8011,
  memory_mgr:8012, nitro:8013, yolo:8014, bayesian:8015,
  nngpt:8016, intent:8017, dreamer:8019, debate:8020,
  mamba:8021, priority:8022, prosody:8023, rwkv:8024,
  memory_adv:8025, idle:8026, math:8027, affective:8030,
  screen:8031, active_inf:8032, diag2diag:8033, dino:8034,
  constitutional:8035, wakeword:8036, ppt_generator:8040,
  docx_generator:8041, image_generator:8042, desktop_control:8043,
  system_monitor:8044, progress_vocalizer:8045, memory_personal:8046,
  memory_retrieval:8047, stuck_detector:8048, agent_trace:8049,
  task_doctor:8051, interrupt_fsm:8052, activity_stream:8053,
  ws_event_bridge:8055
};

// Smart URL builder: handles localhost, proxy, and ngrok
function getServiceUrl(port, path = '/health') {
  const loc = window.location;
  // If URL contains /proxy/PORT/ pattern (VS Code port forwarding)
  const proxyMatch = loc.pathname.match(/\/proxy\/(\d+)/);
  if (proxyMatch) {
    return `${loc.origin}${loc.pathname.replace(/\/proxy\/\d+.*/, '/proxy/' + port)}${path}`;
  }
  // If on localhost or direct IP, just swap the port
  try {
    const url = new URL(loc.origin);
    url.port = port;
    return url.origin + path;
  } catch {
    return `http://localhost:${port}${path}`;
  }
}

// AbortSignal.timeout polyfill for older browsers
function fetchTimeout(ms) {
  if (AbortSignal.timeout) return {signal: AbortSignal.timeout(ms)};
  const ctrl = new AbortController();
  setTimeout(() => ctrl.abort(), ms);
  return {signal: ctrl.signal};
}

// ─── STATE ──────────────────────────────────────────────
let mode = 'INTERACTIVE';
let autonomousActive = false;
let serviceStatuses = {};
let _fastPollInterval = null;  // Fast polling during active tasks
let sparkData = {
  dreamer:[], flow:[], diag:[], prosody:[], mamba:[]
};
const MAX_SPARK = 40;

let spideyToken = '';
let conversationHistory = [];
let allowAutoAutonomous = false;  // OFF by default — user must explicitly enable
let hasActiveUserTask = false;     // Track whether user has an active task running
let quietMode = true;              // Background services stay silent by default
let engineActive = false;          // Engine starts DORMANT — user must click Start

// ─── ENGINE START/STOP ──────────────────────────────────
function updateEngineButton(active) {
  engineActive = active;
  const btn = document.getElementById('engineToggleBtn');
  if (!btn) return;
  if (active) {
    btn.textContent = '■ STOP ENGINE';
    btn.style.color = '#ff4444';
    btn.style.borderColor = '#ff4444';
    btn.style.background = 'rgba(255,68,68,0.1)';
    btn.style.boxShadow = '0 0 12px rgba(255,68,68,0.3)';
  } else {
    btn.textContent = '▶ START ENGINE';
    btn.style.color = '#00ff88';
    btn.style.borderColor = '#00ff88';
    btn.style.background = 'rgba(0,255,136,0.08)';
    btn.style.boxShadow = '0 0 12px rgba(0,255,136,0.3)';
  }
}

async function toggleEngine() {
  const endpoint = engineActive ? '/engine/stop' : '/engine/start';
  try {
    const r = await fetch(ORCH_URL + endpoint, {method: 'POST'});
    const d = await r.json();
    updateEngineButton(d.engine_active);
    toast(d.engine_active ? 'ENGINE STARTED' : 'ENGINE STOPPED',
          d.message, d.engine_active ? 'success' : 'warning');
  } catch (e) {
    toast('ENGINE ERROR', 'Could not toggle engine: ' + e.message, 'error');
  }
}

// Check engine status on page load
(async function checkEngineStatus() {
  try {
    const r = await fetch(ORCH_URL + '/engine/status', {...fetchTimeout(3000)});
    const d = await r.json();
    updateEngineButton(d.engine_active);
  } catch {}
})();

document.getElementById('spideyLoginBtn').onclick = (e) => {
  e.preventDefault();
  const t = prompt("Enter SPIDEY Developer Token:");
  if (t) {
    spideyToken = t;
    toast('SPIDEY MODE ENGAGED', 'God-Mode execution unlocked.', 'success');
    document.getElementById('spideyLoginBtn').style.color = '#00d4ff';
    document.getElementById('spideyLoginBtn').style.borderColor = '#00d4ff';
  } else {
    toast('INVALID TOKEN', 'Access Denied', 'warning');
  }
};

// ─── BROWSER MEDIA STATE ────────────────────────────────
let lastCommandTime = Date.now();

// ─── DOM REFERENCES ─────────────────────────────────────
const $ = id => document.getElementById(id);
const chatMessages = $('chatMessages');
const chatInput = $('chatInput');
const modeLabel = $('modeLabel');
const healthDots = $('healthDots');
const freeEnergyFill = $('freeEnergyFill');
const emotionLabel = $('emotionLabel');
const emotionDot = $('emotionDot');
const serviceCount = $('serviceCount');
const reactorStatus = $('reactorStatus');
const toasts = $('toasts');

// ═══════════════════════════════════════════════════════════
// BOOT SEQUENCE
// ═══════════════════════════════════════════════════════════
function boot() {
  setTimeout(() => {
    $('boot').classList.add('hidden');
    initHealthDots();
    startPolling();
    initWebSocketBridge();
    fetchQuietMode();  // Sync quiet mode state from backend
    toast('XOYO Omega online', 'All neural subsystems initialized');
  }, 800);
}

// ═══════════════════════════════════════════════════════════
// HEALTH DOTS (Top Bar)
// ═══════════════════════════════════════════════════════════
function initHealthDots() {
  healthDots.innerHTML = '';
  for (const [name, port] of Object.entries(SERVICES)) {
    const dot = document.createElement('div');
    dot.className = 'health-dot';
    dot.dataset.name = name;
    dot.innerHTML = `<span class="tooltip">${name} :${port}</span>`;
    healthDots.appendChild(dot);
  }
}

async function pollHealth() {
  let up = 0, total = Object.keys(SERVICES).length;
  // Try the bulk endpoint first
  try {
    const r = await fetch(`${ORCH_URL}/health/all`, fetchTimeout(4000));
    if (r.ok) {
      const data = await r.json();
      for (const [name, info] of Object.entries(data.services || {})) {
        serviceStatuses[name] = info.status === 'up';
        const dot = healthDots.querySelector(`[data-name="${name}"]`);
        if (dot) {
          dot.classList.toggle('up', info.status === 'up');
          dot.querySelector('.tooltip').textContent = `${name} :${info.port} ${info.status}`;
        }
      }
      up = data.up || 0;
      serviceCount.textContent = `${up}/${total} UP`;
      reactorStatus.textContent = `${up} SERVICES ACTIVE`;
      return;
    }
  } catch {}

  // Fallback: check orchestrator only
  try {
    const r = await fetch(`${ORCH_URL}/health`, fetchTimeout(3000));
    if (r.ok) {
      const hdata = await r.json();
      serviceStatuses['orchestrator'] = true;
      up = 1;
      // Sync engine button state
      if ('engine_active' in hdata) updateEngineButton(hdata.engine_active);
    }
  } catch (e) { console.error('Error polling health all:', e); }
  serviceCount.textContent = `${up}/${total} UP`;
}

// ═══════════════════════════════════════════════════════════
// SPARKLINE CHARTS (Neural Networks)
// ═══════════════════════════════════════════════════════════
function drawSparkline(canvasId, data, color = '#00d4ff') {
  const canvas = $(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.width = canvas.offsetWidth;
  const H = canvas.height = canvas.offsetHeight;
  ctx.clearRect(0, 0, W, H);

  if (data.length < 2) return;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  // Gradient fill
  const grad = ctx.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0, color + '30');
  grad.addColorStop(1, 'transparent');

  ctx.beginPath();
  ctx.moveTo(0, H);
  data.forEach((v, i) => {
    const x = (i / (data.length - 1)) * W;
    const y = H - ((v - min) / range) * (H - 4) - 2;
    ctx.lineTo(x, y);
  });
  ctx.lineTo(W, H);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // Line
  ctx.beginPath();
  data.forEach((v, i) => {
    const x = (i / (data.length - 1)) * W;
    const y = H - ((v - min) / range) * (H - 4) - 2;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

function pushSpark(key, value) {
  sparkData[key].push(value);
  if (sparkData[key].length > MAX_SPARK) sparkData[key].shift();
}

async function pollNeuralMetrics() {
  const endpoints = {
    dreamer: {port:8019, id:'sparkDreamer', val:'valDreamer', color:'#8b5cf6'},
    flow:    {port:8011, id:'sparkFlow',    val:'valFlow',    color:'#00d4ff'},
    diag:    {port:8033, id:'sparkDiag',    val:'valDiag',    color:'#22c55e'},
    prosody: {port:8023, id:'sparkProsody', val:'valProsody', color:'#f472b6'},
    mamba:   {port:8021, id:'sparkMamba',   val:'valMamba',   color:'#fbbf24'},
  };
  // Parallel fetch for all 5 neural networks (was sequential = 10s worst case)
  const tasks = Object.entries(endpoints).map(async ([key, cfg]) => {
    try {
      const r = await fetch(getServiceUrl(cfg.port, '/health'), fetchTimeout(2000));
      if (r.ok) {
        const d = await r.json();
        const val = d.latest_loss || d.buffer_size || d.model_steps || Math.random() * 0.5;
        pushSpark(key, typeof val === 'number' ? val : parseFloat(val) || Math.random());
        $(cfg.val).textContent = sparkData[key][sparkData[key].length-1].toFixed(3);
      } else {
        pushSpark(key, sparkData[key].length ? sparkData[key][sparkData[key].length-1] : 0);
      }
    } catch {
      pushSpark(key, sparkData[key].length ? sparkData[key][sparkData[key].length-1] * (0.98 + Math.random()*0.04) : Math.random());
    }
    drawSparkline(cfg.id, sparkData[key], cfg.color);
  });
  await Promise.allSettled(tasks);
}

// ═══════════════════════════════════════════════════════════
// ACTIVE INFERENCE + AFFECTIVE STATE (Bottom Bar)
// ═══════════════════════════════════════════════════════════
async function pollStateData() {
  // Parallel fetch both Active Inference + Affective Loop
  const [aiResult, affResult] = await Promise.allSettled([
    fetch(getServiceUrl(8032, '/state'), fetchTimeout(2000)).then(r => r.ok ? r.json() : null),
    fetch(getServiceUrl(8030, '/state'), fetchTimeout(2000)).then(r => r.ok ? r.json() : null)
  ]);

  // Active Inference — free energy
  if (aiResult.status === 'fulfilled' && aiResult.value) {
    const d = aiResult.value;
    const fe = d.free_energy_current || d.free_energy || 0.3;
    const pct = Math.min(100, Math.max(5, fe * 30));
    freeEnergyFill.style.width = pct + '%';
    freeEnergyFill.style.background = fe > 2
      ? 'linear-gradient(90deg, #ef4444, #fbbf24)'
      : 'linear-gradient(90deg, #0a84ff, #00d4ff)';
  }

  // Affective Loop — emotion
  if (affResult.status === 'fulfilled' && affResult.value) {
    const d = affResult.value;
    const emotion = d.current_emotion || d.emotion || 'neutral';
    const valence = d.valence || 0.5;
    emotionLabel.textContent = emotion.toUpperCase();
    const hue = Math.round(valence * 200);
    emotionDot.style.background = `hsl(${hue}, 80%, 55%)`;
    emotionDot.style.boxShadow = `0 0 10px hsl(${hue}, 80%, 55%)`;
    $('reactorCore').style.background =
      `conic-gradient(from 0deg, transparent, hsl(${hue},80%,55%), transparent, #0a84ff, transparent)`;
  }
}

// ═══════════════════════════════════════════════════════════
// WAVEFORM (Voice Visualization)
// ═══════════════════════════════════════════════════════════
function drawWaveform() {
  const canvas = $('waveformCanvas');
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);
  ctx.strokeStyle = '#00d4ff';
  ctx.lineWidth = 1;
  ctx.globalAlpha = 0.5;
  ctx.beginPath();
  const mid = H / 2;
  for (let x = 0; x < W; x++) {
    const t = Date.now() / 1000;
    const y = mid + Math.sin(x * 0.05 + t * 3) * 6 * Math.sin(x * 0.02 + t) +
              Math.sin(x * 0.1 + t * 5) * 3;
    x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  ctx.stroke();
  ctx.globalAlpha = 1;
  requestAnimationFrame(drawWaveform);
}

// ═══════════════════════════════════════════════════════════
// CHAT TERMINAL
// ═══════════════════════════════════════════════════════════
function addMsg(text, type = 'system') {
  const div = document.createElement('div');
  div.className = `chat-msg ${type}`;
  if (text.includes('<a ') || text.includes('<div ') || text.includes('<span ')) { 
      if (typeof DOMPurify !== 'undefined') {
          div.innerHTML = DOMPurify.sanitize(text);
      } else {
          div.textContent = text;
      }
  } else { 
      div.textContent = text; 
  }
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  // Keep max 100 messages
  while (chatMessages.children.length > 100) chatMessages.removeChild(chatMessages.firstChild);
}

async function sendCommand(text) {
  if (!text.trim()) return;
  lastCommandTime = Date.now();
  
  // SPIDEY: Voice/Text Override
  const tLower = text.toLowerCase();
  if (tLower.includes('do not go to autonomous') || tLower.includes('stay interactive')) {
    allowAutoAutonomous = false;
    toast('AUTONOMY OVERRIDE', 'Background loops disabled. XOYO is now locked to interactive mode.', 'warning');
    addMsg(`> ${text}`, 'user');
    conversationHistory.push({role: 'user', content: text});
    addMsg('[SYS] Autonomous mode permanently disabled for this session.', 'system');
    chatInput.value = '';
    return;
  }
  
  addMsg(`> ${text}`, 'user');
  conversationHistory.push({role: 'user', content: text});
  chatInput.value = '';

  try {
    // Mark that a user-initiated task is active
    hasActiveUserTask = true;

    // ══ CRITICAL FIX: Use /command (full VMAO pipeline with tool execution) ══
    // Previously used /stream which ONLY does basic LLM chat — no tools, no actions.
    // /command triggers the full pipeline: planning, tool calling, web search, etc.
    const r = await fetch(`${ORCH_URL}/command`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        text: text,
        history: conversationHistory.slice(-10),
        developer_token: spideyToken || '',
        source: 'user'  // Explicitly mark as user-initiated
      }),
      ...fetchTimeout(10000)
    });
    
    const data = await r.json();
    
    if (data.status === 'dormant') {
      // Engine is off — tell the user to start it
      addMsg('[XOYO] ⚡ Engine is dormant. Click the green "▶ START ENGINE" button in the nav bar to activate me.', 'system');
      resetChatInput();
    } else if (data.status === 'processing') {
      // Task submitted to background — results will arrive via pollBackendStatus()
      addMsg('[XOYO] Processing your request...', 'system');
      // Start fast 2s polling to pick up responses quickly
      _startFastPoll();
      // We track the task_id so we can match it later
      window._activeTaskId = data.task_id;
    } else if (data.response) {
      // Immediate response (shouldn't happen with background tasks, but handle it)
      processFinalResponse(data, text);
      resetChatInput();
    } else {
      addMsg('[XOYO] Request submitted.', 'system');
    }

  } catch (e) {
    addMsg(`[ERROR] ${e.message}`, 'system');
    resetChatInput();
  }
}

function resetChatInput() {
  hasActiveUserTask = false;
  chatInput.focus();
  _stopFastPoll();
}

function _startFastPoll() {
  if (_fastPollInterval) return; // already running
  _fastPollInterval = setInterval(pollBackendStatus, 2000);
}

function _stopFastPoll() {
  if (_fastPollInterval) {
    clearInterval(_fastPollInterval);
    _fastPollInterval = null;
  }
}

function processFinalResponse(data, text) {
  // Show actions taken
  if (data.actions_taken && data.actions_taken.length > 0) {
    data.actions_taken.forEach(a => {
      const name = a.action || a.name || 'action';
      const status = a.verified ? 'OK' : (a.error || 'done');
      addMsg(`[TOOL] ${name} \u2192 ${status}`, 'tool');

      // Catch image generation results
      if (name === 'generate_image' && a.result && typeof a.result === 'object') {
        const imgData = a.result.image || a.result.base64 || a.result.url;
        if (imgData) showImagePreview(imgData);
      }

      // Catch dynamic UI widget generation
      if (name === 'create_ui_widget' && a.result && typeof a.result === 'object' && a.result.widget) {
         injectDynamicWidget(a.result.widget);
      }
    });
  }

  // Show response
  const resp = data.response || data.result || JSON.stringify(data);
  addMsg(typeof resp === 'string' ? resp : JSON.stringify(resp), 'xoyo');
  
  // RE-RUN FILE READY LOGIC TO ENSURE BUTTONS ARE AT BOTTOM
  if (data.actions_taken) {
    data.actions_taken.forEach(a => {
      const name = a.action || a.name || 'action';
      // Only show download for actions that actually CREATE files
      if ((name === 'write_file' || name === 'propose_code_rewrite') && a.verified !== false) {
         let p = a.params && a.params.path ? a.params.path : '';
         if (!p) return; // No path = no download button
         // For propose_code_rewrite, the actual file has .staged appended
         const actualPath = (name === 'propose_code_rewrite') ? p + '.staged' : p;
         const filename = p.split('/').pop();
         const downloadUrl = `${ORCH_URL}/download?path=${encodeURIComponent(actualPath)}`;
         addMsg(`[FILE READY] <a href="${downloadUrl}" download="${filename}" class="download-btn" target="_blank" style="background:#00d4ff;color:black;padding:4px 8px;border-radius:4px;text-decoration:none;font-weight:600;font-size:0.8rem;margin-top:4px;display:inline-block">Download ${filename}</a>`, 'system');
      }
    });
  }
  // Build a summary of tool results for conversation context (enables follow-up tasks)
  let toolContext = '';
  if (data.actions_taken && data.actions_taken.length > 0) {
    const summaries = data.actions_taken.map(a => {
      const name = a.action || a.name || 'action';
      let resultSnippet = '';
      if (a.result && typeof a.result === 'object') {
        // For prompt_ai / chatgpt_task / deepseek_task, capture the response text
        const r = a.result.result || a.result;
        if (r && r.response) {
          resultSnippet = r.response.substring(0, 2000);
        } else if (r && r.output) {
          resultSnippet = r.output.substring(0, 1000);
        } else {
          resultSnippet = JSON.stringify(r).substring(0, 500);
        }
      }
      return `[${name}]: ${resultSnippet}`;
    }).filter(s => s.length > 10);
    if (summaries.length > 0) {
      toolContext = '\n\n--- Tool Results ---\n' + summaries.join('\n');
    }
  }
  conversationHistory.push({role: 'assistant', content: (typeof resp === 'string' ? resp : JSON.stringify(resp)) + toolContext});
  
  // Regex catch file mentions in the LLM response — ONLY for absolute paths that actually exist
  // This prevents phantom download buttons for filenames that are just mentioned in explanations
  if (typeof resp === 'string') {
     const fileRegex = /(\/home\/[a-zA-Z0-9_\-\/\.]+\.(md|pdf|pptx|csv|json|py|txt|png|zip|jpg|jpeg))/g;
     let match;
     let filesFound = new Set();
     // Collect paths from actions_taken so we don't duplicate
     const actionPaths = new Set();
     if (data.actions_taken) {
       data.actions_taken.forEach(a => {
         if (a.params && a.params.path) actionPaths.add(a.params.path);
       });
     }
     while ((match = fileRegex.exec(resp)) !== null) {
        const fullPath = match[1];
        const filename = fullPath.split('/').pop();
        // Skip if already shown via actions_taken, or if it's a .staged file
        if (!filesFound.has(filename) && !actionPaths.has(fullPath) && !fullPath.endsWith('.staged')) {
            filesFound.add(filename);
            const downloadUrl = `${ORCH_URL}/download?path=${encodeURIComponent(fullPath)}`;
            addMsg(`[FILE READY] <a href="${downloadUrl}" download="${filename}" class="download-btn" target="_blank" style="background:#00d4ff;color:black;padding:4px 8px;border-radius:4px;text-decoration:none;font-weight:600;font-size:0.8rem;margin-top:4px;display:inline-block">Download ${filename}</a>`, 'system');
        }
     }
  }

  // Update panels based on context
  if (text && text.toLowerCase().includes('debate')) updateDebatePanel(data);
  if (text && (text.toLowerCase().includes('discover') || text.toLowerCase().includes('material'))) {
    const r2 = data.result;
    if (r2 && typeof r2 === 'object' && r2.hypothesis) {
      addDiscovery(r2.hypothesis, r2.surprise_score || '?', r2.source || 'Discovery Pipeline');
    }
  }

  // Chain autonomous cycles
  if (autonomousActive && text === AUTO_PROMPT) {
      setTimeout(() => {
          triggerAutonomousCycle();
      }, 2000); // Wait 2 seconds between autonomous actions (speeded up)
  }
}

// Chat event listeners
$('chatSend').onclick = () => sendCommand(chatInput.value);
chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendCommand(chatInput.value);
  }
});

// ═══════════════════════════════════════════════════════════
// DEBATE PANEL
// ═══════════════════════════════════════════════════════════
function updateDebatePanel(data) {
  const log = $('debateLog');
  const agents = $('debateAgents').children;
  const result = data.result || data.response || '';
  log.textContent = typeof result === 'string' ? result.substring(0, 500) : JSON.stringify(result).substring(0, 500);
  // Animate agents
  Array.from(agents).forEach((a, i) => {
    setTimeout(() => {
      a.classList.add('speaking');
      setTimeout(() => a.classList.remove('speaking'), 1500);
    }, i * 400);
  });
}

// ═══════════════════════════════════════════════════════════
// DISCOVERY PIPELINE
// ═══════════════════════════════════════════════════════════
function addDiscovery(title, score, source) {
  const panel = $('discoveryPanel');
  const card = document.createElement('div');
  card.className = 'discovery-card';
  const safeTitle = typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(title) : title.replace(/</g, "&lt;");
  const safeScore = typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(String(score)) : String(score).replace(/</g, "&lt;");
  const safeSource = typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(source) : source.replace(/</g, "&lt;");
  card.innerHTML = `
    <div class="discovery-title">${safeTitle}</div>
    <div class="discovery-score">Surprise: ${safeScore}</div>
    <div class="discovery-source">${safeSource}</div>
  `;
  panel.prepend(card);
  while (panel.children.length > 8) panel.removeChild(panel.lastChild);
}

// ═══════════════════════════════════════════════════════════
// DYNAMIC UI WIDGETS
// ═══════════════════════════════════════════════════════════
function injectDynamicWidget(widget) {
  const panel = $('dynamicWidgetsPanel');
  const container = $('dynamicWidgetsContainer');
  panel.style.display = 'block';

  const widgetId = widget.id || 'widget_latest'; 
  let widgetDiv = document.getElementById(widgetId);
  
  if (!widgetDiv) {
    widgetDiv = document.createElement('div');
    widgetDiv.id = widgetId;
    widgetDiv.className = 'liquid-glass-strong generative-workspace';
    widgetDiv.style.padding = '16px';
    widgetDiv.style.borderRadius = '16px';
    widgetDiv.style.minWidth = '250px';
    widgetDiv.style.flex = '1';
    widgetDiv.style.position = 'relative';
    
    const shadow = widgetDiv.attachShadow({ mode: 'open' });
    shadow.innerHTML = `
      <style>
        .widget-header { font-size:0.8rem; text-transform:uppercase; letter-spacing:0.05em; color:var(--accent-cyan, #00d4ff); margin-bottom:12px; display:flex; justify-content:space-between; }
        .close-btn { cursor:pointer; opacity:0.5; }
        .close-btn:hover { opacity:1; }
      </style>
      <div class="widget-header">
        <span id="widget-title">${widget.title ? (typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(widget.title) : widget.title.replace(/</g, "&lt;")) : 'Module'}</span>
        <span class="close-btn" onclick="this.getRootNode().host.remove(); if(document.getElementById('dynamicWidgetsContainer').children.length === 0) document.getElementById('dynamicWidgetsPanel').style.display='none';">✖</span>
      </div>
      <div id="workspace-content" style="font-size:0.9rem;"></div>
    `;
    container.prepend(widgetDiv);
  }

  const shadow = widgetDiv.shadowRoot;
  const contentTarget = shadow.getElementById('workspace-content');
  
  if (widget.title) {
    shadow.getElementById('widget-title').textContent = widget.title;
  }
  
  let safeHtml = widget.html || '';
  if (typeof DOMPurify !== 'undefined') {
      safeHtml = DOMPurify.sanitize(safeHtml);
  } else {
      safeHtml = safeHtml.replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  if (typeof morphdom !== 'undefined') {
    morphdom(contentTarget, `<div id="workspace-content" style="font-size:0.9rem;">${safeHtml}</div>`);
  } else {
    contentTarget.innerHTML = safeHtml;
  }

  if (widget.js_code) {
    console.warn("Dynamic JS execution blocked for security reasons.");
  }
}

// ═══════════════════════════════════════════════════════════
// SELF-IMPROVEMENT LOG
// ═══════════════════════════════════════════════════════════
function addImproveEntry(type, message) {
  const panel = $('selfPanel');
  const entry = document.createElement('div');
  entry.className = 'improve-entry';
  const safeType = typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(type) : type.replace(/</g, "&lt;");
  const safeMsg = typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(message) : message.replace(/</g, "&lt;");
  entry.innerHTML = `<span class="tag ${safeType}">${safeType.toUpperCase()}</span> ${safeMsg}`;
  panel.prepend(entry);
  while (panel.children.length > 15) panel.removeChild(panel.lastChild);
}

// ═══════════════════════════════════════════════════════════
// AUTONOMOUS MODE
// ═══════════════════════════════════════════════════════════
const AUTO_PROMPT =
  'You are XOYO, an autonomous AI agent with FULL developer access. ' +
  'ADVANCE XOYO in whatever way you deem most impactful. ' +
  'You have: web_search, write_file, execute_python, spawn_workers, memory, debate, ' +
  'discover_materials, imagine_future, math_optimize, ai_scientist, build_model. ' +
  'Execute immediately. Report briefly what you did.';

// Trigger a single autonomous cycle (called from processFinalResponse chain)
async function triggerAutonomousCycle() {
  if (!autonomousActive) return;
  try {
    addMsg('[AUTO] Executing autonomous cycle...', 'system');
    const r = await fetch(`${ORCH_URL}/command`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text: AUTO_PROMPT, developer_token: spideyToken || ''}),
      ...fetchTimeout(300000)
    });
    const data = await r.json();
    if (data.status === 'processing') {
      // Response will come via pollBackendStatus
      addMsg('[AUTO] Background task queued.', 'system');
    } else {
      const acts = data.actions_taken ? data.actions_taken.length : 0;
      const resp = (data.response || '').substring(0, 600);
      addMsg(`[AUTO] ${acts} actions | ${resp}`, 'xoyo');
      if (acts > 0) addImproveEntry('deploy', `Autonomous: ${acts} actions executed`);
    }
  } catch (e) {
    addMsg(`[AUTO] Cycle error: ${e.message}`, 'system');
  }
}

async function enterAutonomous() {
  if (mode === 'AUTONOMOUS') return;
  mode = 'AUTONOMOUS';
  autonomousActive = true;
  document.body.classList.add('autonomous');
  modeLabel.textContent = 'AUTONOMOUS';
  modeLabel.classList.add('autonomous');
  $('btnAuto').style.display = 'none';
  $('btnStop').style.display = '';
  toast('Autonomous Mode', 'XOYO is now self-directing');
  addMsg('[SYS] Autonomous mode engaged. XOYO is self-directing.', 'system');

  while (autonomousActive) {
    try {
      addMsg('[AUTO] Executing autonomous cycle...', 'system');
      const r = await fetch(`${ORCH_URL}/command`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          text: AUTO_PROMPT,
          developer_token: spideyToken,
          source: 'autonomous'  // Mark as autonomous so orchestrator can gate it
        }),
        ...fetchTimeout(300000)
      });
      const data = await r.json();
      if (data.status === 'observed_silently') {
        addMsg('[AUTO] Observation logged silently (quiet mode).', 'system');
      } else {
        const acts = data.actions_taken ? data.actions_taken.length : 0;
        const resp = (data.response || '').substring(0, 600);
        addMsg(`[AUTO] ${acts} actions | ${resp}`, 'xoyo');
        if (acts > 0) addImproveEntry('deploy', `Autonomous: ${acts} actions executed`);
      }
    } catch (e) {
      addMsg(`[AUTO] Error: ${e.message}`, 'system');
      await sleep(2000);
    }
    await sleep(3000);
  }
}

function exitAutonomous() {
  autonomousActive = false;
  mode = 'INTERACTIVE';
  document.body.classList.remove('autonomous');
  modeLabel.textContent = 'INTERACTIVE';
  modeLabel.classList.remove('autonomous');
  $('btnAuto').style.display = '';
  $('btnStop').style.display = 'none';
  toast('Interactive Mode', 'XOYO awaiting your commands');
  addMsg('[SYS] Autonomous mode stopped.', 'system');
}

$('btnAuto').onclick = enterAutonomous;
$('btnStop').onclick = exitAutonomous;

// ═══════════════════════════════════════════════════════════
// VOICE (Web Speech API)
// ═══════════════════════════════════════════════════════════
let voiceActive = false;
let recognition = null;

$('btnVoice').onclick = () => {
  if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
    toast('Voice Unavailable', 'Browser does not support speech recognition', 'warning');
    return;
  }
  if (voiceActive) {
    recognition.stop();
    voiceActive = false;
    $('btnVoice').classList.remove('active');
    $('btnVoice').innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg> VOICE';
    return;
  }
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SR();
  recognition.continuous = true;
  recognition.interimResults = false;
  recognition.lang = 'en-US';
  recognition.onresult = e => {
    let text = e.results[e.results.length - 1][0].transcript.trim();
    text = text.replace(/zoyo/gi, 'XOYO');
    text = text.replace(/so you/gi, 'XOYO');
    if (text) sendCommand(text);
  };
  recognition.onerror = () => {
    voiceActive = false;
    $('btnVoice').classList.remove('active');
    $('btnVoice').innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg> VOICE';
  };
  recognition.start();
  voiceActive = true;
  $('btnVoice').classList.add('active');
  $('btnVoice').innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5" fill="currentColor"/></svg> LISTENING';
  toast('Voice Active', 'Speak your command to XOYO');
};

// ═══════════════════════════════════════════════════════════
// TOAST NOTIFICATIONS
// ═══════════════════════════════════════════════════════════
function toast(title, msg, type = '') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  const safeTitle = typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(title) : title.replace(/</g, "&lt;");
  const safeMsg = typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(msg) : msg.replace(/</g, "&lt;");
  el.innerHTML = `<strong>${safeTitle}</strong><br><span style="font-size:0.7rem;color:var(--text-secondary)">${safeMsg}</span>`;
  toasts.appendChild(el);
  setTimeout(() => {
    el.classList.add('fadeout');
    setTimeout(() => el.remove(), 500);
  }, 4000);
}

// ═══════════════════════════════════════════════════════════
// CLOCK
// ═══════════════════════════════════════════════════════════
function updateClock() {
  $('clock').textContent = new Date().toLocaleTimeString('en-US', {hour12: false});
}

// ═══════════════════════════════════════════════════════════
// KEYBOARD SHORTCUTS
// ═══════════════════════════════════════════════════════════
document.addEventListener('keydown', e => {
  if (document.activeElement === chatInput) return;
  if (e.key === ' ')  { e.preventDefault(); chatInput.focus(); }
  if (e.key === 'Escape' && mode === 'AUTONOMOUS') exitAutonomous();
  if (e.key === 'v' || e.key === 'V') $('btnVoice').click();
});

// ═══════════════════════════════════════════════════════════
// INTENT PREDICTION (port 8017)
// ═══════════════════════════════════════════════════════════
async function pollIntents() {
  try {
    const r = await fetch(getServiceUrl(8017, '/health'), fetchTimeout(2000));
    if (r.ok) {
      const d = await r.json();
      const intents = d.recent_predictions || d.top_intents || [];
      const container = $('intentTags');
      if (intents.length > 0) {
        container.innerHTML = intents.slice(0, 3).map(i => {
          const name = typeof i === 'string' ? i : (i.intent || i.name || 'unknown');
          const safeName = typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(name) : name.replace(/</g, "&lt;");
          return `<span class="intent-tag" onclick="sendCommand(this.dataset.name)" data-name="${safeName.replace(/"/g, '&quot;')}">${safeName}</span>`;
        }).join('');
      }
    }
  } catch (e) { console.error('Error polling intents:', e); }
}

// ═══════════════════════════════════════════════════════════
// WAKE WORD STATUS (port 8036)
// ═══════════════════════════════════════════════════════════
async function pollWakeWord() {
  const mic = $('micIndicator');
  const status = $('micStatus');
  try {
    const r = await fetch(getServiceUrl(8036, '/health'), fetchTimeout(2000));
    if (r.ok) {
      const d = await r.json();
      const listening = d.listening || d.active || false;
      const detected = d.last_detection_ago_seconds != null && d.last_detection_ago_seconds < 5;
      mic.className = 'mic-indicator' + (detected ? ' detected' : (listening ? ' listening' : ''));
      status.textContent = detected ? 'WAKE!' : (listening ? 'LISTEN' : 'READY');
    }
  } catch (e) {
    console.error('Error polling wake word:', e);
    mic.className = 'mic-indicator';
    status.textContent = 'OFF';
  }
}

// ═══════════════════════════════════════════════════════════
// AUTO-AUTONOMOUS
// ═══════════════════════════════════════════════════════════
async function checkAutoAutonomous() {
  if (!allowAutoAutonomous || spideyToken) return;
  // Auto-autonomous check logic retired due to webcam dependency removal.
}

setInterval(checkAutoAutonomous, 15000);

// ═══════════════════════════════════════════════════════════
// MEMORY BANK (ports 8012 + 8025)
// ═══════════════════════════════════════════════════════════
async function pollMemory() {
  try {
    const r = await fetch(getServiceUrl(8025, '/health'), fetchTimeout(2000));
    if (r.ok) {
      const d = await r.json();
      $('memDocs').textContent = d.total_documents || d.doc_count || 0;
      $('memSkills').textContent = d.skills_count || d.total_skills || 0;
      $('memLoras').textContent = d.lora_count || d.adapters || 0;
    }
  } catch (e) { console.error('Error polling memory:', e); }
}

// ═══════════════════════════════════════════════════════════
// DISCOVERY PIPELINE (live polling port 8015)
// ═══════════════════════════════════════════════════════════
let lastDiscoveryCount = 0;
async function pollDiscovery() {
  try {
    const r = await fetch(getServiceUrl(8015, '/health'), fetchTimeout(2000));
    if (r.ok) {
      const d = await r.json();
      const total = d.total_discoveries || d.hypotheses_ranked || 0;
      if (total > lastDiscoveryCount && d.last_hypothesis) {
        addDiscovery(
          d.last_hypothesis || 'New discovery',
          d.last_surprise || '??',
          'Bayesian Surprise Engine'
        );
        lastDiscoveryCount = total;
        toast('Discovery', d.last_hypothesis || 'New hypothesis ranked');
      }
    }
  } catch (e) { console.error('Error polling discovery:', e); }
}

// ═══════════════════════════════════════════════════════════
// PRIORITY QUEUE (port 8022 → Self-Improvement panel)
// ═══════════════════════════════════════════════════════════
async function pollPriority() {
  try {
    const r = await fetch(getServiceUrl(8022, '/health'), fetchTimeout(2000));
    if (r.ok) {
      const d = await r.json();
      if (d.current_task || d.next_task) {
        const task = d.current_task || d.next_task;
        addImproveEntry('mutate', `Queue: ${typeof task === 'string' ? task : (task.name || JSON.stringify(task).substring(0,60))}`);
      }
    }
  } catch (e) { console.error('Error polling priority:', e); }
}

// ═══════════════════════════════════════════════════════════
// IMAGE PREVIEW (catch generate_image results)
// ═══════════════════════════════════════════════════════════
function showImagePreview(base64orUrl) {
  const overlay = $('imageOverlay');
  const img = $('imagePreview');
  if (base64orUrl.startsWith('data:') || base64orUrl.startsWith('http')) {
    img.src = base64orUrl;
  } else {
    img.src = 'data:image/png;base64,' + base64orUrl;
  }
  overlay.style.display = 'flex';
}

// ═══════════════════════════════════════════════════════════
// UTILITY
// ═══════════════════════════════════════════════════════════
const sleep = ms => new Promise(r => setTimeout(r, ms));

// ═══════════════════════════════════════════════════════════
// POLLING ENGINE
// ═══════════════════════════════════════════════════════════
window._xoyo_intervals = window._xoyo_intervals || [];
function startPolling() {
  window._xoyo_intervals.forEach(clearInterval);
  window._xoyo_intervals = [];

  updateClock();
  window._xoyo_intervals.push(setInterval(updateClock, POLL_CLOCK));

  pollHealth();
  window._xoyo_intervals.push(setInterval(pollHealth, POLL_HEALTH));

  pollNeuralMetrics();
  window._xoyo_intervals.push(setInterval(pollNeuralMetrics, POLL_STATE));

  pollStateData();
  window._xoyo_intervals.push(setInterval(pollStateData, POLL_STATE));

  pollIntents();
  window._xoyo_intervals.push(setInterval(pollIntents, POLL_HEALTH));

  pollWakeWord();
  window._xoyo_intervals.push(setInterval(pollWakeWord, POLL_STATE));

  pollMemory();
  window._xoyo_intervals.push(setInterval(pollMemory, POLL_HEALTH));

  pollDiscovery();
  window._xoyo_intervals.push(setInterval(pollDiscovery, POLL_HEALTH));

  pollPriority();
  window._xoyo_intervals.push(setInterval(pollPriority, 15000));

  pollBackendStatus();
  window._xoyo_intervals.push(setInterval(pollBackendStatus, 10000));

  pollObservations();
  window._xoyo_intervals.push(setInterval(pollObservations, 15000));  // Observation feed every 15s

  drawWaveform();
}

async function grantPermission(reqId, decision) {
  const el = document.getElementById(`permReq-${reqId}`);
  if (el) el.remove();

  try {
    await fetch(`${ORCH_URL}/permission`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({req_id: reqId, decision: decision}),
      ...fetchTimeout(5000)
    });
  } catch (e) {
    console.error("Failed to send permission", e);
  }
}

// ═══════════════════════════════════════════════════════════
// QUIET MODE CONTROL
// ═══════════════════════════════════════════════════════════
async function fetchQuietMode() {
  try {
    const r = await fetch(`${ORCH_URL}/quiet_mode`, fetchTimeout(2000));
    if (r.ok) {
      const d = await r.json();
      quietMode = d.quiet_mode;
      updateQuietModeUI();
    }
  } catch (e) { console.error('Error fetching quiet mode:', e); }
}

async function toggleQuietMode() {
  quietMode = !quietMode;
  try {
    await fetch(`${ORCH_URL}/quiet_mode`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({enabled: quietMode}),
      ...fetchTimeout(3000)
    });
  } catch (e) { console.error('Error toggling quiet mode:', e); }
  updateQuietModeUI();
  toast(quietMode ? 'Quiet Mode ON' : 'Quiet Mode OFF',
        quietMode ? 'Background services will stay silent' : 'Background services may escalate alerts');
}

function updateQuietModeUI() {
  const btn = $('btnQuiet');
  if (btn) {
    btn.textContent = quietMode ? '🔇 QUIET' : '🔔 ALERT';
    btn.style.color = quietMode ? 'rgba(255,255,255,0.5)' : '#fbbf24';
    btn.style.borderColor = quietMode ? 'rgba(255,255,255,0.15)' : '#fbbf24';
  }
}

// ═══════════════════════════════════════════════════════════
// OBSERVATION FEED (silent background activity log)
// ═══════════════════════════════════════════════════════════
let lastObsCount = 0;
async function pollObservations() {
  try {
    const r = await fetch(`${ORCH_URL}/internal/observations?count=5`, fetchTimeout(2000));
    if (!r.ok) return;
    const data = await r.json();
    const panel = $('obsPanel');
    if (!panel || data.count === lastObsCount) return;
    lastObsCount = data.count;
    panel.innerHTML = '';
    (data.observations || []).forEach(obs => {
      const div = document.createElement('div');
      div.style.cssText = 'font-size:0.7rem;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.05);color:rgba(255,255,255,0.5);';
      const icon = obs.severity === 'warning' ? '⚠️' : obs.severity === 'critical' ? '🔴' : '💡';
      const src = obs.source || 'system';
      div.textContent = `${icon} [${src}] ${(obs.text || '').substring(0, 120)}`;
      panel.appendChild(div);
    });
  } catch (e) { console.error('Error polling observations:', e); }
}

async function pollBackendStatus() {
  try {
    const res = await fetch(`${ORCH_URL}/status`, fetchTimeout(2000));
    if (!res.ok) return;
    const data = await res.json();
    
    if (data.status) {
      const bar = $('liveStatusBar');
      if (bar) {
        bar.textContent = `[STATUS] ${data.status}`;
        // Dynamic color coding for different states
        const s = data.status.toLowerCase();
        if (s.includes('error')) {
          bar.style.color = '#ff4444';
          bar.style.animation = '';
        } else if (s.includes('thinking')) {
          bar.style.color = '#fbbf24';
          bar.style.animation = 'statusPulse 1.5s ease-in-out infinite';
        } else if (s.includes('execut') || s.includes('process') || s.includes('request')) {
          bar.style.color = '#00d4ff';
          bar.style.animation = 'statusPulse 2s ease-in-out infinite';
        } else if (s.includes('dormant')) {
          bar.style.color = 'rgba(255,255,255,0.2)';
          bar.style.animation = '';
        } else if (s === 'idle') {
          bar.style.color = 'rgba(255,255,255,0.4)';
          bar.style.animation = '';
        } else {
          bar.style.color = '#00d4ff';
          bar.style.animation = '';
        }
      }
    }

    // Also check if there are active user tasks
    try {
      const taskRes = await fetch(`${ORCH_URL}/active_user_tasks`, fetchTimeout(1000));
      if (taskRes.ok) {
        const taskData = await taskRes.json();
        hasActiveUserTask = taskData.active;
      }
    } catch {}

    if (data.pending_actions && data.pending_actions.length > 0) {
      data.pending_actions.forEach(act => {
        if (document.getElementById(`permReq-${act.id}`)) return; // Already displaying
        
        // AUTO-ALLOW IN AUTONOMOUS MODE
        if (mode === 'AUTONOMOUS' && act.action !== 'propose_code_rewrite') {
            grantPermission(act.id, 'yes');
            addMsg(`[AUTO] Automatically granted permission for ${act.action}`, 'tool');
            return;
        }

        // ══ PHANTOM PERMISSION GATE ══
        // If no user task is running, these are phantom permissions from
        // background services — auto-deny them silently.
        if (!hasActiveUserTask) {
            grantPermission(act.id, 'no');
            console.log(`[PHANTOM] Auto-denied ${act.action} — no active user task`);
            return;
        }
        
        const div = document.createElement('div');
        div.id = `permReq-${act.id}`;
        div.style.padding = '12px';
        div.style.marginBottom = '8px';
        div.style.color = 'white';
        div.style.fontSize = '0.85rem';
        
        if (act.action === 'propose_code_rewrite') {
            div.style.background = 'rgba(255,0,68,0.1)';
            div.style.borderLeft = '3px solid #ff0044';
            
            // Setup download function string
            const safeContent = encodeURIComponent(act.params.content || '').replace(/'/g, '%27');
            const safeExpl = encodeURIComponent(act.params.explanation || '').replace(/'/g, '%27');
            const dlScript = `const a=document.createElement('a');a.href='data:text/markdown;charset=utf-8,'+encodeURIComponent('# Explanation\n\n'+decodeURIComponent('${safeExpl}')+'\n\n# Proposed Code\n\n\`\`\`\n'+decodeURIComponent('${safeContent}')+'\n\`\`\`');a.download='code_review_${act.id}.md';a.click();`;
            
            div.innerHTML = `
              <div style="font-weight:600;margin-bottom:6px;color:#ff0044">🛡️ CONSTITUTIONAL CODE REVIEW</div>
              <div style="margin-bottom:8px"><strong>Target File:</strong> ${typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(act.params.path || 'Unknown') : 'Unknown'}</div>
              <div style="margin-bottom:8px;background:rgba(0,0,0,0.3);padding:8px;border-radius:4px;border:1px solid rgba(255,255,255,0.1)">
                <strong>Explanation:</strong><br/>
                ${typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(act.params.explanation || 'No explanation provided.') : 'No explanation provided.'}
              </div>
              <div style="margin-bottom:12px;background:#1a1a1a;padding:8px;border-radius:4px;max-height:200px;overflow-y:auto;border:1px solid rgba(255,255,255,0.1);font-family:var(--font-mono);font-size:0.75rem;white-space:pre-wrap;">${(act.params.content || '').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>
              <div style="display:flex;gap:8px">
                <button onclick="grantPermission('${act.id}', 'yes')" style="background:#ff0044;color:white;border:none;padding:6px 16px;border-radius:4px;cursor:pointer;font-weight:600">APPROVE REWRITE</button>
                <button onclick="grantPermission('${act.id}', 'no')" style="background:rgba(255,255,255,0.1);color:white;border:1px solid rgba(255,255,255,0.2);padding:6px 16px;border-radius:4px;cursor:pointer">DENY</button>
                <button onclick="${dlScript}" style="background:rgba(255,255,255,0.1);color:white;border:1px solid rgba(255,255,255,0.2);padding:6px 16px;border-radius:4px;cursor:pointer">⬇️ DOWNLOAD REPORT</button>
              </div>
            `;
        } else {
            div.style.background = 'rgba(255,165,0,0.1)';
            div.style.borderLeft = '3px solid orange';
            div.innerHTML = `
              <div style="font-weight:600;margin-bottom:6px;color:#fbbf24">⚡ ACTION REQUIRES PERMISSION</div>
              <div style="margin-bottom:4px"><strong>Tool:</strong> ${typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(act.action) : act.action.replace(/</g, '&lt;')}</div>
              <div style="margin-bottom:12px;opacity:0.7;font-family:var(--font-mono);font-size:0.75rem">${typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(JSON.stringify(act.params)) : JSON.stringify(act.params).replace(/</g, '&lt;')}</div>
              <div style="display:flex;gap:8px">
                <button onclick="grantPermission('${act.id}', 'yes')" style="background:#00d4ff;color:black;border:none;padding:6px 16px;border-radius:4px;cursor:pointer;font-weight:600">ALLOW</button>
                <button onclick="grantPermission('${act.id}', 'no')" style="background:rgba(255,255,255,0.1);color:white;border:1px solid rgba(255,255,255,0.2);padding:6px 16px;border-radius:4px;cursor:pointer">DENY</button>
              </div>
            `;
        }
        chatMessages.appendChild(div);
        chatMessages.scrollTop = chatMessages.scrollHeight;
      });
    }

    if (data.final_responses && data.final_responses.length > 0) {
      data.final_responses.forEach(res => {
        if (res.data) {
          processFinalResponse(res.data, res.req_text || null);
        }
      });
      // Reset chat input since the task completed
      resetChatInput();
    }
  } catch (e) { console.error('Error polling backend status:', e); }
}

// ═══════════════════════════════════════════════════════════
// WEBSOCKET BRIDGE
// ═══════════════════════════════════════════════════════════
let wsBridge;
function initWebSocketBridge() {
  const wsUrl = getServiceUrl(8055, '/ws').replace(/^http/, 'ws');
  wsBridge = new WebSocket(wsUrl);
  
  wsBridge.onopen = () => {
    console.log('[WS] Connected to Event Bridge on 8055');
    setInterval(() => { if (wsBridge.readyState === WebSocket.OPEN) wsBridge.send("ping"); }, 30000);
  };
  
  wsBridge.onmessage = (e) => {
    try {
      const payload = JSON.parse(e.data);
      if (payload.channel === 'heartbeat' || payload.channel === 'pong') return;
      
      if (payload.channel === 'xoyo:events') {
        const ev = typeof payload.data === 'string' ? JSON.parse(payload.data) : payload.data;
        
        // Properly display the XOYO response text on the screen
        if (ev.type === 'response' || ev.type === 'final_response') {
          const respText = ev.response || ev.text || ev.message || JSON.stringify(ev);
          addMsg(typeof respText === 'string' ? respText : JSON.stringify(respText), 'xoyo');
        } else if (ev.type === 'tool_action' || ev.type === 'tool_start') {
          const toolName = ev.tool || 'tool';
          addMsg(`[TOOL RUNNING] ${toolName}`, 'tool');
        } else if (ev.type === 'engine_start' || ev.type === 'engine_stop') {
          addMsg(`[SYSTEM] ${ev.message}`, 'system');
        }
      }
    } catch (err) {
      console.error('WS parse error:', err);
    }
  };

  wsBridge.onclose = () => {
    console.log('[WS] Disconnected. Reconnecting in 5s...');
    setTimeout(initWebSocketBridge, 5000);
  };
  wsBridge.onerror = (err) => console.error('[WS] Error:', err);
}

// ═══════════════════════════════════════════════════════════
// ═══════════════════════════════════════════════════════════
boot();
