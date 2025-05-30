# TextffCut Desktop App

## Electron + FastAPI アーキテクチャ

### セットアップ手順

```bash
# 1. Python環境（既存）
pip install fastapi uvicorn python-multipart

# 2. Node.js環境
cd desktop
npm init -y
npm install --save-dev electron electron-builder
npm install axios

# 3. React環境（frontend）
cd frontend
npx create-react-app . --template typescript
npm install axios @mui/material @emotion/react @emotion/styled
```

### 開発の開始

```bash
# Terminal 1: FastAPI サーバー
cd api
uvicorn main:app --reload --port 8000

# Terminal 2: React開発サーバー
cd desktop/frontend
npm start

# Terminal 3: Electron
cd desktop
npm run electron-dev
```

### プロトタイプ実装の優先順位

1. **最小限の動作確認（MVP）**
   - ファイル選択
   - 文字起こし実行
   - 結果表示

2. **基本機能**
   - プログレスバー
   - エラーハンドリング
   - 設定保存

3. **完全機能**
   - 全機能の統合
   - パッケージング
   - 自動更新