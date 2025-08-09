# テーマ切り替え修正について

## 問題
ダークモードでもライトモードでも常にダークモードの表示になってしまう問題が発生していた。

## 原因
- CSSの`@media (prefers-color-scheme: dark)`だけに依存していた
- Streamlitのテーマ設定が正しく反映されていなかった
- 各コンポーネントで独自のテーマ判定を行っていて統一性がなかった

## 解決方法
`ThemeDetector`クラスを作成して、統一的なテーマ検出システムを実装した。

### 1. ThemeDetector (utils/theme_detector.py)
- セッション状態、URLパラメータ、JavaScriptによる検出の優先順位でテーマを判定
- `inject_theme_detector()`でJavaScriptコードを注入して動的にテーマを検出
- `is_dark_mode()`と`get_theme_mode()`で統一的なインターフェースを提供

### 2. 各コンポーネントの修正
- **ui/dark_mode_styles.py**: `get_dark_mode_styles()`でThemeDetectorを使用
- **ui/timeline_color_scheme.py**: `is_dark_mode()`メソッドをThemeDetectorに委譲
- **presentation/views/main.py**: `_apply_custom_css()`でテーマ別のCSSを適用
- **ui/icon_utils.py**: 新規作成。テーマに応じたアイコンを動的生成

### 3. main.pyの修正
- アプリケーション起動時に`ThemeDetector.inject_theme_detector()`を呼び出し
- JavaScriptによるテーマ検出を有効化

## 動作確認方法

1. アプリケーションを起動
```bash
streamlit run main.py
```

2. ブラウザでアクセスして、以下を確認：
   - Streamlitの設定（右上メニュー > Settings > Theme）でテーマを切り替える
   - 各要素（アイコン、ボタン、ステップインジケーターなど）の色が正しく変わることを確認

3. 手動テーマ切り替え（オプション）
   - セッション状態に`theme_mode`を設定することで手動切り替えも可能
   ```python
   st.session_state.theme_mode = "dark"  # または "light"
   ```

## 今後の改善点
- テーマ切り替え時のトランジション効果の追加
- より多くのコンポーネントでのテーマ対応
- テーマのカスタマイズ機能（色の調整など）