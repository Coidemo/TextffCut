# Electron + FastAPIの「ローカルサーバー」の仕組み

## 🏠 完全にローカルで動作

### 動作イメージ

```
ユーザーのPC内部
┌─────────────────────────────────────┐
│                                     │
│  ① TextffCutアプリを起動            │
│     ↓                               │
│  ② Electronが起動                   │
│     ↓                               │
│  ③ 内部でPythonサーバーも起動        │
│     (localhost:8000など)            │
│     ↓                               │
│  ④ ElectronとPythonが通信           │
│     (全てPC内部で完結)              │
│                                     │
│  インターネット接続不要 ❌            │
│  外部サーバー不要 ❌                  │
│                                     │
└─────────────────────────────────────┘
```

### 具体的な流れ

1. **アプリ起動時**
   ```javascript
   // Electronのmain.js
   const { spawn } = require('child_process');
   
   // Pythonサーバーを子プロセスとして起動
   const apiServer = spawn('python', ['api/main.py']);
   
   // Electronウィンドウを開く
   createWindow();
   ```

2. **処理実行時**
   ```javascript
   // ユーザーが「文字起こし」ボタンをクリック
   async function transcribe() {
     // localhost（自分のPC）のAPIを呼ぶ
     const response = await fetch('http://localhost:8000/api/transcribe', {
       method: 'POST',
       body: JSON.stringify({ video_path: selectedFile })
     });
   }
   ```

3. **アプリ終了時**
   ```javascript
   // Pythonサーバーも一緒に終了
   apiServer.kill();
   ```

## 🔍 メリット・デメリット

### メリット
- **完全オフライン動作** 
- **プライバシー保護**（動画データが外部に出ない）
- **高速処理**（ネットワーク遅延なし）
- **モダンなUI**（Web技術を活用）

### デメリット
- **少し複雑**（2つのプロセスが動く）
- **ポート競合の可能性**（8000番が使用中など）
- **起動が少し遅い**（サーバー起動待ち）

## 🆚 PyQt6との違い

### Electron + FastAPI（ローカルサーバーあり）
```
[Electronアプリ] ←HTTP通信→ [Pythonサーバー(localhost)]
```
- 2つのプロセス
- Web技術でUI構築
- 少し複雑

### PyQt6（サーバーなし）
```
[PyQt6アプリ（Python直接実行）]
```
- 1つのプロセス
- ネイティブUI
- シンプル

## 💡 つまり

「サーバーを立てる」と言っても：
- ❌ クラウドサーバーではない
- ❌ インターネット経由ではない
- ✅ ユーザーのPC内で完結
- ✅ アプリの内部的な仕組み

VSCodeも同じような仕組みです（Electron + 内部サーバー）。