'use strict';

const {app, BrowserWindow, Menu, dialog, protocol, session, shell} = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const security = require('./security.cjs');

const COURSE_HOME_URL = 'course://app/roadmap/cpp_backend_roadmap.html';
const LABS = 'course://app/roadmap/visual_labs.html';
const PROGRESS = 'course://app/progress.html';
const APP_NAME = 'C++ Backend';
const windows = new Set();
let site;

function argument(name) {
  const prefix = '--' + name + '=';
  const item = process.argv.find(value => value.startsWith(prefix));
  return item ? item.slice(prefix.length) : null;
}

const testMode = process.argv.includes('--course-test-mode');
const dataOverride = argument('course-data-dir');
const remoteDebug = app.commandLine.hasSwitch('remote-debugging-port')
  || app.commandLine.hasSwitch('remote-debugging-pipe');

app.setName(APP_NAME);
if (process.platform === 'linux') app.setDesktopName('cpp-backend-course-desktop.desktop');
if (process.getuid && process.getuid() === 0) {
  console.error('Запускай учебник от обычного пользователя, без sudo.');
  app.exit(1);
}
if (app.commandLine.hasSwitch('no-sandbox')) {
  console.error('Учебник не поддерживает запуск с выключенной песочницей.');
  app.exit(1);
}
if (remoteDebug && !testMode) {
  console.error('Remote debugging is available only in explicit isolated course test mode.');
  app.exit(1);
}
if (testMode) {
  // A test must not reuse a personal Chrome/Electron profile accidentally.
  if (!dataOverride || !path.isAbsolute(dataOverride)
    || !path.resolve(dataOverride).startsWith(path.resolve(os.tmpdir()) + path.sep)) {
    console.error('Course test mode requires --course-data-dir=/tmp/<temporary-profile>.');
    app.exit(1);
  }
  app.setPath('userData', path.resolve(dataOverride));
  if (app.commandLine.hasSwitch('remote-debugging-port')) {
    app.commandLine.appendSwitch('remote-debugging-address', '127.0.0.1');
  }
} else {
  if (dataOverride) {
    console.error('Custom data directories are available only in course test mode.');
    app.exit(1);
  }
  app.setPath('userData', path.join(app.getPath('appData'), 'cpp-backend-course-desktop'));
}
app.commandLine.appendSwitch('disable-background-networking');
app.commandLine.appendSwitch('disable-component-update');
// The shipped dictionaries are not needed for code/SQL editors; do not download
// Chromium spelling files silently when the reader is working offline.
app.enableSandbox();
protocol.registerSchemesAsPrivileged([{scheme: 'course', privileges: {
  standard: true, secure: true, supportFetchAPI: true, corsEnabled: true,
}}]);

function usableWindow(preferred) {
  if (preferred && !preferred.isDestroyed()) return preferred;
  return BrowserWindow.getFocusedWindow() || [...windows].find(win => !win.isDestroyed());
}

function navigate(url, preferred) {
  const win = usableWindow(preferred);
  if (win) win.loadURL(url).catch(error => console.error('Course navigation failed:', error.message));
  else createWindow(url);
}

async function openExternal(value, owner) {
  const url = security.externalURL(value);
  if (!url) return;
  const win = usableWindow(owner);
  const options = {type: 'question', title: 'Открыть внешнюю ссылку?',
    message: 'Эта страница находится вне учебника.',
    detail: new URL(url).origin + '\n\nОна откроется в обычном браузере и может потребовать интернет. Сам курс останется в приложении.',
    buttons: ['Открыть в браузере', 'Отмена'], defaultId: 1, cancelId: 1, noLink: true};
  const answer = win ? await dialog.showMessageBox(win, options) : await dialog.showMessageBox(options);
  if (answer.response === 0) {
    // Never pass javascript:, file:, custom desktop schemes or credentials to
    // the operating system. Revalidate directly before calling shell.
    const safe = security.externalURL(url);
    if (safe) await shell.openExternal(safe).catch(() => {});
  }
}

function allowInternal(url) {
  const name = security.internalName(url);
  return Boolean(name && site.names.has(name));
}

function secureContents(win) {
  const contents = win.webContents;
  contents.on('will-attach-webview', event => event.preventDefault());
  contents.on('will-navigate', (event, legacyUrl) => {
    const url = event.url || legacyUrl;
    if (!allowInternal(url)) {
      event.preventDefault();
      openExternal(url, win);
    }
  });
  contents.on('will-frame-navigate', event => {
    // No subframe is allowed to turn into a remote website or local file reader.
    // External top-frame links are handled by will-navigate above.
    if (!event.isMainFrame && !allowInternal(event.url)) event.preventDefault();
  });
  contents.on('will-redirect', (event, legacyUrl) => {
    if (!allowInternal(event.url || legacyUrl)) event.preventDefault();
  });
  contents.setWindowOpenHandler(details => {
    if (allowInternal(details.url)) {
      // Do not reuse the question window: target=_blank theory references must
      // leave the current quiz and its unsaved state intact.
      createWindow(details.url);
    } else if (security.externalURL(details.url)) {
      openExternal(details.url, win);
    }
    return {action: 'deny'};
  });
  contents.on('page-title-updated', (event, title) => {
    event.preventDefault();
    win.setTitle(title ? title + ' — C++ Backend' : APP_NAME);
  });
  contents.on('did-fail-load', (_event, code, _description, _url, mainFrame) => {
    if (mainFrame && code !== -3 && !win.isDestroyed()) {
      dialog.showMessageBox(win, {type: 'error', title: 'Не удалось открыть раздел',
        message: 'Локальная страница не загрузилась.',
        detail: 'Вернись к программе курса через меню «Курс». Если ошибка повторяется, переустанови приложение. Сохранённый прогресс находится отдельно от файлов учебника.',
        buttons: ['Понятно']}).catch(() => {});
    }
  });
  contents.on('render-process-gone', (_event, details) => {
    if (!win.isDestroyed() && details.reason !== 'clean-exit') {
      dialog.showMessageBox(win, {type: 'error', title: 'Страница остановилась',
        message: 'Окно учебника нужно открыть заново.',
        detail: 'Сохранённые отметки и завершённые результаты останутся. Текущая незавершённая попытка теста могла не сохраниться.',
        buttons: ['Открыть программу курса', 'Закрыть окно'], defaultId: 0, cancelId: 1})
        .then(answer => answer.response === 0 ? navigate(COURSE_HOME_URL, win) : win.close()).catch(() => {});
    }
  });
}

function createWindow(url = COURSE_HOME_URL) {
  if (!allowInternal(url)) return null;
  const icon = [path.join(site.root, 'icons/app-256.png'), path.join(__dirname, 'assets/icon-256.png')]
    .find(candidate => fs.existsSync(candidate));
  const win = new BrowserWindow({title: APP_NAME, width: 1320, height: 960, minWidth: 380, minHeight: 500,
    backgroundColor: '#18252f', show: false, icon,
    webPreferences: {sandbox: true, contextIsolation: true, nodeIntegration: false,
      nodeIntegrationInWorker: false, nodeIntegrationInSubFrames: false, webSecurity: true,
      allowRunningInsecureContent: false, webviewTag: false, spellcheck: false,
      devTools: testMode, preload: path.join(__dirname, 'preload.cjs')},
  });
  windows.add(win);
  secureContents(win);
  win.once('ready-to-show', () => win.show());
  win.on('closed', () => windows.delete(win));
  win.loadURL(url).catch(error => console.error('Course window failed:', error.message));
  return win;
}

function setMenu() {
  const view = action => () => {
    const win = usableWindow();
    if (win) action(win.webContents);
  };
  const templates = [
    {label: 'Курс', submenu: [
      {label: 'Программа курса', accelerator: 'CmdOrCtrl+Home', click: () => navigate(COURSE_HOME_URL)},
      {label: 'Визуальные лаборатории', click: () => navigate(LABS)},
      {label: 'Прогресс и приложение', click: () => navigate(PROGRESS)},
      {type: 'separator'}, {role: 'close', label: 'Закрыть окно'}, {role: 'quit', label: 'Выйти'},
    ]},
    {label: 'Правка', submenu: [
      {role: 'undo', label: 'Отменить'}, {role: 'redo', label: 'Повторить'}, {type: 'separator'},
      {role: 'cut', label: 'Вырезать'}, {role: 'copy', label: 'Копировать'}, {role: 'paste', label: 'Вставить'},
      {role: 'selectAll', label: 'Выделить всё'},
    ]},
    {label: 'Навигация', submenu: [
      {label: 'Назад', accelerator: 'Alt+Left', click: view(wc => {if (wc.navigationHistory.canGoBack()) wc.navigationHistory.goBack();})},
      {label: 'Вперёд', accelerator: 'Alt+Right', click: view(wc => {if (wc.navigationHistory.canGoForward()) wc.navigationHistory.goForward();})},
      {label: 'Перезагрузить страницу', accelerator: 'CmdOrCtrl+R', click: async () => {
        const win = usableWindow(); if (!win) return;
        const result = await dialog.showMessageBox(win, {type: 'question', title: 'Перезагрузить страницу?',
          message: 'Незавершённая попытка теста или текущий шаг лаборатории начнутся заново.',
          detail: 'Сохранённые отметки, завершённые результаты и SQL-черновики останутся.',
          buttons: ['Перезагрузить', 'Отмена'], defaultId: 1, cancelId: 1});
        if (result.response === 0) win.webContents.reload();
      }},
    ]},
    {label: 'Вид', submenu: [
      {role: 'zoomIn', label: 'Увеличить'}, {role: 'zoomOut', label: 'Уменьшить'},
      {role: 'resetZoom', label: 'Обычный масштаб'}, {type: 'separator'},
      {role: 'togglefullscreen', label: 'Полный экран'},
    ]},
  ];
  if (testMode) templates.push({label: 'Проверка', submenu: [{role: 'toggleDevTools', label: 'Инструменты разработчика'}]});
  Menu.setApplicationMenu(Menu.buildFromTemplate(templates));
}

function configureSession(ses) {
  // Code-copy buttons need write-only clipboard access. Clipboard reads,
  // camera, microphone, geolocation, devices and all other permissions stay off.
  ses.setPermissionRequestHandler((contents, permission, callback, details) => {
    const source = details && details.requestingUrl || (contents && contents.getURL());
    callback(permission === 'clipboard-sanitized-write' && allowInternal(source));
  });
  ses.setPermissionCheckHandler((contents, permission, requestingOrigin) =>
    permission === 'clipboard-sanitized-write' && Boolean(contents) && allowInternal(requestingOrigin));
  ses.on('will-download', (event, item, contents) => {
    const url = item.getURL();
    const source = contents && contents.getURL();
    if (!allowInternal(source) || (!allowInternal(url) && !security.courseBlob(url))) {
      event.preventDefault(); return;
    }
    item.setSaveDialogOptions({title: 'Сохранить файл из учебника',
      defaultPath: path.join(app.getPath('downloads'), path.basename(item.getFilename() || 'course-download')),
      buttonLabel: 'Сохранить'});
  });
  ses.webRequest.onBeforeRequest({urls: ['<all_urls>']}, (details, callback) => {
    const value = details.url;
    const allowed = allowInternal(value) || security.courseBlob(value)
      || value === 'about:blank' || value.startsWith('data:image/');
    callback({cancel: !allowed});
  });
}

if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => {
    const win = usableWindow();
    if (win) { if (win.isMinimized()) win.restore(); win.show(); win.focus(); }
  });
  app.whenReady().then(async () => {
    const override = argument('course-site');
    if (override && app.isPackaged && !testMode) throw new Error('Packaged content cannot be replaced through command-line arguments');
    site = security.loadSite(override || path.join(__dirname, 'site'));
    configureSession(session.defaultSession);
    protocol.handle('course', request => {
      if (!['GET', 'HEAD'].includes(request.method)) return new Response('Method not allowed', {status: 405});
      const initiator = request.initiatorOrigin;
      if (initiator && initiator !== 'course://app' && initiator !== 'null') return new Response('Forbidden', {status: 403});
      try {
        const item = security.readSiteFile(site, request.url);
        if (!item) return new Response('Not a course file', {status: 404});
        const headers = {'Content-Type': item.mime, 'Content-Security-Policy': item.csp,
          'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
          'Cache-Control': 'no-cache', 'Cross-Origin-Resource-Policy': 'same-origin'};
        if (item.name.endsWith('.pcap') || item.name.endsWith('.zip')) {
          headers['Content-Disposition'] = 'attachment; filename="' + path.basename(item.name) + '"';
        }
        return new Response(request.method === 'HEAD' ? null : item.bytes, {headers});
      } catch (_) { return new Response('Packaged file unavailable', {status: 404}); }
    });
    setMenu();
    createWindow();
  }).catch(error => {
    dialog.showErrorBox('Учебник не запустился', 'Не удалось проверить локальные файлы курса. Переустанови приложение. Прогресс хранится отдельно.\n\n' + error.message);
    app.exit(1);
  });
  app.on('activate', () => { if (site && BrowserWindow.getAllWindows().length === 0) createWindow(); });
  app.on('window-all-closed', () => app.quit());
}
