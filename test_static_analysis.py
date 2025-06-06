#!/usr/bin/env python
"""
静的解析テストスクリプト
新しい2段階処理アーキテクチャのコードを検証
"""

import ast
import os
import sys
from pathlib import Path
from typing import List, Dict, Set, Tuple

# 新規追加ファイルのリスト
NEW_FILES = [
    "core/models.py",
    "core/exceptions.py", 
    "core/interfaces.py",
    "core/unified_transcriber.py",
    "core/alignment_processor.py",
    "core/retry_handler.py",
    "core/transcription_worker.py"
]

# 更新されたファイルのリスト
UPDATED_FILES = [
    "core/transcription.py",
    "main.py",
    "worker_align.py",
    "worker_transcribe.py"
]


class CodeAnalyzer:
    """コード解析クラス"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.errors = []
        self.warnings = []
        self.imports = {}  # ファイル名: インポートリスト
        self.defined_names = {}  # ファイル名: 定義された名前のリスト
        self.used_names = {}  # ファイル名: 使用された名前のリスト
        
    def analyze_file(self, filepath: str) -> bool:
        """ファイルを解析"""
        full_path = self.project_root / filepath
        
        if not full_path.exists():
            self.errors.append(f"ファイルが存在しません: {filepath}")
            return False
            
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 構文解析
            tree = ast.parse(content, filename=str(full_path))
            
            # インポート、定義、使用を収集
            self.analyze_ast(tree, filepath)
            
            print(f"✓ {filepath}: 構文エラーなし")
            return True
            
        except SyntaxError as e:
            self.errors.append(f"構文エラー in {filepath}: {e}")
            return False
        except Exception as e:
            self.errors.append(f"解析エラー in {filepath}: {e}")
            return False
    
    def analyze_ast(self, tree: ast.AST, filepath: str):
        """ASTを解析してインポート、定義、使用を収集"""
        imports = []
        defined = set()
        used = set()
        
        class Visitor(ast.NodeVisitor):
            def visit_Import(self, node):
                for alias in node.names:
                    imports.append(alias.name)
                self.generic_visit(node)
                
            def visit_ImportFrom(self, node):
                module = node.module or ''
                for alias in node.names:
                    imports.append(f"{module}.{alias.name}")
                self.generic_visit(node)
                
            def visit_FunctionDef(self, node):
                defined.add(node.name)
                self.generic_visit(node)
                
            def visit_ClassDef(self, node):
                defined.add(node.name)
                self.generic_visit(node)
                
            def visit_Name(self, node):
                if isinstance(node.ctx, ast.Load):
                    used.add(node.id)
                elif isinstance(node.ctx, ast.Store):
                    defined.add(node.id)
                self.generic_visit(node)
                
        visitor = Visitor()
        visitor.visit(tree)
        
        self.imports[filepath] = imports
        self.defined_names[filepath] = defined
        self.used_names[filepath] = used
    
    def check_imports(self):
        """インポートの整合性をチェック"""
        print("\n=== インポートチェック ===")
        
        # プロジェクト内のインポートを確認
        for filepath, imports in self.imports.items():
            for imp in imports:
                if imp.startswith("core.") or imp.startswith("utils."):
                    # プロジェクト内のインポート
                    module_path = imp.replace(".", "/") + ".py"
                    if not (self.project_root / module_path).exists():
                        # __init__.pyやディレクトリの可能性もある
                        dir_path = self.project_root / imp.replace(".", "/")
                        init_path = dir_path / "__init__.py"
                        if not dir_path.exists() and not init_path.exists():
                            self.warnings.append(f"{filepath}: インポート '{imp}' が見つかりません")
    
    def check_undefined_variables(self):
        """未定義変数のチェック"""
        print("\n=== 未定義変数チェック ===")
        
        # Python組み込み名
        builtins = set(dir(__builtins__))
        
        for filepath in self.defined_names:
            defined = self.defined_names[filepath]
            used = self.used_names[filepath]
            
            # インポートされた名前を追加
            imported = set()
            for imp in self.imports.get(filepath, []):
                if "." in imp:
                    # モジュールから特定の名前をインポート
                    parts = imp.split(".")
                    imported.add(parts[-1])
                else:
                    # モジュール全体をインポート
                    imported.add(imp)
            
            # 未定義の名前を検出
            undefined = used - defined - imported - builtins
            
            # 一般的な名前を除外（self, cls, logger等）
            common_names = {'self', 'cls', 'logger', 'Optional', 'List', 'Dict', 
                          'Any', 'Tuple', 'Union', 'Callable', 'TypeVar'}
            undefined = undefined - common_names
            
            if undefined:
                self.warnings.append(f"{filepath}: 未定義の可能性がある名前: {undefined}")
    
    def find_unused_code(self):
        """未使用のコードを検出"""
        print("\n=== 未使用コードチェック ===")
        
        # 各ファイルで定義されているが使用されていない名前
        for filepath in self.defined_names:
            defined = self.defined_names[filepath]
            used = self.used_names[filepath]
            
            # 特殊メソッドやプライベートメソッドを除外
            unused = set()
            for name in defined:
                if name not in used and not name.startswith('_'):
                    # 他のファイルで使用されている可能性があるため警告レベル
                    unused.add(name)
            
            if unused:
                self.warnings.append(f"{filepath}: 未使用の可能性がある定義: {unused}")
    
    def print_results(self):
        """結果を表示"""
        print("\n=== 解析結果 ===")
        
        if self.errors:
            print(f"\n❌ エラー: {len(self.errors)}件")
            for error in self.errors:
                print(f"  - {error}")
        else:
            print("\n✅ エラーなし")
            
        if self.warnings:
            print(f"\n⚠️  警告: {len(self.warnings)}件")
            for warning in self.warnings:
                print(f"  - {warning}")
        else:
            print("\n✅ 警告なし")


def main():
    """メイン処理"""
    project_root = Path(__file__).parent
    analyzer = CodeAnalyzer(project_root)
    
    print("=== 静的解析開始 ===")
    print(f"プロジェクトルート: {project_root}")
    
    # 新規ファイルの解析
    print("\n--- 新規ファイルの解析 ---")
    for filepath in NEW_FILES:
        analyzer.analyze_file(filepath)
    
    # 更新ファイルの解析
    print("\n--- 更新ファイルの解析 ---")
    for filepath in UPDATED_FILES:
        analyzer.analyze_file(filepath)
    
    # チェック実行
    analyzer.check_imports()
    analyzer.check_undefined_variables()
    analyzer.find_unused_code()
    
    # 結果表示
    analyzer.print_results()


if __name__ == "__main__":
    main()