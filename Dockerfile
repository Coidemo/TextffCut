# TextffCut - Docker版
# マルチステージビルドで最適化

# ステージ1: ビルド環境
FROM python:3.10-slim as builder

# ビルドに必要なパッケージをインストール
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Pythonパッケージをインストール
WORKDIR /build
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ステージ2: 実行環境
FROM python:3.10-slim

# メタデータ
LABEL maintainer="TextffCut Development Team" \
      version="1.1.0-dev" \
      description="TextffCut - 動画の文字起こしと切り抜きを効率化するツール"

# 実行に必要なパッケージのみインストール
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    locales \
    && rm -rf /var/lib/apt/lists/* \
    && locale-gen ja_JP.UTF-8

# 日本語環境の設定
ENV LANG=ja_JP.UTF-8 \
    LANGUAGE=ja_JP:ja \
    LC_ALL=ja_JP.UTF-8 \
    TZ=Asia/Tokyo

# ユーザー作成（セキュリティ向上）
RUN useradd -m -u 1000 textffcut

# 作業ディレクトリを設定
WORKDIR /app

# ステージ1からPythonパッケージをコピー
COPY --from=builder /root/.local /home/textffcut/.local

# アプリケーションのソースコードをコピー
COPY --chown=textffcut:textffcut . .

# 必要なディレクトリを作成
RUN mkdir -p videos output logs temp && \
    chown -R textffcut:textffcut /app

# ユーザーを切り替え
USER textffcut

# PATHを更新
ENV PATH=/home/textffcut/.local/bin:$PATH

# ポート8501を公開（Streamlitのデフォルトポート）
EXPOSE 8501

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Streamlitの設定を環境変数で制御
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_BROWSER_SERVER_ADDRESS=localhost

# エントリーポイントスクリプト
COPY --chown=textffcut:textffcut docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["streamlit", "run", "main.py"]