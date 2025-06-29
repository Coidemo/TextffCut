#!/usr/bin/env python3
"""
DI統合の例

main.pyでDIコンテナを使用する方法を示すサンプル実装。
"""

import streamlit as st
from pathlib import Path
from typing import Optional

from di.bootstrap import bootstrap_di, inject_streamlit_session
from di.containers import ApplicationContainer
from dependency_injector.wiring import Provide, inject

# アプリケーション全体で使用するコンテナ
_container: Optional[ApplicationContainer] = None


def get_app_container() -> ApplicationContainer:
    """アプリケーションコンテナを取得"""
    global _container
    if _container is None:
        _container = bootstrap_di()
    return _container


@inject
def process_video_with_di(
    video_path: Path,
    transcription_gateway=Provide[ApplicationContainer.gateways.transcription_gateway],
    video_gateway=Provide[ApplicationContainer.gateways.video_processor_gateway],
    export_gateway=Provide[ApplicationContainer.gateways.fcpxml_export_gateway]
) -> dict:
    """
    DIを使用した動画処理の例
    
    Args:
        video_path: 処理する動画のパス
        
    Returns:
        処理結果の辞書
    """
    # 1. 文字起こし
    transcription_result = transcription_gateway.transcribe(str(video_path))
    
    # 2. 無音検出
    silence_ranges = video_gateway.detect_silence(
        str(video_path),
        threshold=-35.0,
        min_duration=0.3
    )
    
    # 3. エクスポート
    export_result = export_gateway.export(
        video_path=str(video_path),
        time_ranges=[(0, 60)],  # 例：最初の60秒
        output_path="output.fcpxml"
    )
    
    return {
        "transcription": transcription_result,
        "silence_ranges": silence_ranges,
        "export_path": export_result
    }


# Streamlit UIでの使用例
def main():
    st.title("TextffCut - DI統合例")
    
    # DIコンテナを初期化
    container = get_app_container()
    
    # Streamlitセッション状態を注入
    inject_streamlit_session(container)
    
    # サイドバーで設定
    with st.sidebar:
        st.header("設定")
        
        # API設定
        use_api = st.checkbox("APIを使用", key="use_api")
        if use_api:
            api_key = st.text_input("APIキー", type="password", key="api_key")
        
        # モデル設定
        model_size = st.selectbox(
            "モデルサイズ",
            ["tiny", "base", "small", "medium", "large", "large-v3"],
            index=5,
            key="model_size"
        )
    
    # メインコンテンツ
    st.header("動画処理")
    
    # ファイル選択
    video_file = st.file_uploader("動画ファイル", type=["mp4", "mov", "avi"])
    
    if video_file is not None:
        # 一時ファイルに保存
        temp_path = Path(f"/tmp/{video_file.name}")
        temp_path.write_bytes(video_file.read())
        
        if st.button("処理開始"):
            with st.spinner("処理中..."):
                # DIを使用して処理
                result = process_video_with_di(temp_path)
                
                st.success("処理完了！")
                
                # 結果表示
                st.subheader("結果")
                st.json(result)
    
    # デバッグ情報
    with st.expander("デバッグ情報"):
        st.write("コンテナ設定:")
        st.json(container.config().to_dict())
        
        # 各ゲートウェイの状態
        st.write("ゲートウェイ:")
        st.write(f"- Transcription: {container.gateways.transcription_gateway()}")
        st.write(f"- Video: {container.gateways.video_processor_gateway()}")
        st.write(f"- FCPXML: {container.gateways.fcpxml_export_gateway()}")


# 既存のサービスをDIコンテナ経由で使用する例
@inject
def use_legacy_services(
    config_service=Provide[ApplicationContainer.services.configuration_service],
    transcription_service=Provide[ApplicationContainer.services.transcription_service]
):
    """レガシーサービスをDI経由で使用"""
    # 設定サービス
    config = config_service.get_current_config()
    print(f"Current model: {config.transcription.model_size}")
    
    # 文字起こしサービス
    result = transcription_service.transcribe_video("video.mp4")
    return result


# ユースケースを直接使用する例
@inject
def use_cases_example(
    transcribe_use_case=Provide[ApplicationContainer.use_cases.transcribe_video],
    detect_silence_use_case=Provide[ApplicationContainer.use_cases.detect_silence]
):
    """ユースケースをDI経由で使用"""
    from use_cases.transcription.transcribe_video import TranscribeVideoRequest
    from use_cases.video.detect_silence import DetectSilenceRequest
    
    # 文字起こし
    transcribe_request = TranscribeVideoRequest(
        video_path=Path("video.mp4"),
        model_size="large-v3",
        language="ja"
    )
    transcribe_response = transcribe_use_case.execute(transcribe_request)
    
    # 無音検出
    silence_request = DetectSilenceRequest(
        video_path=Path("video.mp4"),
        threshold=-35.0,
        min_duration=0.3
    )
    silence_response = detect_silence_use_case.execute(silence_request)
    
    return transcribe_response, silence_response


if __name__ == "__main__":
    # 例1: 直接実行
    container = bootstrap_di()
    print("Container initialized:", container)
    
    # 例2: Streamlit実行
    # streamlit run di/integration_example.py