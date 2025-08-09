"""
テーマ検出ユーティリティ

Streamlitアプリケーションの現在のテーマ（ダークモード/ライトモード）を
統一的に検出するためのユーティリティ。
"""

import streamlit as st
from typing import Optional


class ThemeDetector:
    """テーマ検出を統一的に行うクラス"""
    
    @staticmethod
    def is_dark_mode() -> bool:
        """
        現在のテーマがダークモードかどうかを判定
        
        Returns:
            ダークモードの場合True、ライトモードの場合False
        """
        # 1. セッション状態で明示的に指定されている場合を最優先
        if "theme_mode" in st.session_state:
            return st.session_state.theme_mode == "dark"
        
        # 2. Streamlitのquery paramsをチェック（URLパラメータでテーマが指定されている場合）
        if "theme" in st.query_params:
            return st.query_params["theme"] == "dark"
        
        # 3. JavaScriptを使った検出結果がセッション状態にある場合
        if "detected_theme" in st.session_state:
            return st.session_state.detected_theme == "dark"
        
        # 4. デフォルトはライトモード
        # 注: Streamlitの設定ファイル（.streamlit/config.toml）での設定は
        # 現在のAPIでは直接取得できないため、JavaScriptでの検出に依存
        return False
    
    @staticmethod
    def get_theme_mode() -> str:
        """
        現在のテーマモードを文字列で取得
        
        Returns:
            "dark" または "light"
        """
        return "dark" if ThemeDetector.is_dark_mode() else "light"
    
    @staticmethod
    def inject_theme_detector() -> None:
        """
        JavaScriptによるテーマ検出コードを注入
        ページロード時に一度だけ実行すること
        """
        if "theme_detector_injected" not in st.session_state:
            detector_script = """
            <script>
            (function() {
                // テーマを検出してStreamlitに送信
                const detectAndSendTheme = () => {
                    let isDark = false;
                    
                    // 1. Streamlitコンテナのdata-theme属性をチェック
                    const container = document.querySelector('[data-testid="stAppViewContainer"]');
                    if (container && container.getAttribute('data-theme') === 'dark') {
                        isDark = true;
                    }
                    
                    // 2. CSS変数から背景色をチェック（フォールバック）
                    if (!isDark) {
                        const bgColor = getComputedStyle(document.documentElement)
                            .getPropertyValue('--background-color').trim();
                        // ダークモードの一般的な背景色
                        if (bgColor && (
                            bgColor.includes('26') ||  // #262730など
                            bgColor.includes('1a') ||  // #1a1a1a など
                            bgColor.includes('0d')     // #0d0d0d など
                        )) {
                            isDark = true;
                        }
                    }
                    
                    // 3. prefers-color-schemeをチェック（最終フォールバック）
                    if (!isDark && window.matchMedia('(prefers-color-scheme: dark)').matches) {
                        isDark = true;
                    }
                    
                    // 検出結果を隠し要素に設定（Streamlitが読み取れるように）
                    const resultElement = document.getElementById('theme-detection-result');
                    if (resultElement) {
                        resultElement.textContent = isDark ? 'dark' : 'light';
                        resultElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
                    }
                };
                
                // DOMロード後とStreamlitの動的レンダリング後の両方で実行
                if (document.readyState === 'loading') {
                    document.addEventListener('DOMContentLoaded', detectAndSendTheme);
                } else {
                    detectAndSendTheme();
                }
                
                // Streamlitの動的レンダリングに対応
                setTimeout(detectAndSendTheme, 500);
                setTimeout(detectAndSendTheme, 1000);
            })();
            </script>
            <div id="theme-detection-result" style="display: none;"></div>
            """
            st.markdown(detector_script, unsafe_allow_html=True)
            st.session_state.theme_detector_injected = True
    
    @staticmethod
    def apply_theme_specific_css() -> None:
        """
        テーマに応じたCSSを適用
        """
        is_dark = ThemeDetector.is_dark_mode()
        
        # 共通CSS
        common_css = """
        <style>
        /* 共通スタイル */
        .theme-aware {
            transition: background-color 0.3s ease, color 0.3s ease;
        }
        </style>
        """
        st.markdown(common_css, unsafe_allow_html=True)
        
        if is_dark:
            # ダークモード用CSS
            dark_css = """
            <style>
            /* ダークモード専用スタイル */
            .main {
                background-color: #0e1117;
                color: #fafafa;
            }
            
            /* ハイライト色の調整 */
            .highlight-match {
                background-color: #2d5a2d !important;
                color: #b8e7b8 !important;
            }
            
            .highlight-addition {
                background-color: #5a2d2d !important;
                color: #ffb3b3 !important;
            }
            </style>
            """
            st.markdown(dark_css, unsafe_allow_html=True)
        else:
            # ライトモード用CSS
            light_css = """
            <style>
            /* ライトモード専用スタイル */
            .main {
                background-color: #ffffff;
                color: #262730;
            }
            
            /* ハイライト色の調整 */
            .highlight-match {
                background-color: #28a745 !important;
                color: #ffffff !important;
            }
            
            .highlight-addition {
                background-color: #dc3545 !important;
                color: #ffffff !important;
            }
            </style>
            """
            st.markdown(light_css, unsafe_allow_html=True)