#!/bin/bash

# TextffCut インストールスクリプト
# macOS/Linux用

set -e  # エラーが発生したら即終了

# 色付き出力用の定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# ヘッダー表示
echo ""
echo "======================================"
echo "   TextffCut インストールスクリプト"
echo "======================================"
echo ""

# OSの確認
OS_TYPE=""
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS_TYPE="macOS"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS_TYPE="Linux"
else
    echo -e "${RED}エラー: サポートされていないOSです。${NC}"
    exit 1
fi

echo "検出されたOS: $OS_TYPE"
echo ""

# Python確認
echo "1. Python環境の確認..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}エラー: Python3がインストールされていません。${NC}"
    echo "Python 3.8以上をインストールしてください。"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "   Python $PYTHON_VERSION が見つかりました。"

# FFmpeg確認
echo ""
echo "2. FFmpegの確認..."
if ! command -v ffmpeg &> /dev/null; then
    echo -e "${YELLOW}警告: FFmpegがインストールされていません。${NC}"
    echo ""
    if [[ "$OS_TYPE" == "macOS" ]]; then
        echo "FFmpegをインストールするには:"
        echo "  brew install ffmpeg"
    else
        echo "FFmpegをインストールするには:"
        echo "  sudo apt-get install ffmpeg  # Ubuntu/Debian"
        echo "  sudo yum install ffmpeg      # CentOS/RHEL"
    fi
    echo ""
    read -p "続行しますか？ (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    FFMPEG_VERSION=$(ffmpeg -version | head -n1 | cut -d' ' -f3)
    echo "   FFmpeg $FFMPEG_VERSION が見つかりました。"
fi

# 仮想環境の作成
echo ""
echo "3. Python仮想環境の作成..."
if [ -d "venv" ]; then
    echo -e "${YELLOW}   既存の仮想環境が見つかりました。${NC}"
    read -p "   再作成しますか？ (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf venv
        python3 -m venv venv
        echo "   仮想環境を再作成しました。"
    fi
else
    python3 -m venv venv
    echo "   仮想環境を作成しました。"
fi

# 仮想環境の有効化
echo ""
echo "4. 仮想環境の有効化..."
source venv/bin/activate
echo "   仮想環境を有効化しました。"

# pipのアップグレード
echo ""
echo "5. pipのアップグレード..."
pip install --upgrade pip > /dev/null 2>&1
echo "   pipをアップグレードしました。"

# 依存関係のインストール
echo ""
echo "6. 依存関係のインストール..."
echo "   これには数分かかる場合があります..."

# PyTorchのインストール（CPU/GPU自動判定）
if [[ "$OS_TYPE" == "macOS" ]]; then
    echo "   macOS用のPyTorchをインストール中..."
    pip install torch torchaudio
else
    # NVIDIAドライバーの確認
    if command -v nvidia-smi &> /dev/null; then
        echo "   NVIDIA GPUが検出されました。CUDA版PyTorchをインストール中..."
        pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
    else
        echo "   CPU版PyTorchをインストール中..."
        pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
    fi
fi

# その他の依存関係
echo "   その他の依存関係をインストール中..."
pip install -r requirements.txt

# インストール確認
echo ""
echo "7. インストールの確認..."
python3 -c "import streamlit; print('   ✓ Streamlit')"
python3 -c "import torch; print('   ✓ PyTorch')"
python3 -c "import whisperx; print('   ✓ WhisperX')"
python3 -c "import openai; print('   ✓ OpenAI')"

# 起動スクリプトの作成
echo ""
echo "8. 起動スクリプトの作成..."
cat > run.sh << 'EOF'
#!/bin/bash
# TextffCut 起動スクリプト

# スクリプトのディレクトリに移動
cd "$(dirname "$0")"

# 仮想環境の有効化
source venv/bin/activate

# アプリケーションの起動
streamlit run main.py
EOF

chmod +x run.sh
echo "   起動スクリプト 'run.sh' を作成しました。"

# 完了メッセージ
echo ""
echo -e "${GREEN}======================================"
echo "   インストールが完了しました！"
echo "======================================${NC}"
echo ""
echo "TextffCutを起動するには:"
echo "  ./run.sh"
echo ""
echo "手動で起動する場合:"
echo "  source venv/bin/activate"
echo "  streamlit run main.py"
echo ""
echo "APIモードを使用する場合は、起動後にサイドバーから"
echo "OpenAI APIキーを設定してください。"
echo ""