const { app, BrowserWindow, dialog, net, protocol, session, shell } = require('electron');
const { existsSync } = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

protocol.registerSchemesAsPrivileged([
  { scheme: 'reharmonized', privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true } },
]);

const origin = 'reharmonized://app';
let mainWindow;

function openExternal(url) {
  if (new URL(url).protocol === 'https:') shell.openExternal(url);
}

function createWindow() {
  mainWindow = new BrowserWindow({
    title: 'REharmonized',
    width: 1200,
    height: 850,
    minWidth: 640,
    minHeight: 480,
    backgroundColor: '#111111',
    webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true },
  });
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    openExternal(url);
    return { action: 'deny' };
  });
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (new URL(url).origin !== new URL(origin).origin || !url.startsWith(`${origin}/`)) {
      event.preventDefault();
      openExternal(url);
    }
  });
  mainWindow.on('closed', () => { mainWindow = null; });
  mainWindow.loadURL(`${origin}/index.html`);
}

app.whenReady().then(() => {
  const root = path.join(app.getAppPath(), 'dist-desktop');
  protocol.handle('reharmonized', async (request) => {
    try {
      const url = new URL(request.url);
      if (url.hostname !== 'app' || request.method !== 'GET') return new Response(null, { status: 403 });
      const filePath = path.resolve(root, `.${decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname)}`);
      if (!filePath.startsWith(`${root}${path.sep}`)) return new Response(null, { status: 403 });
      const response = await net.fetch(pathToFileURL(filePath).href);
      response.headers.set('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; base-uri 'none'");
      return response;
    } catch {
      return new Response(null, { status: 404 });
    }
  });
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  session.defaultSession.webRequest.onBeforeRequest((details, callback) => {
    callback({ cancel: /^https?:/.test(details.url) });
  });
  session.defaultSession.on('will-download', (_event, item) => {
    const filename = path.basename(item.getFilename());
    const extension = path.extname(filename);
    const basename = path.basename(filename, extension);
    let destination = path.join(app.getPath('downloads'), filename);
    let suffix = 1;
    while (existsSync(destination)) {
      destination = path.join(app.getPath('downloads'), `${basename} (${suffix++})${extension}`);
    }
    item.setSavePath(destination);
    item.once('done', (_doneEvent, state) => {
      if (state === 'interrupted') {
        dialog.showErrorBox('ROM download failed', `Could not save the ROM to ${destination}. Check available disk space and folder permissions.`);
      }
    });
  });
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});