"""
サブプロセス実行のユーティリティ
"""
import subprocess
import threading
from typing import Optional, Tuple
from .logging import logger


def run_command_with_timeout(
    cmd: list, 
    timeout: int = 300,  # 5分のタイムアウト
    capture_output: bool = True
) -> Tuple[int, str, str]:
    """
    タイムアウト付きでコマンドを実行
    
    Args:
        cmd: 実行するコマンド
        timeout: タイムアウト秒数
        capture_output: 出力をキャプチャするか
        
    Returns:
        (return_code, stdout, stderr)
    """
    try:
        if capture_output:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        else:
            result = subprocess.run(cmd, timeout=timeout)
            return result.returncode, "", ""
            
    except subprocess.TimeoutExpired:
        logger.error(f"コマンドタイムアウト ({timeout}秒): {' '.join(cmd)}")
        return -1, "", "Command timed out"
    except Exception as e:
        logger.error(f"コマンド実行エラー: {str(e)}")
        return -1, "", str(e)