// 文字起こしエディタ フロントエンド

const AUTOSAVE_INTERVAL_MS = 30_000;

const state = {
  segments: [],     // 各セグメントに _idx / _edited / _original / _reviewed / _skip を付与
  metadata: {},      // JSON の segments 以外のフィールド
  currentIdx: -1,
  playbackTimer: null,
};

const player = document.getElementById("player");
player.src = "/audio";

// ==========================================
// データ読み込み
// ==========================================
async function loadData() {
  const res = await fetch("/data");
  if (!res.ok) {
    showStatus(`データ取得失敗: ${res.status}`, "err");
    return;
  }
  const data = await res.json();
  const { segments, ...metadata } = data;
  state.metadata = metadata;
  state.segments = segments.map((s, idx) => ({
    ...s,
    _idx: idx,
    _edited: s.text || "",
    _original: s.text || "",
    _skip: Boolean(s.skip),
  }));
  renderSegments();
  updateCounters();
}

// ==========================================
// レンダリング
// ==========================================
function renderSegments() {
  const container = document.getElementById("segments-container");
  container.innerHTML = "";
  const fragment = document.createDocumentFragment();
  for (const seg of state.segments) {
    fragment.appendChild(buildRow(seg));
  }
  container.appendChild(fragment);
  // 初期描画後に全 textarea を内容高さに合わせる
  // （appendChild 前だと scrollHeight が 0 になるため、ここで一括処理）
  requestAnimationFrame(() => {
    container.querySelectorAll(".text-input").forEach(autoResize);
  });
}

function autoResize(textArea) {
  textArea.style.height = "auto";
  textArea.style.height = `${textArea.scrollHeight}px`;
}

function buildRow(seg) {
  const row = document.createElement("div");
  row.className = "segment-row";
  row.id = `seg-${seg._idx}`;
  if (seg._skip) row.classList.add("skipped");
  if (seg._edited !== seg._original) row.classList.add("modified");

  const playBtn = document.createElement("button");
  playBtn.className = "play-btn";
  playBtn.textContent = "▶";
  playBtn.title = "このセグメントを再生";
  playBtn.addEventListener("click", () => playSegment(seg._idx));

  const timeDiv = document.createElement("div");
  timeDiv.className = "time";
  timeDiv.innerHTML = `
    ${formatTime(seg.start)}<br>
    <span class="duration">${(seg.end - seg.start).toFixed(1)}s</span>
  `;

  const textArea = document.createElement("textarea");
  textArea.className = "text-input";
  textArea.rows = 1;
  textArea.value = seg._edited;
  textArea.addEventListener("input", () => {
    seg._edited = textArea.value;
    autoResize(textArea);
    row.classList.toggle("modified", seg._edited !== seg._original);
    updateCounters();
  });
  textArea.addEventListener("focus", () => {
    state.currentIdx = seg._idx;
    highlightCurrent(seg._idx);
  });

  const controlsDiv = document.createElement("div");
  controlsDiv.className = "seg-controls";

  const skipLabel = document.createElement("label");
  const skipChk = document.createElement("input");
  skipChk.type = "checkbox";
  skipChk.checked = seg._skip;
  skipChk.addEventListener("change", () => {
    seg._skip = skipChk.checked;
    row.classList.toggle("skipped", seg._skip);
    updateCounters();
  });
  skipLabel.appendChild(skipChk);
  skipLabel.appendChild(document.createTextNode(" Skip"));

  controlsDiv.appendChild(skipLabel);

  row.appendChild(playBtn);
  row.appendChild(timeDiv);
  row.appendChild(textArea);
  row.appendChild(controlsDiv);
  return row;
}

// ==========================================
// 再生
// ==========================================
function playSegment(idx) {
  const seg = state.segments[idx];
  if (!seg) return;

  stopPlayback();

  player.currentTime = seg.start;
  player.play().catch((e) => console.warn("play() failed:", e));

  const duration = (seg.end - seg.start) * 1000 + 50;  // 終端の取りこぼし防止に +50ms
  state.playbackTimer = setTimeout(() => {
    player.pause();
    state.playbackTimer = null;
    document.getElementById(`seg-${idx}`)?.querySelector(".play-btn")?.classList.remove("playing");
  }, duration);

  state.currentIdx = idx;
  highlightCurrent(idx);

  const row = document.getElementById(`seg-${idx}`);
  row?.scrollIntoView({ behavior: "smooth", block: "center" });
  row?.querySelector(".play-btn")?.classList.add("playing");
}

function stopPlayback() {
  if (state.playbackTimer) {
    clearTimeout(state.playbackTimer);
    state.playbackTimer = null;
  }
  if (!player.paused) player.pause();
  document.querySelectorAll(".play-btn.playing").forEach((b) => b.classList.remove("playing"));
}

function highlightCurrent(idx) {
  document.querySelectorAll(".segment-row.current").forEach((r) => r.classList.remove("current"));
  document.getElementById(`seg-${idx}`)?.classList.add("current");
}

// ==========================================
// 補助
// ==========================================
function formatTime(seconds) {
  const mm = Math.floor(seconds / 60);
  const ss = (seconds % 60).toFixed(1).padStart(4, "0");
  return `${String(mm).padStart(2, "0")}:${ss}`;
}

function updateCounters() {
  const total = state.segments.length;
  const modified = state.segments.filter((s) => s._edited !== s._original).length;
  const skipped = state.segments.filter((s) => s._skip).length;
  document.getElementById("total-count").textContent = String(total);
  document.getElementById("modified-count").textContent = String(modified);
  document.getElementById("skip-count").textContent = String(skipped);
}

function showStatus(msg, kind = "") {
  const el = document.getElementById("save-status");
  el.textContent = msg;
  el.className = `save-status ${kind}`;
}

// ==========================================
// 保存
// ==========================================
async function save() {
  showStatus("保存中...");
  const payload = {
    ...state.metadata,
    edited_at: new Date().toISOString(),
    segments: state.segments.map((s) => ({
      start: s.start,
      end: s.end,
      text: s._edited,
      original_text: s._original,
      skip: s._skip,
      words: s.words || [],
      chars: s.chars || [],
    })),
  };
  try {
    const res = await fetch("/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload, null, 2),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const now = new Date().toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    showStatus(`✓ 保存 ${now}`, "ok");
  } catch (e) {
    showStatus(`✗ 保存失敗: ${e.message}`, "err");
  }
}

// ==========================================
// キーボード / ボタン
// ==========================================
document.addEventListener("keydown", (e) => {
  // ⌘S / Ctrl+S で保存
  if ((e.metaKey || e.ctrlKey) && e.key === "s") {
    e.preventDefault();
    save();
    return;
  }
  // Esc で再生停止
  if (e.key === "Escape") {
    stopPlayback();
    return;
  }
  // テキスト入力中以外でスペースで現在のセグメントを再生
  const activeEl = document.activeElement;
  const inTextArea = activeEl && activeEl.tagName === "TEXTAREA";
  if (!inTextArea && e.key === " ") {
    e.preventDefault();
    if (state.currentIdx >= 0) playSegment(state.currentIdx);
  }
});

document.getElementById("save-btn").addEventListener("click", save);

// 自動保存: 何か変更がある場合のみ保存
setInterval(() => {
  const hasChanges = state.segments.some(
    (s) => s._edited !== s._original || s._skip
  );
  if (hasChanges) save();
}, AUTOSAVE_INTERVAL_MS);

// 開始
loadData();
