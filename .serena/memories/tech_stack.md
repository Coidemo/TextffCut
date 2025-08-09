# 技術スタック

## フレームワーク
- **Streamlit 1.45.1**: UIフレームワーク（st.dialog サポート付き）

## 音声・動画処理
- **ffmpeg-python 0.2.0**: 動画処理
- **pydub 0.25.1**: 音声処理
- **yt-dlp**: YouTube動画ダウンロード
- **librosa 0.10.1**: 波形解析

## AI・機械学習
- **OpenAI Whisper**: 文字起こし（ローカル版）
- **WhisperX 3.1.0**: 高精度文字起こし（アライメント機能付き）
- **OpenAI API 1.12.0**: Whisper API、GPT-4o連携
- **torch, torchaudio**: PyTorchベース

## データ処理
- **numpy 1.26.4**: 数値演算（numpy<2制約）
- **pandas 2.0.3**: データフレーム処理
- **plotly 5.18.0**: インタラクティブなグラフ表示

## アーキテクチャ
- **dependency-injector 4.41.0**: DIフレームワーク（クリーンアーキテクチャ実装）

## 開発環境
- **Python 3.11**: ターゲットバージョン
- **Docker**: コンテナ化（docker-compose.yml）
- **pytest**: テストフレームワーク