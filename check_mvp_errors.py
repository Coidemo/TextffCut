"""
MVPアプリケーションのエラーチェック

各Gatewayの設定エラーを確認
"""

import sys
import traceback

from di.bootstrap import bootstrap_di


def check_gateways():
    """各Gatewayの初期化をチェック"""
    errors = []

    try:
        # DIコンテナを初期化
        app_container = bootstrap_di()
        gateways = app_container.gateways()

        # 各Gatewayをチェック
        gateway_list = [
            ("video_processor_gateway", "VideoProcessorGatewayAdapter"),
            ("transcription_gateway", "TranscriptionGatewayAdapter"),
            ("fcpxml_export_gateway", "FCPXMLExportGatewayAdapter"),
            ("edl_export_gateway", "EDLExportGatewayAdapter"),
            ("srt_export_gateway", "SRTExportGatewayAdapter"),
            ("video_export_gateway", "VideoExportGatewayAdapter"),
        ]

        for attr_name, class_name in gateway_list:
            try:
                gateway = getattr(gateways, attr_name)
                print(f"✅ {class_name}: OK")
            except Exception as e:
                error_msg = f"❌ {class_name}: {str(e)}"
                print(error_msg)
                errors.append((class_name, e))
                traceback.print_exc()

    except Exception as e:
        print(f"❌ コンテナ初期化エラー: {e}")
        traceback.print_exc()
        return False

    if errors:
        print(f"\n\n見つかったエラー: {len(errors)}件")
        for class_name, error in errors:
            print(f"- {class_name}: {error}")

        # 共通の問題を特定
        if all("config" in str(e) for _, e in errors):
            print("\n💡 解決策: Gateway Adapterのコンストラクタにconfig引数が不足しています")

    return len(errors) == 0


if __name__ == "__main__":
    print("MVP Gateway エラーチェック\n")
    if check_gateways():
        print("\n✅ すべてのGatewayが正常に初期化されました")
    else:
        print("\n❌ エラーが見つかりました。上記の内容を確認してください")
        sys.exit(1)
