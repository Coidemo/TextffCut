#!/usr/bin/env python3
"""
worker_align.pyを直接テストして問題を調査
"""
import json
import os
import tempfile
import subprocess

# テスト用の設定を作成
test_config = {
    'audio_path': '/tmp/test_audio.wav',
    'segments': [
        {
            'id': 'seg_001',
            'text': 'これはテストです',
            'start': 0.0,
            'end': 2.0,
            'words': None,
            'chars': None,
            'transcription_completed': True,
            'alignment_completed': False,
            'alignment_error': None,
            'metadata': {}
        }
    ],
    'language': 'ja',
    'model_size': 'base',
    'config': {
        'transcription': {
            'language': 'ja',
            'compute_type': 'int8'
        }
    }
}

# 一時ディレクトリを作成
temp_dir = tempfile.mkdtemp(prefix="test_worker_")
config_path = os.path.join(temp_dir, 'config.json')

# 設定を保存
with open(config_path, 'w', encoding='utf-8') as f:
    json.dump(test_config, f, ensure_ascii=False, indent=2)

# テスト音声を作成
cmd = [
    'ffmpeg', '-y',
    '-f', 'lavfi',
    '-i', 'anullsrc=r=16000:cl=mono:d=2',
    '-ar', '16000',
    '-ac', '1',
    '/tmp/test_audio.wav'
]
subprocess.run(cmd, capture_output=True)

print(f"設定ファイル: {config_path}")
print(f"音声ファイル: /tmp/test_audio.wav")
print("\n以下のコマンドを直接実行して問題を確認してください:")
print(f"python worker_align.py {config_path}")
print("\n結果ファイル:")
print(f"{os.path.join(temp_dir, 'align_result.json')}")