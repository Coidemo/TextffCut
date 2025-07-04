"""エラーをキャプチャして詳しく調査"""

import streamlit as st
import sys
import logging
from pathlib import Path

# ロギング設定
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('error_debug.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

# すべてのログを捕捉
logging.getLogger().setLevel(logging.DEBUG)

# エラーハンドラー
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception

# 実際の処理をシミュレート
try:
    from config import Config
    from adapters.gateways.transcription.transcription_gateway import TranscriptionGatewayAdapter
    from domain.value_objects import FilePath
    from adapters.gateways.text_processing.text_processor_gateway import TextProcessorGatewayAdapter
    
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
        print(f"✓ キャッシュ読み込み成功")
        print(f"  - 型: {type(result)}")
        print(f"  - セグメント数: {len(result.segments)}")
        
        # テキスト処理
        full_text = result.text
        edited_text = "はいおはようございます"
        
        print(f"\n✓ テキスト処理開始")
        print(f"  - 元テキスト長: {len(full_text)}")
        print(f"  - 編集テキスト: {edited_text}")
        
        # 差分検出
        diff_result = text_gateway.find_differences(
            original_text=full_text,
            edited_text=edited_text
        )
        
        print(f"\n✓ 差分検出成功")
        print(f"  - 差分結果: {diff_result}")
        
        # 時間範囲取得（ここでエラーが発生している可能性）
        print(f"\n⚠️ 時間範囲取得開始...")
        time_ranges = text_gateway.get_time_ranges(diff_result, result)
        
        print(f"\n✓ 時間範囲取得成功")
        print(f"  - 時間範囲: {time_ranges}")
        
except Exception as e:
    logging.error(f"エラー発生: {e}", exc_info=True)
    print(f"\n❌ エラー: {e}")
    print(f"エラーの型: {type(e)}")
    
    # 詳細な調査
    import traceback
    traceback.print_exc()
    
    # どこでエラーが発生しているか特定
    if 'result' in locals() and result:
        print(f"\n調査: result.segments の内容")
        for i, seg in enumerate(result.segments[:3]):
            print(f"  セグメント{i}: {type(seg)}")
            if hasattr(seg, '__dict__'):
                print(f"    属性: {list(vars(seg).keys())[:5]}...")  # 最初の5つの属性