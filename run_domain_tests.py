#!/usr/bin/env python3
"""
ドメイン層テストを実行して結果を確認
"""

import subprocess
import sys
import os

# PYTHONPATHを設定
env = os.environ.copy()
env['PYTHONPATH'] = os.path.dirname(os.path.abspath(__file__))

# ドメイン層のテストのみを実行
cmd = [
    "pytest",
    "tests/unit/domain/",
    "-v",
    "--tb=short",
    "--cov=domain",
    "--cov-report=term-missing",
    "--cov-report=html"
]

print(f"実行コマンド: {' '.join(cmd)}")
print(f"PYTHONPATH: {env['PYTHONPATH']}")
print("-" * 80)

# テストを実行
result = subprocess.run(cmd, env=env)
sys.exit(result.returncode)