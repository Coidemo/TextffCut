"""
タイムライン編集の問題を修正するパッチ
1. タイムライン編集後の出力でadjusted_time_rangesが使用されない問題
2. 出力ファイル変更時に編集がリセットされる問題
"""

import re


def fix_timeline_issues():
    """main.pyのタイムライン編集関連の問題を修正"""

    with open("main.py", encoding="utf-8") as f:
        content = f.read()

    # 修正1: タイムライン編集で調整された時間範囲を確実に使用する
    # 問題: adjusted_time_rangesの取得タイミングが遅い

    # 「タイムライン編集で調整された時間範囲があれば使用」のブロックを移動
    # 現在は処理実行ボタンの中にあるが、これを「更新ボタン」の処理後に移動する

    # パターン1: 更新ボタンの処理後にadjusted_time_rangesをチェック
    pattern1 = r'(if st\.button\("🔄 更新".*?\n\s+st\.session_state\.edited_text = edited_text)'
    replacement1 = r"""\1

                    # タイムライン編集で調整された時間範囲があれば保持
                    if "adjusted_time_ranges" in st.session_state:
                        st.session_state.time_ranges_cache = st.session_state.adjusted_time_ranges"""

    content = re.sub(pattern1, replacement1, content, flags=re.DOTALL)

    # パターン2: time_rangesの計算時にキャッシュを優先
    pattern2 = r"(time_ranges = diff\.get_time_ranges\(transcription\))"
    replacement2 = r"""# タイムライン編集のキャッシュがあれば優先
                    if "time_ranges_cache" in st.session_state:
                        time_ranges = st.session_state.time_ranges_cache
                    else:
                        time_ranges = diff.get_time_ranges(transcription)"""

    content = re.sub(pattern2, replacement2, content)

    # 修正2: 出力設定変更時のタイムライン編集状態のクリア
    # 問題: 出力設定が変更されてもadjusted_time_rangesが残る

    # パターン3: 出力設定の変更を検出してクリア
    pattern3 = r'(# 出力形式の選択.*?\n.*?st\.selectbox.*?"primary_format".*?\))'
    replacement3 = r"""\1

            # 出力形式が変更されたらタイムライン編集のキャッシュをクリア
            if "last_primary_format" in st.session_state:
                if st.session_state.last_primary_format != primary_format:
                    if "time_ranges_cache" in st.session_state:
                        del st.session_state.time_ranges_cache
                    if "adjusted_time_ranges" in st.session_state:
                        del st.session_state.adjusted_time_ranges
            st.session_state.last_primary_format = primary_format"""

    content = re.sub(pattern3, replacement3, content, flags=re.DOTALL)

    # 修正3: タイムライン編集完了時の処理を改善
    pattern4 = r"(if adjusted_ranges is not None:.*?st\.session_state\.adjusted_time_ranges = adjusted_ranges)"
    replacement4 = r"""\1
                st.session_state.time_ranges_cache = adjusted_ranges  # キャッシュにも保存"""

    content = re.sub(pattern4, replacement4, content, flags=re.DOTALL)

    # 修正4: 処理実行時のadjusted_time_rangesの削除を防ぐ
    pattern5 = r"del st\.session_state\.adjusted_time_ranges  # 使用後は削除"
    replacement5 = "# adjusted_time_rangesは保持（出力設定変更時にクリア）"

    content = content.replace(pattern5, replacement5)

    return content


def create_backup():
    """main.pyのバックアップを作成"""
    import shutil

    shutil.copy("main.py", "main.py.backup")
    print("バックアップを作成しました: main.py.backup")


def apply_fix():
    """修正を適用"""
    create_backup()

    fixed_content = fix_timeline_issues()

    with open("main.py", "w", encoding="utf-8") as f:
        f.write(fixed_content)

    print("修正を適用しました")
    print("\n主な変更点:")
    print("1. タイムライン編集の結果をtime_ranges_cacheに保存")
    print("2. 出力形式変更時にキャッシュをクリア")
    print("3. adjusted_time_rangesの削除を防止")


if __name__ == "__main__":
    apply_fix()
