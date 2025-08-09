# TextffCut パフォーマンス改善計画書 v5

## エグゼクティブサマリー

本改善計画は、**精度を維持しながらメモリ効率を最大化する**アプローチを提案します。主な方針：

1. **デフォルトでメモリ最適化**: WhisperXの内部処理に合わせた事前変換により、精度影響なしで92%のメモリ削減
2. **手動チャンク分割の完全削除**: WhisperXの内部VAD処理に委譲
3. **適応的エラー処理**: エラーから学習し、自動的に設定を調整
4. **シンプルな設定**: 「バランス」をデフォルトとし、ほとんどのユーザーが設定変更不要

## 核心的な発見

### WhisperXの内部処理を理解
- WhisperXは**必ず16kHz/モノラル**に変換して処理
- つまり、48kHz/ステレオの高品質音声を渡しても内部で変換される
- **事前に変換すればメモリを92%削減でき、精度は全く同じ**

### メモリ使用量の比較（90分動画）
| 形式 | メモリ使用量 | 精度への影響 |
|------|-------------|-------------|
| 元音声（48kHz/ステレオ/float32） | 2.1GB | - |
| 最適化済み（16kHz/モノラル/int16） | 173MB | なし |
| 削減率 | **92%削減** | **影響なし** |

## 改善計画

### 1. 音声処理の統一戦略

```python
class OptimizedAudioProcessor:
    """精度を保ちながらメモリ効率を最大化"""
    
    # デフォルト設定（WhisperX内部処理と同一）
    DEFAULT_SETTINGS = {
        'sample_rate': 16000,  # WhisperX内部と同じ
        'channels': 1,         # モノラル
        'bit_depth': 16,       # 16bit PCM
    }
    
    def prepare_audio(self, video_path: Path, mode: str) -> Union[Path, np.ndarray]:
        """用途に応じた最適な音声準備"""
        
        if mode == "api_upload":
            # API: ファイルサイズ制限のため圧縮
            return self._prepare_for_api(video_path)
        
        elif mode == "local_transcription":
            # ローカル: メモリ効率最適化（デフォルト）
            return self._prepare_for_local(video_path)
        
        elif mode == "alignment":
            # アライメント: わずかに高品質
            return self._prepare_for_alignment(video_path)
    
    def _prepare_for_local(self, video_path: Path) -> np.ndarray:
        """ローカル処理用: 常に最適化"""
        
        # 一時ファイルに最適化済み音声を作成
        temp_path = video_path.with_suffix('.optimized.wav')
        
        cmd = [
            'ffmpeg', '-i', str(video_path),
            '-vn',  # 映像除外
            '-ar', str(self.DEFAULT_SETTINGS['sample_rate']),
            '-ac', str(self.DEFAULT_SETTINGS['channels']),
            '-acodec', 'pcm_s16le',  # 16bit PCM
            '-y',  # 上書き
            str(temp_path)
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            audio = whisperx.load_audio(temp_path)
            
            # メモリ削減効果をログ
            original_size = video_path.stat().st_size
            optimized_size = temp_path.stat().st_size
            reduction = (1 - optimized_size / original_size) * 100
            
            logger.info(f"""
            音声最適化完了:
            - 元サイズ: {original_size / (1024**3):.1f}GB
            - 最適化後: {optimized_size / (1024**3):.1f}GB
            - 削減率: {reduction:.0f}%
            - 精度影響: なし
            """)
            
            return audio
            
        finally:
            temp_path.unlink(missing_ok=True)
    
    def _prepare_for_api(self, video_path: Path, target_bitrate: str = "32k") -> Path:
        """API送信用: 25MB制限に収める"""
        
        output_path = video_path.with_suffix(f'.api_{target_bitrate}.mp3')
        
        cmd = [
            'ffmpeg', '-i', str(video_path),
            '-vn',
            '-ar', '16000',  # API側でも変換されるので事前に削減
            '-ac', '1',
            '-ab', target_bitrate,
            '-f', 'mp3',
            str(output_path)
        ]
        
        subprocess.run(cmd, check=True)
        
        # ファイルサイズチェック
        if output_path.stat().st_size > 25 * 1024 * 1024:
            if target_bitrate != "24k":
                # より低いビットレートで再試行
                output_path.unlink()
                return self._prepare_for_api(video_path, "24k")
            else:
                raise ValueError("ファイルが大きすぎます。より短い動画に分割してください。")
        
        return output_path
    
    def _prepare_for_alignment(self, video_path: Path) -> Path:
        """アライメント用: やや高品質を維持"""
        
        output_path = video_path.with_suffix('.align.wav')
        
        cmd = [
            'ffmpeg', '-i', str(video_path),
            '-vn',
            '-ar', '16000',  # 基本は同じ
            '-ac', '1',
            '-acodec', 'pcm_s24le',  # 24bit（少し高品質）
            str(output_path)
        ]
        
        subprocess.run(cmd, check=True)
        return output_path
```

### 2. パフォーマンスプロファイルの簡素化

```python
@dataclass
class PerformanceProfile:
    """シンプルで効果的な設定管理"""
    
    # メモリ最適化レベル
    memory_optimization: str = "balanced"  # "maximum_quality", "balanced", "maximum_memory_saving"
    
    # 処理設定（自動調整）
    batch_size: Optional[int] = None
    compute_type: Optional[str] = None
    
    # エラー履歴による学習
    error_history: List[Dict] = field(default_factory=list)
    success_history: List[Dict] = field(default_factory=list)
    
    def get_audio_settings(self) -> dict:
        """メモリ最適化レベルに応じた音声設定"""
        
        settings = {
            "maximum_quality": {
                # 実質的に不要（WhisperXが変換するため）
                'optimize_memory': False,
                'description': '無圧縮（非推奨）'
            },
            "balanced": {
                # デフォルト推奨
                'optimize_memory': True,
                'sample_rate': 16000,
                'channels': 1,
                'bit_depth': 16,
                'description': 'メモリ92%削減、精度影響なし'
            },
            "maximum_memory_saving": {
                # 極限までメモリ削減
                'optimize_memory': True,
                'sample_rate': 16000,
                'channels': 1,
                'bit_depth': 8,  # 8bit（品質低下の可能性）
                'api_bitrate': '16k',
                'description': 'メモリ95%削減、品質低下の可能性'
            }
        }
        
        return settings[self.memory_optimization]
    
    def get_processing_config(self) -> dict:
        """処理設定の取得"""
        
        base_config = {
            'use_manual_chunks': False,  # 常にFalse（WhisperXに委譲）
            'batch_size': self.batch_size or self._get_default_batch_size(),
            'compute_type': self.compute_type or 'int8',
        }
        
        # エラー履歴に基づく自動調整
        if len(self.error_history) > 0:
            last_error = self.error_history[-1]
            if "OutOfMemoryError" in last_error['error_type']:
                base_config['batch_size'] = max(1, base_config['batch_size'] // 2)
                base_config['memory_optimization'] = "maximum_memory_saving"
        
        return base_config
    
    def _get_default_batch_size(self) -> int:
        """メモリ最適化レベルに応じたデフォルトバッチサイズ"""
        
        if self.memory_optimization == "maximum_memory_saving":
            return 2
        elif self.memory_optimization == "balanced":
            return 4
        else:
            return 8
```

### 3. 統合処理エンジン

```python
class UnifiedTranscriber:
    """APIとローカルを統一的に処理"""
    
    def __init__(self, config: Config, profile: PerformanceProfile):
        self.config = config
        self.profile = profile
        self.audio_processor = OptimizedAudioProcessor()
    
    def transcribe(self, video_path: Path) -> TranscriptionResult:
        """メイン処理"""
        
        if self.config.use_api:
            return self._transcribe_api(video_path)
        else:
            return self._transcribe_local(video_path)
    
    def _transcribe_local(self, video_path: Path) -> TranscriptionResult:
        """ローカル処理（最適化済み）"""
        
        # 1. 音声を最適化（デフォルトで有効）
        audio = self.audio_processor.prepare_audio(
            video_path, 
            mode="local_transcription"
        )
        
        # 2. 処理設定を取得
        config = self.profile.get_processing_config()
        
        # 3. モデル読み込み
        model = whisperx.load_model(
            self.config.model_size,
            self.device,
            compute_type=config['compute_type'],
            language=self.config.language
        )
        
        # 4. WhisperXに完全委譲（手動チャンク分割なし）
        result = model.transcribe(
            audio,
            batch_size=config['batch_size'],
            language=self.config.language
        )
        
        # 5. アライメント（必要に応じて）
        if self.config.enable_alignment:
            # 同じ最適化済み音声を使用
            result = self._perform_alignment(result, audio)
        
        return result
    
    def _transcribe_api(self, video_path: Path) -> TranscriptionResult:
        """API処理（ファイルサイズ最適化）"""
        
        # 1. API用に圧縮
        api_audio = self.audio_processor.prepare_audio(
            video_path,
            mode="api_upload"
        )
        
        try:
            # 2. 単一API呼び出し（チャンク分割なし）
            with open(api_audio, 'rb') as f:
                response = self.api_client.transcribe(f)
            
            # 3. アライメント（必要に応じて）
            if self.config.enable_alignment:
                align_audio = self.audio_processor.prepare_audio(
                    video_path,
                    mode="alignment"
                )
                result = self._perform_alignment(response, align_audio)
            
            return result
            
        finally:
            api_audio.unlink(missing_ok=True)
```

### 4. UI実装（シンプル化）

```python
def render_performance_settings():
    """シンプルなパフォーマンス設定UI"""
    
    with st.expander("⚙️ パフォーマンス設定", expanded=False):
        
        # メモリ最適化レベル
        optimization = st.select_slider(
            "メモリ最適化",
            options=["maximum_quality", "balanced", "maximum_memory_saving"],
            value="balanced",
            format_func=lambda x: {
                "maximum_quality": "最大品質（非推奨）",
                "balanced": "バランス（推奨）⭐",
                "maximum_memory_saving": "省メモリ"
            }[x],
            help="""
            **バランス（推奨）**: メモリ92%削減、精度影響なし
            最大品質: 無圧縮（メリットなし）
            省メモリ: さらなる削減（品質低下の可能性）
            """
        )
        
        # 設定の効果を表示
        if optimization == "balanced":
            st.success("""
            ✅ **推奨設定が選択されています**
            - 90分動画: 2.1GB → 173MB（92%削減）
            - 精度への影響: なし
            - M1 Mac 8GBでも処理可能
            """)
        elif optimization == "maximum_quality":
            st.warning("""
            ⚠️ この設定は推奨されません
            - WhisperXが内部で変換するため、メリットがありません
            - メモリを無駄に消費します
            """)
        
        # 詳細設定（オプション）
        if st.checkbox("詳細設定", value=False):
            col1, col2 = st.columns(2)
            
            with col1:
                batch_size = st.number_input(
                    "バッチサイズ",
                    min_value=1,
                    max_value=16,
                    value=4,
                    help="メモリエラーが発生する場合は減らしてください"
                )
            
            with col2:
                compute_type = st.selectbox(
                    "計算精度",
                    ["int8", "float16", "float32"],
                    help="int8が最もメモリ効率的"
                )
```

## 実装のメリット

### 1. メモリ効率の大幅改善
- **デフォルトで92%のメモリ削減**
- **精度への影響なし**（WhisperXの内部処理と同一）
- M1 Mac 8GBでも90分動画を安定処理

### 2. コードの簡素化
- 手動チャンク分割コードを完全削除
- 音声処理を統一的に管理
- エラー処理を一元化

### 3. ユーザー体験の向上
- デフォルト設定で最適動作
- 設定項目を最小限に
- エラー時の自動回復

### 4. 保守性の向上
- WhisperXの更新に自動対応
- 設定の意図が明確
- テストが容易

## 実装スケジュール

### フェーズ1: 音声処理の統一（3日）
- [ ] OptimizedAudioProcessorの実装
- [ ] 既存の音声読み込み処理を置き換え
- [ ] メモリ削減効果の測定

### フェーズ2: チャンク分割の削除（2日）
- [ ] 手動チャンク分割コードの削除
- [ ] WhisperX直接呼び出しへの移行
- [ ] 統合テスト

### フェーズ3: UI/UXの簡素化（2日）
- [ ] パフォーマンス設定UIの実装
- [ ] デフォルト設定の最適化
- [ ] ユーザーガイドの作成

### フェーズ4: エラー処理の実装（3日）
- [ ] 適応的エラー処理の実装
- [ ] 設定の永続化
- [ ] 総合テスト

## リスクと対策

| リスク | 影響 | 対策 |
|--------|------|------|
| 8bit音声での品質低下 | 低 | デフォルトは16bit、8bitはオプション |
| 既存ユーザーへの影響 | 中 | 移行ガイドとデフォルト設定で対応 |
| WhisperX仕様変更 | 低 | 16kHz/モノラルは業界標準 |

## まとめ

本改善計画により：

1. **全ユーザーがメモリ効率的に使用可能**
   - デフォルトで92%のメモリ削減
   - 精度への影響なし

2. **シンプルで分かりやすい設定**
   - 「バランス」推奨で迷わない
   - 技術的詳細を隠蔽

3. **将来性のある実装**
   - WhisperXの内部処理に合わせた設計
   - 拡張性と保守性を確保

これにより、M1 Mac 8GBから高性能ワークステーションまで、すべての環境で最適なパフォーマンスを実現します。

---

最終更新: 2025-01-26
バージョン: 5.0（メモリ効率最大化版）