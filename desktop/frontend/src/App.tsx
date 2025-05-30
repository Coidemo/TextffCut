import React, { useState, useEffect } from 'react';
import {
  Container,
  Box,
  Button,
  Typography,
  Paper,
  LinearProgress,
  Alert,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  TextField,
  Switch,
  FormControlLabel,
  Stack,
  Divider,
} from '@mui/material';
import {
  VideoFile,
  Transcribe,
  ContentCut,
  Download
} from '@mui/icons-material';
import './App.css';

// Electron APIの型定義
declare global {
  interface Window {
    electronAPI: {
      selectVideoFile: () => Promise<string | null>;
      transcribe: (videoPath: string, modelSize: string) => Promise<any>;
      processVideo: (params: any) => Promise<any>;
      getSettings: () => Promise<any>;
      checkTranscriptionCache: (videoName: string, modelSize: string) => Promise<any>;
      loadFromCache: (videoName: string, modelSize: string) => Promise<any>;
      getProgress: (taskId: string) => Promise<any>;
    };
  }
}

// 差分表示用の関数
const generateDiffView = (originalText: string, editedText: string): string => {
  if (!originalText || !editedText) {
    return originalText || '';
  }

  // 簡単な差分アルゴリズム：編集されたテキストに含まれる部分を緑でハイライト
  const editedWords = editedText.split(/\s+/).filter(word => word.trim().length > 0);
  const originalWords = originalText.split(/\s+/);
  
  let highlightedText = '';
  let currentPos = 0;
  
  // 編集されたテキストの各単語が元のテキストのどこにあるかを探す
  for (const editedWord of editedWords) {
    const cleanEditedWord = editedWord.replace(/[^\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]/g, '');
    
    // 現在位置から該当する単語を探す
    let found = false;
    for (let i = currentPos; i < originalWords.length; i++) {
      const cleanOriginalWord = originalWords[i].replace(/[^\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]/g, '');
      if (cleanOriginalWord === cleanEditedWord) {
        // 見つからなかった部分を追加
        for (let j = currentPos; j < i; j++) {
          highlightedText += originalWords[j] + ' ';
        }
        // 一致した部分を緑でハイライト
        highlightedText += `<span style="background-color: #e6ffe6; color: #2e7d32;">${originalWords[i]}</span> `;
        currentPos = i + 1;
        found = true;
        break;
      }
    }
    
    if (!found) {
      // 見つからない場合は現在位置を進める
      break;
    }
  }
  
  // 残りの部分を追加
  for (let i = currentPos; i < originalWords.length; i++) {
    highlightedText += originalWords[i] + ' ';
  }
  
  return highlightedText.trim().replace(/\n/g, '<br>');
};

function App() {
  const [videoPath, setVideoPath] = useState<string>('');
  const [originalText, setOriginalText] = useState<string>('');
  const [editedText, setEditedText] = useState<string>('');
  const [modelSize, setModelSize] = useState<string>('large-v3');
  const [removeSilence, setRemoveSilence] = useState<boolean>(true);
  const [outputVideo, setOutputVideo] = useState<boolean>(false);
  const [noiseThreshold, setNoiseThreshold] = useState<number>(-35);
  const [paddingStart, setPaddingStart] = useState<number>(0.1);
  const [paddingEnd, setPaddingEnd] = useState<number>(0.1);
  const [loading, setLoading] = useState<boolean>(false);
  const [progress, setProgress] = useState<number>(0);
  const [message, setMessage] = useState<string>('');
  const [settings, setSettings] = useState<any>(null);
  const [hasCache, setHasCache] = useState<boolean>(false);
  const [cacheInfo, setCacheInfo] = useState<any>(null);
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [progressDetails, setProgressDetails] = useState<any>(null);
  const [transcriptionSegments, setTranscriptionSegments] = useState<any[]>([]);

  useEffect(() => {
    // 設定を読み込み
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const data = await window.electronAPI.getSettings();
      setSettings(data);
    } catch (error) {
      console.error('Failed to load settings:', error);
    }
  };

  const selectVideo = async () => {
    const path = await window.electronAPI.selectVideoFile();
    if (path) {
      setVideoPath(path);
      setMessage(`動画を選択しました: ${path}`);
      
      // キャッシュチェック
      await checkCache(path, modelSize);
    }
  };

  const checkCache = async (videoPath: string, modelSize: string) => {
    if (!videoPath) return;
    
    try {
      const videoName = videoPath.split('/').pop()?.replace(/\.[^/.]+$/, '') || '';
      const cacheStatus = await window.electronAPI.checkTranscriptionCache(videoName, modelSize);
      
      setHasCache(cacheStatus.has_cache);
      setCacheInfo(cacheStatus);
      
      if (cacheStatus.has_cache) {
        setMessage(`キャッシュが見つかりました: ${videoName}_${modelSize}.json`);
      }
    } catch (error) {
      console.error('キャッシュチェックエラー:', error);
    }
  };

  const loadFromCache = async () => {
    if (!cacheInfo) return;
    
    setLoading(true);
    setMessage('キャッシュから読み込み中...');
    
    try {
      const result = await window.electronAPI.loadFromCache(cacheInfo.video_name, cacheInfo.model_size);
      
      if (result.success) {
        setOriginalText(result.text);
        setEditedText(''); // 切り抜き箇所は空にする
        setTranscriptionSegments(result.segments || []); // セグメント情報も保存
        setMessage('キャッシュから文字起こし結果を読み込みました');
      }
    } catch (error) {
      setMessage(`キャッシュ読み込みエラー: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const monitorProgress = async (taskId: string) => {
    const interval = setInterval(async () => {
      try {
        const progressData = await window.electronAPI.getProgress(taskId);
        
        setProgress(progressData.progress || 0);
        setProgressDetails(progressData);
        setMessage(progressData.message || '処理中...');
        
        // タスクが完了またはエラーの場合は監視を停止
        if (progressData.status === 'completed' || progressData.status === 'error') {
          clearInterval(interval);
          setCurrentTaskId(null);
          setLoading(false);
          
          if (progressData.status === 'error') {
            setMessage(`エラー: ${progressData.message}`);
          }
        }
      } catch (error) {
        // タスクが見つからない場合は監視を停止
        clearInterval(interval);
        setCurrentTaskId(null);
      }
    }, 1000); // 1秒間隔でポーリング
    
    // 5分後にタイムアウト
    setTimeout(() => {
      clearInterval(interval);
      if (currentTaskId === taskId) {
        setCurrentTaskId(null);
        setLoading(false);
        setMessage('タイムアウト: 処理に時間がかかりすぎています');
      }
    }, 300000);
  };

  const transcribeVideo = async () => {
    if (!videoPath) {
      setMessage('動画を選択してください');
      return;
    }

    setLoading(true);
    setProgress(0);
    setMessage('文字起こしを実行中...');

    try {
      const result = await window.electronAPI.transcribe(videoPath, modelSize);
      if (result.success) {
        setOriginalText(result.text);
        setEditedText(''); // 切り抜き箇所は空にする
        setTranscriptionSegments(result.segments || []); // セグメント情報も保存
        setMessage('文字起こしが完了しました');
        
        // タスクIDがある場合はプログレス監視開始
        if (result.task_id) {
          setCurrentTaskId(result.task_id);
          monitorProgress(result.task_id);
          return; // monitorProgressが完了処理を行うため、ここでreturn
        }
      } else {
        setMessage('文字起こしに失敗しました');
      }
    } catch (error) {
      setMessage(`エラー: ${error}`);
    } finally {
      // プログレス監視が開始されない場合のみローディング終了
      if (!currentTaskId) {
        setLoading(false);
        setProgress(100);
      }
    }
  };

  const processVideo = async () => {
    if (!videoPath || !originalText || !editedText) {
      setMessage('必要な情報が不足しています');
      return;
    }

    setLoading(true);
    setProgress(0);
    setMessage('動画を処理中...');

    try {
      const result = await window.electronAPI.processVideo({
        video_path: videoPath,
        original_text: originalText,
        edited_text: editedText,
        transcription_segments: transcriptionSegments, // セグメント情報を追加
        remove_silence: removeSilence,
        output_video: outputVideo,
        noise_threshold: noiseThreshold,
        padding_start: paddingStart,
        padding_end: paddingEnd
      });

      if (result.success) {
        setMessage(`処理が完了しました: ${result.output_dir}`);
        
        // タスクIDがある場合はプログレス監視開始
        if (result.task_id) {
          setCurrentTaskId(result.task_id);
          monitorProgress(result.task_id);
          return; // monitorProgressが完了処理を行うため、ここでreturn
        }
      } else {
        setMessage(result.message || '処理に失敗しました');
      }
    } catch (error) {
      setMessage(`エラー: ${error}`);
    } finally {
      // プログレス監視が開始されない場合のみローディング終了
      if (!currentTaskId) {
        setLoading(false);
        setProgress(100);
      }
    }
  };

  return (
    <Container maxWidth="lg">
      <Box sx={{ my: 4 }}>
        <Typography variant="h3" component="h1" gutterBottom align="center">
          TextffCut Desktop
        </Typography>
        
        <Paper sx={{ p: 3, mb: 3 }}>
          <Typography variant="h5" gutterBottom>
            1. 動画ファイルを選択
          </Typography>
          <Stack direction="row" spacing={2} alignItems="center">
            <Button
              variant="contained"
              startIcon={<VideoFile />}
              onClick={selectVideo}
              disabled={loading}
            >
              動画を選択
            </Button>
            <Typography variant="body1" color="text.secondary">
              {videoPath || '未選択'}
            </Typography>
          </Stack>
        </Paper>

        <Paper sx={{ p: 3, mb: 3 }}>
          <Typography variant="h5" gutterBottom>
            2. 文字起こし
          </Typography>
          <Stack spacing={2}>
            <FormControl>
              <InputLabel>モデルサイズ</InputLabel>
              <Select
                value={modelSize}
                onChange={async (e) => {
                  const newModelSize = e.target.value;
                  setModelSize(newModelSize);
                  // モデル変更時もキャッシュチェック
                  if (videoPath) {
                    await checkCache(videoPath, newModelSize);
                  }
                }}
                disabled={loading}
              >
                {settings?.whisper_models?.map((model: string) => (
                  <MenuItem key={model} value={model}>{model}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <Stack direction="row" spacing={2}>
              {hasCache && (
                <Button
                  variant="outlined"
                  color="secondary"
                  onClick={loadFromCache}
                  disabled={loading || !cacheInfo}
                >
                  キャッシュから読み込み
                </Button>
              )}
              <Button
                variant="contained"
                startIcon={<Transcribe />}
                onClick={transcribeVideo}
                disabled={loading || !videoPath}
              >
                文字起こし実行
              </Button>
            </Stack>
          </Stack>
        </Paper>

        <Paper sx={{ p: 3, mb: 3 }}>
          <Typography variant="h5" gutterBottom>
            3. テキスト編集
          </Typography>
          <Box sx={{ display: 'flex', gap: 2 }}>
            <Box sx={{ flex: 1 }}>
              <Typography variant="h6" gutterBottom>
                文字起こし結果
              </Typography>
              <Box
                sx={{
                  height: 400,
                  border: '1px solid #ddd',
                  borderRadius: 1,
                  p: 2,
                  overflow: 'auto',
                  backgroundColor: '#f9f9f9',
                  fontFamily: 'monospace',
                  fontSize: '14px',
                  lineHeight: 1.5,
                }}
                dangerouslySetInnerHTML={{
                  __html: generateDiffView(originalText, editedText)
                }}
              />
            </Box>
            <Box sx={{ flex: 1 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                <Typography variant="h6">
                  編集テキスト
                </Typography>
                <Button
                  variant="outlined"
                  size="small"
                  onClick={() => {
                    // 強制的に再レンダリングをトリガーするため、一度別の値にする
                    setEditedText(prev => {
                      // 一度空にしてから元の値を設定することで、確実に再レンダリングを発生させる
                      setEditedText('');
                      setTimeout(() => setEditedText(prev), 10);
                      return prev;
                    });
                    setMessage('ハイライトを更新しました');
                  }}
                  disabled={loading || !originalText}
                >
                  ハイライト更新
                </Button>
              </Box>
              <TextField
                fullWidth
                multiline
                rows={17}
                value={editedText}
                onChange={(e) => setEditedText(e.target.value)}
                placeholder="文字起こし結果を編集してください"
                disabled={loading}
                sx={{
                  '& .MuiInputBase-root': {
                    fontFamily: 'monospace',
                    fontSize: '14px',
                  }
                }}
              />
            </Box>
          </Box>
        </Paper>

        <Paper sx={{ p: 3, mb: 3 }}>
          <Typography variant="h5" gutterBottom>
            4. 処理オプション
          </Typography>
          <Stack spacing={2}>
            <FormControlLabel
              control={
                <Switch
                  checked={removeSilence}
                  onChange={(e) => setRemoveSilence(e.target.checked)}
                  disabled={loading}
                />
              }
              label="無音部分を削除"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={outputVideo}
                  onChange={(e) => setOutputVideo(e.target.checked)}
                  disabled={loading}
                />
              }
              label="動画ファイルも出力"
            />
            {removeSilence && (
              <>
                <TextField
                  label="ノイズ閾値 (dB)"
                  type="number"
                  value={noiseThreshold}
                  onChange={(e) => setNoiseThreshold(Number(e.target.value))}
                  disabled={loading}
                />
                <TextField
                  label="開始パディング (秒)"
                  type="number"
                  value={paddingStart}
                  onChange={(e) => setPaddingStart(Number(e.target.value))}
                  disabled={loading}
                  inputProps={{ min: 0, max: 0.5, step: 0.1 }}
                />
                <TextField
                  label="終了パディング (秒)"
                  type="number"
                  value={paddingEnd}
                  onChange={(e) => setPaddingEnd(Number(e.target.value))}
                  disabled={loading}
                  inputProps={{ min: 0, max: 0.5, step: 0.1 }}
                />
              </>
            )}
          </Stack>
        </Paper>

        <Paper sx={{ p: 3, mb: 3 }}>
          <Button
            variant="contained"
            color="primary"
            size="large"
            fullWidth
            startIcon={<ContentCut />}
            onClick={processVideo}
            disabled={loading || !videoPath || !editedText}
          >
            動画を処理
          </Button>
        </Paper>

        {loading && (
          <Box sx={{ width: '100%', mb: 2 }}>
            <LinearProgress variant="determinate" value={progress} />
            {progressDetails && (
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
                <Typography variant="body2" color="text.secondary">
                  {progressDetails.message}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {Math.round(progress)}%
                </Typography>
              </Box>
            )}
          </Box>
        )}

        {message && (
          <Alert severity={message.includes('エラー') ? 'error' : 'info'}>
            {message}
          </Alert>
        )}
      </Box>
    </Container>
  );
}

export default App;
