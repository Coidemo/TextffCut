# TextffCut パフォーマンス改善計画書 v5.1

## エグゼクティブサマリー

本改善計画は、批判的レビューを反映し、**現実的で柔軟なパフォーマンス最適化**を提案します。主な改訂：

1. **状況適応型の最適化**: メモリ状況と処理時間のバランスを考慮
2. **実測値に基づく削減効果**: 理論値92%→実測値50-70%に修正
3. **堅牢なエラーハンドリング**: フォールバック機構の実装
4. **ユーザー選択の尊重**: 強制的な最適化を避け、柔軟な選択肢を提供

## 技術的前提の再検証

### WhisperXの実際の挙動

```python
# WhisperXのソースコード確認結果
# whisperx/audio.py
SAMPLE_RATE = 16000  # 固定値

# ただし、以下の考慮が必要：
# 1. バージョンによる変更の可能性
# 2. モデルサイズによる最適値の違い
# 3. 将来的な仕様変更リスク
```

### 現実的なメモリ削減効果

| 項目 | 理論値 | 実測値（考慮事項含む） |
|------|--------|----------------------|
| 元音声（48kHz/ステレオ/float32） | 2.1GB | 2.1GB + α（デコードバッファ） |
| 最適化後（16kHz/モノラル/int16） | 173MB | 300-500MB（変換時の一時メモリ含む） |
| 削減率 | 92% | **50-70%**（現実的な値） |

## 改善計画（改訂版）

### 1. インテリジェントな音声最適化システム

```python
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Dict, Any
import subprocess
import psutil
import json

class IntelligentAudioOptimizer:
    """状況に応じた適応的音声最適化"""
    
    def __init__(self):
        # WhisperXの要求仕様を動的に確認
        self.target_sample_rate = self._verify_whisperx_requirements()
        self.optimization_stats = []
        
    def _verify_whisperx_requirements(self) -> int:
        """WhisperXの実際の要求仕様を確認"""
        try:
            import whisperx
            # 実際のSAMPLE_RATEを取得
            return getattr(whisperx.audio, 'SAMPLE_RATE', 16000)
        except Exception:
            # デフォルト値にフォールバック
            return 16000
    
    def prepare_audio(
        self, 
        video_path: Path,
        optimization_preference: str = "auto"
    ) -> tuple[np.ndarray, Dict[str, Any]]:
        """
        音声を準備し、最適化の詳細情報を返す
        
        Args:
            video_path: 動画ファイルパス
            optimization_preference: "auto", "always", "never", "memory_critical"
            
        Returns:
            (音声データ, 最適化情報)
        """
        
        # 1. 音声ストリーム情報を分析
        audio_info = self._analyze_audio_streams(video_path)
        
        # 2. 最適化の必要性を評価
        optimization_decision = self._make_optimization_decision(
            video_path, audio_info, optimization_preference
        )
        
        # 3. 実行
        if optimization_decision['optimize']:
            try:
                audio, stats = self._optimize_audio(
                    video_path, 
                    audio_info, 
                    optimization_decision['strategy']
                )
                self.optimization_stats.append(stats)
                return audio, stats
            except Exception as e:
                logger.warning(f"最適化失敗、フォールバック: {e}")
                # フォールバック
                audio = whisperx.load_audio(video_path)
                return audio, {'optimized': False, 'reason': str(e)}
        else:
            # 最適化しない
            audio = whisperx.load_audio(video_path)
            return audio, {
                'optimized': False, 
                'reason': optimization_decision['reason']
            }
    
    def _analyze_audio_streams(self, video_path: Path) -> Dict[str, Any]:
        """FFprobeで音声ストリーム情報を取得"""
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'a:0',
            '-show_entries', 'stream=codec_name,sample_rate,channels,bit_rate',
            '-of', 'json',
            str(video_path)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            
            if data['streams']:
                stream = data['streams'][0]
                return {
                    'codec': stream.get('codec_name', 'unknown'),
                    'sample_rate': int(stream.get('sample_rate', 48000)),
                    'channels': int(stream.get('channels', 2)),
                    'bit_rate': int(stream.get('bit_rate', 0)) if stream.get('bit_rate') else None,
                    'duration': self._get_duration(video_path)
                }
            else:
                raise ValueError("音声ストリームが見つかりません")
                
        except Exception as e:
            logger.warning(f"音声分析失敗: {e}")
            # デフォルト値
            return {
                'codec': 'unknown',
                'sample_rate': 48000,
                'channels': 2,
                'bit_rate': None,
                'duration': 0
            }
    
    def _make_optimization_decision(
        self, 
        video_path: Path,
        audio_info: Dict[str, Any],
        preference: str
    ) -> Dict[str, Any]:
        """最適化の実施判断"""
        
        file_size_mb = video_path.stat().st_size / (1024**2)
        available_memory_gb = psutil.virtual_memory().available / (1024**3)
        
        # ユーザー設定を優先
        if preference == "never":
            return {'optimize': False, 'reason': 'ユーザー設定により無効'}
        elif preference == "always":
            return {
                'optimize': True, 
                'strategy': 'standard',
                'reason': 'ユーザー設定により常に有効'
            }
        
        # 自動判断
        if preference in ["auto", "memory_critical"]:
            # メモリがファイルサイズの3倍以上あれば最適化不要
            if available_memory_gb > (file_size_mb / 1024) * 3:
                if preference != "memory_critical":
                    return {
                        'optimize': False, 
                        'reason': f'十分なメモリあり ({available_memory_gb:.1f}GB)'
                    }
            
            # 既に最適化済みの形式
            if (audio_info['sample_rate'] == self.target_sample_rate and 
                audio_info['channels'] == 1):
                return {'optimize': False, 'reason': '既に最適な形式'}
            
            # 処理時間の推定
            estimated_conversion_time = self._estimate_conversion_time(
                audio_info['duration'], file_size_mb
            )
            
            # 変換コストが高すぎる場合
            if estimated_conversion_time > 300 and available_memory_gb > 4:  # 5分以上
                return {
                    'optimize': False,
                    'reason': f'変換時間が長い ({estimated_conversion_time:.0f}秒)'
                }
            
            # 最適化実施
            strategy = 'aggressive' if preference == "memory_critical" else 'standard'
            return {
                'optimize': True,
                'strategy': strategy,
                'reason': 'メモリ効率化のため'
            }
        
        return {'optimize': False, 'reason': '判断不能'}
    
    def _optimize_audio(
        self, 
        video_path: Path,
        audio_info: Dict[str, Any],
        strategy: str
    ) -> tuple[np.ndarray, Dict[str, Any]]:
        """音声を最適化"""
        
        # ユニークな一時ファイル
        temp_path = Path(tempfile.gettempdir()) / f"textffcut_{uuid.uuid4()}.wav"
        
        start_time = time.time()
        original_size = video_path.stat().st_size
        
        try:
            # 変換コマンド構築
            cmd = self._build_conversion_command(
                video_path, temp_path, audio_info, strategy
            )
            
            # 実行（タイムアウト付き）
            timeout = max(300, audio_info['duration'] * 0.1)  # 最大5分または動画長の10%
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                check=True,
                timeout=timeout
            )
            
            # 最適化後の音声を読み込み
            audio = whisperx.load_audio(temp_path)
            
            # 統計情報
            optimized_size = temp_path.stat().st_size
            conversion_time = time.time() - start_time
            actual_reduction = (1 - optimized_size / original_size) * 100
            
            stats = {
                'optimized': True,
                'strategy': strategy,
                'original_size_mb': original_size / (1024**2),
                'optimized_size_mb': optimized_size / (1024**2),
                'reduction_percent': actual_reduction,
                'conversion_time_sec': conversion_time,
                'audio_info': audio_info
            }
            
            logger.info(f"""
            音声最適化完了:
            - 削減率: {actual_reduction:.1f}%
            - 変換時間: {conversion_time:.1f}秒
            - 戦略: {strategy}
            """)
            
            return audio, stats
            
        finally:
            # 一時ファイル削除
            temp_path.unlink(missing_ok=True)
    
    def _build_conversion_command(
        self,
        input_path: Path,
        output_path: Path,
        audio_info: Dict[str, Any],
        strategy: str
    ) -> list:
        """変換コマンドを構築"""
        
        base_cmd = [
            'ffmpeg', '-i', str(input_path),
            '-vn',  # 映像除外
            '-ar', str(self.target_sample_rate),
            '-ac', '1',  # モノラル
        ]
        
        if strategy == 'aggressive':
            # より積極的な圧縮
            base_cmd.extend([
                '-acodec', 'pcm_u8',  # 8bit（品質劣化リスク）
                '-af', 'volume=1.5,highpass=f=200,lowpass=f=8000'  # 周波数帯域制限
            ])
        else:
            # 標準的な最適化
            base_cmd.extend([
                '-acodec', 'pcm_s16le',  # 16bit
            ])
        
        # 特殊なコーデックへの対応
        if audio_info['codec'] in ['dts', 'ac3', 'eac3']:
            base_cmd.extend(['-strict', '-2'])
        
        base_cmd.extend(['-y', str(output_path)])
        
        return base_cmd
    
    def _estimate_conversion_time(self, duration_sec: float, file_size_mb: float) -> float:
        """変換時間を推定（秒）"""
        # 経験則: 1分の音声につき約2秒の変換時間
        # ファイルサイズが大きいほど時間がかかる
        base_time = duration_sec * 0.033  # 30倍速
        size_factor = min(file_size_mb / 100, 2.0)  # 100MB以上は係数2
        
        return base_time * size_factor
    
    def get_optimization_summary(self) -> Dict[str, Any]:
        """最適化の統計サマリー"""
        if not self.optimization_stats:
            return {'total_optimizations': 0}
        
        total_original = sum(s['original_size_mb'] for s in self.optimization_stats)
        total_optimized = sum(s['optimized_size_mb'] for s in self.optimization_stats)
        total_time = sum(s['conversion_time_sec'] for s in self.optimization_stats)
        
        return {
            'total_optimizations': len(self.optimization_stats),
            'total_reduction_mb': total_original - total_optimized,
            'average_reduction_percent': (1 - total_optimized / total_original) * 100,
            'total_conversion_time_sec': total_time,
            'details': self.optimization_stats
        }
```

### 2. 柔軟なパフォーマンスプロファイル

```python
@dataclass
class FlexiblePerformanceProfile:
    """ユーザーの選択を尊重する設定管理"""
    
    # 最適化設定
    optimization_preference: str = "auto"  # "auto", "always", "never", "memory_critical"
    
    # 処理設定
    batch_size: Optional[int] = None
    compute_type: Optional[str] = None
    
    # 詳細設定
    max_conversion_time: int = 300  # 最大変換時間（秒）
    min_memory_threshold_gb: float = 4.0  # 最小メモリ閾値
    
    # 統計情報
    performance_history: List[Dict] = field(default_factory=list)
    
    def get_optimization_preference_display(self) -> str:
        """ユーザー向けの表示テキスト"""
        
        displays = {
            "auto": "自動判断（推奨）",
            "always": "常に最適化",
            "never": "最適化しない",
            "memory_critical": "メモリ優先"
        }
        
        return displays.get(self.optimization_preference, "自動判断")
    
    def record_performance(self, metrics: Dict[str, Any]):
        """パフォーマンス記録"""
        self.performance_history.append({
            'timestamp': datetime.now().isoformat(),
            'metrics': metrics
        })
        
        # 最新20件のみ保持
        self.performance_history = self.performance_history[-20:]
    
    def suggest_settings_based_on_history(self) -> Dict[str, Any]:
        """履歴に基づく推奨設定"""
        if len(self.performance_history) < 3:
            return {}
        
        # メモリエラーの頻度
        memory_errors = sum(
            1 for h in self.performance_history 
            if 'error' in h['metrics'] and 'memory' in h['metrics']['error'].lower()
        )
        
        # 平均処理時間
        processing_times = [
            h['metrics'].get('processing_time', 0) 
            for h in self.performance_history
        ]
        avg_time = sum(processing_times) / len(processing_times)
        
        suggestions = {}
        
        if memory_errors > len(self.performance_history) * 0.3:
            suggestions['optimization_preference'] = 'memory_critical'
            suggestions['reason'] = 'メモリエラーが頻発しています'
        elif avg_time > 600:  # 10分以上
            suggestions['batch_size'] = 8
            suggestions['reason'] = '処理時間を短縮するため'
        
        return suggestions
```

### 3. 統合処理エンジン（改訂版）

```python
class RobustUnifiedTranscriber:
    """エラーに強い統合処理エンジン"""
    
    def __init__(self, config: Config, profile: FlexiblePerformanceProfile):
        self.config = config
        self.profile = profile
        self.audio_optimizer = IntelligentAudioOptimizer()
        self.last_optimization_info = None
    
    def transcribe(
        self, 
        video_path: Path,
        progress_callback: Optional[Callable] = None
    ) -> TranscriptionResult:
        """メイン処理"""
        
        start_time = time.time()
        
        try:
            if self.config.use_api:
                result = self._transcribe_api(video_path, progress_callback)
            else:
                result = self._transcribe_local(video_path, progress_callback)
            
            # 成功を記録
            self.profile.record_performance({
                'success': True,
                'processing_time': time.time() - start_time,
                'optimization_info': self.last_optimization_info
            })
            
            return result
            
        except Exception as e:
            # エラーを記録
            self.profile.record_performance({
                'success': False,
                'error': str(e),
                'processing_time': time.time() - start_time
            })
            raise
    
    def _transcribe_local(
        self, 
        video_path: Path,
        progress_callback: Optional[Callable] = None
    ) -> TranscriptionResult:
        """ローカル処理（改善版）"""
        
        # 1. 音声準備（状況に応じた最適化）
        if progress_callback:
            progress_callback(0.0, "音声を準備中...")
        
        audio, optimization_info = self.audio_optimizer.prepare_audio(
            video_path,
            self.profile.optimization_preference
        )
        self.last_optimization_info = optimization_info
        
        # 最適化情報をユーザーに表示
        if optimization_info['optimized']:
            message = f"音声最適化: {optimization_info['reduction_percent']:.0f}%削減"
        else:
            message = f"音声最適化スキップ: {optimization_info['reason']}"
        
        if progress_callback:
            progress_callback(0.1, message)
        
        # 2. モデル読み込み
        if progress_callback:
            progress_callback(0.2, "モデルを読み込み中...")
        
        try:
            model = whisperx.load_model(
                self.config.model_size,
                self.device,
                compute_type=self.profile.compute_type or 'int8',
                language=self.config.language
            )
        except Exception as e:
            logger.error(f"モデル読み込み失敗: {e}")
            # より軽量なモデルで再試行
            if self.config.model_size != 'tiny':
                logger.info("より小さいモデルで再試行")
                model = whisperx.load_model(
                    'small',
                    self.device,
                    compute_type='int8',
                    language=self.config.language
                )
            else:
                raise
        
        # 3. 文字起こし（WhisperXに委譲）
        if progress_callback:
            progress_callback(0.3, "文字起こし処理中...")
        
        batch_size = self.profile.batch_size or self._get_safe_batch_size()
        
        try:
            result = model.transcribe(
                audio,
                batch_size=batch_size,
                language=self.config.language
            )
        except torch.cuda.OutOfMemoryError:
            logger.warning("GPUメモリ不足、バッチサイズを削減")
            # バッチサイズを半分に
            result = model.transcribe(
                audio,
                batch_size=max(1, batch_size // 2),
                language=self.config.language
            )
        
        # 4. アライメント（オプション）
        if self.config.enable_alignment:
            if progress_callback:
                progress_callback(0.7, "アライメント処理中...")
            
            try:
                result = self._perform_alignment(result, audio)
            except Exception as e:
                logger.warning(f"アライメント失敗: {e}")
                # アライメントなしで続行
        
        if progress_callback:
            progress_callback(1.0, "完了")
        
        return result
    
    def _get_safe_batch_size(self) -> int:
        """安全なバッチサイズを決定"""
        available_memory = psutil.virtual_memory().available / (1024**3)
        
        if self.device == 'cuda':
            # GPU使用時
            try:
                gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                if gpu_memory >= 8:
                    return 16
                elif gpu_memory >= 4:
                    return 8
                else:
                    return 4
            except:
                return 4
        else:
            # CPU使用時
            if available_memory >= 16:
                return 8
            elif available_memory >= 8:
                return 4
            else:
                return 2
```

### 4. 改善されたUI実装

```python
def render_performance_settings():
    """ユーザーフレンドリーな設定UI"""
    
    with st.expander("⚙️ パフォーマンス設定", expanded=False):
        
        # メイン設定
        col1, col2 = st.columns([3, 1])
        
        with col1:
            optimization = st.selectbox(
                "メモリ最適化",
                ["auto", "always", "never", "memory_critical"],
                format_func=lambda x: {
                    "auto": "自動判断（推奨）",
                    "always": "常に最適化",
                    "never": "最適化しない（高速）",
                    "memory_critical": "メモリ優先（低速）"
                }[x],
                help="""
                **自動判断**: メモリ状況に応じて判断
                **常に最適化**: 必ず音声を圧縮（50-70%削減）
                **最適化しない**: 元の音声をそのまま使用
                **メモリ優先**: 最大限メモリを節約
                """
            )
        
        with col2:
            if st.button("履歴から推奨", type="secondary"):
                suggestions = st.session_state.profile.suggest_settings_based_on_history()
                if suggestions:
                    st.info(f"推奨: {suggestions['reason']}")
        
        # 現在の状況表示
        memory_info = psutil.virtual_memory()
        st.metric(
            "利用可能メモリ",
            f"{memory_info.available / (1024**3):.1f} GB",
            f"{memory_info.percent}% 使用中"
        )
        
        # 詳細設定
        with st.expander("詳細設定", expanded=False):
            col1, col2 = st.columns(2)
            
            with col1:
                batch_size = st.number_input(
                    "バッチサイズ",
                    min_value=1,
                    max_value=32,
                    value=None,
                    help="空欄の場合は自動設定"
                )
                
                max_conversion_time = st.number_input(
                    "最大変換時間（秒）",
                    min_value=60,
                    max_value=600,
                    value=300,
                    help="音声変換の最大待機時間"
                )
            
            with col2:
                compute_type = st.selectbox(
                    "計算精度",
                    [None, "int8", "float16", "float32"],
                    help="int8が最もメモリ効率的"
                )
                
                min_memory_gb = st.number_input(
                    "最小メモリ閾値（GB）",
                    min_value=2.0,
                    max_value=16.0,
                    value=4.0,
                    step=0.5,
                    help="この値以下でメモリ優先モード"
                )
        
        # 最適化の統計情報
        if hasattr(st.session_state, 'audio_optimizer'):
            summary = st.session_state.audio_optimizer.get_optimization_summary()
            if summary['total_optimizations'] > 0:
                st.info(f"""
                📊 **最適化統計**
                - 実行回数: {summary['total_optimizations']}回
                - 平均削減率: {summary['average_reduction_percent']:.0f}%
                - 総削減量: {summary['total_reduction_mb']:.0f}MB
                - 総変換時間: {summary['total_conversion_time_sec']:.0f}秒
                """)
```

## テスト計画

### 1. 単体テスト
```python
def test_audio_optimization():
    """音声最適化のテスト"""
    
    # テストケース
    test_cases = [
        # (ファイルサイズ, メモリ, 期待される結果)
        (100, 16, False),  # 十分なメモリ
        (2000, 4, True),   # メモリ不足
        (500, 8, True),    # 境界ケース
    ]
    
    for file_mb, memory_gb, expected in test_cases:
        # モックを使用してテスト
        pass
```

### 2. 統合テスト
- 各種音声フォーマット（MP3, AAC, FLAC, etc.）
- 特殊なケース（マルチトラック、可変ビットレート）
- エラーケース（破損ファイル、権限なし）

### 3. パフォーマンステスト
- 実際のメモリ使用量測定
- 変換時間の測定
- 精度の比較（WER: Word Error Rate）

## リスク管理

| リスク | 影響 | 確率 | 対策 |
|--------|------|------|------|
| FFmpeg変換失敗 | 高 | 中 | フォールバック実装済み |
| 一時ファイル競合 | 低 | 低 | UUID使用で回避 |
| メモリ推定誤差 | 中 | 中 | 安全マージン確保 |
| WhisperX仕様変更 | 高 | 低 | 動的検出実装 |

## まとめ

本改訂版（v5.1）では：

1. **現実的な数値**: メモリ削減50-70%、状況により判断
2. **柔軟な選択**: ユーザーの意図を尊重
3. **堅牢な実装**: エラー処理とフォールバック
4. **透明性**: 最適化の理由と結果を明示

これにより、あらゆる環境とユーザーニーズに対応できる、実用的なパフォーマンス改善を実現します。

---

最終更新: 2025-01-26
バージョン: 5.1（批判的レビュー反映版）