#!/bin/bash
# モデル切り替え品質比較テスト
# 3動画 × 3パターン = 9回実行
#
# パターンA: 全 gpt-4.1-mini (--quality-model gpt-4.1-mini)
# パターンB: 品質評価のみ gpt-4.1 (デフォルト動作)
# パターンC: 全 gpt-4.1 (--ai-model gpt-4.1)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# 動画リスト
VIDEOS=(
  "videos/20260115_スピードが速くなった世界では煙に巻くのは逆効果.mp4"
  "videos/20260129_生成AIの世界で情報収集が完結する人が増えている.mp4"
  "videos/20260122_メタゲームの概念を持っておくと人生は楽かも.mp4"
)

# ログディレクトリ
LOG_DIR="logs/model_comparison"
mkdir -p "$LOG_DIR"

# 開始時刻
echo "=== モデル比較テスト開始: $(date '+%Y-%m-%d %H:%M:%S') ==="
echo ""

run_pattern() {
  local video="$1"
  local pattern="$2"
  local extra_args="$3"
  local name
  name=$(basename "$video" .mp4)
  local base="videos/${name}_TextffCut"
  local log_file="${LOG_DIR}/${name}_${pattern}.log"

  echo "--- [$pattern] $name ---"
  echo "  開始: $(date '+%H:%M:%S')"

  # 実行（SRT生成あり、タイトル画像なし、SE/BGM/フレームなし = AI比較に集中）
  if textffcut clip "$video" \
    --no-title-image --no-frame --no-bgm --no-se \
    $extra_args 2>&1 | tee "$log_file"; then
    echo "  完了: $(date '+%H:%M:%S')"
  else
    echo "  エラー: $(date '+%H:%M:%S')" >&2
  fi

  # fcpxml/ を パターン別にコピー保存
  if [ -d "${base}/fcpxml" ]; then
    rm -rf "${base}/fcpxml_${pattern}"
    cp -r "${base}/fcpxml" "${base}/fcpxml_${pattern}"
    echo "  保存: fcpxml_${pattern}/"
  fi

  echo ""
}

for video in "${VIDEOS[@]}"; do
  if [ ! -f "$video" ]; then
    echo "スキップ: $video (ファイルなし)"
    continue
  fi

  echo "=========================================="
  echo "動画: $(basename "$video")"
  echo "=========================================="
  echo ""

  # パターンA: 全 gpt-4.1-mini
  run_pattern "$video" "A_all_mini" "--quality-model gpt-4.1-mini"

  # パターンB: 品質評価のみ gpt-4.1（デフォルト）
  run_pattern "$video" "B_quality_41" ""

  # パターンC: 全 gpt-4.1
  run_pattern "$video" "C_all_41" "--ai-model gpt-4.1"
done

echo "=== テスト完了: $(date '+%Y-%m-%d %H:%M:%S') ==="
echo ""
echo "ログ: ${LOG_DIR}/"
echo "比較: python scripts/compare_model_results.py"
