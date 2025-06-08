# Phase 2: サービス層の設計と実装

## 目的
main.py（1178行）のUI層とビジネスロジックを分離し、テスタブルで保守性の高いアーキテクチャに改善する。

## 現状の問題点

### 1. main.pyの責任過多
- UIの表示ロジック
- ビジネスロジック（文字起こし、動画処理、エクスポート）
- 状態管理（st.session_state）
- エラーハンドリング
- ファイル操作

### 2. テストの困難性
- StreamlitのUIコンポーネントと密結合
- ビジネスロジックが独立してテストできない

### 3. 拡張性の低さ
- 新機能追加時に main.py が肥大化
- 責任の境界が不明確

## 設計方針

### 1. レイヤードアーキテクチャ
```
┌─────────────────────┐
│   UI Layer (main.py)│ ← Streamlit UI
├─────────────────────┤
│  Service Layer      │ ← ビジネスロジック
├─────────────────────┤
│  Core Layer         │ ← ドメインモデル
└─────────────────────┘
```

### 2. サービス層の責任
- ビジネスロジックの実装
- Core層の複数コンポーネントの協調
- トランザクション境界の管理
- エラーハンドリングの統一

## 実装計画

### Phase 2-1: サービス層の基本構造

#### 1. サービス基底クラス
```python
# services/base.py
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class ServiceResult:
    """サービス層の統一レスポンス"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = None

class BaseService(ABC):
    """サービス層の基底クラス"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = get_logger(self.__class__.__name__)
    
    @abstractmethod
    def execute(self, **kwargs) -> ServiceResult:
        """サービスのメイン実行メソッド"""
        pass
```

#### 2. 文字起こしサービス
```python
# services/transcription_service.py
from typing import Optional
from core import Transcriber
from .base import BaseService, ServiceResult

class TranscriptionService(BaseService):
    """文字起こし処理のビジネスロジック"""
    
    def execute(
        self, 
        video_path: str,
        model_size: str,
        use_api: bool = False,
        use_cache: bool = True,
        progress_callback: Optional[callable] = None
    ) -> ServiceResult:
        """文字起こしを実行"""
        try:
            # Transcriberの選択
            transcriber = self._get_transcriber(use_api)
            
            # キャッシュチェック
            if use_cache:
                cached_result = self._check_cache(video_path, model_size)
                if cached_result:
                    return ServiceResult(
                        success=True,
                        data=cached_result,
                        metadata={'from_cache': True}
                    )
            
            # 文字起こし実行
            result = transcriber.transcribe(
                video_path=video_path,
                model_size=model_size,
                progress_callback=progress_callback
            )
            
            return ServiceResult(
                success=True,
                data=result,
                metadata={'from_cache': False}
            )
            
        except Exception as e:
            self.logger.error(f"文字起こしエラー: {e}")
            return ServiceResult(
                success=False,
                error=str(e)
            )
```

#### 3. テキスト編集サービス
```python
# services/text_editing_service.py
class TextEditingService(BaseService):
    """テキスト編集と差分検出のビジネスロジック"""
    
    def find_differences(
        self,
        original_segments: List[Segment],
        edited_text: str
    ) -> ServiceResult:
        """編集されたテキストとの差分を検出"""
        try:
            processor = TextProcessor()
            diff_segments = processor.find_differences(
                original_segments, 
                edited_text
            )
            
            return ServiceResult(
                success=True,
                data=diff_segments,
                metadata={
                    'total_segments': len(original_segments),
                    'changed_segments': len(diff_segments)
                }
            )
            
        except Exception as e:
            self.logger.error(f"差分検出エラー: {e}")
            return ServiceResult(
                success=False,
                error=str(e)
            )
```

#### 4. 動画処理サービス
```python
# services/video_processing_service.py
class VideoProcessingService(BaseService):
    """動画処理のビジネスロジック"""
    
    def remove_silence(
        self,
        video_path: str,
        segments: List[Segment],
        threshold: float = -35.0,
        min_silence_duration: float = 0.3,
        pad_seconds: float = 0.0,
        progress_callback: Optional[callable] = None
    ) -> ServiceResult:
        """無音部分を削除"""
        try:
            processor = VideoProcessor()
            
            # 無音検出
            silence_ranges = processor.detect_silence(
                video_path,
                segments,
                threshold,
                min_silence_duration
            )
            
            # セグメントの調整
            adjusted_segments = processor.adjust_segments(
                segments,
                silence_ranges,
                pad_seconds
            )
            
            return ServiceResult(
                success=True,
                data=adjusted_segments,
                metadata={
                    'original_count': len(segments),
                    'adjusted_count': len(adjusted_segments),
                    'removed_silence_duration': self._calculate_removed_duration(silence_ranges)
                }
            )
            
        except Exception as e:
            self.logger.error(f"無音削除エラー: {e}")
            return ServiceResult(
                success=False,
                error=str(e)
            )
```

#### 5. エクスポートサービス
```python
# services/export_service.py
class ExportService(BaseService):
    """エクスポート処理のビジネスロジック"""
    
    def export_fcpxml(
        self,
        video_path: str,
        segments: List[Segment],
        output_path: str,
        settings: Dict[str, Any]
    ) -> ServiceResult:
        """FCPXMLエクスポート"""
        try:
            exporter = FCPXMLExporter()
            
            # エクスポート実行
            exporter.export(
                video_path=video_path,
                segments=segments,
                output_path=output_path,
                **settings
            )
            
            return ServiceResult(
                success=True,
                data={'output_path': output_path},
                metadata={
                    'format': 'FCPXML',
                    'segments_count': len(segments)
                }
            )
            
        except Exception as e:
            self.logger.error(f"エクスポートエラー: {e}")
            return ServiceResult(
                success=False,
                error=str(e)
            )
```

### Phase 2-2: ワークフローサービス

#### 統合ワークフローサービス
```python
# services/workflow_service.py
class WorkflowService(BaseService):
    """複数のサービスを組み合わせたワークフロー"""
    
    def __init__(self, config: Config):
        super().__init__(config)
        self.transcription_service = TranscriptionService(config)
        self.text_editing_service = TextEditingService(config)
        self.video_processing_service = VideoProcessingService(config)
        self.export_service = ExportService(config)
    
    def process_video_with_editing(
        self,
        video_path: str,
        edited_text: str,
        export_settings: Dict[str, Any],
        progress_callback: Optional[callable] = None
    ) -> ServiceResult:
        """動画処理の完全なワークフロー"""
        try:
            # Step 1: 文字起こし
            transcription_result = self.transcription_service.execute(
                video_path=video_path,
                model_size=export_settings.get('model_size', 'medium'),
                use_api=export_settings.get('use_api', False)
            )
            
            if not transcription_result.success:
                return transcription_result
            
            # Step 2: 差分検出
            diff_result = self.text_editing_service.find_differences(
                transcription_result.data.segments,
                edited_text
            )
            
            if not diff_result.success:
                return diff_result
            
            # Step 3: 無音削除（オプション）
            segments = diff_result.data
            if export_settings.get('remove_silence', False):
                silence_result = self.video_processing_service.remove_silence(
                    video_path=video_path,
                    segments=segments,
                    threshold=export_settings.get('silence_threshold', -35.0)
                )
                
                if not silence_result.success:
                    return silence_result
                
                segments = silence_result.data
            
            # Step 4: エクスポート
            export_result = self.export_service.export_fcpxml(
                video_path=video_path,
                segments=segments,
                output_path=export_settings['output_path'],
                settings=export_settings
            )
            
            return export_result
            
        except Exception as e:
            self.logger.error(f"ワークフローエラー: {e}")
            return ServiceResult(
                success=False,
                error=str(e)
            )
```

### Phase 2-3: main.pyのリファクタリング

#### リファクタリング後のmain.py構造
```python
# main.py (UI層のみ)
from services import WorkflowService, TranscriptionService

def main():
    """UIのみを担当"""
    # UI表示
    st.title("TextffCut")
    
    # 動画選択
    video_path = show_video_input()
    if not video_path:
        return
    
    # サービスの初期化
    workflow_service = WorkflowService(config)
    
    # 文字起こしセクション
    if st.button("文字起こし実行"):
        with st.spinner("処理中..."):
            result = workflow_service.transcription_service.execute(
                video_path=video_path,
                model_size=st.session_state.model_size,
                progress_callback=lambda p, m: show_progress(p, m)
            )
            
            if result.success:
                st.success("完了！")
                st.session_state.transcription_result = result.data
            else:
                st.error(f"エラー: {result.error}")
    
    # 編集セクション
    if 'transcription_result' in st.session_state:
        edited_text = show_text_editor(
            st.session_state.transcription_result
        )
        
        # エクスポート
        if st.button("エクスポート"):
            export_settings = {
                'model_size': st.session_state.model_size,
                'remove_silence': st.session_state.remove_silence,
                'output_path': get_output_path()
            }
            
            result = workflow_service.process_video_with_editing(
                video_path=video_path,
                edited_text=edited_text,
                export_settings=export_settings
            )
            
            if result.success:
                st.success(f"エクスポート完了: {result.data['output_path']}")
            else:
                st.error(f"エラー: {result.error}")
```

## Phase 2-4: 統合テスト

### 1. サービス層の単体テスト
```python
# tests/test_services.py
import pytest
from services import TranscriptionService, ServiceResult

def test_transcription_service():
    """文字起こしサービスのテスト"""
    service = TranscriptionService(test_config)
    
    result = service.execute(
        video_path="test_video.mp4",
        model_size="base",
        use_api=False
    )
    
    assert isinstance(result, ServiceResult)
    assert result.success
    assert result.data is not None
```

### 2. ワークフローの統合テスト
```python
def test_complete_workflow():
    """完全なワークフローのテスト"""
    workflow = WorkflowService(test_config)
    
    result = workflow.process_video_with_editing(
        video_path="test_video.mp4",
        edited_text="編集されたテキスト",
        export_settings={
            'model_size': 'base',
            'remove_silence': True,
            'output_path': 'output.fcpxml'
        }
    )
    
    assert result.success
    assert Path(result.data['output_path']).exists()
```

## 期待される効果

1. **保守性の向上**
   - UI層とビジネスロジックの分離
   - 責任の明確化
   - コードの再利用性向上

2. **テスタビリティの向上**
   - サービス層の独立したテスト
   - モックを使用した単体テスト
   - 統合テストの簡易化

3. **拡張性の向上**
   - 新しいサービスの追加が容易
   - 既存コードへの影響最小化
   - プラグイン的な機能追加

## 実装順序

1. **Phase 2-1**: サービス基底クラスと基本サービスの実装
2. **Phase 2-2**: ワークフローサービスの実装
3. **Phase 2-3**: main.pyのリファクタリング
4. **Phase 2-4**: 統合テストの実装

## リスクと対策

### リスク
- 大規模な変更によるデグレード
- Streamlitのセッション管理との整合性

### 対策
- 段階的な移行（サービスごとに実装）
- 既存のテストケースの維持
- 並行稼働期間の設定