#!/usr/bin/env python3
"""
API定義の検証スクリプト

docs/api_schemas/内のJSONファイルを検証し、
必要に応じて実際のAPIとの整合性をチェックする。
"""

import json
import sys
from pathlib import Path


def validate_json_schema(file_path: Path) -> list[str]:
    """JSONスキーマファイルを検証"""
    errors = []

    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        print(f"✅ {file_path.name}: JSONフォーマットOK")

        # 基本的な構造チェック
        if file_path.name == "whisper_api_schema.json":
            if "openapi" not in data:
                errors.append("OpenAPIバージョンが指定されていません")
            if "paths" not in data:
                errors.append("APIパス定義がありません")

        elif file_path.name == "ffmpeg_commands.json":
            if "commands" not in data:
                errors.append("コマンド定義がありません")

    except json.JSONDecodeError as e:
        errors.append(f"JSONパースエラー: {e}")
    except Exception as e:
        errors.append(f"読み込みエラー: {e}")

    return errors


def check_api_consistency():
    """APIの整合性チェック（将来の拡張用）"""
    print("\n📋 API整合性チェック:")

    # Whisper API料金チェック
    try:
        with open("main.py", encoding="utf-8") as f:
            content = f.read()
            if "$0.006/分" in content:
                print("✅ Whisper API料金: $0.006/分で一致")
            else:
                print("⚠️  main.pyのAPI料金を確認してください")
    except:
        print("⚠️  main.pyが見つかりません")


def main():
    """メイン処理"""
    print("🔍 API定義を検証中...\n")

    # スキーマディレクトリの確認
    schema_dir = Path("docs/api_schemas")
    if not schema_dir.exists():
        print("❌ docs/api_schemas/ディレクトリが見つかりません")
        sys.exit(1)

    # JSONファイルの検証
    json_files = list(schema_dir.glob("*.json"))
    if not json_files:
        print("⚠️  JSONファイルが見つかりません")
        sys.exit(0)

    all_errors = []
    for json_file in json_files:
        errors = validate_json_schema(json_file)
        if errors:
            print(f"❌ {json_file.name}:")
            for error in errors:
                print(f"   - {error}")
            all_errors.extend(errors)

    # API整合性チェック
    check_api_consistency()

    # 結果表示
    print("\n" + "=" * 50)
    if all_errors:
        print(f"❌ {len(all_errors)}個のエラーが見つかりました")
        sys.exit(1)
    else:
        print("✅ すべてのAPI定義が正常です！")

    # 利用可能なAPI情報を表示
    print("\n📚 利用可能なAPI定義:")
    for json_file in json_files:
        print(f"   - {json_file.name}")


if __name__ == "__main__":
    main()
