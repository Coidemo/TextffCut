#!/bin/bash

# TextffCut インストールスクリプト
# macOS専用

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
echo "        macOS専用版"
echo "======================================"
echo ""

# macOSの確認
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo -e "${RED}エラー: このスクリプトはmacOS専用です。${NC}"
    exit 1
fi

# macOSバージョンの確認
MAC_VERSION=$(sw_vers -productVersion)
echo "macOS $MAC_VERSION を検出しました。"
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

# Homebrew確認
echo ""
echo "2. Homebrewの確認..."
if ! command -v brew &> /dev/null; then
    echo -e "${YELLOW}警告: Homebrewがインストールされていません。${NC}"
    echo "Homebrewをインストールするには:"
    echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    echo ""
    read -p "続行しますか？ (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    BREW_VERSION=$(brew --version | head -n1 | cut -d' ' -f2)
    echo "   Homebrew $BREW_VERSION が見つかりました。"
fi

# FFmpeg確認
echo ""
echo "3. FFmpegの確認..."
if ! command -v ffmpeg &> /dev/null; then
    echo -e "${YELLOW}警告: FFmpegがインストールされていません。${NC}"
    echo ""
    echo "FFmpegをインストールするには:"
    echo "  brew install ffmpeg"
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
echo "4. Python仮想環境の作成..."
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
echo "5. 仮想環境の有効化..."
source venv/bin/activate
echo "   仮想環境を有効化しました。"

# pipのアップグレード
echo ""
echo "6. pipのアップグレード..."
pip install --upgrade pip > /dev/null 2>&1
echo "   pipをアップグレードしました。"

# 依存関係のインストール
echo ""
echo "7. 依存関係のインストール..."
echo "   これには数分かかる場合があります..."

# Apple Silicon確認
ARCH=$(uname -m)
if [[ "$ARCH" == "arm64" ]]; then
    echo "   Apple Silicon (M1/M2/M3)を検出しました。"
    echo "   Metal Performance Shaders対応のPyTorchをインストール中..."
else
    echo "   Intel Macを検出しました。"
    echo "   macOS用のPyTorchをインストール中..."
fi

# macOS用PyTorchのインストール
pip install torch torchaudio

# その他の依存関係
echo "   その他の依存関係をインストール中..."
pip install -r requirements.txt

# インストール確認
echo ""
echo "8. インストールの確認..."
python3 -c "import streamlit; print('   ✓ Streamlit')"
python3 -c "import torch; print('   ✓ PyTorch')"
python3 -c "import whisperx; print('   ✓ WhisperX')"
python3 -c "import openai; print('   ✓ OpenAI')"

# Apple Siliconの場合のMPS確認
if [[ "$ARCH" == "arm64" ]]; then
    python3 -c "import torch; print(f'   ✓ Metal Performance Shaders: {torch.backends.mps.is_available()}')"
fi

# 起動スクリプトの作成
echo ""
echo "9. 起動スクリプトの作成..."
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