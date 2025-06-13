# TextffCut Windows インストールガイド

## 📋 必要なソフトウェア

1. **ffmpeg**（必須）
2. **TextffCut CLI**（このパッケージに含まれています）

## 🚀 クイックスタート

### ステップ1: ffmpegのインストール

#### 方法A: 公式サイトから（推奨）
1. [ffmpeg公式サイト](https://ffmpeg.org/download.html#build-windows)にアクセス
2. 「Windows builds by BtbN」をクリック
3. `ffmpeg-master-latest-win64-gpl.zip`をダウンロード
4. ZIPファイルを解凍（例: `C:\ffmpeg`）
5. システム環境変数PATHに`C:\ffmpeg\bin`を追加

#### 方法B: Chocolateyを使用
```powershell
# 管理者権限でPowerShellを開く
choco install ffmpeg
```

#### 方法C: Scoopを使用
```powershell
scoop install ffmpeg
```

### ステップ2: ffmpegの動作確認
```cmd
ffmpeg -version
```
バージョン情報が表示されればOK

### ステップ3: TextffCutの設置
1. ダウンロードしたファイルを任意のフォルダに解凍
   例: `C:\Users\YourName\TextffCut`

2. そのフォルダでコマンドプロンプトを開く

## 💻 使い方

### 基本的な使用方法

#### 1. 動画情報を確認
```cmd
textffcut_cli_windows.bat info "C:\Videos\sample.mp4"
```

#### 2. 無音部分を検出
```cmd
textffcut_cli_windows.bat silence "C:\Videos\sample.mp4"
```

#### 3. 無音を削除してFCPXMLを出力
```cmd
textffcut_cli_windows.bat process "C:\Videos\sample.mp4" --remove-silence
```

### 詳細オプション

#### 無音検出の閾値を調整（デフォルト: -35dB）
```cmd
textffcut_cli_windows.bat process "video.mp4" --threshold -40
```

#### 最小無音時間を調整（デフォルト: 0.3秒）
```cmd
textffcut_cli_windows.bat process "video.mp4" --min-duration 0.5
```

#### 出力先を指定
```cmd
textffcut_cli_windows.bat process "video.mp4" --output-dir "D:\Exports"
```

## 🔧 トラブルシューティング

### ffmpegが見つからない
- 環境変数PATHにffmpegのbinフォルダが追加されているか確認
- コマンドプロンプトを再起動
- `where ffmpeg`で場所を確認

### ファイルパスにスペースが含まれる場合
必ず引用符で囲んでください：
```cmd
textffcut_cli_windows.bat info "C:\My Videos\sample video.mp4"
```

### アクセス拒否エラー
- 出力先フォルダに書き込み権限があるか確認
- 管理者権限でコマンドプロンプトを実行

### 文字化けする場合
コマンドプロンプトの文字コードを変更：
```cmd
chcp 65001
```

## 🎯 実用例

### 90分の講義動画から無音を削除
```cmd
textffcut_cli_windows.bat process "lecture.mp4" --threshold -40 --min-duration 1.0
```

### バッチ処理（複数ファイル）
```batch
@echo off
for %%f in (*.mp4) do (
    echo Processing: %%f
    textffcut_cli_windows.bat process "%%f" --output-dir "processed"
)
```

## 📝 FCPXMLの使い方

1. 生成されたFCPXMLファイルをDaVinci ResolveやFinal Cut Proで開く
2. 無音部分が削除されたタイムラインが自動生成される
3. 必要に応じて微調整して、最終的な動画を書き出す

## 🆘 サポート

問題が発生した場合：
1. ffmpegが正しくインストールされているか確認
2. ファイルパスが正しいか確認
3. ログメッセージを確認
4. GitHubのIssuesで報告

## 📌 Tips

- 長時間の動画は処理に時間がかかります（90分で約5-10分）
- 閾値を下げすぎると必要な音声も削除される可能性があります
- まず短い動画でテストすることをお勧めします