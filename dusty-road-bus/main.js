const { app, BrowserWindow, ipcMain, Menu } = require('electron');
const path = require('path');
const fs = require('fs');

const saveFile = () => path.join(app.getPath('userData'), 'save.json');

ipcMain.handle('save:read', () => {
  try { return fs.readFileSync(saveFile(), 'utf8'); } catch (e) { return null; }
});
ipcMain.handle('save:write', (_e, text) => {
  try {
    const tmp = saveFile() + '.tmp';
    fs.writeFileSync(tmp, String(text));
    fs.renameSync(tmp, saveFile());
    return true;
  } catch (e) { return false; }
});
ipcMain.handle('app:quit', () => app.quit());
ipcMain.handle('app:fullscreen', (e) => {
  const w = BrowserWindow.fromWebContents(e.sender);
  if (w) w.setFullScreen(!w.isFullScreen());
});

function createWindow() {
  Menu.setApplicationMenu(null);
  const win = new BrowserWindow({
    width: 1280, height: 720, minWidth: 800, minHeight: 500,
    backgroundColor: '#000000', title: 'Dusty Road Bus', autoHideMenuBar: true,
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false }
  });
  win.loadFile('index.html');
}

app.whenReady().then(createWindow);
app.on('window-all-closed', () => app.quit());
