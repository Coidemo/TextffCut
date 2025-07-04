"""修正の動作確認"""

from config import Config
from adapters.gateways.transcription.transcription_gateway import TranscriptionGatewayAdapter
from domain.value_objects import FilePath
from adapters.gateways.text_processing.text_processor_gateway import TextProcessorGatewayAdapter

try:
    # 設定
    config = Config()
    config.transcription.use_api = True
    
    # ゲートウェイ
    transcription_gateway = TranscriptionGatewayAdapter(config)
    text_gateway = TextProcessorGatewayAdapter()
    
    # キャッシュ読み込み
    video_path = FilePath("videos/（朝ラジオ）習慣が続かないのはモチベーション次第で辞めるから_original.mp4")
    result = transcription_gateway.load_from_cache(video_path, "whisper-1")
    
    if result:
        print("✓ キャッシュ読み込み成功")
        
        # テキスト処理
        full_text = result.text
        edited_text = "はいおはようございます"
        
        # 差分検出
        diff_result = text_gateway.find_differences(
            original_text=full_text,
            edited_text=edited_text
        )
        
        print("✓ 差分検出成功")
        print(f"  - diff_result type: {type(diff_result)}")
        print(f"  - has differences: {hasattr(diff_result, 'differences')}")
        print(f"  - has common_positions: {hasattr(diff_result, 'common_positions')}")
        
        # show_diff_viewerのテスト
        from ui.components import show_diff_viewer
        
        # ドメインエンティティ形式で呼び出し（エラーが出ないことを確認）
        try:
            # Streamlitのモックを作成
            import sys
            from unittest.mock import MagicMock
            sys.modules['streamlit'] = MagicMock()
            
            show_diff_viewer(full_text, diff_result)
            print("✓ show_diff_viewer が正常に動作しました")
        except Exception as e:
            print(f"✗ show_diff_viewer でエラー: {e}")
            
except Exception as e:
    print(f"エラー: {e}")
    import traceback
    traceback.print_exc()