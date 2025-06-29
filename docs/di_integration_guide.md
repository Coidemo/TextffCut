# DI統合ガイド

## 概要

このガイドでは、TextffCutアプリケーションにDI（Dependency Injection）コンテナを統合する方法を説明します。

## 統合の利点

1. **テスタビリティの向上**: モックオブジェクトを簡単に注入できる
2. **モジュール性**: 依存関係が明確になり、コンポーネントの交換が容易
3. **設定管理**: 環境ごとの設定切り替えが簡単
4. **段階的移行**: 既存コードを徐々にDIベースに移行可能

## 統合手順

### 1. 最小限の統合（推奨）

main.pyの最初に以下を追加：

```python
# main.pyの冒頭に追加
from di.bootstrap import bootstrap_di, inject_streamlit_session
from di.containers import ApplicationContainer
from typing import Optional

# グローバルコンテナ
_app_container: Optional[ApplicationContainer] = None

def get_container() -> ApplicationContainer:
    """アプリケーションコンテナを取得"""
    global _app_container
    if _app_container is None:
        _app_container = bootstrap_di()
    return _app_container

# main関数の最初で初期化
def main():
    # DIコンテナを初期化
    container = get_container()
    inject_streamlit_session(container)
    
    # 既存のコード...
```

### 2. 既存サービスの段階的移行

#### Step 1: サービスをコンテナから取得

```python
# 従来の方法
config = Config.from_env()
transcriber = Transcriber(config)

# DI経由
container = get_container()
config = container.legacy_config()
transcriber = container.gateways.transcription_gateway()
```

#### Step 2: 関数に@injectデコレータを追加

```python
from dependency_injector.wiring import Provide, inject

@inject
def process_transcription(
    video_path: str,
    transcription_gateway=Provide[ApplicationContainer.gateways.transcription_gateway]
):
    """文字起こし処理"""
    return transcription_gateway.transcribe(video_path)
```

### 3. 設定の動的更新

Streamlitのセッション状態と連携：

```python
# サイドバーでの設定変更を自動的にDIコンテナに反映
with st.sidebar:
    api_key = st.text_input("APIキー", key="api_key")
    model_size = st.selectbox("モデル", options, key="model_size")
    
# DIコンテナが自動的にセッション状態を読み取る
# （inject_streamlit_sessionを呼び出していれば）
```

### 4. テスト環境での使用

```python
# テストでモックを注入
def test_transcription():
    container = create_test_container()
    
    # モックゲートウェイを注入
    mock_gateway = Mock()
    container.gateways.transcription_gateway.override(
        providers.Object(mock_gateway)
    )
    
    # テスト実行
    result = process_transcription("test.mp4")
    mock_gateway.transcribe.assert_called_once()
```

## 移行戦略

### Phase 1: 読み取り専用（現在）
- DIコンテナを追加するが、既存コードは変更しない
- 設定の読み取りのみDI経由にする

### Phase 2: ゲートウェイ層の利用
- 新機能はゲートウェイ経由で実装
- 既存機能は必要に応じて移行

### Phase 3: ユースケースの活用
- ビジネスロジックをユースケースに移行
- UIとビジネスロジックの分離を進める

### Phase 4: 完全なDIベース
- すべての依存関係をDIコンテナで管理
- 環境ごとの設定を完全に分離

## 注意事項

1. **既存コードへの影響を最小限に**
   - 一度にすべてを変更しない
   - 段階的に移行する

2. **Streamlitの制約**
   - リロード時にコンテナが再作成される
   - セッション状態を適切に管理する

3. **パフォーマンス**
   - シングルトンは一度だけ作成される
   - ファクトリーは毎回新しいインスタンスを作成

## 具体的な統合例

### 現在のmain.pyへの最小限の変更

```python
# main.py の変更例
import streamlit as st
from di.bootstrap import bootstrap_di, inject_streamlit_session
from di.containers import ApplicationContainer

# グローバル変数
_container: Optional[ApplicationContainer] = None

def get_container() -> ApplicationContainer:
    global _container
    if _container is None:
        _container = bootstrap_di()
    return _container

def main():
    st.set_page_config(page_title="TextffCut", layout="wide")
    
    # DIコンテナ初期化（追加）
    container = get_container()
    inject_streamlit_session(container)
    
    # 既存の初期化処理
    init_session_state()
    
    # 既存のUI処理...
    # （変更不要）
```

これにより、既存のコードを変更することなく、DIコンテナを追加できます。

## 今後の展開

1. **API/ローカル切り替えの改善**
   ```python
   # ConditionalProviderを使用
   transcription_provider = ConditionalProvider(
       condition=use_api_provider,
       when_true=api_transcription_gateway,
       when_false=local_transcription_gateway
   )
   ```

2. **プラグインシステム**
   - 新しいエクスポート形式を簡単に追加
   - カスタムプロセッサーの登録

3. **マルチ環境対応**
   - 開発/ステージング/本番の設定分離
   - 環境変数による自動切り替え