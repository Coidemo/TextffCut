import subprocess
import tempfile
import os
from typing import Tuple, Optional, List
import streamlit as st
from pathlib import Path
import shutil


class PreviewGenerator:
    """タイムラインのプレビュー動画を生成するクラス"""
    
    def __init__(self, video_path: str):
        """
        Args:
            video_path: 元動画のパス
        """
        self.video_path = video_path
        self.temp_dir = None
    
    def __enter__(self):
        """一時ディレクトリを作成"""
        self.temp_dir = tempfile.mkdtemp(prefix="textffcut_preview_")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """一時ディレクトリをクリーンアップ"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def generate_transition_preview(
        self,
        transition_point: float,
        before_duration: float = 2.0,
        after_duration: float = 2.0,
        output_filename: Optional[str] = None
    ) -> Optional[str]:
        """
        つなぎ目のプレビュー動画を生成
        
        Args:
            transition_point: つなぎ目の時刻（秒）
            before_duration: つなぎ目前の表示時間（秒）
            after_duration: つなぎ目後の表示時間（秒）
            output_filename: 出力ファイル名（Noneの場合は自動生成）
            
        Returns:
            生成されたプレビュー動画のパス、失敗時はNone
        """
        if not self.temp_dir:
            raise RuntimeError("PreviewGeneratorはコンテキストマネージャとして使用してください")
        
        # 出力ファイル名の生成
        if output_filename is None:
            output_filename = f"preview_transition_{transition_point:.1f}.mp4"
        
        output_path = os.path.join(self.temp_dir, output_filename)
        
        # 開始時刻と継続時間を計算
        start_time = max(0, transition_point - before_duration)
        duration = before_duration + after_duration
        
        # FFmpegコマンドを構築
        cmd = [
            'ffmpeg',
            '-ss', str(start_time),
            '-i', self.video_path,
            '-t', str(duration),
            '-c:v', 'libx264',
            '-preset', 'ultrafast',  # 高速エンコード
            '-crf', '23',  # 品質設定
            '-c:a', 'aac',
            '-b:a', '128k',
            '-y',  # 上書き
            output_path
        ]
        
        try:
            # FFmpegを実行
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            if os.path.exists(output_path):
                return output_path
            else:
                st.error("プレビュー動画の生成に失敗しました")
                return None
                
        except subprocess.CalledProcessError as e:
            st.error(f"FFmpegエラー: {e.stderr}")
            return None
    
    def generate_segment_preview(
        self,
        start_time: float,
        end_time: float,
        max_duration: float = 10.0,
        output_filename: Optional[str] = None
    ) -> Optional[str]:
        """
        セグメントのプレビュー動画を生成（最初と最後の数秒）
        
        Args:
            start_time: セグメントの開始時刻（秒）
            end_time: セグメントの終了時刻（秒）
            max_duration: プレビューの最大時間（秒）
            output_filename: 出力ファイル名
            
        Returns:
            生成されたプレビュー動画のパス、失敗時はNone
        """
        if not self.temp_dir:
            raise RuntimeError("PreviewGeneratorはコンテキストマネージャとして使用してください")
        
        segment_duration = end_time - start_time
        
        if output_filename is None:
            output_filename = f"preview_segment_{start_time:.1f}_{end_time:.1f}.mp4"
        
        output_path = os.path.join(self.temp_dir, output_filename)
        
        if segment_duration <= max_duration:
            # セグメント全体が短い場合はそのまま抽出
            duration = segment_duration
            extract_start = start_time
        else:
            # 長い場合は最初と最後を抽出
            preview_each = max_duration / 2
            
            # 一時ファイルのパス
            temp_start = os.path.join(self.temp_dir, "temp_start.mp4")
            temp_end = os.path.join(self.temp_dir, "temp_end.mp4")
            
            # 最初の部分を抽出
            cmd_start = [
                'ffmpeg',
                '-ss', str(start_time),
                '-i', self.video_path,
                '-t', str(preview_each),
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-crf', '23',
                '-c:a', 'aac',
                '-y',
                temp_start
            ]
            
            # 最後の部分を抽出
            cmd_end = [
                'ffmpeg',
                '-ss', str(end_time - preview_each),
                '-i', self.video_path,
                '-t', str(preview_each),
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-crf', '23',
                '-c:a', 'aac',
                '-y',
                temp_end
            ]
            
            try:
                # 両方の部分を抽出
                subprocess.run(cmd_start, capture_output=True, check=True)
                subprocess.run(cmd_end, capture_output=True, check=True)
                
                # 結合用のファイルリストを作成
                concat_list = os.path.join(self.temp_dir, "concat_list.txt")
                with open(concat_list, 'w') as f:
                    f.write(f"file '{temp_start}'\n")
                    f.write(f"file '{temp_end}'\n")
                
                # 結合
                cmd_concat = [
                    'ffmpeg',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', concat_list,
                    '-c', 'copy',
                    '-y',
                    output_path
                ]
                
                subprocess.run(cmd_concat, capture_output=True, check=True)
                
                # 一時ファイルを削除
                for temp_file in [temp_start, temp_end, concat_list]:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                
                return output_path if os.path.exists(output_path) else None
                
            except subprocess.CalledProcessError as e:
                st.error(f"プレビュー生成エラー: {e.stderr}")
                return None
        
        # 短いセグメントの場合の処理
        cmd = [
            'ffmpeg',
            '-ss', str(start_time),
            '-i', self.video_path,
            '-t', str(duration),
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-y',
            output_path
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            return output_path if os.path.exists(output_path) else None
        except subprocess.CalledProcessError as e:
            st.error(f"プレビュー生成エラー: {e.stderr}")
            return None
    
    def generate_multiple_previews(
        self,
        preview_points: List[Tuple[str, float, float, float]]
    ) -> List[Tuple[str, Optional[str]]]:
        """
        複数のプレビューを一括生成
        
        Args:
            preview_points: [(名前, 時刻, 前の時間, 後の時間), ...] のリスト
            
        Returns:
            [(名前, プレビューパス), ...] のリスト
        """
        results = []
        
        for name, point, before, after in preview_points:
            preview_path = self.generate_transition_preview(
                point, before, after,
                output_filename=f"preview_{name}.mp4"
            )
            results.append((name, preview_path))
        
        return results