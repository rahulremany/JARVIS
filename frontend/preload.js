const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('jarvis', {
  getSystemStats: () => ipcRenderer.invoke('jarvis:get-system-stats'),
  getWeather: () => ipcRenderer.invoke('jarvis:get-weather'),
  getBackendUrl: () => ipcRenderer.invoke('jarvis:get-backend-url'),
  getFitnessSummary: () => ipcRenderer.invoke('jarvis:get-fitness-summary'),
  getFitnessFrontendUrl: () => ipcRenderer.invoke('jarvis:get-fitness-frontend-url'),
  noteCommand: () => ipcRenderer.invoke('jarvis:note-command'),
  saveTextFile: (text, opts) => ipcRenderer.invoke('jarvis:save-text-file', text, opts),
  // Pushed from main.js when the backend's real voice loop starts/stops
  // speaking (see the /speaking route on the local wake-listener HTTP
  // server) -- lets the renderer react live to TTS that plays server-side,
  // outside the browser's own audio stack.
  onSpeaking: (callback) => ipcRenderer.on('jarvis:speaking', (_event, active) => callback(active)),
});
