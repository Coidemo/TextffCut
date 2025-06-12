#!/usr/bin/env python3
"""
オフライン環境用にアライメントモデルを事前ダウンロード
"""
import os
import sys
import json
import shutil
from pathlib import Path

def download_all_models():
    """全ての必要なモデルをダウンロード"""
    try:
        import whisperx
        import torch
        
        # モデル保存先
        cache_dir = Path.home() / ".cache" / "torch" / "hub"
        os.makedirs(cache_dir, exist_ok=True)
        
        print("アライメントモデルをダウンロード中...")
        
        # 主要言語のモデルをダウンロード
        languages = ['ja', 'en', 'zh', 'ko', 'es', 'fr', 'de']
        
        for lang in languages:
            print(f"\n{lang}モデルをダウンロード中...")
            try:
                # モデルをダウンロード
                model, metadata = whisperx.load_align_model(lang, 'cpu')
                print(f"✓ {lang}モデル: 成功")
                
                # メモリ解放
                del model
                del metadata
                torch.cuda.empty_cache() if torch.cuda.is_available() else None
                
            except Exception as e:
                print(f"✗ {lang}モデル: 失敗 - {e}")
        
        # キャッシュサイズを確認
        total_size = sum(f.stat().st_size for f in cache_dir.rglob('*') if f.is_file())
        print(f"\n合計キャッシュサイズ: {total_size / (1024**3):.2f} GB")
        
        # モデルリストを保存
        model_list = {
            "languages": languages,
            "cache_dir": str(cache_dir),
            "total_size_gb": total_size / (1024**3)
        }
        
        with open("models_manifest.json", "w") as f:
            json.dump(model_list, f, indent=2)
        
        print("\nモデルのダウンロードが完了しました！")
        print("models_manifest.json に情報を保存しました。")
        
        return True
        
    except ImportError:
        print("エラー: WhisperXがインストールされていません")
        return False
    except Exception as e:
        print(f"エラー: {e}")
        return False

def package_models_for_docker():
    """Dockerイメージ用にモデルをパッケージ"""
    cache_dir = Path.home() / ".cache" / "torch" / "hub"
    docker_models_dir = Path("docker_models")
    
    if cache_dir.exists():
        print(f"\nモデルをDockerイメージ用にコピー中...")
        shutil.copytree(cache_dir, docker_models_dir, dirs_exist_ok=True)
        print(f"✓ {docker_models_dir} にコピー完了")

if __name__ == "__main__":
    if download_all_models():
        package_models_for_docker()