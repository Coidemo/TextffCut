# TextffCut - Docker版（シンプル版）
# サブプロセス分離によるメモリリーク対策を含む

FROM python:3.11

# 作業ディレクトリ
WORKDIR /app

# システム依存関係のインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    curl \
    locales \
    && rm -rf /var/lib/apt/lists/* \
    && locale-gen ja_JP.UTF-8

# 日本語環境の設定
ENV LANG=ja_JP.UTF-8 \
    LANGUAGE=ja_JP:ja \
    LC_ALL=ja_JP.UTF-8 \
    TZ=Asia/Tokyo

# Pythonパッケージのインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションのコピー
COPY . .

# 必要なディレクトリを作成
RUN mkdir -p /app/videos /app/output /app/transcriptions /app/logs

# WhisperXモデルを事前ダウンロード（baseモデル）
RUN python -c "import whisperx; whisperx.load_model('base', 'cpu', language='ja', compute_type='int8')"

# Streamlit設定
RUN mkdir -p ~/.streamlit
RUN echo '[server]\nheadless = true\nport = 8501\naddress = "0.0.0.0"\n' > ~/.streamlit/config.toml

# 環境変数
ENV PYTHONUNBUFFERED=1
ENV TEXTFFCUT_ISOLATION_MODE=subprocess

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# ポート公開
EXPOSE 8501

# 起動コマンド
CMD ["streamlit", "run", "main.py"]