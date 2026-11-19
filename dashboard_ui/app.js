"use strict";

const $ = (id) => document.getElementById(id);
const api = {
  async get(path) { const r = await fetch(path); return r.json(); },
  async post(path, body) {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
    return { ok: r.ok, data: await r.json().catch(() => ({})) };
  },
};

let CLIPS = [];
let current = null; // clip in the drawer

// ---------- tabs ----------
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $("tab-" + btn.dataset.tab).classList.add("active");
  });
});

// ---------- stats + clips ----------
function tile(num, lab, cls) {
  return `<div class="tile ${cls || ""}"><div class="num">${num}</div><div class="lab">${lab}</div></div>`;
}
function renderStats(s) {
  $("stats").innerHTML = [
    tile(s.total, "clips total"),
    tile(s.approved, "approved", "green"),
    tile(s.pending, "pending review", "accent"),
    tile(s.published, "published", "blue"),
    tile(s.avg_score == null ? "—" : s.avg_score, "avg score"),
    tile(s.test, "test clips"),
  ].join("");
}

function badge(c) {
  const out = [];
  if (typeof c.score === "number") out.push(`<span class="badge score">★ ${c.score}</span>`);
  if (c.test) out.push(`<span class="badge test">TEST</span>`);
  if (c.published) out.push(`<span class="badge published">PUBLISHED</span>`);
  else if (c.approved) out.push(`<span class="badge approved">APPROVED</span>`);
  else out.push(`<span class="badge pending">PENDING</span>`);
  return out.join("");
}

function renderClips() {
  const hideTest = $("hideTest").checked;
  const sortBy = $("sortBy").value;
  let list = CLIPS.filter((c) => !(hideTest && c.test));
  list.sort((a, b) => sortBy === "score" ? (b.score || 0) - (a.score || 0) : b.mtime - a.mtime);
  const grid = $("clipGrid");
  $("clipsEmpty").hidden = list.length > 0;
  grid.innerHTML = list.map((c) => `
    <div class="card" data-name="${c.name}" data-folder="${c.folder}">
      <div class="thumb">
        ${c.has_video
          ? `<video src="${c.video_url}#t=1" preload="metadata" muted></video>`
          : `<span class="novid">no video</span>`}
        <div class="badges">${badge(c)}</div>
      </div>
      <div class="card-body">
        <div class="title">${c.title || c.name}</div>
        <div class="line">${c.streamer || "—"}${c.caption_language ? " · " + c.caption_language : ""}</div>
        <div class="line">${(c.transcript || "").slice(0, 60) || "no transcript"}</div>
      </div>
    </div>`).join("");
  grid.querySelectorAll(".card").forEach((el) => {
    el.addEventListener("click", () => openDrawer(el.dataset.folder, el.dataset.name));
  });
}

async function loadClips() {
  const d = await api.get("/api/clips");
  CLIPS = d.clips || [];
  renderStats(d.stats || {});
  renderClips();
}
$("refreshClips").addEventListener("click", loadClips);
$("hideTest").addEventListener("change", renderClips);
$("sortBy").addEventListener("change", renderClips);

// ---------- drawer / editor ----------
function chip(label, val) {
  if (val === null || val === undefined || val === "") return "";
  return `<span class="chip">${label} <b>${val}</b></span>`;
}
function openDrawer(folder, name) {
  const c = CLIPS.find((x) => x.folder === folder && x.name === name);
  if (!c) return;
  current = c;
  $("drawerName").textContent = c.name;
  const v = $("drawerVideo");
  if (c.has_video) { v.src = c.video_url; v.hidden = false; } else { v.removeAttribute("src"); v.hidden = true; }
  $("drawerChips").innerHTML = [
    chip("score", c.score),
    chip("spoken", c.spoken_language),
    chip("captions", c.caption_language),
    chip("source", c.moment_source_used),
    chip("chat msgs", c.chat_message_count),
    chip("chatters", c.unique_chatters),
    chip("reactions", c.reaction_chatters),
    chip("stream", c.stream_title),
  ].join("");
  $("edTitle").value = c.title || "";
  $("edYt").value = c.youtube_description || "";
  $("edIg").value = c.instagram_caption || "";
  $("edTags").value = (c.hashtags || []).join(", ");
  $("edPostAt").value = c.post_at || "";
  $("edApproved").checked = !!c.approved;
  $("savedMsg").textContent = "";
  updatePublishNote();
  $("drawer").hidden = false;
  $("drawerBackdrop").hidden = false;
}
function closeDrawer() {
  $("drawer").hidden = true;
  $("drawerBackdrop").hidden = true;
  const v = $("drawerVideo"); v.pause();
  current = null;
}
$("closeDrawer").addEventListener("click", closeDrawer);
$("drawerBackdrop").addEventListener("click", closeDrawer);

function updatePublishNote() {
  const note = $("publishNote");
  const cmd = $("publishCmd");
  if (!current) return;
  const missing = [];
  if (!$("edTitle").value.trim()) missing.push("title");
  if (!$("edYt").value.trim()) missing.push("YouTube description");
  if (!$("edIg").value.trim()) missing.push("Instagram caption");
  if (!$("edApproved").checked) missing.push("approval");
  if (current.test) {
    note.className = "publish-note";
    note.textContent = "Test clips cannot be published.";
    cmd.textContent = "";
    return;
  }
  if (missing.length) {
    note.className = "publish-note";
    note.textContent = "Needs " + missing.join(", ") + " before it can be scheduled.";
    cmd.textContent = "";
  } else {
    note.className = "publish-note ok";
    note.textContent = "Ready to schedule. Preview (dry-run) with:";
    cmd.textContent = `.venv\\Scripts\\python.exe zernio_publish.py "output\\${current.name}" --scheduled-for "${current.post_at || "2026-11-20T12:00:00+05:30"}"`;
  }
}
["edTitle", "edYt", "edIg", "edApproved", "edPostAt"].forEach((id) =>
  $(id).addEventListener("input", updatePublishNote));

$("saveClip").addEventListener("click", async () => {
  if (!current) return;
  const patch = {
    title: $("edTitle").value.trim(),
    youtube_description: $("edYt").value.trim(),
    instagram_caption: $("edIg").value.trim(),
    hashtags: $("edTags").value,
    post_at: $("edPostAt").value.trim(),
    approved: $("edApproved").checked,
  };
  const { ok, data } = await api.post("/api/clip/update", { folder: current.folder, name: current.name, patch });
  if (ok) {
    $("savedMsg").textContent = "saved ✓";
    await loadClips();
    const fresh = CLIPS.find((x) => x.folder === current.folder && x.name === current.name);
    if (fresh) current = fresh;
    updatePublishNote();
  } else {
    $("savedMsg").textContent = data.error || "save failed";
  }
});

// ---------- capture ----------
function captureOpts() {
  return {
    url: $("capUrl").value, file: $("capFile").value,
    clip_len: $("capClipLen").value, chunk: $("capChunk").value, lead_in: $("capLeadIn").value,
    top: $("capTop").value, min_score: $("capMinScore").value, max_seconds: $("capMaxSeconds").value,
    layout: $("capLayout").value, moment_source: $("capMoment").value, spoken_language: $("capLang").value,
    gameplay_confirmed: $("capConfirmed").checked, test: $("capTest").checked, no_chat: $("capNoChat").checked,
  };
}
function previewCmd() {
  const o = captureOpts();
  const parts = ["python", "clip.py"];
  if (o.file) parts.push("--file", `"${o.file}"`, "--test");
  else if (o.url) {
    parts.push(`"${o.url}"`);
    if (o.test) parts.push("--test");
    if (o.gameplay_confirmed) parts.push("--gameplay-confirmed");
  }
  parts.push("--clip-len", o.clip_len, "--chunk", o.chunk, "--lead-in", o.lead_in,
    "--top", o.top, "--min-score", o.min_score, "--max-seconds", o.max_seconds,
    "--layout", o.layout, "--moment-source", o.moment_source, "--spoken-language", o.spoken_language);
  if (o.no_chat) parts.push("--no-chat");
  $("cmdPreview").textContent = parts.join(" ");
}
["capUrl","capFile","capClipLen","capChunk","capLeadIn","capTop","capMinScore","capMaxSeconds",
 "capLayout","capMoment","capLang","capConfirmed","capTest","capNoChat"].forEach((id) =>
  $(id).addEventListener("input", previewCmd));

$("captureForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const { ok, data } = await api.post("/api/capture/start", captureOpts());
  if (!ok) { alert(data.error || "could not start"); return; }
  document.querySelector('.tab[data-tab="log"]').click();
});

// ---------- discovery ----------
$("discoverForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const { ok, data } = await api.post("/api/discovery/start", { query: $("discQuery").value, max: $("discMax").value });
  if (!ok) { alert(data.error || "could not start"); return; }
  document.querySelector('.tab[data-tab="log"]').click();
});

// ---------- run control / polling ----------
$("stopRun").addEventListener("click", () => api.post("/api/run/stop"));
$("stopRun2").addEventListener("click", () => api.post("/api/run/stop"));

let lastRunning = false;
async function pollRun() {
  let st;
  try { st = await api.get("/api/run"); } catch { return; }
  const dot = $("runDot"), label = $("runLabel");
  if (st.running) {
    dot.classList.add("live");
    label.textContent = `${st.kind} · ${st.elapsed ?? 0}s`;
  } else {
    dot.classList.remove("live");
    label.textContent = st.returncode == null ? "idle" : `idle (last exit ${st.returncode})`;
  }
  $("runMeta").textContent = st.cmd ? st.cmd.join(" ") : "";
  const box = $("logBox");
  const atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 40;
  box.textContent = (st.log && st.log.length) ? st.log.join("\n") : "No run yet.";
  if (atBottom) box.scrollTop = box.scrollHeight;
  // when a run finishes, refresh the clip list once
  if (lastRunning && !st.running) loadClips();
  lastRunning = st.running;
}

previewCmd();
loadClips();
pollRun();
setInterval(pollRun, 1500);
