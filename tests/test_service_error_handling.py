#!/usr/bin/env python3
"""
サービス層のエラーハンドリング統合テスト
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from core.error_handling import FileValidationError, ProcessingError, ValidationError, VideoProcessingError
from services.base_updated import BaseService, ServiceResult


class SampleService(BaseService):
    """テスト用のサンプルサービス"""

    def execute(self, **kwargs) -> ServiceResult:
        """サンプル実行メソッド"""
        action = kwargs.get("action", "default")

        if action == "validate_file":
            return self.validate_file_action(kwargs.get("file_path"))
        elif action == "process_video":
            return self.process_video_action(kwargs.get("video_path"))
        elif action == "error_test":
            return self.error_test_action(kwargs.get("error_type"))
        else:
            return self.create_error_result("不明なアクション", error_type="ValidationError")

    def validate_file_action(self, file_path: str) -> ServiceResult:
        """ファイル検証アクション"""
        try:
            path = self.validate_file_exists(file_path)
            return self.create_success_result(
                data={"path": str(path), "size": path.stat().st_size}, metadata={"action": "validate_file"}
            )
        except FileValidationError as e:
            return self.handle_service_error("validate_file", e)

    def process_video_action(self, video_path: str) -> ServiceResult:
        """動画処理アクション（エラーシミュレーション）"""
        try:
            # 動画処理のシミュレーション
            if not video_path:
                raise ValidationError("動画パスが指定されていません")

            if not video_path.endswith(".mp4"):
                raise VideoProcessingError(
                    "サポートされていない形式",
                    details={"path": video_path, "supported": ["mp4", "mov"]},
                    user_message="MP4またはMOV形式の動画を指定してください",
                )

            # 処理成功
            return self.create_success_result(data={"processed": True, "path": video_path})

        except Exception as e:
            return self.handle_service_error("process_video", e)

    def error_test_action(self, error_type: str) -> ServiceResult:
        """エラーテスト用アクション"""
        try:
            if error_type == "validation":
                raise ValidationError("テスト検証エラー")
            elif error_type == "processing":
                raise ProcessingError("テスト処理エラー")
            elif error_type == "unexpected":
                raise ValueError("予期しないエラー")
            else:
                return self.create_success_result(data={"test": "ok"})
        except Exception as e:
            return self.wrap_error(e)


def test_service_error_handling():
    """サービスのエラーハンドリングをテスト"""
    print("=== サービス層エラーハンドリングテスト ===\n")

    config = Config()
    service = SampleService(config)

    # 1. ファイル検証（成功）
    print("1. ファイル検証（成功ケース）")
    result = service.execute(action="validate_file", file_path=__file__)
    print(f"  成功: {result.success}")
    if result.success:
        print(f"  データ: {result.data}")
    print()

    # 2. ファイル検証（失敗）
    print("2. ファイル検証（失敗ケース）")
    result = service.execute(action="validate_file", file_path="/nonexistent/file.txt")
    print(f"  成功: {result.success}")
    if not result.success:
        print(f"  エラー: {result.error}")
        print(f"  エラータイプ: {result.error_type}")
        print(f"  エラーコード: {result.error_code}")
        print(f"  回復可能: {result.metadata.get('recoverable', False)}")
    print()

    # 3. 動画処理（検証エラー）
    print("3. 動画処理（検証エラー）")
    result = service.execute(action="process_video", video_path="")
    print(f"  成功: {result.success}")
    if not result.success:
        print(f"  エラー: {result.error}")
        print(f"  エラーコード: {result.error_code}")
    print()

    # 4. 動画処理（形式エラー）
    print("4. 動画処理（形式エラー）")
    result = service.execute(action="process_video", video_path="test.avi")
    print(f"  成功: {result.success}")
    if not result.success:
        print(f"  エラー: {result.error}")
        print(f"  詳細: {result.metadata.get('details', {})}")
    print()

    # 5. エラーテスト（ValidationError）
    print("5. エラーテスト（ValidationError）")
    result = service.execute(action="error_test", error_type="validation")
    print(f"  成功: {result.success}")
    print(f"  エラー: {result.error}")
    print(f"  エラーコード: {result.error_code}")
    print()

    # 6. エラーテスト（予期しないエラー）
    print("6. エラーテスト（予期しないエラー）")
    result = service.execute(action="error_test", error_type="unexpected")
    print(f"  成功: {result.success}")
    print(f"  エラー: {result.error}")
    print(f"  エラーコード: {result.error_code}")
    print()

    print("=== テスト完了 ===")


def test_error_metadata():
    """エラーメタデータの詳細テスト"""
    print("\n=== エラーメタデータテスト ===\n")

    config = Config()
    service = SampleService(config)

    # VideoProcessingErrorの詳細情報
    result = service.execute(action="process_video", video_path="test.avi")

    print("VideoProcessingErrorの詳細:")
    print(f"  success: {result.success}")
    print(f"  error: {result.error}")
    print(f"  error_type: {result.error_type}")
    print(f"  error_code: {result.error_code}")
    print(f"  metadata: {result.metadata}")

    # error_detailsの内容を確認
    if "error_details" in result.metadata:
        details = result.metadata["error_details"]
        print("\nエラー詳細情報:")
        for key, value in details.items():
            print(f"    {key}: {value}")


if __name__ == "__main__":
    test_service_error_handling()
    test_error_metadata()
