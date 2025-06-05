#!/usr/bin/env python
"""
ワーカープロセス用の文字起こし処理スクリプト

サブプロセスやDockerコンテナから実行され、
処理完了後に自動的に終了してメモリを解放する。
"""

import json
import os
import sys
import time
import logging
from pathlib import Path

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def send_progress(progress: float, message: str = ""):
    """プログレス情報を親プロセスに送信"""
    print(f"PROGRESS:{progress}|{message}", flush=True)


def main():
    """ワーカーメイン処理"""
    try:
        # コマンドライン引数から設定ファイルパスを取得
        if len(sys.argv) < 2:
            logger.error("設定ファイルパスが指定されていません")
            sys.exit(1)
        
        config_path = sys.argv[1]
        
        if not os.path.exists(config_path):
            logger.error(f"設定ファイルが見つかりません: {config_path}")
            sys.exit(1)
        
        # 設定を読み込み
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        
        video_path = config_data['video_path']
        model_size = config_data['model_size']
        use_cache = config_data.get('use_cache', False)
        save_cache = config_data.get('save_cache', False)
        config_dict = config_data['config']
        
        logger.info(f"ワーカー処理を開始: {video_path}")
        send_progress(0.0, "処理を開始しています...")
        
        # 設定を復元
        from config import Config
        config = Config()
        
        # TranscriptionConfigを更新
        transcription_config = config_dict['transcription']
        config.transcription.use_api = transcription_config['use_api']
        config.transcription.api_provider = transcription_config.get('api_provider', 'openai')
        config.transcription.api_key = transcription_config.get('api_key')
        config.transcription.model_size = transcription_config['model_size']
        config.transcription.language = transcription_config['language']
        config.transcription.compute_type = transcription_config['compute_type']
        config.transcription.chunk_seconds = transcription_config['chunk_seconds']
        config.transcription.sample_rate = transcription_config['sample_rate']
        config.transcription.num_workers = transcription_config['num_workers']
        config.transcription.batch_size = transcription_config['batch_size']
        config.transcription.isolation_mode = transcription_config.get('isolation_mode', 'none')
        
        # Transcriberを作成（分離モードは'none'に設定されているので再帰しない）
        from core.transcription_smart_split import SmartSplitTranscriber
        transcriber = SmartSplitTranscriber(config)
        
        # プログレスコールバック
        def progress_callback(progress: float, message: str):
            logger.info(f"進捗: {progress:.1%} - {message}")
            send_progress(progress, message)
        
        # 文字起こし実行
        logger.info("文字起こし処理を実行中...")
        
        result = transcriber.transcribe(
            video_path=video_path,
            model_size=model_size,
            progress_callback=progress_callback,
            use_cache=use_cache,
            save_cache=save_cache
        )
        
        # 結果を保存
        result_data = result.to_dict()
        
        # 結果ファイルのパスを設定ファイルと同じディレクトリに
        result_path = os.path.join(os.path.dirname(config_path), 'result.json')
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        
        logger.info("処理が完了しました")
        send_progress(1.0, "処理が完了しました")
        
        # メモリ使用量を記録
        try:
            import psutil
            process = psutil.Process()
            mem_info = process.memory_info()
            mem_mb = mem_info.rss / 1024 / 1024
            logger.info(f"最終メモリ使用量: {mem_mb:.1f}MB")
        except:
            pass
        
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"ワーカー処理でエラー: {str(e)}", exc_info=True)
        print(f"ERROR:{str(e)}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()