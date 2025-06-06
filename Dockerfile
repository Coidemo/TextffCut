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

# アプリケーション用ユーザーを作成
RUN useradd -m -s /bin/bash appuser

# 必要なディレクトリを作成（root権限で）
RUN mkdir -p /app/videos /app/output /app/transcriptions /app/logs /app/temp

# キャッシュディレクトリを作成（モデルは初回実行時にダウンロード）
RUN mkdir -p /home/appuser/.cache /home/appuser/.cache/matplotlib \
    /home/appuser/.cache/whisperx /home/appuser/.cache/huggingface && \
    chown -R appuser:appuser /home/appuser/.cache

# アプリケーションディレクトリの所有権を変更
# videosとlogsは書き込み可能にする必要がある
RUN chown -R appuser:appuser /app && \
    chmod -R 755 /app && \
    chmod -R 777 /app/videos /app/output /app/transcriptions /app/logs /app/temp

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

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# ポート公開
EXPOSE 8501

# 起動コマンド
CMD ["streamlit", "run", "main.py"]