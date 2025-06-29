#!/usr/bin/env python3
"""
型アノテーションの自動修正スクリプト
"""
import re
from pathlib import Path


def add_return_none_annotation(content: str) -> str:
    """関数定義に -> None を追加"""
    # def func(): の形式を def func() -> None: に変換
    pattern = r'(\n\s*def\s+\w+\s*\([^)]*\)\s*):((?:\s*(?:#.*)?(?:\n|$))*\s*""")'

    def replace_func(match):
        prefix = match.group(1)
        suffix = match.group(2)
        # すでに型アノテーションがある場合はスキップ
        if "->" in prefix:
            return match.group(0)
        return f"{prefix} -> None:{suffix}"

    return re.sub(pattern, replace_func, content)


def add_type_imports(content: str) -> str:
    """必要な型インポートを追加"""
    lines = content.split("\n")

    # typing インポートを探す
    typing_import_idx = -1
    has_any = False

    for i, line in enumerate(lines):
        if line.startswith("from typing import"):
            typing_import_idx = i
            if "Any" in line:
                has_any = True
            if "Optional" in line:
                pass
            break

    # Anyが使われているが、インポートされていない場合
    if "Any" in content and not has_any:
        if typing_import_idx >= 0:
            # 既存のtypingインポートに追加
            lines[typing_import_idx] = lines[typing_import_idx].rstrip(")") + ", Any)"
        else:
            # 新規にtypingインポートを追加
            for i, line in enumerate(lines):
                if line.startswith("import ") or line.startswith("from "):
                    lines.insert(i, "from typing import Any")
                    break

    return "\n".join(lines)


def fix_path_type_annotations(content: str) -> str:
    """Path型の引数を Union[str, Path] に変換"""
    # video_path: str を video_path: Union[str, Path] に
    pattern = r"(\w+_path):\s*str\b"

    def needs_union_import(content: str) -> bool:
        return "Union[" in content or re.search(pattern, content) is not None

    if needs_union_import(content):
        # Union と Path のインポートを確認・追加
        if "from typing import" in content and "Union" not in content:
            content = content.replace("from typing import", "from typing import Union,")
        if "from pathlib import Path" not in content:
            # インポート部分に追加
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if line.startswith("import ") or line.startswith("from "):
                    lines.insert(i + 1, "from pathlib import Path")
                    break
            content = "\n".join(lines)

    # 型アノテーションを置換
    content = re.sub(pattern, r"\1: Union[str, Path]", content)
    return content


def fix_file(file_path: Path) -> bool:
    """ファイルの型アノテーションを修正"""
    try:
        content = file_path.read_text(encoding="utf-8")
        original = content

        # 各種修正を適用
        content = add_return_none_annotation(content)
        content = add_type_imports(content)
        content = fix_path_type_annotations(content)

        # 変更があった場合のみ書き込み
        if content != original:
            file_path.write_text(content, encoding="utf-8")
            print(f"Fixed: {file_path}")
            return True
        return False
    except Exception as e:
        print(f"Error fixing {file_path}: {e}")
        return False


def main():
    """メイン処理"""
    project_root = Path(__file__).parent
    fixed_count = 0

    # 対象ファイルを収集
    target_files: list[Path] = []
    for pattern in ["*.py", "core/*.py", "utils/*.py", "ui/*.py"]:
        target_files.extend(project_root.glob(pattern))

    # 各ファイルを修正
    for file_path in target_files:
        if file_path.name == "fix_type_annotations.py":
            continue
        if fix_file(file_path):
            fixed_count += 1

    print(f"\nTotal files fixed: {fixed_count}")


if __name__ == "__main__":
    main()
