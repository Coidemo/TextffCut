# GitHub Organization 設定ガイド

## 組織作成と移行手順

### 1. Organization の作成
1. GitHub → 右上のプロフィール → Settings
2. 左メニュー → Organizations → New organization
3. Free プランを選択
4. 組織名を入力（例: TextffCut-Official）

### 2. リポジトリの移行
```
個人リポジトリ → Settings → Transfer ownership
→ 作成した Organization を選択
```

### 3. 基本権限の設定
```
Organization → Settings → Member privileges
→ Base permissions → "Read" を選択
```

### 4. 購入者チームの作成
```
Organization → Teams → New team
→ "購入者" または "Customers" という名前で作成
→ リポジトリアクセス: Read権限
```

## 購入者の追加フロー

### 方法1: 直接招待
1. Organization → People → Invite member
2. GitHubユーザー名を入力
3. "購入者チーム" に追加

### 方法2: 招待リンク
1. Teams → 購入者チーム → Settings
2. "Team invite link" を生成
3. 購入完了メールに含める

## メリット
- ✅ **Read-only権限**が無料で設定可能
- ✅ チーム単位での一括管理
- ✅ アクセスログの確認
- ✅ 有効期限の設定（手動）

## デメリット
- ⚠️ 購入者はGitHubアカウントが必要
- ⚠️ 一度クローンされたら制御不可
- ⚠️ Private fork の制限（無料プランでは不可）

## セキュリティ設定

### 推奨設定
- [ ] Allow members to create repositories → OFF
- [ ] Allow members to create teams → OFF  
- [ ] Allow forking of private repositories → OFF
- [ ] Default repository permission → Read

### 監視
- 定期的にアクセスログを確認
- 不審なアクティビティがあれば即座に削除
- クローン履歴の記録

## 自動化スクリプト例

```python
# 購入者追加スクリプト
import requests

def add_customer_to_github(username, org_name, team_slug, token):
    """購入者をGitHub組織に追加"""
    
    # チームに追加
    url = f"https://api.github.com/orgs/{org_name}/teams/{team_slug}/memberships/{username}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    response = requests.put(url, headers=headers)
    
    if response.status_code == 200:
        print(f"✅ {username} を追加しました")
        return True
    else:
        print(f"❌ エラー: {response.status_code}")
        return False

# 使用例
add_customer_to_github(
    username="購入者のGitHubユーザー名",
    org_name="TextffCut-Official", 
    team_slug="customers",
    token="あなたのGitHub Personal Access Token"
)
```

## まとめ

Organization への移行により、以下が実現できます：

1. **Read-only権限の付与** ✅
2. **購入者の一括管理** ✅
3. **アクセス制御** ✅
4. **無料で利用可能** ✅

ただし、完全なコピー防止はできないため、ライセンスでの法的保護も併用することを推奨します。