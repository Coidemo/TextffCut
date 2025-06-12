# TextffCut 代替技術スタック分析

## 現状の課題
- Streamlit × PyInstaller: 356MB～1.35GB、起動に問題
- CLI/Video版は成功（7MB）だが、UIが必要

## 評価基準
1. **開発効率**: 既存Pythonコードの活用度
2. **配布サイズ**: 目標100MB以下
3. **クロスプラットフォーム**: Windows/Mac必須
4. **ユーザビリティ**: インストール・使用の簡単さ
5. **将来性**: WhisperX統合の可能性

## 🏆 推奨技術スタック（優先順）

### 1. **Flet** ⭐最推奨
```python
import flet as ft

def main(page):
    file_picker = ft.FilePicker()
    page.add(
        ft.Text("TextffCut", size=30),
        ft.ElevatedButton("動画を選択", on_click=lambda _: file_picker.pick_files())
    )

ft.app(target=main)
```

**メリット**
- ✅ Pythonのみで開発（学習コスト最小）
- ✅ モダンUI（Flutter ベース）
- ✅ `flet build macos/windows`で簡単ビルド
- ✅ PWA対応（Web版も同時提供可能）
- ✅ 2024年も活発に開発中

**デメリット**
- ❌ パッケージサイズ未検証（推定50-100MB）
- ❌ 比較的新しい（2023年～）

**移行工数**: 1-2週間

---

### 2. **PyWebView + FastAPI** ⭐実用的
```python
# backend.py (FastAPI)
from fastapi import FastAPI
app = FastAPI()

@app.post("/transcribe")
async def transcribe(file_path: str):
    # 既存のcore/モジュールを使用
    return {"status": "success"}

# frontend.py (PyWebView)
import webview
webview.create_window('TextffCut', 'http://localhost:8000')
webview.start()
```

**メリット**
- ✅ 超軽量（WebViewのみ、重いGUIツールキットなし）
- ✅ 既存のStreamlit UIをHTML/CSSで再利用可能
- ✅ PyInstallerで10-20MB程度
- ✅ システムのWebViewを使用（Safari/Edge）

**デメリット**
- ❌ HTML/CSS/JSの作業が必要
- ❌ ネイティブ機能に制限

**移行工数**: 2-3週間

---

### 3. **Tauri + Python Backend**
```javascript
// Tauri (Rust + JS)
invoke('transcribe', { filePath: '/path/to/video.mp4' })
```

**メリット**
- ✅ 最軽量（600KB + Python部分）
- ✅ 最高速
- ✅ セキュア（Rust）

**デメリット**
- ❌ Rust/JS知識が必要
- ❌ 開発の複雑さ
- ❌ Python部分の配布が別途必要

**移行工数**: 3-4週間

---

### 4. **PyQt6/PySide6**
```python
from PySide6.QtWidgets import QApplication, QMainWindow
# ネイティブUIだが学習コスト高
```

**メリット**
- ✅ 成熟・安定
- ✅ 完全なネイティブUI
- ✅ 豊富な機能

**デメリット**
- ❌ LGPLライセンス（商用利用時要確認）
- ❌ 学習コスト高
- ❌ パッケージサイズ大（100MB+）

**移行工数**: 3-4週間

---

## 📊 比較表

| 技術スタック | サイズ目安 | 開発速度 | 将来性 | 既存資産活用 |
|------------|----------|---------|--------|------------|
| Flet | 50-100MB | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| PyWebView+FastAPI | 10-20MB | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Tauri+Python | 20-50MB | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| PyQt6 | 100MB+ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |

## 🎯 推奨アクションプラン

### Phase 1: Flet POC（1週間）
1. Fletで最小限のUIを実装
2. 動画選択・情報表示機能
3. Windows/Macでビルドテスト
4. サイズ・パフォーマンス評価

### Phase 2: 本実装（2-3週間）
1. 選定した技術で全機能実装
2. 既存core/モジュールの統合
3. CI/CD設定
4. 配布パッケージ作成

### Phase 3: 最適化（1週間）
1. パッケージサイズ最適化
2. 起動速度改善
3. ユーザーテスト

## 💡 結論

**Flet**を第一候補として推奨します。理由：
1. Pythonのみで開発可能（既存チームのスキルセット）
2. モダンで美しいUI（Flutter）
3. 開発速度が最速
4. Web版も同時に提供可能（PWA）

バックアッププランとして**PyWebView+FastAPI**も検討価値があります。