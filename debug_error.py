"""エラーの詳細を調査"""

import traceback
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
        
        # 時間範囲取得（ここでエラーが発生）
        try:
            time_ranges = text_gateway.get_time_ranges(diff_result, result)
            print("✓ 時間範囲取得成功")
        except Exception as e:
            print(f"\n❌ get_time_ranges でエラー: {e}")
            print("\n詳細なスタックトレース:")
            traceback.print_exc()
            
            # result.segments の詳細を調査
            print(f"\nresult type: {type(result)}")
            print(f"result.segments type: {type(result.segments)}")
            if result.segments:
                print(f"First segment type: {type(result.segments[0])}")
                seg = result.segments[0]
                print(f"Segment is dict: {isinstance(seg, dict)}")
                if isinstance(seg, dict):
                    print(f"Segment keys: {list(seg.keys())[:10]}")
                elif hasattr(seg, '__dict__'):
                    print(f"Segment attributes: {list(vars(seg).keys())[:10]}")
                    
except Exception as e:
    print(f"エラー: {e}")
    traceback.print_exc()