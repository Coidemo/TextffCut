const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const axios = require('axios');

let mainWindow;
let pythonProcess;
const API_URL = 'http://127.0.0.1:8001';
const isDev = process.env.ELECTRON_IS_DEV === '1';

// Pythonサーバーを起動
async function startPythonServer() {
  console.log('Starting Python API server...');
  
  const pythonPath = isDev ? 'python' : path.join(process.resourcesPath, 'python', 'python');
  const apiPath = isDev 
    ? path.join(__dirname, '../../api/main.py')
    : path.join(process.resourcesPath, 'api/main.py');
  
  pythonProcess = spawn(pythonPath, [apiPath]);
  
  pythonProcess.stdout.on('data', (data) => {
    console.log(`Python: ${data}`);
  });
  
  pythonProcess.stderr.on('data', (data) => {
    console.error(`Python Error: ${data}`);
  });
  
  pythonProcess.on('close', (code) => {
    console.log(`Python process exited with code ${code}`);
  });
  
  // サーバーが起動するまで待機
  return await waitForServer();
}

// サーバーの起動を待つ
async function waitForServer(maxRetries = 30) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      await axios.get(API_URL);
      console.log('Python server is ready!');
      return true;
    } catch (error) {
      console.log(`Waiting for server... (${i + 1}/${maxRetries})`);
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }
  throw new Error('Failed to start Python server');
}

// 既存のサーバーをチェック
async function checkExistingServer() {
  try {
    console.log(`Checking server at ${API_URL}...`);
    const response = await axios.get(API_URL, { timeout: 3000 });
    console.log('Server is already running!', response.data);
    return true;
  } catch (error) {
    console.log('Server check failed:', error.message);
    return false;
  }
}

// メインウィンドウを作成
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    },
    icon: path.join(__dirname, '../assets/icon.png')
  });

  // 開発時はReactの開発サーバーを使用
  if (isDev) {
    mainWindow.loadURL('http://localhost:3000');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '../frontend/build/index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// アプリケーションの初期化
app.whenReady().then(async () => {
  try {
    // 既存のサーバーをチェック
    console.log('Checking for existing server...');
    const serverExists = await checkExistingServer();
    if (!serverExists) {
      console.log('Server not found, starting new server...');
      await startPythonServer();
    } else {
      console.log('Using existing server');
    }
    createWindow();
  } catch (error) {
    console.error('Failed to initialize app:', error);
    dialog.showErrorBox('起動エラー', 'アプリケーションの起動に失敗しました。');
    app.quit();
  }
});

// 全てのウィンドウが閉じられた時
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// アプリケーション終了時
app.on('before-quit', () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
});

// アクティベート時
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

// IPC通信の設定
ipcMain.handle('select-video-file', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    filters: [
      { name: 'Video Files', extensions: ['mp4', 'mov', 'avi', 'mkv', 'wmv'] },
      { name: 'All Files', extensions: ['*'] }
    ]
  });
  
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle('api-request', async (event, endpoint, method, data) => {
  try {
    const response = await axios({
      method,
      url: `${API_URL}${endpoint}`,
      data
    });
    return response.data;
  } catch (error) {
    console.error('API request failed:', error);
    throw error;
  }
});