"""Local operator dashboard for GTA Auto Clipper.

A single-file control plane (Python stdlib only, no extra dependencies) that:
  - lists rendered clips in output/ with their metadata and stats,
  - serves the MP4s so you can review them in the browser,
  - lets you edit title / descriptions / caption / hashtags / schedule and
    toggle "approved" (written straight back to each clip's .json),
  - starts and stops clip.py capture runs and find_streams.py discovery,
  - streams the live run log.

This never posts anything. Publishing still happens through zernio_publish.py.

Run:
    .venv\\Scripts\\python.exe dashboard.py
then open http://127.0.0.1:8787 in a browser. Bound to localhost only.
"""
import argparse
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import env_loader; env_loader.load()

HERE = Path(__file__).resolve().parent
OUTPUT_DIR = HERE / "output"
TEST_OUT = HERE / "test_out"
STATIC = HERE / "dashboard_ui"
PY = sys.executable  # the venv's python, since the dashboard is launched with it

# Fields in a clip's JSON that the operator may edit from the UI.
EDITABLE = ("title", "youtube_description", "instagram_caption", "hashtags", "post_at", "approved", "source_link")


# ---------------------------------------------------------------- run manager
class RunManager:
    """Owns at most one child process (a capture or a discovery run) at a time."""

    def __init__(self):
        self.proc = None
        self.kind = None          # "capture" | "discovery" | None
        self.cmd = None
        self.started = None
        self.lines = deque(maxlen=800)
        self.lock = threading.Lock()

    def is_running(self):
        return self.proc is not None and self.proc.poll() is None

    def _pump(self, proc):
        for raw in iter(proc.stdout.readline, ""):
            self.lines.append(raw.rstrip("\n"))
        proc.stdout.close()

    def start(self, kind, cmd):
        with self.lock:
            if self.is_running():
                return False, f"A {self.kind} run is already active. Stop it first."
            self.lines.clear()
            # New process group so we can stop the whole ffmpeg/yt-dlp tree cleanly.
            creationflags = 0
            preexec = None
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                preexec = os.setsid
            self.proc = subprocess.Popen(
                cmd, cwd=str(HERE), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, encoding="utf-8", errors="replace",
                creationflags=creationflags, preexec_fn=preexec,
            )
            self.kind = kind
            self.cmd = cmd
            self.started = time.time()
            threading.Thread(target=self._pump, args=(self.proc,), daemon=True).start()
            return True, "started"

    def stop(self):
        with self.lock:
            if not self.is_running():
                return False, "Nothing is running."
            try:
                if os.name == "nt":
                    # CTRL_BREAK reaches the whole process group; clip.py treats it as Ctrl+C.
                    self.proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGINT)
            except Exception:
                self.proc.terminate()
            return True, "stop signal sent"

    def status(self):
        running = self.is_running()
        code = None if running else (self.proc.returncode if self.proc else None)
        return {
            "running": running,
            "kind": self.kind if (running or self.proc) else None,
            "cmd": self.cmd,
            "returncode": code,
            "started": self.started,
            "elapsed": round(time.time() - self.started, 1) if self.started else None,
            "log": list(self.lines)[-200:],
        }


RUN = RunManager()


# ---------------------------------------------------------------- clip model
def _read_json(path):
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def list_clips():
    clips = []
    for base_dir, is_test in ((OUTPUT_DIR, False), (TEST_OUT, True)):
        if not base_dir.is_dir():
            continue
        for meta_path in sorted(base_dir.glob("*.json"), reverse=True):
            meta = _read_json(meta_path)
            if meta is None:
                continue
            mp4 = meta_path.with_suffix(".mp4")
            name = meta_path.stem
            posted = meta.get("posted") or {}
            published = bool(meta.get("zernio_post_id")) or bool(posted)
            publishable = bool(
                meta.get("title") and meta.get("youtube_description")
                and meta.get("instagram_caption") and meta.get("approved")
                and not meta.get("test")
            )
            clips.append({
                "name": name,
                "folder": "test_out" if is_test else "output",
                "video_url": f"/media/{'test_out' if is_test else 'output'}/{mp4.name}" if mp4.is_file() else None,
                "has_video": mp4.is_file(),
                "size": mp4.stat().st_size if mp4.is_file() else 0,
                "mtime": meta_path.stat().st_mtime,
                "score": meta.get("score"),
                "streamer": meta.get("streamer"),
                "stream_title": meta.get("stream_title"),
                "transcript": meta.get("transcript", ""),
                "spoken_language": meta.get("spoken_language"),
                "caption_language": meta.get("caption_language"),
                "moment_source_used": meta.get("moment_source_used"),
                "chat_message_count": meta.get("chat_message_count"),
                "unique_chatters": meta.get("unique_chatters"),
                "reaction_chatters": meta.get("reaction_chatters"),
                "test": bool(meta.get("test")),
                "approved": bool(meta.get("approved")),
                "published": published,
                "publishable": publishable,
                "zernio_post_id": meta.get("zernio_post_id"),
                "zernio_status": meta.get("zernio_status"),
                "title": meta.get("title") or "",
                "youtube_description": meta.get("youtube_description") or "",
                "instagram_caption": meta.get("instagram_caption") or "",
                "hashtags": meta.get("hashtags") or [],
                "post_at": meta.get("post_at") or "",
                "source_url": meta.get("source_url") or "",
                "source_link": meta.get("source_link") or meta.get("source_url") or "",
            })
    return clips


def stats(clips):
    non_test = [c for c in clips if not c["test"]]
    scores = [c["score"] for c in clips if isinstance(c.get("score"), (int, float))]
    return {
        "total": len(clips),
        "output": len(non_test),
        "test": len(clips) - len(non_test),
        "approved": sum(1 for c in non_test if c["approved"]),
        "pending": sum(1 for c in non_test if not c["approved"] and not c["published"]),
        "published": sum(1 for c in clips if c["published"]),
        "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
    }


def _clip_meta_path(folder, name):
    # Guard against path traversal; only our two known folders and plain stems.
    if folder not in ("output", "test_out"):
        return None
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name or ""):
        return None
    base = OUTPUT_DIR if folder == "output" else TEST_OUT
    path = (base / f"{name}.json").resolve()
    if base.resolve() not in path.parents:
        return None
    return path


def update_clip(folder, name, patch):
    meta_path = _clip_meta_path(folder, name)
    if not meta_path or not meta_path.is_file():
        return None, "clip not found"
    meta = _read_json(meta_path)
    if meta is None:
        return None, "could not read metadata"
    for key in EDITABLE:
        if key in patch:
            value = patch[key]
            if key == "hashtags" and isinstance(value, str):
                value = [t.strip().lstrip("#") for t in re.split(r"[,\s]+", value) if t.strip()]
            if key == "approved":
                value = bool(value)
            meta[key] = value
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta, "ok"


def cleanup_low_scores(threshold=3.0, dry_run=False):
    """Delete output clips (mp4 + json) scoring below `threshold`.

    Approved and already-published clips are always kept, as a safety net.
    Returns (removed_names, kept_count). dry_run just lists what would go.
    """
    removed = []
    kept = 0
    for meta_path in sorted(OUTPUT_DIR.glob("*.json")):
        meta = _read_json(meta_path)
        if meta is None:
            continue
        score = meta.get("score")
        protected = bool(meta.get("approved")) or bool(meta.get("zernio_post_id")) or bool(meta.get("posted"))
        if isinstance(score, (int, float)) and score < threshold and not protected:
            if not dry_run:
                meta_path.unlink(missing_ok=True)
                meta_path.with_suffix(".mp4").unlink(missing_ok=True)
            removed.append(meta_path.stem)
        else:
            kept += 1
    return removed, kept


# ---------------------------------------------------------------- command builders
def build_capture_cmd(opts):
    """opts is a dict from the UI. Returns (cmd_list, error)."""
    url = (opts.get("url") or "").strip()
    file = (opts.get("file") or "").strip()
    if not url and not file:
        return None, "Provide a live URL or a local file path."
    cmd = [PY, "clip.py"]
    if file:
        if not Path(file).is_file():
            return None, f"File not found: {file}"
        cmd += ["--file", file, "--test"]
    else:
        if not re.match(r"https?://", url):
            return None, "URL must start with http(s)://"
        cmd.append(url)
        if opts.get("test"):
            cmd.append("--test")
        if opts.get("gameplay_confirmed"):
            cmd.append("--gameplay-confirmed")
    # numeric / choice options, validated
    for flag, key, caster in (
        ("--max-seconds", "max_seconds", int), ("--chunk", "chunk", int),
        ("--clip-len", "clip_len", int), ("--lead-in", "lead_in", float),
        ("--top", "top", int), ("--min-score", "min_score", float),
    ):
        if opts.get(key) not in (None, ""):
            try:
                cmd += [flag, str(caster(opts[key]))]
            except (TypeError, ValueError):
                return None, f"{key} must be a number."
    if opts.get("layout") in ("fill", "fit"):
        cmd += ["--layout", opts["layout"]]
    if opts.get("moment_source") in ("chat", "combined", "audio"):
        cmd += ["--moment-source", opts["moment_source"]]
    if opts.get("spoken_language") in ("auto", "en", "hi"):
        cmd += ["--spoken-language", opts["spoken_language"]]
    if opts.get("no_chat"):
        cmd.append("--no-chat")
    return cmd, None


def run_publish(folder, name, scheduled_for, do_publish, now):
    """Run zernio_publish.py for one clip. Returns (ok, output_text, publishing_configured).

    do_publish=False is a dry run (sends nothing). now=True publishes immediately
    instead of using scheduled_for. This is synchronous so the UI gets the result.
    """
    if folder != "output":
        return False, "Only clips in output/ can be published (test clips cannot).", True
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name or ""):
        return False, "bad clip name", True
    cmd = [PY, "zernio_publish.py", str((OUTPUT_DIR / name))]
    if now:
        cmd.append("--now")
    elif scheduled_for:
        cmd += ["--scheduled-for", scheduled_for]
    if do_publish:
        cmd.append("--publish")
    try:
        result = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=1800)
    except subprocess.TimeoutExpired:
        return False, "Publish timed out after 30 minutes.", True
    out = (result.stdout or "") + (result.stderr or "")
    # Whether real publishing is even possible depends on the Zernio env vars.
    configured = bool(os.environ.get("ZERNIO_API_KEY")) and bool(
        os.environ.get("ZERNIO_INSTAGRAM_ACCOUNT_ID") or os.environ.get("ZERNIO_YOUTUBE_ACCOUNT_ID"))
    return result.returncode == 0, out.strip(), configured


# ---------------------------------------------------------------- HTTP handler
class Handler(BaseHTTPRequestHandler):
    server_version = "GTAClipperDashboard/1.0"

    def log_message(self, *args):
        pass  # quiet; the run log is what matters

    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    # ---- static + media ----
    def _send_file(self, path: Path, content_type):
        if not path.is_file():
            self._send_json({"error": "not found"}, 404)
            return
        size = path.stat().st_size
        range_header = self.headers.get("Range")
        if range_header and content_type.startswith("video"):
            m = re.match(r"bytes=(\d+)-(\d*)", range_header)
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else size - 1
            end = min(end, size - 1)
            self.send_response(206)
            self.send_header("Content-Type", content_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            with path.open("rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        with path.open("rb") as f:
            self.wfile.write(f.read())

    def do_GET(self):
        parsed = urlparse(self.path)
        route = parsed.path
        if route == "/" or route == "/index.html":
            self._send_file(STATIC / "index.html", "text/html; charset=utf-8")
            return
        if route == "/app.js":
            self._send_file(STATIC / "app.js", "application/javascript; charset=utf-8")
            return
        if route == "/styles.css":
            self._send_file(STATIC / "styles.css", "text/css; charset=utf-8")
            return
        if route == "/api/clips":
            clips = list_clips()
            self._send_json({"clips": clips, "stats": stats(clips)})
            return
        if route == "/api/run":
            self._send_json(RUN.status())
            return
        if route.startswith("/media/"):
            rel = route[len("/media/"):]
            folder, _, fname = rel.partition("/")
            if folder in ("output", "test_out") and re.fullmatch(r"[A-Za-z0-9._-]+\.mp4", fname or ""):
                base = OUTPUT_DIR if folder == "output" else TEST_OUT
                self._send_file(base / fname, "video/mp4")
                return
            self._send_json({"error": "bad media path"}, 400)
            return
        self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        route = urlparse(self.path).path
        body = self._body_json()
        if route == "/api/clip/update":
            meta, msg = update_clip(body.get("folder"), body.get("name"), body.get("patch") or {})
            if meta is None:
                self._send_json({"error": msg}, 400)
            else:
                self._send_json({"ok": True})
            return
        if route == "/api/clip/publish":
            ok, output, configured = run_publish(
                body.get("folder"), body.get("name"),
                (body.get("scheduled_for") or "").strip(),
                bool(body.get("publish")), bool(body.get("now")))
            self._send_json({"ok": ok, "output": output, "configured": configured})
            return
        if route == "/api/clips/cleanup":
            try:
                threshold = float(body.get("threshold", 3.0))
            except (TypeError, ValueError):
                threshold = 3.0
            removed, kept = cleanup_low_scores(threshold, dry_run=bool(body.get("dry_run")))
            self._send_json({"ok": True, "removed": removed, "kept": kept,
                             "threshold": threshold, "dry_run": bool(body.get("dry_run"))})
            return
        if route == "/api/capture/start":
            cmd, err = build_capture_cmd(body)
            if err:
                self._send_json({"error": err}, 400)
                return
            ok, msg = RUN.start("capture", cmd)
            self._send_json({"ok": ok, "message": msg, "cmd": cmd} if ok else {"error": msg},
                            200 if ok else 409)
            return
        if route == "/api/discovery/start":
            key = os.environ.get("YOUTUBE_API_KEY")
            if not key:
                self._send_json({"error": "YOUTUBE_API_KEY is not set in the dashboard's environment."}, 400)
                return
            query = (body.get("query") or "GTA 6").strip()
            cmd = [PY, "find_streams.py", query, "--max", str(int(body.get("max") or 10))]
            ok, msg = RUN.start("discovery", cmd)
            self._send_json({"ok": ok, "message": msg} if ok else {"error": msg}, 200 if ok else 409)
            return
        if route == "/api/run/stop":
            ok, msg = RUN.stop()
            self._send_json({"ok": ok, "message": msg})
            return
        self._send_json({"error": "not found"}, 404)


def main():
    ap = argparse.ArgumentParser(description="Local operator dashboard for GTA Auto Clipper.")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1", help="bind address (localhost only by default)")
    args = ap.parse_args()
    OUTPUT_DIR.mkdir(exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print(f"GTA Auto Clipper dashboard -> {url}")
    print("Serving clips from output/ and test_out/. This never posts anything.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down ...")
        if RUN.is_running():
            RUN.stop()
        server.shutdown()


if __name__ == "__main__":
    main()
