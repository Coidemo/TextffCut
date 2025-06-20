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
import gc
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
        except Exception:
            logger.debug("メモリ情報取得をスキップ")
        
        # 設定を復元
        from config import Config
        config = Config()
        
        # TranscriptionConfigを更新（必要な項目のみ）
        transcription_config = config_dict['transcription']
        config.transcription.use_api = transcription_config['use_api']
        config.transcription.api_provider = transcription_config.get('api_provider', 'openai')
        config.transcription.api_key = transcription_config.get('api_key')
        config.transcription.model_size = transcription_config['model_size']
        config.transcription.language = transcription_config['language']
        config.transcription.compute_type = transcription_config['compute_type']
        config.transcription.sample_rate = transcription_config['sample_rate']
        config.transcription.isolation_mode = transcription_config.get('isolation_mode', 'none')
        
        # 自動最適化エンジンとメモリモニターを初期化
        from core.auto_optimizer import AutoOptimizer
        from core.memory_monitor import MemoryMonitor
        
        optimizer = AutoOptimizer(model_size)
        memory_monitor = MemoryMonitor()
        
        # 新しい処理の開始なので診断モードをリセット
        optimizer.reset_diagnostic_mode()
        
        # Transcriberを作成（分離モードは'none'に設定されているので再帰しない）
        # APIモードかローカルモードかで処理を分ける
        if config.transcription.use_api:
            # APIモードの場合は直接Transcriberを使用（並列処理はAPITranscriber内で実装済み）
            from core.transcription import Transcriber
            transcriber = Transcriber(config)
            logger.info("APIモードで処理")
            task_type = 'transcribe_only'  # APIモードではtranscribe_onlyを使用
        else:
            # ローカルモードでは常に分離モード + SmartBoundaryTranscriberを使用
            logger.info("ローカルモード: 自動最適化による分離処理")
            task_type = 'separated_mode'
            
            # SmartBoundaryTranscriberを動的パラメータで使用（optimizer, memory_monitorを渡す）
            from core.transcription_smart_boundary import SmartBoundaryTranscriber
            transcriber = SmartBoundaryTranscriber(config, optimizer=optimizer, memory_monitor=memory_monitor)
            
            # 初期パラメータを自動最適化エンジンから取得してログ
            current_memory = memory_monitor.get_memory_usage()
            optimal_params = optimizer.get_optimal_params(current_memory)
            logger.info(f"自動最適化パラメータ（初期）: チャンク={optimal_params['chunk_seconds']}秒, ワーカー={optimal_params['max_workers']}")
        
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
            
            result = transcriber.transcribe(
                video_path=video_path,
                model_size=model_size,
                progress_callback=progress_callback,
                use_cache=False,  # 文字起こしのみの場合はキャッシュを使わない
                save_cache=False,  # 中間結果は保存しない
                skip_alignment=True  # アライメントをスキップ
            )
            
            # wordsフィールドの検証をスキップ（文字起こしのみなので）
            logger.info("文字起こしのみ完了（アライメント処理は別途実行）")
            
        elif task_type == 'separated_mode':
            # 分離モード（文字起こし→アライメント）
            logger.info("分離モード: 文字起こしフェーズ開始")
            
            # ステップ1: 文字起こしのみ
            def transcribe_progress(progress: float, message: str):
                # 文字起こしは全体の50%
                progress_callback(progress * 0.5, f"[文字起こし] {message}")
            
            # パラメータ最適化はSmartBoundaryTranscriber内部で各セグメントごとに実行される
            logger.info("文字起こしフェーズ: 動的最適化が有効です")
            
            result = transcriber.transcribe(
                video_path=video_path,
                model_size=model_size,
                progress_callback=transcribe_progress,
                use_cache=False,
                save_cache=False,
                skip_alignment=True
            )
            
            logger.info("分離モード: アライメントフェーズ開始")
            
            # ステップ2: アライメント処理
            from core.alignment_processor import AlignmentProcessor
            
            def alignment_progress(progress: float, message: str):
                # アライメントは全体の50-100%（診断10% + 本番処理90%）
                # 診断フェーズは0-10%、本番は10-100%
                progress_callback(0.5 + progress * 0.5, f"[アライメント] {message}")
            
            # アライメント前に再度パラメータを最適化
            current_memory = memory_monitor.get_memory_usage()
            optimal_params = optimizer.get_optimal_params(current_memory)
            
            # アライメント診断を実行して最適なバッチサイズを決定
            logger.info("アライメント用診断フェーズを開始")
            
            # 診断結果のキャッシュキーを生成（ファイルパス + サイズ + セグメント数）
            try:
                file_stat = os.stat(video_path)
                cache_key = f"{video_path}_{file_stat.st_size}_{len(result.segments)}"
            except:
                cache_key = None
            
            # キャッシュされた診断結果を確認
            # 注: ユーザー環境は変わる可能性があるため、キャッシュは無効化
            diagnostic_result = None
            # if cache_key and hasattr(optimizer, '_alignment_diagnostic_cache'):
            #     diagnostic_result = optimizer._alignment_diagnostic_cache.get(cache_key)
            #     if diagnostic_result:
            #         logger.info("キャッシュされた診断結果を使用")
            
            # キャッシュがない場合は診断を実行
            if not diagnostic_result:
                # まず診断用のAlignmentProcessorを作成
                diagnostic_processor = AlignmentProcessor(config)
                
                # 診断用のサンプルセグメント（最初の10セグメント）を準備
                sample_segments = None
                if hasattr(result, 'to_v2_format'):
                    v2_result = result.to_v2_format()
                    sample_segments = v2_result.segments[:10] if len(v2_result.segments) >= 10 else v2_result.segments
                elif result.segments:
                    sample_segments = result.segments[:10] if len(result.segments) >= 10 else result.segments
                
                # 診断を実行
                diagnostic_result = diagnostic_processor.run_diagnostic(
                    audio_path=video_path,
                    language=result.language,
                    sample_segments=sample_segments,
                    progress_callback=lambda p, m: alignment_progress(p * 0.2, f"[診断] {m}")  # 診断は全体の20%
                )
                
                # 診断結果をキャッシュに保存
                # 注: ユーザー環境は変わる可能性があるため、キャッシュは無効化
                # if cache_key and diagnostic_result['diagnostic_completed']:
                #     if not hasattr(optimizer, '_alignment_diagnostic_cache'):
                #         optimizer._alignment_diagnostic_cache = {}
                #     optimizer._alignment_diagnostic_cache[cache_key] = diagnostic_result
                #     logger.info("診断結果をキャッシュに保存")
                
                # 診断用プロセッサをクリーンアップ
                del diagnostic_processor
                gc.collect()
            
            # 診断結果を使用
            if diagnostic_result['diagnostic_completed']:
                optimal_batch_size = diagnostic_result['optimal_batch_size']
                logger.info(f"診断完了: 最適バッチサイズ={optimal_batch_size}")
                logger.info(f"  - モデルメモリ: {diagnostic_result['model_memory']:.1f}%")
                logger.info(f"  - 音声メモリ（推定）: {diagnostic_result['audio_memory']:.1f}%")
                logger.info(f"  - バッチあたり: {diagnostic_result['batch_memory_per_segment']:.1f}%/セグメント")
            else:
                # 診断が失敗した場合は従来の推定ロジックを使用
                logger.warning("診断が完了しなかったため、推定値を使用")
                
                # バッチサイズはチャンクサイズと相関させる（大きいチャンク = 小さいバッチ）
                if optimal_params['align_chunk_seconds'] >= 540:
                    optimal_batch_size = 4
                elif optimal_params['align_chunk_seconds'] >= 360:
                    optimal_batch_size = 6
                elif optimal_params['align_chunk_seconds'] >= 240:
                    optimal_batch_size = 8
                else:
                    optimal_batch_size = 12
                
                # メモリ使用率が高い場合はさらに削減
                current_memory = memory_monitor.get_memory_usage()
                if current_memory > 70:
                    optimal_batch_size = max(2, optimal_batch_size // 2)
            
            logger.info(f"アライメント用パラメータ: バッチサイズ={optimal_batch_size}")
            
            # 最適化されたバッチサイズで本番用AlignmentProcessorを初期化
            alignment_processor = AlignmentProcessor(config, batch_size=optimal_batch_size)
            
            # V2形式に変換してアライメント実行
            if hasattr(result, 'to_v2_format'):
                v2_result = result.to_v2_format()
                segments = v2_result.segments
            else:
                segments = result.segments
            
            # アライメント本体の実行（診断後なので進捗は20%から開始）
            def main_alignment_progress(progress: float, message: str):
                # 診断が20%まで使用、本体は20-100%
                actual_progress = 0.2 + progress * 0.8
                alignment_progress(actual_progress, message)
            
            aligned_segments = alignment_processor.align(
                segments,
                video_path,
                result.language,
                progress_callback=main_alignment_progress
            )
            
            # アライメント結果で更新
            if aligned_segments:
                result.segments = aligned_segments
                logger.info("分離モード: アライメント完了")
            else:
                logger.error("分離モード: アライメント失敗")
                # アライメントが失敗してもエラーにはしない（文字起こし結果は有効）
                
        else:
            # 通常の処理（文字起こし＋アライメント）
            result = transcriber.transcribe(
                video_path=video_path,
                model_size=model_size,
                progress_callback=progress_callback,
                use_cache=use_cache,
                save_cache=save_cache,
                skip_alignment=False  # 通常モードではアライメントを実行
            )
        
        # デバッグ: APIモードの状態を出力
        logger.info(f"検証前の状態 - task_type: {task_type}, use_api: {config.transcription.use_api}, segments: {len(result.segments) if result.segments else 0}")
        
        # デバッグ: 最初のセグメントのwords情報を確認
        if result.segments and len(result.segments) > 0:
            first_seg = result.segments[0]
            logger.info(f"最初のセグメントの詳細 - text: '{first_seg.text[:50]}...', words: {len(first_seg.words) if first_seg.words else 'None'}")
            if first_seg.words and len(first_seg.words) > 0:
                first_word = first_seg.words[0]
                logger.info(f"最初のwordの型: {type(first_word)}, 内容: {first_word}")
        
        # APIモードの場合は検証を完全にスキップ
        if config.transcription.use_api:
            logger.info("APIモード: wordsフィールドの検証をスキップします")
        # wordsフィールドの厳密な検証（transcribe_onlyモードまたはAPIモードではスキップ）
        elif task_type != 'transcribe_only' and result.segments:
            logger.info("ローカルモード: wordsフィールドの検証を開始します")
            # 検証を実行（ローカルモードのみ）
            is_valid, errors = result.validate_has_words()
            if not is_valid:
                logger.error("文字起こし結果の検証に失敗しました:")
                for error in errors:
                    logger.error(f"  - {error}")
                
                # デバッグ: 各セグメントの詳細を出力
                for i, seg in enumerate(result.segments[:5]):  # 最初の5セグメントのみ
                    logger.error(f"セグメント {i}: text='{seg.text[:30]}...', words={seg.words is not None}, words_count={len(seg.words) if seg.words else 0}")
                
                # V2形式での詳細なエラー生成
                try:
                    v2_result = result.to_v2_format()
                    v2_result.require_valid_words()
                except Exception as e:
                    logger.error(f"V2形式でのエラー: {str(e)}")
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
        
        # ローカルモードの場合、成功した実行のパラメータを保存
        if not config.transcription.use_api and hasattr(result, 'processing_time'):
            try:
                # 平均メモリ使用率を計算
                avg_memory = memory_monitor.get_average_usage(seconds=int(result.processing_time))
                
                # 実行メトリクスを作成
                metrics = {
                    'completed': True,
                    'avg_memory': avg_memory,
                    'processing_time': result.processing_time,
                    'segments_count': len(result.segments) if result.segments else 0,
                    'successful_runs': 1
                }
                
                # 最適化プロファイルを保存
                optimizer.save_successful_run(optimal_params, metrics)
                logger.info(f"実行プロファイルを保存しました（平均メモリ: {avg_memory:.1f}%）")
                
            except Exception as e:
                logger.warning(f"プロファイル保存エラー: {e}")
        
        # メモリ使用量を記録
        try:
            import psutil
            process = psutil.Process()
            mem_info = process.memory_info()
            mem_mb = mem_info.rss / 1024 / 1024
            logger.info(f"最終メモリ使用量: {mem_mb:.1f}MB")
        except Exception:
            logger.debug("メモリ情報取得をスキップ")
        
        sys.exit(0)
        
    except MemoryError as e:
        # メモリエラーの特別処理
        logger.error(f"メモリ不足エラー: {str(e)}")
        print(f"ERROR:メモリ不足により処理を中断しました: {str(e)}", file=sys.stderr, flush=True)
        
        # エラー結果を保存
        error_result = {
            "success": False,
            "error": f"メモリ不足: {str(e)}",
            "error_type": "MemoryError",
            "suggestion": "より小さなモデル（medium等）を使用するか、システムメモリを増やしてください。"
        }
        
        if 'config_path' in locals():
            result_path = os.path.join(os.path.dirname(config_path), 'result.json')
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(error_result, f, ensure_ascii=False, indent=2)
        
        sys.exit(1)
        
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"ワーカー処理でエラー: {str(e)}\n{error_traceback}")
        
        # エラー詳細を標準エラー出力にも出力
        print(f"ERROR:ワーカー処理エラー: {str(e)}", file=sys.stderr, flush=True)
        print(f"TRACEBACK:\n{error_traceback}", file=sys.stderr, flush=True)
        
        # エラー結果を保存
        error_result = {
            "success": False,
            "error": str(e),
            "traceback": error_traceback
        }
        
        # 結果ファイルパスを取得
        if 'config_path' in locals():
            result_path = os.path.join(os.path.dirname(config_path), 'result.json')
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(error_result, f, ensure_ascii=False, indent=2)
        
        sys.exit(1)


if __name__ == "__main__":
    main()