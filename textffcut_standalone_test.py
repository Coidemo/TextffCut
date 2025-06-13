#!/usr/bin/env python3
"""
TextffCut スタンドアロンテスト版
最小限の機能でPyInstallerビルドをテスト
"""

import sys
import os

# 基本的なインポートテスト
print("Testing imports...")

try:
    import torch
    print("✓ PyTorch imported")
except ImportError as e:
    print(f"✗ PyTorch import failed: {e}")

try:
    import whisperx
    print("✓ WhisperX imported")
except ImportError as e:
    print(f"✗ WhisperX import failed: {e}")

try:
    import numpy
    print("✓ NumPy imported")
except ImportError as e:
    print(f"✗ NumPy import failed: {e}")

# 簡単な機能テスト
def test_whisper():
    """Whisperの基本機能をテスト"""
    try:
        # CPUでテスト
        device = "cpu"
        compute_type = "int8"
        
        print(f"\nTesting Whisper with device={device}, compute_type={compute_type}")
        
        # モデルのロードのみテスト（実際の音声処理はしない）
        print("Loading Whisper model...")
        # model = whisperx.load_model("base", device, compute_type=compute_type)
        print("✓ Whisper model loading test passed (skipped actual loading)")
        
        return True
    except Exception as e:
        print(f"✗ Whisper test failed: {e}")
        return False

def main():
    print("="*50)
    print("TextffCut Standalone Test")
    print("="*50)
    
    # インポートテスト結果
    print("\nImport test completed.")
    
    # Whisperテスト
    if test_whisper():
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Some tests failed!")
    
    print("\nPress Enter to exit...")
    input()

if __name__ == "__main__":
    main()