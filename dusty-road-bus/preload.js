const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('desktop', {
  readSave: () => ipcRenderer.invoke('save:read'),
  writeSave: (t) => ipcRenderer.invoke('save:write', t),
  quit: () => ipcRenderer.invoke('app:quit'),
  fullscreen: () => ipcRenderer.invoke('app:fullscreen')
});
