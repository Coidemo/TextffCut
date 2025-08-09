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
                    let isDark = null;
                    
                    // 1. Streamlitの設定オブジェクトから直接取得
                    try {
                        // Streamlitのグローバル設定を探す
                        if (window.streamlit && window.streamlit.getTheme) {
                            const theme = window.streamlit.getTheme();
                            if (theme && theme.base) {
                                isDark = theme.base === 'dark';
                            }
                        }
                    } catch (e) {
                        console.log('Theme detection error (method 1):', e);
                    }
                    
                    // 2. CSSカスタムプロパティから取得
                    if (isDark === null) {
                        try {
                            const rootStyles = getComputedStyle(document.documentElement);
                            const bgColor = rootStyles.getPropertyValue('--background-color').trim();
                            // Streamlitのデフォルト背景色で判定
                            if (bgColor === '#0e1117' || bgColor === 'rgb(14, 17, 23)') {
                                isDark = true;
                            } else if (bgColor === '#ffffff' || bgColor === 'rgb(255, 255, 255)') {
                                isDark = false;
                            }
                        } catch (e) {
                            console.log('Theme detection error (method 2):', e);
                        }
                    }
                    
                    // 3. body要素の背景色をチェック
                    if (isDark === null) {
                        const body = document.body;
                        const bgColor = window.getComputedStyle(body).backgroundColor;
                        // RGB値を解析
                        const rgb = bgColor.match(/\d+/g);
                        if (rgb && rgb.length >= 3) {
                            // 暗い色かどうかを判定（しきい値: 128）
                            const brightness = (parseInt(rgb[0]) + parseInt(rgb[1]) + parseInt(rgb[2])) / 3;
                            isDark = brightness < 128;
                        }
                    }
                    
                    // 4. prefers-color-schemeをチェック（最終フォールバック）
                    if (isDark === null) {
                        isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
                    }
                    
                    // 検出結果をコンソールに出力（デバッグ用）
                    const theme = isDark ? 'dark' : 'light';
                    console.log('Detected theme:', theme);
                };
                
                // DOMロード後とStreamlitの動的レンダリング後の両方で実行
                if (document.readyState === 'loading') {
                    document.addEventListener('DOMContentLoaded', detectAndSendTheme);
                } else {
                    detectAndSendTheme();
                }
                
                // Streamlitの動的レンダリングに対応
                setTimeout(detectAndSendTheme, 100);
                setTimeout(detectAndSendTheme, 500);
                setTimeout(detectAndSendTheme, 1000);
                
                // 背景色を強制的に適用
                const applyBackgroundColor = () => {
                    const isDarkMode = window.matchMedia('(prefers-color-scheme: dark)').matches;
                    const bgColor = isDarkMode ? '#0e1117' : '#ffffff';
                    const textColor = isDarkMode ? '#fafafa' : '#262730';
                    
                    // 複数の要素に背景色を適用
                    const elements = [
                        document.documentElement,
                        document.body,
                        document.querySelector('.stApp'),
                        document.querySelector('.main'),
                        document.querySelector('[data-testid="stAppViewContainer"]')
                    ];
                    
                    elements.forEach(el => {
                        if (el) {
                            el.style.backgroundColor = bgColor;
                            el.style.color = textColor;
                        }
                    });
                    
                    // サイドバーの背景色も設定
                    const sidebar = document.querySelector('section[data-testid="stSidebar"]');
                    if (sidebar) {
                        sidebar.style.backgroundColor = isDarkMode ? '#262730' : '#f0f2f6';
                    }
                };
                
                // 初回実行と遅延実行
                applyBackgroundColor();
                setTimeout(applyBackgroundColor, 200);
                setTimeout(applyBackgroundColor, 500);
                setTimeout(applyBackgroundColor, 1000);
            })();
            </script>
            """
            st.markdown(detector_script, unsafe_allow_html=True)
            st.session_state.theme_detector_injected = True
    
    @staticmethod
    def apply_theme_specific_css() -> None:
        """
        テーマに応じたCSSを適用
        背景色を確実に設定する
        """
        # CSS media queriesを使った自動切り替え方式に変更
        theme_css = """
        <style>
        /* ライトモード用のスタイル */
        @media (prefers-color-scheme: light) {
            /* メインアプリケーションの背景 */
            html, body, .stApp, .main, [data-testid="stAppViewContainer"] {
                background-color: #ffffff !important;
                color: #262730 !important;
            }
            
            /* Streamlitの内部要素も白背景に */
            .block-container, div[data-testid="block-container"] {
                background-color: #ffffff !important;
            }
            
            /* サイドバー */
            section[data-testid="stSidebar"], .css-1d391kg {
                background-color: #f0f2f6 !important;
                color: #262730 !important;
            }
            
            /* ヘッダー */
            header[data-testid="stHeader"] {
                background-color: #ffffff !important;
            }
            
            /* すべてのセクション背景を透明に */
            section.main > div {
                background-color: transparent !important;
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
        }
        
        /* ダークモード用のスタイル */
        @media (prefers-color-scheme: dark) {
            /* メインアプリケーションの背景 */
            html, body, .stApp, .main, [data-testid="stAppViewContainer"] {
                background-color: #0e1117 !important;
                color: #fafafa !important;
            }
            
            /* サイドバー */
            section[data-testid="stSidebar"], .css-1d391kg {
                background-color: #262730 !important;
                color: #fafafa !important;
            }
            
            /* ヘッダー */
            header[data-testid="stHeader"] {
                background-color: #0e1117 !important;
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
        }
        
        /* 共通の強制スタイル - Streamlitのデフォルトスタイルを上書き */
        .stApp > div:first-child {
            background-color: inherit !important;
        }
        
        /* メインコンテンツエリアの背景を確実に設定 */
        .main .block-container {
            background-color: transparent !important;
        }
        </style>
        """
        st.markdown(theme_css, unsafe_allow_html=True)