// JARVIS Electron renderer -- wires the dashboard UI to:
//  - main.js IPC (system stats, weather, uptime counters, transcript export)
//  - the Python/FastAPI backend (chat streaming, session clear, health)

const state = {
  backendUrl: 'http://127.0.0.1:3000',
  backendOnline: false,
  sessionId: `session-${Date.now()}`,
  commandCount: 0,
  sessionStart: Date.now(),
  cameraOn: false,
  cameraStream: null,
  micActive: false,
  mediaRecorder: null,
  audioChunks: [],
  transcribeActive: false,
  transcribeRecorder: null,
  transcribeChunks: [],
  lastNotes: '',
  projects: [],
  activeProjectId: null,
};

const $ = (id) => document.getElementById(id);

// ---------- Clock ----------
function tickClock() {
  const now = new Date();
  const time = now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true });
  const date = now.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
  $('clock-time').textContent = time;
  $('clock-date').textContent = date;
}

// ---------- Uptime ----------
function formatDuration(seconds) {
  const h = Math.floor(seconds / 3600).toString().padStart(2, '0');
  const m = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0');
  const s = Math.floor(seconds % 60).toString().padStart(2, '0');
  return `${h}:${m}:${s}`;
}

function tickUptime() {
  const elapsed = (Date.now() - state.sessionStart) / 1000;
  const formatted = formatDuration(elapsed);
  $('uptime-value').textContent = formatted;
  $('uptime-value-2').textContent = formatted;
}

// ---------- Backend status ----------
function setBackendStatus(online) {
  state.backendOnline = online;
  const pill = $('backend-status');
  pill.classList.toggle('offline', !online);
  pill.innerHTML = `<span class="dot"></span>${online ? 'Online' : 'Offline'}`;
}

async function pollBackendHealth() {
  try {
    const res = await fetch(`${state.backendUrl}/health/claude`, { method: 'GET' });
    setBackendStatus(res.ok);
  } catch {
    setBackendStatus(false);
  }
}

// ---------- System stats ----------
async function refreshSystemStats() {
  if (!window.jarvis) return;
  const stats = await window.jarvis.getSystemStats();
  $('cpu-percent').textContent = `${stats.cpuPercent}%`;
  $('cpu-tile').textContent = `${stats.cpuPercent}%`;
  $('cpu-bar').style.width = `${stats.cpuPercent}%`;

  $('ram-label').textContent = `${stats.ramUsedGB.toFixed(1)} GB`;
  $('mem-tile').textContent = `${stats.ramPercent}%`;
  $('ram-bar').style.width = `${stats.ramPercent}%`;

  if (stats.disk) {
    $('disk-tile').textContent = `${Math.round(stats.disk.usedGB)}/${Math.round(stats.disk.totalGB)} GB`;
  }

  const load = stats.cpuPercent;
  $('load-percent').textContent = `${load}%`;
  $('load-bar').style.width = `${load}%`;
  const label = load < 40 ? 'Low' : load < 75 ? 'Moderate' : 'High';
  $('load-label').textContent = label;
  $('load-label').style.color = load < 40 ? 'var(--green-ok)' : load < 75 ? 'var(--amber)' : 'var(--red-bright)';
}

// ---------- Weather ----------
async function refreshWeather() {
  if (!window.jarvis) return;
  const body = $('weather-body');
  const header = $('header-weather-text');
  try {
    const weather = await window.jarvis.getWeather();
    if (!weather.configured) {
      body.innerHTML = '<div class="weather-empty">Set <code>WEATHER_API_KEY</code> in .env to enable</div>';
      header.textContent = 'Weather unavailable';
      return;
    }
    if (weather.error) {
      body.innerHTML = `<div class="weather-empty">${weather.error}</div>`;
      header.textContent = 'Weather unavailable';
      return;
    }
    header.textContent = `${Math.round(weather.tempC)}°C ${weather.city || ''}`;
    body.innerHTML = `
      <div class="weather-top">
        <div>
          <div class="weather-temp">${Math.round(weather.tempC)}°C</div>
          <div class="weather-city">${weather.city || ''}</div>
        </div>
        <div class="weather-icon">☁</div>
      </div>
      <div class="weather-desc">${weather.description || ''}</div>
      <div class="stat-grid">
        <div class="stat-tile"><span class="label">Humidity</span><span class="value">${weather.humidity ?? '--'}%</span></div>
        <div class="stat-tile"><span class="label">Wind</span><span class="value">${weather.windMs ?? '--'} m/s</span></div>
        <div class="stat-tile"><span class="label">Feels Like</span><span class="value">${Math.round(weather.feelsLikeC ?? 0)}°C</span></div>
      </div>`;
  } catch (err) {
    body.innerHTML = '<div class="weather-empty">Weather unavailable</div>';
  }
}

// ---------- Fitness widget ----------
async function refreshFitness() {
  if (!window.jarvis) return;
  const body = $('fitness-body');
  try {
    const summary = await window.jarvis.getFitnessSummary();
    if (!summary.online) {
      body.innerHTML = '<div class="weather-empty">Fitness tracker offline -- run <code>fitness.sh</code></div>';
      return;
    }
    body.innerHTML = `
      <div class="stat-grid two">
        <div class="stat-tile"><span class="label">HRV</span><span class="value">${summary.hrv ?? '--'}</span></div>
        <div class="stat-tile"><span class="label">Sleep Score</span><span class="value">${summary.sleepScore ?? '--'}</span></div>
        <div class="stat-tile"><span class="label">Resting HR</span><span class="value">${summary.restingHr ?? '--'}</span></div>
        <div class="stat-tile"><span class="label">Stress</span><span class="value">${summary.stressScore ?? '--'}</span></div>
      </div>`;
  } catch (err) {
    body.innerHTML = '<div class="weather-empty">Fitness tracker offline -- run <code>fitness.sh</code></div>';
  }
}

async function openFitnessDashboard() {
  if (!window.jarvis) return;
  const overlay = $('fitness-overlay');
  const webview = $('fitness-webview');
  const url = await window.jarvis.getFitnessFrontendUrl();
  if (webview.getAttribute('src') !== url) {
    webview.setAttribute('src', url);
  }
  overlay.hidden = false;
}

function closeFitnessDashboard() {
  $('fitness-overlay').hidden = true;
}

// ---------- R&D Project workspace ----------
async function refreshProjectsWidget() {
  const body = $('projects-widget-body');
  try {
    const res = await fetch(`${state.backendUrl}/projects`);
    if (!res.ok) throw new Error('offline');
    const data = await res.json();
    const projects = data.projects || [];
    if (!projects.length) {
      body.innerHTML = '<div class="weather-empty">No projects yet</div>';
      return;
    }
    const active = projects.filter((p) => !['done', 'archived'].includes(p.status));
    body.innerHTML = `
      <div class="stat-grid two">
        <div class="stat-tile"><span class="label">Total</span><span class="value">${projects.length}</span></div>
        <div class="stat-tile"><span class="label">Active</span><span class="value">${active.length}</span></div>
      </div>`;
  } catch {
    body.innerHTML = '<div class="weather-empty">JARVIS backend offline</div>';
  }
}

function statusOptions(current) {
  const statuses = ['idea', 'planning', 'building', 'testing', 'done', 'archived'];
  return statuses.map((s) => `<option value="${s}" ${s === current ? 'selected' : ''}>${s}</option>`).join('');
}

function renderProjectList() {
  const list = $('project-list');
  if (!state.projects.length) {
    list.innerHTML = '<div class="weather-empty">No projects yet -- create one to start.</div>';
    return;
  }
  list.innerHTML = state.projects.map((p) => `
    <div class="project-list-item fx-interactive ${p.id === state.activeProjectId ? 'active' : ''}" data-id="${p.id}">
      <span class="name">${escapeHtml(p.name)}</span>
      <span class="status-tag">${p.status}</span>
    </div>`).join('');

  list.querySelectorAll('.project-list-item').forEach((el) => {
    el.addEventListener('click', () => selectProject(el.dataset.id));
  });
}

function renderProjectDetail(project) {
  const pane = $('project-detail-pane');
  if (!project) {
    pane.innerHTML = '<div class="project-empty-state">Select a project, or create a new one.</div>';
    return;
  }

  const phases = (project.fabrication_plan?.phases || []).map((phase) => `
    <div class="project-phase">
      <span class="phase-name">${escapeHtml(phase.name)}</span>
      <ul>${phase.tasks.map((t) => `<li>${escapeHtml(t)}</li>`).join('')}</ul>
    </div>`).join('');

  const artifacts = (project.artifacts || []).slice().reverse().map((a) => `
    <div class="artifact-row">
      <span class="artifact-type fx-readout">${escapeHtml(a.type)}</span>
      <span>${escapeHtml(a.name)}${a.notes ? ` -- ${escapeHtml(a.notes)}` : ''}</span>
    </div>`).join('') || '<div class="hint">No artifacts yet.</div>';

  const notes = (project.notes || []).slice().reverse().map((n) => `
    <div class="note-row">
      <span class="note-time">${new Date(n.timestamp).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</span>
      <span>${escapeHtml(n.text)}</span>
    </div>`).join('') || '<div class="hint">No notes yet.</div>';

  pane.innerHTML = `
    <div class="project-detail-header holo-in">
      <div>
        <h2>${escapeHtml(project.name)}</h2>
        <div class="objective">${escapeHtml(project.objective)}</div>
      </div>
      <select class="project-status-select" id="project-status-select">${statusOptions(project.status)}</select>
    </div>

    <div class="project-section">
      <h3>Fabrication Plan</h3>
      ${phases || '<div class="hint">No plan.</div>'}
    </div>

    <div class="project-section">
      <h3>Artifacts</h3>
      ${artifacts}
      <form class="project-add-form" id="artifact-form">
        <input type="text" id="artifact-type-input" placeholder="type (cad/circuit/sim_result)" autocomplete="off" />
        <input type="text" id="artifact-name-input" placeholder="name" autocomplete="off" />
        <button type="submit" class="icon-btn small fx-interactive" title="Add artifact">＋</button>
      </form>
    </div>

    <div class="project-section">
      <h3>Notes</h3>
      ${notes}
      <form class="project-add-form" id="note-form">
        <input type="text" id="note-input" placeholder="Add a note..." autocomplete="off" />
        <button type="submit" class="icon-btn small fx-interactive" title="Add note">＋</button>
      </form>
    </div>`;

  $('project-status-select').addEventListener('change', async (e) => {
    await fetch(`${state.backendUrl}/projects/${project.id}/status`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: e.target.value }),
    });
    await loadProjects();
    selectProject(project.id);
  });

  $('artifact-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const type = $('artifact-type-input').value.trim() || 'file';
    const name = $('artifact-name-input').value.trim();
    if (!name) return;
    await fetch(`${state.backendUrl}/projects/${project.id}/artifacts`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, name }),
    });
    await loadProjects();
    selectProject(project.id);
  });

  $('note-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = $('note-input').value.trim();
    if (!text) return;
    await fetch(`${state.backendUrl}/projects/${project.id}/notes`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    await loadProjects();
    selectProject(project.id);
  });
}

async function loadProjects() {
  try {
    const res = await fetch(`${state.backendUrl}/projects`);
    const data = await res.json();
    state.projects = data.projects || [];
  } catch {
    state.projects = [];
  }
  renderProjectList();
}

function selectProject(projectId) {
  state.activeProjectId = projectId;
  const project = state.projects.find((p) => p.id === projectId);
  renderProjectList();
  renderProjectDetail(project);
}

async function createProject() {
  const name = prompt('Project name:');
  if (!name || !name.trim()) return;
  const objective = prompt('Objective:') || '';
  try {
    const res = await fetch(`${state.backendUrl}/projects`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, objective }),
    });
    const created = await res.json();
    await loadProjects();
    if (created?.id) selectProject(created.id);
  } catch { /* backend offline */ }
}

async function openProjectsWorkspace() {
  $('projects-overlay').hidden = false;
  await loadProjects();
  if (state.activeProjectId) selectProject(state.activeProjectId);
}

function closeProjectsWorkspace() {
  $('projects-overlay').hidden = true;
}

// ---------- Camera ----------
async function toggleCamera() {
  const video = $('camera-video');
  const offLabel = $('camera-off-label');
  const hint = $('camera-hint');

  if (state.cameraOn) {
    if (state.cameraStream) {
      state.cameraStream.getTracks().forEach((t) => t.stop());
      state.cameraStream = null;
    }
    video.hidden = true;
    offLabel.style.display = 'flex';
    hint.textContent = 'Camera is inactive. Click the power button to start.';
    state.cameraOn = false;
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true });
    state.cameraStream = stream;
    video.srcObject = stream;
    video.hidden = false;
    offLabel.style.display = 'none';
    hint.textContent = 'Camera is active.';
    state.cameraOn = true;
  } catch (err) {
    hint.textContent = 'Camera permission denied or unavailable.';
  }
}

function snapshotCamera() {
  if (!state.cameraOn) return;
  const video = $('camera-video');
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);
  const link = document.createElement('a');
  link.download = `jarvis-snapshot-${Date.now()}.png`;
  link.href = canvas.toDataURL('image/png');
  link.click();
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ---------- Conversation ----------
function setVoiceStatus(text, mode) {
  const pill = $('voice-status');
  pill.innerHTML = `<span class="dot"></span>${text}`;
  const orb = $('orb');
  orb.classList.remove('listening', 'speaking');
  if (mode) orb.classList.add(mode);
  window.jarvisParticles?.setSpeaking(mode === 'speaking');
}

async function sendPrompt(prompt) {
  if (!prompt.trim()) return;
  if (window.jarvis) {
    state.commandCount = await window.jarvis.noteCommand();
    $('commands-tile').textContent = state.commandCount;
  }

  // No chat panel to stream text into anymore -- /chat/test is the same
  // path the real voice loop uses, so the backend speaks the reply itself
  // (and pushes live speaking state over IPC, see onSpeaking below).
  setVoiceStatus('Thinking…', 'speaking');
  try {
    const res = await fetch(`${state.backendUrl}/chat/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: prompt, session_id: state.sessionId }),
    });
    if (!res.ok) throw new Error(`Backend responded with ${res.status}`);
  } catch (err) {
    // JARVIS backend is offline or the request failed -- nothing more to do
  } finally {
    setVoiceStatus('Idle', null);
  }
}

// ---------- Mic (push to talk -> /transcribe -> sendPrompt) ----------
async function toggleMic() {
  const micBtn = $('mic-action');
  if (state.micActive) {
    state.mediaRecorder?.stop();
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream);
    state.mediaRecorder = recorder;
    state.audioChunks = [];
    state.micActive = true;
    micBtn.classList.add('active');
    setVoiceStatus('Listening…', 'listening');

    recorder.ondataavailable = (e) => state.audioChunks.push(e.data);
    recorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      state.micActive = false;
      micBtn.classList.remove('active');
      setVoiceStatus('Transcribing…', null);

      const blob = new Blob(state.audioChunks, { type: 'audio/webm' });
      const form = new FormData();
      form.append('file', blob, 'audio.webm');

      try {
        const res = await fetch(`${state.backendUrl}/transcribe`, { method: 'POST', body: form });
        const data = await res.json();
        if (data.text) {
          await sendPrompt(data.text);
        } else {
          setVoiceStatus('Idle', null);
        }
      } catch {
        setVoiceStatus('Idle', null);
      }
    };

    recorder.start();
  } catch (err) {
    setVoiceStatus('Mic unavailable', null);
  }
}

// ---------- Transcribe mode (lecture/meeting -> study notes) ----------
// Unlike toggleMic (push-to-talk, short commands, auto-processed on stop),
// this records continuously with no length limit until the user explicitly
// ends it, then batches the whole thing through Whisper + one Claude call
// (see jarvis/tools/lecture_notes.py) instead of transcribing/summarizing
// incrementally throughout -- cheaper and simpler than a running update loop.
async function toggleTranscribe() {
  const btn = $('transcribe-action');
  const hint = $('transcribe-hint');

  if (state.transcribeActive) {
    state.transcribeRecorder?.stop();
    return;
  }

  try {
    // echoCancellation/noiseSuppression off, autoGainControl on -- default
    // browser noise suppression tends to clip out quieter, farther-away
    // speech, which is exactly what a large room needs picked up.
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: true },
    });
    const recorder = new MediaRecorder(stream);
    state.transcribeRecorder = recorder;
    state.transcribeChunks = [];
    state.transcribeActive = true;
    btn.classList.add('active');
    btn.title = 'Recording Done (click to stop and generate notes)';
    hint.hidden = false;
    hint.textContent = '🔴 Transcribing -- click the pencil again when done.';

    recorder.ondataavailable = (e) => state.transcribeChunks.push(e.data);
    recorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      state.transcribeActive = false;
      btn.classList.remove('active');
      btn.title = 'Transcribe mode (lecture/meeting notes)';
      hint.textContent = 'Transcribing and building notes -- this can take a few minutes for a long recording.';

      const blob = new Blob(state.transcribeChunks, { type: 'audio/webm' });
      const form = new FormData();
      form.append('file', blob, 'lecture.webm');

      try {
        const res = await fetch(`${state.backendUrl}/notes/lecture`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(`Backend responded with ${res.status}`);
        const data = await res.json();
        state.lastNotes = data.notes || '';
        $('notes-body').textContent = state.lastNotes || 'No notes were generated.';
        $('notes-overlay').hidden = false;
        hint.hidden = true;
      } catch (err) {
        hint.textContent = 'Failed to generate notes -- backend may be offline.';
        setTimeout(() => { hint.hidden = true; }, 4000);
      }
    };

    recorder.start();
  } catch (err) {
    hint.hidden = false;
    hint.textContent = 'Microphone unavailable.';
  }
}

function closeNotesOverlay() {
  $('notes-overlay').hidden = true;
}

async function saveNotes() {
  if (!window.jarvis || !state.lastNotes) return;
  await window.jarvis.saveTextFile(state.lastNotes, {
    title: 'Save Lecture Notes',
    defaultPath: `lecture-notes-${Date.now()}.md`,
  });
}

// ---------- Wire up UI ----------
function init() {
  tickClock();
  setInterval(tickClock, 1000);
  setInterval(tickUptime, 1000);

  refreshSystemStats();
  refreshWeather();
  refreshFitness();
  refreshProjectsWidget();
  pollBackendHealth();

  setInterval(refreshSystemStats, 3000);
  setInterval(refreshWeather, 5 * 60 * 1000);
  setInterval(refreshFitness, 60 * 1000);
  setInterval(refreshProjectsWidget, 60 * 1000);
  setInterval(pollBackendHealth, 10000);

  if (window.jarvis) {
    window.jarvis.getBackendUrl().then((url) => {
      if (url) state.backendUrl = url;
    });
    // The real wake-word voice loop's TTS plays server-side (afplay/say in
    // conversation_handler.py), not through this window's audio at all --
    // this is how the particle field finds out JARVIS is actually talking
    // during that flow, pushed over IPC from main.js's local HTTP listener.
    window.jarvis.onSpeaking?.((active) => {
      if (!$('mic-action').classList.contains('active')) {
        setVoiceStatus(active ? 'Speaking…' : 'Idle', active ? 'speaking' : null);
      }
    });
  }

  $('refresh-stats').addEventListener('click', refreshSystemStats);
  $('refresh-weather').addEventListener('click', refreshWeather);

  $('refresh-fitness').addEventListener('click', (e) => {
    e.stopPropagation();
    refreshFitness();
  });
  $('fitness-widget').addEventListener('click', openFitnessDashboard);
  $('fitness-overlay-close').addEventListener('click', closeFitnessDashboard);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !$('fitness-overlay').hidden) closeFitnessDashboard();
    if (e.key === 'Escape' && !$('projects-overlay').hidden) closeProjectsWorkspace();
    if (e.key === 'Escape' && !$('notes-overlay').hidden) closeNotesOverlay();
  });

  $('refresh-projects').addEventListener('click', (e) => {
    e.stopPropagation();
    refreshProjectsWidget();
  });
  $('projects-widget').addEventListener('click', openProjectsWorkspace);
  $('projects-overlay-close').addEventListener('click', closeProjectsWorkspace);
  $('project-new-btn').addEventListener('click', createProject);

  $('camera-toggle').addEventListener('click', toggleCamera);
  $('camera-action').addEventListener('click', toggleCamera);
  $('camera-snapshot').addEventListener('click', snapshotCamera);

  $('mic-action').addEventListener('click', toggleMic);
  $('transcribe-action').addEventListener('click', toggleTranscribe);
  $('notes-overlay-close').addEventListener('click', closeNotesOverlay);
  $('notes-save-btn').addEventListener('click', saveNotes);
}

document.addEventListener('DOMContentLoaded', init);
