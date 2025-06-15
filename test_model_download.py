#!/usr/bin/env python3
"""
モデルダウンロードのテストスクリプト
環境変数設定とダウンロード動作を確認
"""
import os
import sys

# 環境変数を設定
os.environ['HF_HOME'] = '/tmp/test_hf_cache'
os.environ['TRANSFORMERS_CACHE'] = '/tmp/test_hf_cache'
os.environ['TORCH_HOME'] = '/tmp/test_torch_cache'

print("=== 環境変数設定 ===")
print(f"HF_HOME: {os.environ['HF_HOME']}")
print(f"TRANSFORMERS_CACHE: {os.environ['TRANSFORMERS_CACHE']}")
print(f"TORCH_HOME: {os.environ['TORCH_HOME']}")

# キャッシュディレクトリを作成
os.makedirs(os.environ['HF_HOME'], exist_ok=True)
os.makedirs(os.environ['TORCH_HOME'], exist_ok=True)

try:
    import whisperx
    print("\n=== WhisperXインポート成功 ===")
    
    # アライメントモデルのロードテスト
    print("\n=== アライメントモデルのロードテスト ===")
    print("日本語アライメントモデルをロード中...")
    
    model, metadata = whisperx.load_align_model(
        language_code="ja",
        device="cpu"
    )
    print("✓ アライメントモデルのロード成功")
    
    # キャッシュディレクトリの内容を確認
    print("\n=== キャッシュディレクトリの内容 ===")
    for root, dirs, files in os.walk(os.environ['HF_HOME']):
        level = root.replace(os.environ['HF_HOME'], '').count(os.sep)
        indent = ' ' * 2 * level
        print(f"{indent}{os.path.basename(root)}/")
        subindent = ' ' * 2 * (level + 1)
        for file in files:
            if file.endswith(('.bin', '.safetensors', '.json')):
                size = os.path.getsize(os.path.join(root, file))
                print(f"{subindent}{file} ({size / (1024**2):.1f} MB)")
    
    # クリーンアップ
    del model
    del metadata
    
except Exception as e:
    print(f"\n✗ エラー: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✓ テスト完了")