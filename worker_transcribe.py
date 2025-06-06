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
        task_type = config_data.get('task_type', 'full')  # デフォルトはフル処理
        
        logger.info(f"ワーカー処理を開始: {video_path} (タスク: {task_type})")
        send_progress(0.0, "処理を開始しています...")
        
        # 初期メモリ使用量を記録
        try:
            import psutil
            process = psutil.Process()
            mem_info = process.memory_info()
            mem_mb = mem_info.rss / 1024 / 1024
            logger.info(f"初期メモリ使用量: {mem_mb:.1f}MB")
        except:
            pass
        
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
        # APIモードかローカルモードかで処理を分ける
        if config.transcription.use_api:
            # APIモードの場合は直接Transcriberを使用（並列処理はAPITranscriber内で実装済み）
            from core.transcription import Transcriber
            transcriber = Transcriber(config)
            logger.info("APIモードで処理")
        else:
            # ローカルモードの場合はメモリに応じて最適な実装を選択
            try:
                import psutil
                mem_gb = psutil.virtual_memory().available / (1024 ** 3)
                logger.info(f"利用可能メモリ: {mem_gb:.1f}GB")
                
                threshold = float(os.environ.get('PARALLEL_MEMORY_THRESHOLD', '8'))
                if mem_gb > threshold:  # 閾値以上なら並列処理
                    from core.transcription_parallel import ParallelTranscriber
                    transcriber = ParallelTranscriber(config)
                    logger.info("並列処理モードを使用")
                else:  # それ以下ならスマート境界検出
                    from core.transcription_smart_boundary import SmartBoundaryTranscriber
                    transcriber = SmartBoundaryTranscriber(config)
                    logger.info("スマート境界検出モードを使用")
            except Exception as e:
                logger.warning(f"最適化選択エラー: {e}")
                from core.transcription_smart_boundary import SmartBoundaryTranscriber
                transcriber = SmartBoundaryTranscriber(config)
        
        # プログレスコールバック
        def progress_callback(progress: float, message: str):
            logger.info(f"進捗: {progress:.1%} - {message}")
            send_progress(progress, message)
        
        # 文字起こし実行
        logger.info("文字起こし処理を実行中...")
        
        # タスクタイプに応じて処理を分岐
        if task_type == 'transcribe_only':
            # 文字起こしのみ（アライメントなし）
            logger.info("文字起こしのみモード（アライメントなし）")
            
            # 一時的にローカルモードの設定を変更してアライメントをスキップ
            # ※将来的には専用のフラグを追加する方が良い
            result = transcriber.transcribe(
                video_path=video_path,
                model_size=model_size,
                progress_callback=progress_callback,
                use_cache=False,  # 文字起こしのみの場合はキャッシュを使わない
                save_cache=False   # 中間結果は保存しない
            )
            
            # wordsフィールドの検証をスキップ（文字起こしのみなので）
            logger.info("文字起こしのみ完了（アライメント処理は別途実行）")
            
        else:
            # 通常の処理（文字起こし＋アライメント）
            result = transcriber.transcribe(
                video_path=video_path,
                model_size=model_size,
                progress_callback=progress_callback,
                use_cache=use_cache,
                save_cache=save_cache
            )
        
        # デバッグ: APIモードの状態を出力
        logger.info(f"検証前の状態 - task_type: {task_type}, use_api: {config.transcription.use_api}, segments: {len(result.segments) if result.segments else 0}")
        
        # APIモードの場合は検証を完全にスキップ
        if config.transcription.use_api:
            logger.info("APIモード: wordsフィールドの検証をスキップします")
        # wordsフィールドの厳密な検証（transcribe_onlyモードまたはAPIモードではスキップ）
        elif task_type != 'transcribe_only' and result.segments:
            # 検証を実行（ローカルモードのみ）
            is_valid, errors = result.validate_has_words()
            if not is_valid:
                logger.error("文字起こし結果の検証に失敗しました:")
                for error in errors:
                    logger.error(f"  - {error}")
                
                # V2形式での詳細なエラー生成
                try:
                    v2_result = result.to_v2_format()
                    v2_result.require_valid_words()
                except Exception as e:
                    # エラーメッセージを親プロセスに送信
                    print(f"ERROR:{str(e)}", flush=True)
                    sys.exit(1)
        
        # 結果を保存
        result_data = result.to_dict()
        
        logger.info(f"文字起こし結果 - セグメント数: {len(result.segments) if result.segments else 0}")
        if result.segments:
            logger.info(f"最初のセグメント: {result.segments[0].text[:50] if result.segments[0].text else '(空)'}")
        
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