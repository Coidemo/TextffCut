#!/bin/bash
# スモークテスト実行スクリプト

echo "=== TextffCut スモークテスト実行 ==="
echo ""

# Pythonパスの確認
echo "Python: $(which python)"
echo "Version: $(python --version)"
echo ""

# テスト実行
python test_smoke.py

# 終了コードを保存
exit_code=$?

# 結果に応じてメッセージ
if [ $exit_code -eq 0 ]; then
    echo ""
    echo "✅ ビルドは正常です"
else
    echo ""
    echo "❌ ビルドに問題があります"
fi

exit $exit_code