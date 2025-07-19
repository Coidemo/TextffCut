"""
E2Eテスト用のヘルパー関数

Streamlit特有の要素選択やイベント待機を簡略化します。
"""

from playwright.sync_api import Page, Locator
import time


class E2EHelper:
    """E2Eテスト用ヘルパークラス"""
    
    def __init__(self, page: Page):
        """
        Args:
            page: Playwrightのページオブジェクト
        """
        self.page = page
    
    def wait_for_streamlit_reload(self, timeout: int = 10000):
        """Streamlitのリロードを待つ
        
        Args:
            timeout: タイムアウト時間（ミリ秒）
        """
        # Streamlitのローディングインジケータが消えるまで待つ
        try:
            # アプリコンテナが表示されるまで待つ
            self.page.wait_for_selector('[data-testid="stAppViewContainer"]', state="visible", timeout=timeout)
            # 追加の待機（Streamlitは非同期で更新されるため）
            self.page.wait_for_timeout(1000)
        except:
            # 代替のセレクタを試す
            self.page.wait_for_selector('.main', state="visible", timeout=timeout)
            self.page.wait_for_timeout(1000)
    
    def get_by_key(self, key: str) -> Locator:
        """Streamlitのkey属性で要素を取得
        
        Args:
            key: Streamlitコンポーネントのkey
            
        Returns:
            Playwrightのロケーター
        """
        return self.page.locator(f'.st-key-{key}').first
    
    def scroll_to_element(self, locator: Locator):
        """要素までスクロール
        
        Args:
            locator: スクロール先の要素
        """
        locator.scroll_into_view_if_needed()
        self.page.wait_for_timeout(300)
    
    def take_screenshot(self, name: str, path: str = None):
        """スクリーンショットを撮影
        
        Args:
            name: ファイル名（拡張子なし）
            path: 保存先ディレクトリ（指定しない場合はデフォルト）
        """
        if path:
            full_path = f"{path}/{name}.png"
        else:
            full_path = f"screenshots/{name}.png"
        
        self.page.screenshot(path=full_path)
    
    def wait_for_element_visible(self, selector: str, timeout: int = 30000) -> bool:
        """要素が表示されるまで待つ
        
        Args:
            selector: セレクター
            timeout: タイムアウト時間（ミリ秒）
            
        Returns:
            要素が見つかった場合True
        """
        try:
            self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            return True
        except:
            return False
    
    def get_error_messages(self) -> list[str]:
        """画面上のエラーメッセージを取得
        
        Returns:
            エラーメッセージのリスト
        """
        error_alerts = self.page.locator('[data-testid="stAlert"][data-baseweb="notification"]').all()
        messages = []
        for alert in error_alerts:
            if "error" in alert.get_attribute("class", "").lower():
                messages.append(alert.text_content())
        return messages
    
    def clear_and_type(self, locator: Locator, text: str):
        """入力フィールドをクリアしてテキストを入力
        
        Args:
            locator: 入力フィールドのロケーター
            text: 入力するテキスト
        """
        locator.click()
        locator.press("Control+a" if self.page.evaluate("navigator.platform").startswith("Win") else "Meta+a")
        locator.type(text)