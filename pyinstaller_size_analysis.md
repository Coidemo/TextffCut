# PyInstaller ファイルサイズ分析

## 現在のビルド結果

| バージョン | サイズ | 状態 | 含まれるもの |
|----------|-------|-----|------------|
| TextffCut_MVP (Streamlit版) | 341MB | 起動に課題 | Streamlit + 全依存関係 |
| TextffCut_CLI | 7.1MB | ✅ 正常動作 | 純Python（標準ライブラリのみ） |

## サイズの内訳予測

### TextffCut_MVP (341MB)
- Streamlit本体: ~50MB
- NumPy: ~20MB
- Pandas: ~40MB
- PyArrow: ~80MB
- Altair (可視化): ~30MB
- その他依存関係: ~120MB

### 最適化の方針

1. **不要な依存関係の除外**
   ```python
   # pyinstaller で除外
   --exclude-module matplotlib
   --exclude-module scipy
   --exclude-module sklearn
   ```

2. **段階的な機能追加**
   - Phase 1: CLI版 (7MB) ✅
   - Phase 2: + ffmpeg-python (10MB予想)
   - Phase 3: + OpenAI API (15MB予想)
   - Phase 4: + WhisperX (1GB予想)

3. **UPX圧縮の検討**
   - 30-50%のサイズ削減可能
   - 起動時間が遅くなるトレードオフ

## 次のステップ

1. Phase 2の実装（動画処理機能）
2. Windows版のクロスビルドテスト
3. GitHub Actionsでの自動ビルド設定