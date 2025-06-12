# Windows環境でのトラブルシューティング

## WSL2関連のエラーが出る場合

### エラー: "WSL2 is not supported with your current machine configuration"

このエラーは以下の環境で発生します：
- 仮想マシン内のWindows（VMware、VirtualBox、Parallels等）
- AWS WorkSpaces等のクラウドデスクトップ
- 古いWindows 10（バージョン2004以前）

### 解決方法

#### 1. 物理的なWindows PCの場合
管理者権限でコマンドプロンプトを開き、以下を実行：

```cmd
cd TextffCut
scripts\setup_wsl2.bat
```

実行後、PCを再起動してください。

#### 2. 仮想マシン内のWindowsの場合

**Parallels Desktop:**
1. VMをシャットダウン
2. 設定 → ハードウェア → CPU とメモリ
3. 「ネストされた仮想化を有効にする」にチェック
4. メモリを8GB以上に設定

**VMware:**
1. VMをシャットダウン
2. VM設定 → プロセッサ
3. 「仮想化エンジン」で「Intel VT-x/EPTまたはAMD-V/RVIを仮想化」を有効化

#### 3. それでも動作しない場合

以下の代替インストール方法をお試しください：

1. **Rancher Desktop（無料）**
   - https://rancherdesktop.io/ からダウンロード
   - WSL2不要でDockerコンテナを実行可能

2. **Python直接実行版**
   - Dockerを使わない軽量版
   - 別途提供のインストーラーを使用

## アライメント処理が終わらない場合

### 症状
- 「アライメントモデルを読み込み中」で止まる
- 処理が数分以上進まない

### 原因
- ネットワーク経由でのモデルダウンロードの失敗
- Windows Defenderによるブロック
- プロキシ環境での接続問題

### 解決方法

1. **Windows Defenderの除外設定**
   ```
   Windows セキュリティ → ウイルスと脅威の防止 → 設定の管理
   → 除外の追加 → フォルダー → TextffCutフォルダを追加
   ```

2. **オフラインモデルの使用**
   - 提供されたモデルファイルを `models` フォルダに配置
   - 自動的に読み込まれます

3. **プロキシ環境の場合**
   ```cmd
   set HTTP_PROXY=http://proxy.example.com:8080
   set HTTPS_PROXY=http://proxy.example.com:8080
   ```

## サポート

問題が解決しない場合は、以下の情報と共にお問い合わせください：

1. Windowsのバージョン（`winver`コマンドで確認）
2. Docker Desktopのバージョン
3. `logs`フォルダ内の最新ログファイル
4. エラーメッセージのスクリーンショット