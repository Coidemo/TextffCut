# TextffCut - Docker版（モデル同梱版）
# v0.9.7: Whisper mediumモデル固定版
# マルチステージビルドでイメージサイズを最適化

# ========================================
# Stage 1: モデルダウンロード専用ステージ
# ========================================
FROM python:3.11-slim AS model-downloader

WORKDIR /download

# OpenMPライブラリ（libgomp）をインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# モデルダウンロードに最小限必要なパッケージのみインストール
COPY requirements.txt .
RUN pip install --no-cache-dir \
    numpy==1.26.4 \
    torch==2.2.0 \
    torchaudio==2.2.0 \
    openai-whisper==20231117 \
    whisperx==3.1.5 \
    transformers==4.36.0 \
    && rm -rf /root/.cache/pip

# ダウンロードスクリプトをコピー
COPY scripts/download_models.py .
COPY scripts/download_models_alt.py .

# Hugging Faceのキャッシュ設定（ビルド時は通常のパス）
ENV HF_HOME=/home/appuser/.cache/huggingface
ENV HUGGINGFACE_HUB_CACHE=/home/appuser/.cache/huggingface/hub
ENV TRANSFORMERS_CACHE=/home/appuser/.cache/huggingface/transformers

# モデルをダウンロード（/home/appuser配下に保存）
RUN mkdir -p /home/appuser/.cache && \
    # 通常のスクリプトで試し、失敗したら代替スクリプトを使用
    (python download_models.py || python download_models_alt.py) && \
    # 不要なファイルを削除
    find /home/appuser/.cache -name "*.pyc" -delete && \
    find /home/appuser/.cache -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# ========================================
# Stage 2: 実行用ステージ（最終イメージ）
# ========================================
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

# アプリケーション用ユーザーを作成（COPYの前に）
RUN useradd -m -s /bin/bash appuser

# アプリケーションのコピー（--chownで所有者を設定）
COPY --chown=appuser:appuser . .

# 必要なディレクトリを作成（root権限で）
RUN mkdir -p /app/videos /app/output /app/transcriptions /app/logs /app/temp /app/default_prompts

# キャッシュディレクトリを作成
RUN mkdir -p /home/appuser/.cache/matplotlib && \
    chown -R appuser:appuser /home/appuser

# Stage 1からダウンロード済みモデルをコピー（別ディレクトリに保存）
COPY --from=model-downloader --chown=appuser:appuser /home/appuser/.cache /app/model_cache

# デフォルトプロンプトファイルをコピー（ボリュームマウント前の初期化用）
COPY --chown=appuser:appuser prompts/ /app/default_prompts/

# 書き込み可能なディレクトリのみ権限を変更
# （既にCOPY時に所有権は設定済み）
RUN chmod -R 777 /app/videos /app/output /app/transcriptions /app/logs /app/temp

# Streamlit設定（appuserのホームディレクトリに）
USER appuser
RUN mkdir -p /home/appuser/.streamlit && \
    echo '[server]\nheadless = true\nport = 8501\naddress = "0.0.0.0"\n' > /home/appuser/.streamlit/config.toml

# 権限テスト（ビルド時に実行して問題を早期発見）
# test_docker_permissions.pyがある場合のみ実行
RUN if [ -f test_docker_permissions.py ]; then python test_docker_permissions.py; fi

# 環境変数
ENV PYTHONUNBUFFERED=1
ENV TEXTFFCUT_ISOLATION_MODE=subprocess
ENV MPLCONFIGDIR=/home/appuser/.cache/matplotlib
# モデルキャッシュの環境変数を設定
ENV HF_HOME=/app/model_cache/huggingface
ENV HUGGINGFACE_HUB_CACHE=/app/model_cache/huggingface/hub
ENV TRANSFORMERS_CACHE=/app/model_cache/huggingface/transformers

# オフラインモードを強制（ネットワーク通信を防ぐ）
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# ポート公開
EXPOSE 8501

# 起動コマンド
CMD ["streamlit", "run", "main.py"]