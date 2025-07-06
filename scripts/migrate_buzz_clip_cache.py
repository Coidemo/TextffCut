#!/usr/bin/env python3
"""
バズクリップキャッシュを新しい構造に移行するスクリプト

旧構造:
  transcriptions/
    - {model}_buzz_{num}_{min}_{max}.json
    - buzz_{num}_{min}_{max}.json

新構造:
  buzz_clips/
    - {model}.json
    - default.json
"""

import json
import logging
import shutil
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def migrate_buzz_clip_cache(videos_dir: Path) -> None:
    """バズクリップキャッシュを新しい構造に移行"""
    
    # videosディレクトリ内の全ての_TextffCutフォルダを検索
    textffcut_dirs = list(videos_dir.glob("*_TextffCut"))
    
    if not textffcut_dirs:
        logger.info("移行対象のディレクトリが見つかりません。")
        return
    
    logger.info(f"見つかったTextffCutディレクトリ: {len(textffcut_dirs)}個")
    
    migrated_count = 0
    
    for textffcut_dir in textffcut_dirs:
        transcriptions_dir = textffcut_dir / "transcriptions"
        buzz_clips_dir = textffcut_dir / "buzz_clips"
        
        if not transcriptions_dir.exists():
            continue
        
        # バズクリップキャッシュを探す
        buzz_files = list(transcriptions_dir.glob("*buzz*.json"))
        
        if not buzz_files:
            continue
        
        logger.info(f"\n処理中: {textffcut_dir.name}")
        logger.info(f"  見つかったバズクリップファイル: {len(buzz_files)}個")
        
        # buzz_clipsディレクトリを作成
        buzz_clips_dir.mkdir(exist_ok=True)
        
        for buzz_file in buzz_files:
            # ファイル名を解析
            filename = buzz_file.name
            
            # パターン1: {model}_buzz_{num}_{min}_{max}.json
            if "_buzz_" in filename:
                parts = filename.split("_buzz_")
                if len(parts) == 2:
                    model_name = parts[0]
                    new_filename = f"{model_name}.json"
                else:
                    continue
            # パターン2: buzz_{num}_{min}_{max}.json
            elif filename.startswith("buzz_"):
                new_filename = "default.json"
            else:
                continue
            
            # 新しいパスを作成
            new_path = buzz_clips_dir / new_filename
            
            # ファイルを移動
            if new_path.exists():
                logger.warning(f"  既に存在するため上書き: {new_filename}")
            
            shutil.move(str(buzz_file), str(new_path))
            logger.info(f"  移動: {filename} → buzz_clips/{new_filename}")
            migrated_count += 1
    
    logger.info(f"\n移行完了: {migrated_count}個のファイルを移動しました。")


def main():
    """メイン処理"""
    import sys
    
    # スクリプトの親ディレクトリ（プロジェクトルート）を取得
    project_root = Path(__file__).parent.parent
    videos_dir = project_root / "videos"
    
    if not videos_dir.exists():
        logger.error(f"videosディレクトリが見つかりません: {videos_dir}")
        return
    
    logger.info("バズクリップキャッシュの移行を開始します...")
    logger.info(f"対象ディレクトリ: {videos_dir}")
    
    # コマンドライン引数で確認をスキップ
    if len(sys.argv) > 1 and sys.argv[1] == "--yes":
        logger.info("自動実行モード")
    else:
        # 確認
        response = input("\n続行しますか？ (y/n): ")
        if response.lower() != 'y':
            logger.info("キャンセルしました。")
            return
    
    migrate_buzz_clip_cache(videos_dir)


if __name__ == "__main__":
    main()