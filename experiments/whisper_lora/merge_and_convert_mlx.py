"""LoRA を base Whisper にマージし、MLX 形式に変換するスクリプト。

処理:
    1. HF Whisper Large-v3 をロード
    2. PEFT LoRA アダプタを装着 → merge_and_unload() で base にマージ
    3. HF パラメータ名 → MLX パラメータ名へキー変換、必要な形状変換を実施
    4. weights.npz + config.json を mlx-community 形式で保存

使い方:
    /Users/naoki/.pyenv/shims/python3 \
      experiments/whisper_lora/merge_and_convert_mlx.py \
        --adapter experiments/whisper_lora/outputs/20260129_phase_a/final \
        --out     experiments/whisper_lora/mlx_models/whisper-large-v3-lora-20260129

出力:
    {out}/config.json
    {out}/weights.npz

後続:
    mlx_whisper.transcribe(video_path, path_or_hf_repo=str({out}))
    で LoRA 適用済みの高速 (mlx_whisper ネイティブ) 推論が可能になる。

設計メモ:
    - HF では encoder の positional embedding も weight として保存されるが、
      MLX は sinusoid を実行時に生成するためスキップ
    - HF の proj_out.weight は decoder.embed_tokens.weight と tied されるので
      MLX 側に別途保存しない (MLX Whisper も同じ tied 構造)
    - Conv1d の weight shape が HF (out, in, k) と MLX (out, k, in) で異なり、
      (0, 2, 1) に permute が必要
    - HF の dtype は fp16 のまま MLX に渡す (mlx_whisper は fp16 対応)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import torch
from peft import PeftModel
from transformers import WhisperForConditionalGeneration

MODEL_ID = "openai/whisper-large-v3"


def build_hf_to_mlx_map() -> list[tuple[re.Pattern, str]]:
    """HF パラメータ名を MLX パラメータ名に変換する順序付きルール。

    先に出てきたパターンから優先的に適用する (re.sub の繰り返し)。
    """
    rules: list[tuple[re.Pattern, str]] = [
        # top-level prefix
        (re.compile(r"^model\."), ""),
        # encoder/decoder の blocks 命名
        (re.compile(r"encoder\.layers\.(\d+)"), r"encoder.blocks.\1"),
        (re.compile(r"decoder\.layers\.(\d+)"), r"decoder.blocks.\1"),
        # self-attention (encoder は self のみ、decoder にも self あり)
        (re.compile(r"\.self_attn\.q_proj"), r".attn.query"),
        (re.compile(r"\.self_attn\.k_proj"), r".attn.key"),
        (re.compile(r"\.self_attn\.v_proj"), r".attn.value"),
        (re.compile(r"\.self_attn\.out_proj"), r".attn.out"),
        (re.compile(r"\.self_attn_layer_norm"), r".attn_ln"),
        # cross-attention (decoder のみ)
        (re.compile(r"\.encoder_attn\.q_proj"), r".cross_attn.query"),
        (re.compile(r"\.encoder_attn\.k_proj"), r".cross_attn.key"),
        (re.compile(r"\.encoder_attn\.v_proj"), r".cross_attn.value"),
        (re.compile(r"\.encoder_attn\.out_proj"), r".cross_attn.out"),
        (re.compile(r"\.encoder_attn_layer_norm"), r".cross_attn_ln"),
        # FFN
        (re.compile(r"\.fc1"), r".mlp1"),
        (re.compile(r"\.fc2"), r".mlp2"),
        (re.compile(r"\.final_layer_norm"), r".mlp_ln"),
        # encoder/decoder の終端 LayerNorm
        (re.compile(r"^encoder\.layer_norm"), r"encoder.ln_post"),
        (re.compile(r"^decoder\.layer_norm"), r"decoder.ln"),
        # decoder embeddings
        (re.compile(r"^decoder\.embed_tokens\.weight$"), r"decoder.token_embedding.weight"),
        (re.compile(r"^decoder\.embed_positions\.weight$"), r"decoder.positional_embedding"),
    ]
    return rules


def convert_key(hf_key: str, rules: list[tuple[re.Pattern, str]]) -> str:
    k = hf_key
    for pat, repl in rules:
        k = pat.sub(repl, k)
    return k


# MLX 形式で保存「しない」HF キー (MLX 側で sinusoid 生成 or tied weight のため)
SKIP_HF_KEYS = {
    "model.encoder.embed_positions.weight",  # MLX は sinusoid を runtime 生成
    "proj_out.weight",  # MLX は token_embedding と tied
}


def hf_to_mlx_config(hf_config) -> dict:
    """HF WhisperConfig → MLX ModelDimensions 互換 JSON。"""
    return {
        "n_mels": hf_config.num_mel_bins,
        "n_audio_ctx": hf_config.max_source_positions,
        "n_audio_state": hf_config.d_model,
        "n_audio_head": hf_config.encoder_attention_heads,
        "n_audio_layer": hf_config.encoder_layers,
        "n_vocab": hf_config.vocab_size,
        "n_text_ctx": hf_config.max_target_positions,
        "n_text_state": hf_config.d_model,
        "n_text_head": hf_config.decoder_attention_heads,
        "n_text_layer": hf_config.decoder_layers,
        "model_type": "whisper",
    }


def to_numpy(t: torch.Tensor) -> np.ndarray:
    # fp16 のまま numpy に落として npz に保存する
    return t.detach().cpu().contiguous().numpy()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", type=Path, required=True, help="PEFT LoRA の final/ ディレクトリ")
    parser.add_argument("--out", type=Path, required=True, help="MLX モデル出力先ディレクトリ")
    parser.add_argument(
        "--dtype",
        default="float16",
        choices=["float16", "float32"],
        help="出力 weight dtype (default: float16)",
    )
    args = parser.parse_args()

    if not args.adapter.exists():
        print(f"adapter が見つかりません: {args.adapter}", file=sys.stderr)
        sys.exit(1)

    torch_dtype = torch.float16 if args.dtype == "float16" else torch.float32
    np_dtype = np.float16 if args.dtype == "float16" else np.float32

    print(f"[1/5] {MODEL_ID} を {args.dtype} でロード ...")
    base = WhisperForConditionalGeneration.from_pretrained(MODEL_ID, torch_dtype=torch_dtype)

    print(f"[2/5] LoRA アダプタを装着: {args.adapter}")
    peft_model = PeftModel.from_pretrained(base, str(args.adapter))

    print("[3/5] merge_and_unload() で LoRA を base にマージ ...")
    merged = peft_model.merge_and_unload()
    merged.eval()
    print("     マージ完了。PEFT 層は取り除かれ、純粋な WhisperForConditionalGeneration になった。")

    # ---- キー変換 & weights.npz 生成 ----
    print("[4/5] HF → MLX キー変換と weight 変換 ...")
    rules = build_hf_to_mlx_map()
    mlx_weights: dict[str, np.ndarray] = {}
    skipped: list[str] = []

    for hf_key, tensor in merged.state_dict().items():
        if hf_key in SKIP_HF_KEYS:
            skipped.append(hf_key)
            continue

        mlx_key = convert_key(hf_key, rules)
        arr = to_numpy(tensor).astype(np_dtype)

        # Conv1d の shape 変換: HF (out, in, k) → MLX (out, k, in)
        if mlx_key.endswith((".conv1.weight", ".conv2.weight")):
            arr = np.transpose(arr, (0, 2, 1)).copy()

        mlx_weights[mlx_key] = arr

    print(f"     変換後: {len(mlx_weights)} keys, skipped {len(skipped)} keys")
    for k in skipped:
        print(f"     skip: {k}")

    # alignment_heads (word-level timestamp 用の cross-attention head 指定) を埋め込む
    # HF では generation_config、MLX では weights.npz の alignment_heads キーに格納
    ah = getattr(merged.generation_config, "alignment_heads", None)
    if ah:
        ah_arr = np.array(ah, dtype=np.int64)
        mlx_weights["alignment_heads"] = ah_arr
        print(f"     alignment_heads: shape={ah_arr.shape}")

    # ---- config.json ----
    mlx_config = hf_to_mlx_config(merged.config)

    # ---- 書き出し ----
    args.out.mkdir(parents=True, exist_ok=True)
    weights_path = args.out / "weights.npz"
    config_path = args.out / "config.json"

    print(f"[5/5] 書き出し: {args.out}")
    np.savez(str(weights_path), **mlx_weights)
    config_path.write_text(json.dumps(mlx_config, indent=2), encoding="utf-8")
    print(f"     weights.npz ({weights_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"     config.json")

    # ---- サンキーキーチェック (MLX 参照モデルと比較) ----
    ref_mlx_npz = Path(
        "/Users/naoki/.cache/huggingface/hub/models--mlx-community--whisper-large-v3-mlx/"
        "snapshots/49e6aa286ad60c14352c404340ded53710378a11/weights.npz"
    )
    if ref_mlx_npz.exists():
        ref = np.load(str(ref_mlx_npz))
        ref_keys = set(ref.keys())
        my_keys = set(mlx_weights.keys())
        missing = ref_keys - my_keys
        extra = my_keys - ref_keys
        if missing:
            print(f"\n  [WARN] 参照モデルに存在するが出力に無いキー: {len(missing)}")
            for k in sorted(missing)[:10]:
                print(f"    - {k}")
        if extra:
            print(f"\n  [WARN] 出力に存在するが参照モデルに無いキー: {len(extra)}")
            for k in sorted(extra)[:10]:
                print(f"    - {k}")
        if not missing and not extra:
            print(f"\n  [OK] 参照 MLX モデルと key set が完全一致 ({len(ref_keys)} keys)")

    print("\nDone.")
    print(f"使用例: mlx_whisper.transcribe(video, path_or_hf_repo='{args.out}')")


if __name__ == "__main__":
    main()
