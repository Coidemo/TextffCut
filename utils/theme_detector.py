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
                // テーマ検出の状態管理
                let lastDetectedTheme = null;
                let themeDetectionComplete = false;
                
                // テーマを検出する関数
                const detectTheme = () => {
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
                        console.debug('Theme detection method 1 not available');
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
                            console.debug('Theme detection method 2 not available');
                        }
                    }
                    
                    // 3. body要素の背景色をチェック
                    if (isDark === null && document.body) {
                        try {
                            const bgColor = window.getComputedStyle(document.body).backgroundColor;
                            // RGB値を解析
                            const rgb = bgColor.match(/\\d+/g);
                            if (rgb && rgb.length >= 3) {
                                // 暗い色かどうかを判定（しきい値: 128）
                                const brightness = (parseInt(rgb[0]) + parseInt(rgb[1]) + parseInt(rgb[2])) / 3;
                                isDark = brightness < 128;
                            }
                        } catch (e) {
                            console.debug('Theme detection method 3 failed');
                        }
                    }
                    
                    // 4. prefers-color-schemeをチェック（最終フォールバック）
                    if (isDark === null) {
                        try {
                            isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
                        } catch (e) {
                            // フォールバック: ライトモードをデフォルトとする
                            isDark = false;
                            console.debug('Using default theme: light');
                        }
                    }
                    
                    return isDark;
                };
                
                // 背景色を適用する関数（より効率的に）
                const applyBackgroundColor = () => {
                    const isDarkMode = window.matchMedia('(prefers-color-scheme: dark)').matches;
                    const theme = isDarkMode ? 'dark' : 'light';
                    
                    // すでに適用済みならスキップ
                    if (document.documentElement.getAttribute('data-theme-applied') === theme) {
                        return;
                    }
                    
                    const bgColor = isDarkMode ? '#0e1117' : '#ffffff';
                    const textColor = isDarkMode ? '#fafafa' : '#262730';
                    const sidebarBg = isDarkMode ? '#262730' : '#f0f2f6';
                    
                    // CSSカスタムプロパティを使用して一括適用
                    const style = document.createElement('style');
                    style.id = 'theme-detector-styles';
                    style.textContent = `
                        :root {
                            --theme-bg-color: ${bgColor};
                            --theme-text-color: ${textColor};
                            --theme-sidebar-bg: ${sidebarBg};
                        }
                        html, body, .stApp, .main, [data-testid="stAppViewContainer"] {
                            background-color: var(--theme-bg-color);
                            color: var(--theme-text-color);
                        }
                        section[data-testid="stSidebar"], .css-1d391kg {
                            background-color: var(--theme-sidebar-bg);
                        }
                    `;
                    
                    // 既存のスタイルを置き換え
                    const existingStyle = document.getElementById('theme-detector-styles');
                    if (existingStyle) {
                        existingStyle.remove();
                    }
                    document.head.appendChild(style);
                    
                    // 適用済みフラグを設定
                    document.documentElement.setAttribute('data-theme-applied', theme);
                };
                
                // MutationObserverを使ってDOM変更を監視
                const observer = new MutationObserver((mutations) => {
                    // Streamlitの動的レンダリングを検出
                    const shouldRecheck = mutations.some(mutation => {
                        return mutation.type === 'childList' && 
                               (mutation.target.classList.contains('stApp') || 
                                mutation.target.tagName === 'BODY');
                    });
                    
                    if (shouldRecheck && !themeDetectionComplete) {
                        const currentTheme = detectTheme();
                        if (currentTheme !== null && currentTheme !== lastDetectedTheme) {
                            lastDetectedTheme = currentTheme;
                            console.log('Theme detected:', currentTheme ? 'dark' : 'light');
                            applyBackgroundColor();
                            
                            // 安定したテーマが検出されたら監視を減らす
                            if (currentTheme !== null) {
                                themeDetectionComplete = true;
                                // 監視を続けるが、頻度を下げる
                                observer.disconnect();
                                observer.observe(document.body, {
                                    childList: true,
                                    subtree: false // subtreeをfalseにして負荷を軽減
                                });
                            }
                        }
                    }
                });
                
                // 初期設定とオブザーバーの開始
                const initialize = () => {
                    // 初回のテーマ検出と適用
                    lastDetectedTheme = detectTheme();
                    applyBackgroundColor();
                    
                    // DOM監視を開始
                    if (document.body) {
                        observer.observe(document.body, {
                            childList: true,
                            subtree: true,
                            attributes: false,
                            characterData: false
                        });
                    }
                    
                    // メディアクエリの変更を監視
                    try {
                        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
                            console.log('System theme changed:', e.matches ? 'dark' : 'light');
                            applyBackgroundColor();
                        });
                    } catch (e) {
                        // 古いブラウザのフォールバック
                        window.matchMedia('(prefers-color-scheme: dark)').addListener((e) => {
                            console.log('System theme changed:', e.matches ? 'dark' : 'light');
                            applyBackgroundColor();
                        });
                    }
                };
                
                // DOMContentLoadedまたは即座に実行
                if (document.readyState === 'loading') {
                    document.addEventListener('DOMContentLoaded', initialize);
                } else {
                    initialize();
                }
                
                // クリーンアップ関数（必要に応じて）
                window.addEventListener('beforeunload', () => {
                    observer.disconnect();
                });
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
        # より具体的なセレクタで特異性を高め、!importantの使用を最小限に
        theme_css = """
        <style>
        /* デフォルト値（CSS変数非対応ブラウザ用フォールバック） */
        :root {
            /* ライトモードをデフォルトとして設定 */
            --textffcut-bg-primary: #ffffff;
            --textffcut-bg-secondary: #f0f2f6;
            --textffcut-text-primary: #262730;
            --textffcut-text-secondary: #555555;
            --textffcut-highlight-match: #28a745;
            --textffcut-highlight-addition: #dc3545;
            --textffcut-highlight-text: #ffffff;
            --textffcut-highlight-text-match: #ffffff;
            --textffcut-highlight-text-addition: #ffffff;
        }
        
        /* CSS変数の定義 - メディアクエリで上書き */
        @media (prefers-color-scheme: light) {
            :root {
                --textffcut-bg-primary: #ffffff;
                --textffcut-bg-secondary: #f0f2f6;
                --textffcut-text-primary: #262730;
                --textffcut-text-secondary: #555555;
                --textffcut-highlight-match: #28a745;
                --textffcut-highlight-addition: #dc3545;
                --textffcut-highlight-text: #ffffff;
                --textffcut-highlight-text-match: #ffffff;
                --textffcut-highlight-text-addition: #ffffff;
            }
        }
        
        @media (prefers-color-scheme: dark) {
            :root {
                --textffcut-bg-primary: #0e1117;
                --textffcut-bg-secondary: #262730;
                --textffcut-text-primary: #fafafa;
                --textffcut-text-secondary: #cccccc;
                --textffcut-highlight-match: #2d5a2d;
                --textffcut-highlight-addition: #5a2d2d;
                --textffcut-highlight-text-match: #b8e7b8;
                --textffcut-highlight-text-addition: #ffb3b3;
            }
        }
        
        /* CSS変数非対応ブラウザ用の直接指定フォールバック */
        @supports not (--css: variables) {
            /* ライトモードのフォールバック */
            html, body, .stApp {
                background-color: #ffffff;
                color: #262730;
            }
            
            section[data-testid="stSidebar"] {
                background-color: #f0f2f6;
                color: #262730;
            }
        }
        
        /* 特異性の高いセレクタで背景色を設定 */
        /* ルート要素 */
        html:root,
        body:root {
            background-color: var(--textffcut-bg-primary);
            color: var(--textffcut-text-primary);
        }
        
        /* Streamlitメインアプリケーション */
        .stApp,
        body > div:first-child > div.stApp,
        [data-testid="stAppViewContainer"] {
            background-color: var(--textffcut-bg-primary);
            color: var(--textffcut-text-primary);
        }
        
        /* メインコンテンツエリア */
        .main,
        section.main,
        .stApp > section.main {
            background-color: var(--textffcut-bg-primary);
        }
        
        /* ブロックコンテナ - transparentで親の背景を継承 */
        .block-container,
        div[data-testid="block-container"],
        .main .block-container,
        section.main .block-container {
            background-color: transparent;
        }
        
        /* サイドバー - より具体的なセレクタ */
        section[data-testid="stSidebar"],
        .stApp section[data-testid="stSidebar"],
        section[data-testid="stSidebar"] > div:first-child {
            background-color: var(--textffcut-bg-secondary);
            color: var(--textffcut-text-primary);
        }
        
        /* ヘッダー */
        header[data-testid="stHeader"],
        .stApp header[data-testid="stHeader"] {
            background-color: var(--textffcut-bg-primary);
        }
        
        /* 内部要素の背景を継承 */
        .stApp > div:first-child,
        section.main > div {
            background-color: inherit;
        }
        
        /* ハイライト色 - より具体的なセレクタで!importantを回避 */
        /* ライトモード */
        @media (prefers-color-scheme: light) {
            .highlight-match,
            .stApp .highlight-match,
            span.highlight-match {
                background-color: var(--textffcut-highlight-match);
                color: var(--textffcut-highlight-text);
                padding: 2px 4px;
                border-radius: 3px;
            }
            
            .highlight-addition,
            .stApp .highlight-addition,
            span.highlight-addition {
                background-color: var(--textffcut-highlight-addition);
                color: var(--textffcut-highlight-text);
                padding: 2px 4px;
                border-radius: 3px;
            }
        }
        
        /* ダークモード */
        @media (prefers-color-scheme: dark) {
            .highlight-match,
            .stApp .highlight-match,
            span.highlight-match {
                background-color: var(--textffcut-highlight-match);
                color: var(--textffcut-highlight-text-match);
                padding: 2px 4px;
                border-radius: 3px;
            }
            
            .highlight-addition,
            .stApp .highlight-addition,
            span.highlight-addition {
                background-color: var(--textffcut-highlight-addition);
                color: var(--textffcut-highlight-text-addition);
                padding: 2px 4px;
                border-radius: 3px;
            }
        }
        
        /* Streamlitのデフォルトスタイルより優先度を高くする追加セレクタ */
        /* 必要最小限の!importantのみ使用 */
        html body .stApp {
            background-color: var(--textffcut-bg-primary) !important;
        }
        
        /* トランジションを追加してちらつきを軽減 */
        html, body, .stApp, .main, section[data-testid="stSidebar"] {
            transition: background-color 0.2s ease, color 0.2s ease;
        }
        </style>
        """
        st.markdown(theme_css, unsafe_allow_html=True)
