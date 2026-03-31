# TextffCut MLX-Whisper統合セッション (2026-03-29)

## 完了した作業

### 1. mlx-forced-aligner (新規リポジトリ)
- **GitHub**: https://github.com/Coidemo/mlx-forced-aligner
- **HuggingFace**: https://huggingface.co/Coidemo/wav2vec2-japanese-mlx
- wav2vec2 (jonatasgrosman/wav2vec2-large-xlsr-53-japanese) をMLXに移植
- torch完全不要、PyTorchと推論結果が完全一致 (max_diff < 0.002)
- WhisperX互換のViterbiアルゴリズム（trellis+backtrack方式）
- 先頭/末尾のblank区間トリム
- <unk>トークンを元テキスト文字に復元
- 1文字=1word出力（日本語WhisperX互換）
- HuggingFace Hubから自動ダウンロード対応
- **重要な修正**: weight_normのnorm次元バグ修正 (dim=(0,1)が正解、(1,2)は誤り)

### 2. TextffCut MLXバックエンド (PR #91 MERGED)
- **PR**: https://github.com/Coidemo/TextffCut/pull/91
- ブランチ: feature/mlx-whisper → main にマージ済み
- 変更ファイル: 11ファイル, +643行
- Apple Silicon Macで自動的にMLXを使用、それ以外はWhisperXにフォールバック

#### 変更ファイル一覧
- `utils/environment.py`: IS_APPLE_SILICON, MLX_AVAILABLE検出
- `config.py`: use_mlx_whisper設定 + TEXTFFCUT_USE_MLX_WHISPER環境変数
- `core/transcription.py`: _transcribe_mlxメソッド、MLX_MODEL_MAP、ForcedAlignerキャッシュ
- `adapters/gateways/transcription/optimized_transcription_gateway.py`: MLXモード分岐、safe_callback
- `domain/entities/transcription.py`: confidence範囲外をNoneにリセット
- `domain/use_cases/character_array_builder.py`: charsベース構築（wordsが1文字超の場合のみ）
- `presentation/`: モデル選択ドロップダウン（medium, large-v3, large-v3-turbo, small, base）
- `requirements-mlx.txt`: mlx-whisper>=0.4.0, mlx-forced-aligner>=0.1.0

### 3. ベンチマーク結果 (30分動画)
| パイプライン | 合計時間 | 速度比 |
|---|---|---|
| WhisperX medium | 524s (8.7分) | 1x |
| MLX medium | 99s (1.7分) | **5.2x** |
| MLX large-v3 | 179s (3.0分) | **2.9x** |

### 4. アライメント品質 (修正後)
- 全体: WX 28% vs MLX 27% (20ms以下の文字割合、同等)
- 同一テキスト比較: WX 28% vs MLX 8% (MLXが優秀)

## レビューで修正した問題
1. durationにprocessing_timeを設定 → セグメント末尾時間
2. progress_callback型不一致 → safe_callbackでラップ
3. get_full_text()がMLXで失敗 → chars/textフォールバック
4. CoreTranscriber毎回生成 → _legacy_transcriber再利用
5. デフォルトモデルがlarge-v3 → medium維持
6. Adapter→Core逆依存 → 親クラスのインスタンス再利用
7. モデルマッピング重複 → Transcriber.MLX_MODEL_MAP参照
8. ForcedAligner毎回生成 → self._mlx_alignerキャッシュ
9. コメント不正確 → 修正
10. ゼロ除算ガード → 追加
11. charsパスがWhisperXに影響 → wordsが1文字超の場合のみ

## 次にやること（未着手）
1. **CLIパイプライン**: `python cli.py video.mp4 --anthropic-key sk-ant-xxx`
   - mlx-whisper → mlx-forced-aligner → Claude API(バズクリップ) → FCPXML
   - AnthropicGateway新規作成
   - prompts/clip_suggestions_json.md (JSON出力版プロンプト)
   - pipeline.py (オーケストレーター)
2. **テキスト差分検出の改善**: 残すテキストが不連続な場合に時間範囲を分割する
3. **TextffCutのworktree**: hopeful-lehmannで作業中。mainへの反映確認が必要
