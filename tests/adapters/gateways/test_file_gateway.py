"""
FileGatewayAdapterのテスト
"""

import json
import pytest
import tempfile
from pathlib import Path

from domain.value_objects import FilePath
from adapters.gateways.file.file_gateway import FileGatewayAdapter


class TestFileGatewayAdapter:
    """FileGatewayAdapterのテスト"""
    
    @pytest.fixture
    def gateway(self):
        """テスト用ゲートウェイ"""
        return FileGatewayAdapter()
    
    @pytest.fixture
    def temp_dir(self):
        """テスト用一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as temp:
            yield Path(temp)
    
    def test_file_operations(self, gateway, temp_dir):
        """ファイル操作の基本テスト"""
        # テストファイルのパス
        test_file = FilePath(str(temp_dir / "test.txt"))
        
        # 存在確認（まだ存在しない）
        assert not gateway.exists(test_file)
        assert not gateway.is_file(test_file)
        
        # ファイル書き込み
        content = "Hello, World!"
        gateway.write_text(test_file, content)
        
        # 存在確認
        assert gateway.exists(test_file)
        assert gateway.is_file(test_file)
        assert not gateway.is_directory(test_file)
        
        # ファイル読み込み
        read_content = gateway.read_text(test_file)
        assert read_content == content
        
        # ファイルサイズ
        size = gateway.get_size(test_file)
        assert size == len(content.encode('utf-8'))
        
        # ファイル削除
        gateway.delete_file(test_file)
        assert not gateway.exists(test_file)
    
    def test_json_operations(self, gateway, temp_dir):
        """JSON操作のテスト"""
        json_file = FilePath(str(temp_dir / "test.json"))
        
        # JSONデータ
        data = {
            "name": "テスト",
            "value": 123,
            "nested": {"key": "value"}
        }
        
        # JSON書き込み
        gateway.write_json(json_file, data)
        assert gateway.exists(json_file)
        
        # JSON読み込み
        loaded_data = gateway.read_json(json_file)
        assert loaded_data == data
        
        # 無効なJSON
        invalid_json_file = FilePath(str(temp_dir / "invalid.json"))
        gateway.write_text(invalid_json_file, "{invalid json")
        
        with pytest.raises(ValueError, match="Invalid JSON format"):
            gateway.read_json(invalid_json_file)
    
    def test_directory_operations(self, gateway, temp_dir):
        """ディレクトリ操作のテスト"""
        # ネストしたディレクトリ
        nested_dir = FilePath(str(temp_dir / "a" / "b" / "c"))
        
        # ディレクトリ作成
        gateway.create_directory(nested_dir)
        assert gateway.exists(nested_dir)
        assert gateway.is_directory(nested_dir)
        assert not gateway.is_file(nested_dir)
        
        # ファイル一覧（空）
        files = gateway.list_files(nested_dir)
        assert files == []
        
        # ファイルを作成
        file1 = FilePath(str(Path(str(nested_dir)) / "file1.txt"))
        file2 = FilePath(str(Path(str(nested_dir)) / "file2.txt"))
        gateway.write_text(file1, "content1")
        gateway.write_text(file2, "content2")
        
        # ファイル一覧
        files = gateway.list_files(nested_dir)
        assert len(files) == 2
        assert file1 in files
        assert file2 in files
        
        # パターンマッチ
        txt_files = gateway.list_files(nested_dir, "*.txt")
        assert len(txt_files) == 2
        
        # ディレクトリ削除（再帰的）
        root_dir = FilePath(str(temp_dir / "a"))
        gateway.delete_directory(root_dir, recursive=True)
        assert not gateway.exists(root_dir)
    
    def test_copy_and_move_operations(self, gateway, temp_dir):
        """コピーと移動のテスト"""
        # ソースファイル
        source = FilePath(str(temp_dir / "source.txt"))
        content = "Test content"
        gateway.write_text(source, content)
        
        # ファイルコピー
        copy_dest = FilePath(str(temp_dir / "copy.txt"))
        gateway.copy_file(source, copy_dest)
        
        assert gateway.exists(source)  # ソースは残る
        assert gateway.exists(copy_dest)
        assert gateway.read_text(copy_dest) == content
        
        # ファイル移動
        move_dest = FilePath(str(temp_dir / "moved.txt"))
        gateway.move_file(source, move_dest)
        
        assert not gateway.exists(source)  # ソースは削除される
        assert gateway.exists(move_dest)
        assert gateway.read_text(move_dest) == content
    
    def test_temp_directory_management(self, gateway):
        """一時ディレクトリ管理のテスト"""
        # 一時ディレクトリ作成
        temp1 = gateway.create_temp_directory(prefix="test1_")
        temp2 = gateway.create_temp_directory(prefix="test2_", suffix="_tmp")
        
        assert gateway.exists(temp1)
        assert gateway.exists(temp2)
        assert gateway.is_directory(temp1)
        assert gateway.is_directory(temp2)
        
        # プレフィックス/サフィックスの確認
        assert "test1_" in str(temp1)
        assert "test2_" in str(temp2)
        assert str(temp2).endswith("_tmp")
        
        # クリーンアップ
        gateway.cleanup_temp_directories()
        
        # クリーンアップ後は存在しない
        assert not Path(str(temp1)).exists()
        assert not Path(str(temp2)).exists()
    
    def test_path_operations(self, gateway, temp_dir):
        """パス操作のテスト"""
        # ベースパスを設定したゲートウェイ
        base_gateway = FileGatewayAdapter(base_path=temp_dir)
        
        # 絶対パス
        rel_path = FilePath("subdir/file.txt")
        abs_path = base_gateway.get_absolute_path(rel_path)
        assert Path(str(abs_path)).is_absolute()
        
        # 相対パス
        full_path = FilePath(str(temp_dir / "a" / "b" / "c.txt"))
        relative = base_gateway.get_relative_path(full_path)
        assert str(relative) == "a/b/c.txt"
        
        # 基準外のパス
        outside_path = FilePath("/tmp/outside.txt")
        relative_outside = base_gateway.get_relative_path(outside_path)
        assert relative_outside == outside_path  # 変更されない
    
    def test_error_handling(self, gateway, temp_dir):
        """エラーハンドリングのテスト"""
        # 存在しないファイルの読み込み
        non_existent = FilePath(str(temp_dir / "non_existent.txt"))
        
        with pytest.raises(IOError, match="Failed to read file"):
            gateway.read_text(non_existent)
        
        # 存在しないファイルのサイズ取得
        with pytest.raises(IOError, match="Failed to get file size"):
            gateway.get_size(non_existent)
        
        # ファイルをディレクトリとして扱う
        file_path = FilePath(str(temp_dir / "file.txt"))
        gateway.write_text(file_path, "content")
        
        with pytest.raises(IOError, match="Failed to list files"):
            gateway.list_files(file_path)
    
    def test_encoding_support(self, gateway, temp_dir):
        """エンコーディングサポートのテスト"""
        # UTF-8（デフォルト）
        utf8_file = FilePath(str(temp_dir / "utf8.txt"))
        japanese_text = "日本語のテキスト🎌"
        gateway.write_text(utf8_file, japanese_text)
        assert gateway.read_text(utf8_file) == japanese_text
        
        # UTF-8 with BOM
        utf8_bom_file = FilePath(str(temp_dir / "utf8_bom.txt"))
        gateway.write_text(utf8_bom_file, japanese_text, encoding="utf-8-sig")
        assert gateway.read_text(utf8_bom_file, encoding="utf-8-sig") == japanese_text
    
    def test_recursive_file_listing(self, gateway, temp_dir):
        """再帰的ファイルリストのテスト"""
        # ディレクトリ構造を作成
        structure = {
            "a/file1.txt": "content1",
            "a/b/file2.txt": "content2",
            "a/b/c/file3.txt": "content3",
            "a/b/c/file4.log": "log content"
        }
        
        for path, content in structure.items():
            file_path = FilePath(str(temp_dir / path))
            gateway.write_text(file_path, content)
        
        # 非再帰（aディレクトリ直下のみ）
        root_dir = FilePath(str(temp_dir / "a"))
        files = gateway.list_files(root_dir)
        assert len(files) == 1
        assert "file1.txt" in str(files[0])
        
        # 再帰的（すべてのtxtファイル）
        txt_files = gateway.list_files(root_dir, "*.txt", recursive=True)
        assert len(txt_files) == 3
        
        # 再帰的（すべてのファイル）
        all_files = gateway.list_files(root_dir, "*", recursive=True)
        assert len(all_files) == 4