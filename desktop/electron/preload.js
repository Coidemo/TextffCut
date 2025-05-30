const { contextBridge, ipcRenderer } = require('electron');

// Reactアプリケーションに安全なAPIを提供
contextBridge.exposeInMainWorld('electronAPI', {
  // ファイル選択
  selectVideoFile: () => ipcRenderer.invoke('select-video-file'),
  
  // API通信
  apiRequest: (endpoint, method = 'GET', data = null) => 
    ipcRenderer.invoke('api-request', endpoint, method, data),
  
  // 文字起こし実行
  transcribe: async (videoPath, modelSize = 'large-v3') => {
    return await ipcRenderer.invoke('api-request', '/api/transcribe', 'POST', {
      video_path: videoPath,
      model_size: modelSize
    });
  },
  
  // 動画処理実行
  processVideo: async (params) => {
    return await ipcRenderer.invoke('api-request', '/api/process', 'POST', params);
  },
  
  // 設定取得
  getSettings: async () => {
    return await ipcRenderer.invoke('api-request', '/api/settings', 'GET');
  },
  
  // キャッシュ確認
  checkTranscriptionCache: async (videoName, modelSize) => {
    return await ipcRenderer.invoke('api-request', `/api/transcribe/cache-status/${videoName}/${modelSize}`, 'GET');
  },
  
  // キャッシュから読み込み
  loadFromCache: async (videoName, modelSize) => {
    return await ipcRenderer.invoke('api-request', '/api/transcribe/from-cache', 'POST', {
      video_name: videoName,
      model_size: modelSize
    });
  },
  
  // プログレス確認
  getProgress: async (taskId) => {
    return await ipcRenderer.invoke('api-request', `/api/progress/${taskId}`, 'GET');
  },
  
  // テキスト検証（セパレータ対応・エラー検出）
  validateText: async (originalText, editedText, transcriptionSegments = []) => {
    return await ipcRenderer.invoke('api-request', '/api/text/validate', 'POST', {
      original_text: originalText,
      edited_text: editedText,
      transcription_segments: transcriptionSegments
    });
  }
});