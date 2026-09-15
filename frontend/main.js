const path = require('path');
const os = require('os');
const fs = require('fs');
const http = require('http');
const { spawn } = require('child_process');
const { app, BrowserWindow, ipcMain, session } = require('electron');

require('dotenv').config({ path: path.join(__dirname, '..', '.env') });

const REPO_ROOT = path.join(__dirname, '..');
const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:3000';
const WEATHER_API_KEY = process.env.WEATHER_API_KEY || '';
const WEATHER_CITY = process.env.WEATHER_CITY || 'Quezon City,PH';
const FITNESS_BACKEND_URL = process.env.FITNESS_BACKEND_URL || 'http://127.0.0.1:8000';
const FITNESS_FRONTEND_URL = process.env.FITNESS_FRONTEND_URL || 'http://127.0.0.1:5173';
// Matches wake_system_integrated.py's self.wake_notify_url -- the voice
// pipeline POSTs here the instant the wake word fires so this window jumps
// to the front immediately, before the mic even finishes recording the command.
const WAKE_PORT = parseInt(process.env.JARVIS_WAKE_PORT || '3131', 10);

let mainWindow;
let sessionCommandCount = 0;

// ---------- Backend + voice pipeline orchestration ----------
// The whole point of the desktop app is "run this one thing and you have
// JARVIS" -- no separate terminals for the FastAPI backend and the
// wake-word/voice script. This app spawns both as child processes and owns
// their lifetime, same as start_backend.sh/start_jarvis.sh do manually.
let backendProcess = null;
let voiceProcess = null;
let servicesStarted = false;

function resolvePython() {
  const venvPython = path.join(REPO_ROOT, '.venv', 'bin', 'python3');
  return fs.existsSync(venvPython) ? venvPython : 'python3';
}

function spawnManagedProcess(label, command, args) {
  const child = spawn(command, args, { cwd: REPO_ROOT, env: process.env });
  child.stdout.on('data', (data) => process.stdout.write(`[${label}] ${data}`));
  child.stderr.on('data', (data) => process.stderr.write(`[${label}] ${data}`));
  child.on('exit', (code, signal) => {
    console.log(`[${label}] exited (code=${code} signal=${signal})`);
  });
  child.on('error', (error) => {
    console.error(`[${label}] failed to start:`, error.message);
  });
  return child;
}

async function isBackendHealthy() {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 1500);
    const res = await fetch(`${BACKEND_URL}/health/claude`, { signal: controller.signal });
    clearTimeout(timer);
    return res.ok;
  } catch {
    return false;
  }
}

async function waitForBackendHealthy(timeoutMs) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await isBackendHealthy()) return true;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  return false;
}

async function startServices() {
  if (servicesStarted) return;
  servicesStarted = true;
  const python = resolvePython();

  // Don't double-spawn if a backend is already running (e.g. someone started
  // it manually with start_backend.sh) -- just wait for it instead.
  if (await isBackendHealthy()) {
    console.log('[backend] already running, reusing it');
  } else {
    console.log(`[backend] starting via ${python} -m jarvis.main`);
    backendProcess = spawnManagedProcess('backend', python, ['-m', 'jarvis.main']);
  }

  const backendReady = await waitForBackendHealthy(30000);
  if (!backendReady) {
    console.error('[backend] did not become healthy within 30s -- voice pipeline will keep retrying against it anyway');
  }

  console.log(`[voice] starting via ${python} wake_system_integrated.py`);
  voiceProcess = spawnManagedProcess('voice', python, ['wake_system_integrated.py']);
}

function stopServices() {
  for (const child of [backendProcess, voiceProcess]) {
    if (child && !child.killed) child.kill('SIGTERM');
  }
}

function focusMainWindow() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
  app.focus({ steal: true });
}

function readJsonBody(req) {
  return new Promise((resolve) => {
    let raw = '';
    req.on('data', (chunk) => { raw += chunk; });
    req.on('end', () => {
      try {
        resolve(JSON.parse(raw || '{}'));
      } catch {
        resolve({});
      }
    });
  });
}

// Deliberately a bare http.createServer instead of a dependency -- this is a
// single trusted local caller (the backend/wake-word script on the same
// machine) hitting a couple routes, not a real API surface.
function startWakeListener() {
  const server = http.createServer(async (req, res) => {
    if (req.method === 'POST' && req.url === '/wake') {
      focusMainWindow();
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ focused: true }));
      return;
    }
    if (req.method === 'POST' && req.url === '/speaking') {
      // conversation_handler.py posts here around actual TTS playback (see
      // its _notify_frontend_speaking) -- the real voice loop's audio plays
      // server-side (afplay/say), so this is the only way the renderer's
      // particle field finds out JARVIS is talking during that flow.
      const body = await readJsonBody(req);
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('jarvis:speaking', !!body.active);
      }
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ ok: true }));
      return;
    }
    res.writeHead(404);
    res.end();
  });

  server.on('error', (error) => {
    console.error(`[wake-listener] failed to bind 127.0.0.1:${WAKE_PORT}:`, error.message);
  });

  server.listen(WAKE_PORT, '127.0.0.1', () => {
    console.log(`[wake-listener] listening on http://127.0.0.1:${WAKE_PORT}`);
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    backgroundColor: '#0a0505',
    title: 'J.A.R.V.I.S.',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      webviewTag: true,
    },
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));
}

// Renderer runs with contextIsolation -- camera/mic still need the OS-level
// permission grant Electron gates behind this handler.
function allowMediaPermissions() {
  session.defaultSession.setPermissionRequestHandler((_webContents, permission, callback) => {
    callback(permission === 'media');
  });
}

// Two os.cpus() snapshots a short interval apart -- os.loadavg() isn't a
// direct percentage and doesn't exist on Windows, this works everywhere.
function sampleCpuPercent() {
  const start = os.cpus();
  return new Promise((resolve) => {
    setTimeout(() => {
      const end = os.cpus();
      let idleDiff = 0;
      let totalDiff = 0;
      for (let i = 0; i < start.length; i++) {
        const s = start[i].times;
        const e = end[i].times;
        const sIdle = s.idle;
        const eIdle = e.idle;
        const sTotal = s.user + s.nice + s.sys + s.idle + s.irq;
        const eTotal = e.user + e.nice + e.sys + e.idle + e.irq;
        idleDiff += eIdle - sIdle;
        totalDiff += eTotal - sTotal;
      }
      const percent = totalDiff > 0 ? 100 - (100 * idleDiff) / totalDiff : 0;
      resolve(Math.max(0, Math.min(100, Math.round(percent))));
    }, 200);
  });
}

function getDiskUsage() {
  return new Promise((resolve) => {
    if (typeof fs.statfs !== 'function') {
      resolve(null);
      return;
    }
    fs.statfs('/', (err, stats) => {
      if (err) {
        resolve(null);
        return;
      }
      const totalBytes = stats.blocks * stats.bsize;
      const freeBytes = stats.bfree * stats.bsize;
      resolve({
        totalGB: totalBytes / 1024 ** 3,
        usedGB: (totalBytes - freeBytes) / 1024 ** 3,
      });
    });
  });
}

ipcMain.handle('jarvis:get-system-stats', async () => {
  const [cpuPercent, disk] = await Promise.all([sampleCpuPercent(), getDiskUsage()]);
  const totalMemGB = os.totalmem() / 1024 ** 3;
  const freeMemGB = os.freemem() / 1024 ** 3;
  const usedMemGB = totalMemGB - freeMemGB;

  return {
    cpuPercent,
    ramUsedGB: usedMemGB,
    ramTotalGB: totalMemGB,
    ramPercent: Math.round((usedMemGB / totalMemGB) * 100),
    disk,
    uptimeSeconds: process.uptime(),
  };
});

ipcMain.handle('jarvis:get-weather', async () => {
  if (!WEATHER_API_KEY) {
    return { configured: false };
  }

  const url = `https://api.openweathermap.org/data/2.5/weather?q=${encodeURIComponent(WEATHER_CITY)}&units=metric&appid=${WEATHER_API_KEY}`;
  try {
    const response = await fetch(url);
    if (!response.ok) {
      return { configured: true, error: `Weather API error: ${response.status}` };
    }
    const data = await response.json();
    return {
      configured: true,
      tempC: data.main?.temp,
      feelsLikeC: data.main?.feels_like,
      humidity: data.main?.humidity,
      windMs: data.wind?.speed,
      description: data.weather?.[0]?.description,
      icon: data.weather?.[0]?.main,
      city: data.name,
    };
  } catch (error) {
    return { configured: true, error: String(error) };
  }
});

ipcMain.handle('jarvis:get-backend-url', () => BACKEND_URL);

ipcMain.handle('jarvis:get-fitness-frontend-url', () => FITNESS_FRONTEND_URL);

ipcMain.handle('jarvis:get-fitness-summary', async () => {
  try {
    const response = await fetch(`${FITNESS_BACKEND_URL}/garmin-recovery/latest`);
    if (!response.ok) {
      return { online: false };
    }
    const data = await response.json();
    return {
      online: true,
      date: data.date,
      hrv: data.hrv,
      sleepScore: data.sleep_score,
      stressScore: data.stress_score,
      restingHr: data.resting_hr,
    };
  } catch (error) {
    return { online: false };
  }
});

ipcMain.handle('jarvis:note-command', () => {
  sessionCommandCount += 1;
  return sessionCommandCount;
});

ipcMain.handle('jarvis:save-text-file', async (_event, text, opts = {}) => {
  const { dialog } = require('electron');
  const result = await dialog.showSaveDialog(mainWindow, {
    title: opts.title || 'Save',
    defaultPath: opts.defaultPath || `jarvis-notes-${Date.now()}.md`,
    filters: [{ name: 'Markdown', extensions: ['md'] }, { name: 'Text', extensions: ['txt'] }],
  });
  if (result.canceled || !result.filePath) {
    return { saved: false };
  }
  fs.writeFileSync(result.filePath, text, 'utf-8');
  return { saved: true, path: result.filePath };
});

app.whenReady().then(() => {
  allowMediaPermissions();
  createWindow();
  startWakeListener();
  startServices();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  stopServices();
});
