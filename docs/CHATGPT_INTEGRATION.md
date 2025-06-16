# ChatGPT連携機能

## 概要
TextffCutにChatGPT連携機能を追加しました。この機能により、文字起こし結果や切り抜き箇所のテキストを簡単にChatGPTで分析・活用できます。

## 現在の実装（v1）

### 基本機能
- **テキスト選択**: 「切り抜き箇所」または「文字起こし結果全文」を選択可能
- **プロンプトテンプレート**: よく使う分析パターンをテンプレート化
  - バズる切り抜き案の提案
  - 魅力的なタイトルの提案
  - 内容の要約
  - カスタムプロンプト
- **ワンクリックコピー**: プロンプトをクリップボードにコピー
- **ChatGPT起動**: 新しいタブでChatGPTを開く

### 使い方
1. 文字起こしを実行し、切り抜き箇所を指定
2. 右カラムの下部にある「ChatGPT連携」セクションを確認
3. 使用するテキストとプロンプトテンプレートを選択
4. 「プロンプトをコピー」ボタンをクリック
5. 「ChatGPTを開く」ボタンでChatGPTを新規タブで開く
6. ChatGPTにプロンプトをペースト

### 技術的な実装
- **サービス層**: `services/chatgpt_service.py`
  - プロンプトテンプレート管理
  - テキスト処理とプロンプト生成
- **UI層**: `ui/components.py`の`show_chatgpt_integration`関数
  - Streamlitコンポーネントでの表示
  - JavaScriptを使用したクリップボード操作

## 将来的な拡張計画（v2）

### API統合による自動化
1. **ChatGPT API統合**
   - OpenAI APIキーの管理（既存のWhisper API管理機能を流用）
   - API経由での直接リクエスト
   - レスポンスの自動取得と表示

2. **インライン結果表示**
   - ChatGPTの応答を同じ画面内に表示
   - 結果をテキストエリアに自動挿入
   - 「次の案」ボタンで複数の提案を順次表示

3. **高度な機能**
   - バッチ処理: 複数セクションの一括分析
   - 履歴管理: 過去の分析結果の保存と再利用
   - プロンプトの最適化: ユーザーの使用パターンに基づく改善

### 実装予定のUI改善
```python
# 将来的なUI例
with st.container():
    # API統合時のUI
    response = st.empty()  # ChatGPTレスポンス表示エリア
    
    if st.button("🤖 バズる切り抜きを自動提案"):
        with st.spinner("ChatGPTで分析中..."):
            suggestions = chatgpt_service.get_viral_suggestions(text)
            response.markdown(suggestions)
    
    # 提案結果を直接テキストエリアに挿入
    if st.button("✏️ この提案を採用"):
        st.session_state.edited_text = suggestions[0]['text']
```

### API料金の考慮
- GPT-4: 約$0.03/1Kトークン（入力）、$0.06/1Kトークン（出力）
- GPT-3.5: 約$0.0015/1Kトークン（入力）、$0.002/1Kトークン（出力）
- 使用量に応じた料金表示機能の実装

## 設定ファイルの拡張

将来的に以下の設定を`config.py`に追加予定:

```python
@dataclass
class ChatGPTConfig:
    """ChatGPT連携の設定"""
    api_key: Optional[str] = None
    model: str = "gpt-3.5-turbo"
    max_tokens: int = 2000
    temperature: float = 0.7
    enable_auto_suggestion: bool = False
    cache_responses: bool = True
```

## セキュリティとプライバシー
- APIキーは暗号化して保存（既存の仕組みを利用）
- ユーザーデータの送信前に確認ダイアログを表示
- ローカルキャッシュによるAPI呼び出しの最適化

## まとめ
現在の実装は、外部タブでChatGPTを開く基本的な連携機能です。将来的には、API統合により完全に統合された体験を提供し、動画編集のワークフローをさらに効率化します。