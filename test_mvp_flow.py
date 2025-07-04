"""
MVPアプリケーションの動作テストスクリプト

文字起こしボタンが有効になるかテストします。
"""

import time

from di.bootstrap import bootstrap_di


def test_video_selection_flow():
    """動画選択フローのテスト"""
    print("=== MVP動作テスト開始 ===\n")

    # DIコンテナを初期化
    print("1. DIコンテナを初期化...")
    app_container = bootstrap_di()
    presentation_container = app_container.presentation()

    # Presenterを取得
    main_presenter = presentation_container.main_presenter()
    video_input_presenter = presentation_container.video_input_presenter()

    print("✅ DIコンテナの初期化成功\n")

    # 初期状態を確認
    print("2. 初期状態を確認...")
    print(f"   - current_step: {main_presenter.view_model.current_step}")
    print(f"   - video_input_completed: {main_presenter.view_model.video_input_completed}")
    print(f"   - can_proceed_to_transcription: {main_presenter.view_model.can_proceed_to_transcription}")
    print()

    # 動画ファイル一覧を取得
    print("3. 動画ファイル一覧を取得...")
    video_input_presenter.initialize()
    video_input_presenter.refresh_video_list()

    files = video_input_presenter.view_model.video_files
    print(f"   - 見つかった動画ファイル: {len(files)}個")
    if files:
        print(f"   - 最初のファイル: {files[0]}")
    print()

    # 動画を選択
    if files:
        print("4. 動画を選択...")
        selected_file = files[0]
        video_input_presenter.select_video(selected_file)

        # 選択処理が完了するまで待機
        time.sleep(1)

        print(f"   - 選択したファイル: {selected_file}")
        print(f"   - video_info: {video_input_presenter.view_model.video_info}")
        print(f"   - is_valid: {video_input_presenter.view_model.is_valid}")
        print()

        # MainPresenterに通知
        print("5. MainPresenterに動画選択を通知...")
        main_presenter._on_video_input_changed()

        # 状態を再確認
        print("\n6. 動画選択後の状態:")
        print(f"   - current_step: {main_presenter.view_model.current_step}")
        print(f"   - video_input_completed: {main_presenter.view_model.video_input_completed}")
        print(f"   - video_path: {main_presenter.view_model.video_path}")
        print(f"   - can_proceed_to_transcription: {main_presenter.view_model.can_proceed_to_transcription}")

        # 文字起こしステップに進めるか確認
        if main_presenter.view_model.can_proceed_to_transcription:
            print("\n✅ 文字起こしボタンが有効になりました！")
            print("   → 文字起こしステップに進むことができます")
        else:
            print("\n❌ 文字起こしボタンはまだ無効です")
            print("   問題: can_proceed_to_transcriptionがFalseのままです")
    else:
        print("❌ 動画ファイルが見つかりません")

    print("\n=== テスト完了 ===")


if __name__ == "__main__":
    test_video_selection_flow()
