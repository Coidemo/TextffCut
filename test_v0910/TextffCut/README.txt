=====================================
TextffCut
=====================================

動画の文字起こしと切り抜きを効率化するツールです。

【クイックスタート】

1. Docker Desktop を起動
   Docker Desktop がインストールされていない場合は、
   公式サイトからダウンロードしてください。
   https://www.docker.com/products/docker-desktop/

2. TextffCut を起動
   【通常起動（推奨）】
   - Windows: START.bat をダブルクリック
   - macOS: START.command をダブルクリック
   
   【クリーン起動】
   問題が発生した場合や、完全にリセットしたい場合：
   - Windows: START_CLEAN.bat をダブルクリック
   - macOS: START_CLEAN.command をダブルクリック
   ※ クリーン起動は既存のコンテナ・イメージを全て削除するため時間がかかります

3. 使い方
   (1) videos フォルダに動画ファイル（MP4）を入れる
   (2) ブラウザで自動的に開く画面で操作
   (3) 結果は videos フォルダ内に保存される

4. 終了方法
   ターミナル/コマンドプロンプトで Ctrl+C を押す

【トラブルシューティング】

問題が発生した場合:
   - Windows: START_CLEAN.bat をダブルクリック
   - macOS: START_CLEAN.command をダブルクリック
   （Dockerイメージを削除して再読み込みします）

【詳しい使い方】

スクリーンショット付きの詳しい説明は note をご覧ください：
https://note.com/coidemo


【動作環境】
- Docker Desktop 必須
- メモリ 8GB以上推奨（16GB推奨）
- 検証済み: macOS + MP4形式
