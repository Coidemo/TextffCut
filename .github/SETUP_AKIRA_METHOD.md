# Claude Code GitHub Actions セットアップガイド（Akira-Papa方式）

このドキュメントは、[あきらパパさんの記事](https://note.com/akira_papa_ai/n/n0e158a650c4a)に基づいたClaude Code GitHub Actionsのセットアップ方法です。

## 📋 前提条件

1. **Claude Maxプラン**（月額$100または$200）に加入済み
2. **GitHubアカウント**とリポジトリ管理者権限
3. **Claude Code**をローカルにインストール済み

## 🚀 セットアップ手順

### 1. リポジトリのフォーク

以下の2つのリポジトリをGitHubでフォークしてください：

1. **claude-code-action**
   - 元リポジトリ: https://github.com/Akira-Papa/claude-code-action
   - あなたのGitHubアカウントでフォーク

2. **claude-code-base-action**
   - 元リポジトリ: https://github.com/Akira-Papa/claude-code-base-action
   - あなたのGitHubアカウントでフォーク

### 2. API Keyの取得

1. [Anthropic Console](https://console.anthropic.com)にログイン
2. 「API Keys」セクションへ移動
3. 「Create Key」で新しいキーを生成
4. 生成されたキーをコピー（後で使用）

### 3. GitHub Secretsの設定

1. TextffCutリポジトリの「Settings」を開く
2. 左メニューから「Secrets and variables」→「Actions」を選択
3. 「New repository secret」をクリック
4. 以下を入力：
   - **Name**: `ANTHROPIC_API_KEY`
   - **Secret**: 先ほどコピーしたAPIキー
5. 「Add secret」をクリック

### 4. ワークフローファイルの確認

`.github/workflows/claude-actions.yml`が作成されています。
このファイルは、フォークしたアクションを使用するように設定されています。

### 5. 使用方法

#### Issue/PRでのClaude呼び出し

IssueやPull Requestのコメントで`@claude`をメンションします：

```
@claude このコードのパフォーマンスを改善してください
```

```
@claude この機能のテストコードを書いてください
```

#### 自動応答

- 新しいIssueが作成されると、Claudeが自動的に応答
- 新しいPRが作成されると、Claudeが自動的にコードレビューを実施

## ⚠️ 注意事項

1. **フォークの更新**: 定期的に元リポジトリの更新を確認し、必要に応じてフォークを更新してください
2. **API制限**: Claude MaxプランのAPI制限内で使用されます
3. **セキュリティ**: API Keyは絶対に公開しないでください

## 🔧 トラブルシューティング

### Claudeが反応しない場合

1. GitHub Actionsが有効になっているか確認
2. Secretsが正しく設定されているか確認
3. フォークしたリポジトリが正しく参照されているか確認
4. Actionsタブでワークフローの実行ログを確認

### エラーが発生する場合

1. API Keyが有効か確認
2. ワークフローファイルの構文エラーがないか確認
3. フォークしたアクションのバージョンを確認

## 📚 参考リンク

- [元記事（あきらパパ）](https://note.com/akira_papa_ai/n/n0e158a650c4a)
- [Anthropic Console](https://console.anthropic.com)
- [GitHub Actions ドキュメント](https://docs.github.com/ja/actions)