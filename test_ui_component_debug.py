"""UIコンポーネントのデバッグ"""

from domain.entities.text_difference import DifferenceType, TextDifference

# テスト用の差分情報
differences = [
    (DifferenceType.UNCHANGED, "これは変更なしのテキストです", None),
    (DifferenceType.ADDED, "これは追加されたテキスト", None),
    (DifferenceType.UNCHANGED, "また変更なし", None),
]

diff = TextDifference(
    id="test",
    original_text="これは変更なしのテキストですまた変更なし",
    edited_text="これは変更なしのテキストですこれは追加されたテキストまた変更なし",
    differences=differences
)

# UIコンポーネントの動作を確認
print("差分情報:")
for diff_type, text, _ in diff.differences:
    print(f"  {diff_type.value}: {text}")

print(f"\n追加文字の数: {diff.added_count}")
print(f"追加された文字: {diff.added_chars}")

# HTMLの生成を確認
from ui.components import show_edited_text_with_highlights

# 実際のHTMLを生成する部分をシミュレート
added_chars = diff.added_chars
edited_text = diff.edited_text

print(f"\n追加文字セット: {added_chars}")
print(f"編集テキスト: {edited_text}")

# 各文字が追加文字かチェック
for char in edited_text:
    if char in added_chars:
        print(f"'{char}' -> 赤")
    else:
        print(f"'{char}' -> 通常")