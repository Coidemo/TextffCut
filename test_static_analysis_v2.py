#!/usr/bin/env python
"""
静的解析テストスクリプト v2
より詳細な解析とレポート機能を追加
"""

import ast
import os
import sys
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
import importlib.util

class DetailedCodeAnalyzer:
    """詳細なコード解析クラス"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.results = {}  # filepath: {errors, warnings, info}
        
    def analyze_file(self, filepath: str) -> dict:
        """ファイルを詳細に解析"""
        full_path = self.project_root / filepath
        result = {
            'errors': [],
            'warnings': [],
            'info': {
                'imports': [],
                'functions': [],
                'classes': [],
                'globals': [],
                'line_count': 0
            }
        }
        
        if not full_path.exists():
            result['errors'].append(f"ファイルが存在しません: {filepath}")
            return result
            
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
                result['info']['line_count'] = len(content.splitlines())
                
            # 構文解析
            tree = ast.parse(content, filename=str(full_path))
            
            # 詳細解析
            analyzer = FileAnalyzer(filepath)
            analyzer.visit(tree)
            
            # 結果を統合
            result['warnings'].extend(analyzer.warnings)
            result['info'].update({
                'imports': analyzer.imports,
                'functions': analyzer.functions,
                'classes': analyzer.classes,
                'globals': analyzer.globals,
                'used_names': analyzer.used_names,
                'defined_names': analyzer.defined_names
            })
            
        except SyntaxError as e:
            result['errors'].append(f"構文エラー: {e}")
        except Exception as e:
            result['errors'].append(f"解析エラー: {e}")
            
        self.results[filepath] = result
        return result
    
    def check_unused_imports(self):
        """未使用のインポートをチェック"""
        for filepath, result in self.results.items():
            if 'errors' in result and result['errors']:
                continue
                
            imports = result['info'].get('imports', [])
            used_names = result['info'].get('used_names', set())
            
            for imp in imports:
                imp_name = imp.split('.')[-1]
                # asで別名を付けている場合の処理
                if ' as ' in imp:
                    imp_name = imp.split(' as ')[-1].strip()
                    
                if imp_name not in used_names and not imp_name.startswith('_'):
                    result['warnings'].append(f"未使用のインポート: {imp}")
    
    def check_undefined_names(self):
        """未定義の名前をチェック"""
        builtins = set(dir(__builtins__))
        common_globals = {'__name__', '__file__', '__doc__', 'logger'}
        
        for filepath, result in self.results.items():
            if 'errors' in result and result['errors']:
                continue
                
            defined = result['info'].get('defined_names', set())
            used = result['info'].get('used_names', set())
            imports = result['info'].get('imports', [])
            
            # インポートされた名前を追加
            imported_names = set()
            for imp in imports:
                if ' as ' in imp:
                    imported_names.add(imp.split(' as ')[-1].strip())
                elif 'from ' in imp:
                    parts = imp.split()
                    if 'import' in parts:
                        idx = parts.index('import')
                        imported_names.update(parts[idx+1:])
                else:
                    imported_names.add(imp.split('.')[-1])
            
            # 未定義の名前を検出
            undefined = used - defined - imported_names - builtins - common_globals
            
            # 型アノテーション関連を除外
            type_names = {'Optional', 'List', 'Dict', 'Tuple', 'Union', 'Any', 
                         'Callable', 'TypeVar', 'Type', 'Set', 'Literal'}
            undefined = undefined - type_names
            
            # self, clsなどを除外
            special_names = {'self', 'cls', 'args', 'kwargs'}
            undefined = undefined - special_names
            
            if undefined:
                result['warnings'].append(f"未定義の可能性がある名前: {sorted(undefined)}")
    
    def check_unused_definitions(self):
        """未使用の定義をチェック"""
        # 全ファイルのエクスポートを収集
        all_exports = set()
        for filepath, result in self.results.items():
            # __init__.pyの場合、全定義がエクスポートされる可能性
            if filepath.endswith('__init__.py'):
                all_exports.update(result['info'].get('defined_names', set()))
        
        for filepath, result in self.results.items():
            if 'errors' in result and result['errors']:
                continue
                
            functions = result['info'].get('functions', [])
            classes = result['info'].get('classes', [])
            used = result['info'].get('used_names', set())
            
            # 未使用の関数
            for func in functions:
                if (func not in used and 
                    not func.startswith('_') and 
                    func not in all_exports and
                    func not in ['main', 'setup', 'teardown']):
                    result['warnings'].append(f"未使用の可能性がある関数: {func}")
            
            # 未使用のクラス
            for cls in classes:
                if (cls not in used and 
                    not cls.startswith('_') and 
                    cls not in all_exports):
                    result['warnings'].append(f"未使用の可能性があるクラス: {cls}")
    
    def report_results(self):
        """結果をレポート"""
        print(f"\n{'='*50}")
        print("静的解析結果")
        print(f"{'='*50}")
        
        print(f"\n解析ファイル数: {len(self.results)}")
        
        # エラーと警告の集計
        total_errors = sum(len(r['errors']) for r in self.results.values())
        total_warnings = sum(len(r['warnings']) for r in self.results.values())
        
        print(f"総エラー数: {total_errors}")
        print(f"総警告数: {total_warnings}")
        
        # 警告の種類別集計
        warning_types = {}
        for filepath, result in self.results.items():
            for warning in result['warnings']:
                # 警告の種類を抽出
                if "未使用のインポート" in warning:
                    key = "未使用のインポート"
                elif "未使用の可能性がある関数" in warning:
                    key = "未使用の関数"
                elif "未使用の可能性があるクラス" in warning:
                    key = "未使用のクラス"
                elif "未定義の可能性がある名前" in warning:
                    key = "未定義の名前"
                else:
                    key = "その他"
                
                if key not in warning_types:
                    warning_types[key] = []
                warning_types[key].append((filepath, warning))
        
        # 種類別に表示
        print(f"\n{'='*30}")
        print("警告の種類別内訳")
        print(f"{'='*30}")
        for wtype, items in sorted(warning_types.items()):
            print(f"\n{wtype}: {len(items)}件")
            # 最初の3件を例として表示
            for i, (filepath, warning) in enumerate(items[:3]):
                print(f"  例{i+1}: {os.path.basename(filepath)}: {warning}")
            if len(items) > 3:
                print(f"  ... 他 {len(items)-3}件")
        
        # エラー詳細
        if total_errors > 0:
            print(f"\n{'='*30}")
            print("エラー詳細")
            print(f"{'='*30}")
            for filepath, result in self.results.items():
                if result['errors']:
                    print(f"\n{filepath}:")
                    for error in result['errors']:
                        print(f"  E: {error}")
        
        # ファイル情報サマリー
        print(f"\n{'='*30}")
        print("ファイル情報サマリー")
        print(f"{'='*30}")
        total_lines = sum(r['info']['line_count'] for r in self.results.values())
        total_functions = sum(len(r['info']['functions']) for r in self.results.values())
        total_classes = sum(len(r['info']['classes']) for r in self.results.values())
        
        print(f"総行数: {total_lines}")
        print(f"総関数数: {total_functions}")
        print(f"総クラス数: {total_classes}")
        
        return total_errors == 0


class FileAnalyzer(ast.NodeVisitor):
    """個別ファイルのAST解析"""
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.warnings = []
        self.imports = []
        self.functions = []
        self.classes = []
        self.globals = []
        self.used_names = set()
        self.defined_names = set()
        self.current_scope = []
        
    def visit_Import(self, node):
        for alias in node.names:
            import_str = alias.name
            if alias.asname:
                import_str += f" as {alias.asname}"
                self.defined_names.add(alias.asname)
            else:
                self.defined_names.add(alias.name.split('.')[0])
            self.imports.append(import_str)
        self.generic_visit(node)
        
    def visit_ImportFrom(self, node):
        module = node.module or ''
        for alias in node.names:
            if alias.name == '*':
                self.imports.append(f"from {module} import *")
                self.warnings.append(f"ワイルドカードインポート: from {module} import *")
            else:
                import_str = f"from {module} import {alias.name}"
                if alias.asname:
                    import_str += f" as {alias.asname}"
                    self.defined_names.add(alias.asname)
                else:
                    self.defined_names.add(alias.name)
                self.imports.append(import_str)
        self.generic_visit(node)
        
    def visit_FunctionDef(self, node):
        self.functions.append(node.name)
        self.defined_names.add(node.name)
        
        # 関数内のスコープ
        self.current_scope.append('function')
        
        # デコレータをチェック
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name):
                self.used_names.add(decorator.id)
        
        self.generic_visit(node)
        self.current_scope.pop()
        
    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)  # 同じ処理
        
    def visit_ClassDef(self, node):
        self.classes.append(node.name)
        self.defined_names.add(node.name)
        
        # クラス内のスコープ
        self.current_scope.append('class')
        
        # 基底クラスをチェック
        for base in node.bases:
            if isinstance(base, ast.Name):
                self.used_names.add(base.id)
        
        self.generic_visit(node)
        self.current_scope.pop()
        
    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            self.used_names.add(node.id)
        elif isinstance(node.ctx, ast.Store):
            self.defined_names.add(node.id)
            # グローバル変数
            if not self.current_scope:
                self.globals.append(node.id)
        self.generic_visit(node)
        
    def visit_Attribute(self, node):
        # 属性アクセス（例: os.path）
        if isinstance(node.value, ast.Name) and isinstance(node.ctx, ast.Load):
            self.used_names.add(node.value.id)
        self.generic_visit(node)


def analyze_all_files(project_root: Path):
    """プロジェクト全体を解析"""
    analyzer = DetailedCodeAnalyzer(project_root)
    
    # 新規追加ファイル
    new_files = [
        "core/models.py",
        "core/exceptions.py", 
        "core/interfaces.py",
        "core/unified_transcriber.py",
        "core/alignment_processor.py",
        "core/retry_handler.py",
        "core/transcription_worker.py"
    ]
    
    # 更新されたファイル
    updated_files = [
        "core/transcription.py",
        "main.py",
        "worker_align.py", 
        "worker_transcribe.py",
        "utils/system_resources.py"
    ]
    
    print("=== 詳細静的解析開始 ===")
    print(f"プロジェクトルート: {project_root}")
    
    # 全ファイルを解析
    all_files = new_files + updated_files
    for filepath in all_files:
        analyzer.analyze_file(filepath)
    
    # 各種チェックを実行
    analyzer.check_unused_imports()
    analyzer.check_undefined_names()
    analyzer.check_unused_definitions()
    
    # 結果レポート
    success = analyzer.report_results()
    
    # 詳細な警告リストを別ファイルに出力
    if '--verbose' in sys.argv:
        print(f"\n{'='*30}")
        print("警告詳細（全リスト）")
        print(f"{'='*30}")
        for filepath, result in analyzer.results.items():
            if result['warnings']:
                print(f"\n{filepath}:")
                for warning in result['warnings']:
                    print(f"  W: {warning}")
    
    return success


if __name__ == "__main__":
    project_root = Path(__file__).parent
    success = analyze_all_files(project_root)
    sys.exit(0 if success else 1)