# Windows環境でのインストールガイド

## 動作要件

### 必須要件
- Windows 10 バージョン 2004以降 または Windows 11
- WSL2（Windows Subsystem for Linux 2）
- Docker Desktop for Windows

### 推奨環境
- メモリ: 8GB以上
- ストレージ: 20GB以上の空き容量

## インストール手順

### 1. WSL2のセットアップ

**重要**: Docker DesktopでLinuxコンテナを使用するにはWSL2が必須です。

管理者権限でPowerShellを開き、以下を実行：

```powershell
# WSL2をインストール
wsl --install

# PCを再起動
Restart-Computer
```

### 2. Docker Desktopのインストール

1. [Docker Desktop](https://www.docker.com/products/docker-desktop/)をダウンロード
2. インストーラーを実行
3. 「Use WSL 2 instead of Hyper-V」にチェック

### 3. TextffCutの起動

```cmd
cd TextffCut
START_GUI.bat
```

## トラブルシューティング

### WSL2がインストールできない場合

以下の環境ではWSL2は使用できません：
- 仮想マシン内のWindows（VMware、Parallels等）
- Windows Server
- ARM版Windows（一部制限あり）

#### 代替方法1: クラウド版を使用
- [TextffCut Cloud](https://textffcut.example.com)（準備中）

#### 代替方法2: ローカルPython版
WSL2/Dockerが使えない環境向けの軽量版：

1. Python 3.11をインストール
2. `install_local.bat`を実行
3. `start_local.bat`で起動

### よくある質問

**Q: WSL2なしでDockerは使えませんか？**
A: Linuxコンテナを使用するアプリケーションでは、WSL2が必須です。

**Q: 仮想マシンでも動作しますか？**
A: ネストされた仮想化をサポートする環境（VMware Workstation Pro等）では可能ですが、パフォーマンスが低下します。

**Q: Windows Serverで使えますか？**
A: Windows ServerではDocker EEを使用するか、ローカルPython版をご利用ください。