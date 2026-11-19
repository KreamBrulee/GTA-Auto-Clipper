# GTA Auto Clipper

Find high-energy moments in live gameplay and render full-screen 9:16 clips with pop-up captions: each word pops in yellow the moment it is spoken. The clipper runs on your computer. A separate Zernio command can schedule the finished clip to your connected YouTube and Instagram accounts.

The software is free and MIT-licensed. The optional AI workflow guide and prompt pack are a separate digital product.

## What it does

- Searches current YouTube live results for a phrase such as `GTA 6` and prints machine-readable JSON for AI agents.
- Requires an explicit visual confirmation before live capture, so a discussion stream or facecam-only source is not silently treated as gameplay.
- Records a live source in rolling chunks. By default it ranks moments by live-chat reactions, then falls back to audio and speech if chat is unavailable or has no messages for a chunk. Combined chat, audio, and speech scoring is also available.
- Starts clips a few seconds before the detected highlight (6 seconds by default).
- Captions English speech in English and Hindi speech in romanized Hinglish. Other or uncertain languages, including Hindi the recognizer returns in an unsupported script, have no captions. Captions are short one-line phrases (up to 3 words) at one fixed spot: each word pops in yellow when it is spoken, earlier words turn white, and the next phrase replaces the last one in the same place (never stacked). Source audio stays unchanged.
- Places captions in the lower third of the visible gameplay panel instead of using one fixed position near the bottom of the full vertical canvas.
- Fills the whole 9:16 screen with gameplay by default (`--layout fill`), centered on the player. It samples frames for facecams, shifts the crop away from a persistent side facecam, and in stacked portrait streams cuts out the facecam and fills the screen with the gameplay part. `--layout fit` keeps the old look: the full source in the middle over a blurred background.
- Resets audio and video timestamps before burning the captions.
- Masks swear words and sexual words in the burned-in captions (for example `s***`) so platforms do not limit the clip; the original audio is unchanged.
- Saves MP4 and JSON metadata in `output/`. It never posts as part of clipping.
- Schedules reviewed clips through Zernio by default. Optional unattended scheduling is available after account setup and with a standing source-rights policy; dry-run is the default.

## Install

Requirements: Python 3.10+, FFmpeg in PATH, Node.js or Deno (yt-dlp needs a JavaScript runtime to read YouTube; the clipper uses Node automatically when Deno is missing), OpenCV for `--crop` face detection, and a stable connection for first-run speech-model downloads.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

For a reproducible install with the exact versions this was tested against, use the lockfile instead: `pip install -r requirements.lock.txt`.

### Quick start (easiest path)

If you just want to get going, use the dashboard — it drives everything from a browser:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env          # then paste your keys into .env
.venv\Scripts\python.exe dashboard.py
```

Open `http://127.0.0.1:8787`, go to the **Capture** tab, paste a live URL (or a local file for a test), and start. Clips appear in the gallery as they render; open one to review, caption, approve, and publish. The command-line tools below are the same steps without the browser.

### API keys

Keys live in a local `.env` file that is gitignored, so they never get committed. Copy the template and fill in what you need:

```powershell
Copy-Item .env.example .env
# then edit .env and paste your keys
```

Every script loads `.env` automatically on startup. A variable you also set in the terminal (`$env:YOUTUBE_API_KEY = "..."`) still overrides the `.env` value. Only `YOUTUBE_API_KEY` is needed for stream search and YouTube live-chat scoring; the `ZERNIO_*` keys are only for publishing. Keep keys out of prompts, source files, and GitHub.

```powershell
python find_streams.py "GTA 6" --max 25 --json
```

The YouTube API returns live search candidates in `viewCount` order. It is not a dependable ranking of current live viewers; open a candidate and confirm the stream before use.

## Make clips

Open the candidate stream and verify that actual GTA gameplay is visible in the video. A GTA title, thumbnail, or talking head is not enough. Then start capture and keep it running until you press Ctrl+C. The default is chat-first. If chat is unavailable or has no messages for a chunk, the clipper automatically uses audio and speech instead. The clipper writes each selected highlight to `output/`:

```powershell
python clip.py "https://www.youtube.com/watch?v=VIDEO_ID" --gameplay-confirmed --max-seconds 0 --clip-len 30 --lead-in 6 --top 2
```

Important options:

| Option | Default | Purpose |
| --- | ---: | --- |
| `--max-seconds` | `0` | Capture duration; `0` runs until stopped |
| `--chunk` | `90` | Analysis chunk size in seconds |
| `--clip-len` | `30` | Rendered highlight length |
| `--lead-in` | `6` | Seconds before the detected moment |
| `--top` | `1` | Highlights kept from each chunk |
| `--gameplay-confirmed` | required for live capture | Confirm you inspected the stream and saw actual gameplay before recording |
| `--min-score` | `2.5` | Minimum moment score |
| `--layout` | `fill` | `fill`: gameplay covers the full 9:16 screen, facecams cropped out. `fit`: full source in the middle over a blurred background |
| `--crop` | off | Old flag, same as `--layout fill` |
| `--moment-source` | `chat` | Choose `chat`, `combined`, or `audio` for highlight selection |
| `--spoken-language` | `auto` | `auto` detects the language and locks to Hindi (Hinglish captions) once a stream is clearly Hindi. `hi` / `en` force it for the whole stream |
| `--no-chat` | off | Skip live-chat collection and use audio and speech only |
| `--output-dir` | `output/` | Custom destination folder |

Examples: `--moment-source chat` uses chat reactions first; `--moment-source combined` scores chat, audio, and speech together; `--moment-source audio` uses the original audio and speech method. Chat mode falls back to audio and speech when it has no chat data.

Test a local video first. Test output goes to `test_out/` and cannot be published:

```powershell
python clip.py --file "C:\videos\gameplay.mp4" --test --clip-len 30
```

## Operator dashboard

A local control panel for reviewing clips and running captures from a browser. It uses only the Python standard library (no extra install) and never posts anything.

```powershell
.venv\Scripts\python.exe dashboard.py
```

Then open `http://127.0.0.1:8787`. It is bound to localhost only. From the dashboard you can:

- See stats (clips total, approved, pending, published, average score) and a gallery of every clip in `output/` and `test_out/`, each playable in the browser.
- Open a clip to review its score, transcript, language, and live-chat stats, edit the title / YouTube description / Instagram caption / hashtags / source link / schedule, and toggle **Approved** — all written straight back to the clip's `.json`.
- Insert a trending caption with one click from the preset chips above the Instagram caption field.
- Start and stop `clip.py` captures (live URL or local test file) and watch the run log live, with a banner while a capture is running.
- Run `find_streams.py` discovery (needs `YOUTUBE_API_KEY` in the dashboard's environment).
- **Clean up < 3**: delete unapproved, unpublished clips scoring below 3 (approved and published clips are always kept; it previews the list and asks before deleting).
- **Publish** an approved clip to your connected accounts: a dry-run button (sends nothing) and a publish button, both calling `zernio_publish.py` under the hood. The source link you set is appended to the descriptions automatically.

For Instagram-only setups, a clip only needs an Instagram caption and **Approved** to publish — a YouTube title and description are required only when a YouTube account is configured.

## Schedule to YouTube + Instagram

Connect a YouTube account and/or an Instagram Creator or Business account to Zernio. Put the key and account IDs in your `.env` (see `.env.example`). **Set only the accounts you actually use** — the clip is posted only to the platforms whose account ID is present, so an Instagram-only setup just leaves the YouTube ID blank:

```
ZERNIO_API_KEY=YOUR_ZERNIO_API_KEY
ZERNIO_INSTAGRAM_ACCOUNT_ID=YOUR_INSTAGRAM_ACCOUNT_ID
# ZERNIO_YOUTUBE_ACCOUNT_ID=          # leave blank for Instagram-only
```

A clip needs an Instagram caption to post to Instagram, and a title plus YouTube description to post to YouTube; fields for a platform you have not configured are not required.

Review the clip and its JSON metadata, then mark the metadata `"approved": true`. Preview the schedule first:

```powershell
python zernio_publish.py "output\gta-CLIP-ID" --scheduled-for "2026-11-18T12:00:00+05:30"
```

The dry run sends nothing. To schedule the post to both accounts, add `--publish`:

```powershell
python zernio_publish.py "output\gta-CLIP-ID" --scheduled-for "2026-11-18T12:00:00+05:30" --publish
```

For unattended posting, first make sure the AI agent is restricted to sources you have the right to use and that you have tested its output. Then set `GTA_UNATTENDED_POSTS=1` in the machine's private environment and run with `--publish --unattended`. A scheduled post already accepted by Zernio can publish while your computer is asleep. Discovery and clip rendering still require an awake, connected runner.

`publish.py` is the same command as `zernio_publish.py`, but it also accepts the generic variable names `PUBLISH_API_KEY`, `PUBLISH_YOUTUBE_ACCOUNT_ID` and `PUBLISH_INSTAGRAM_ACCOUNT_ID`, so either spelling works: `python publish.py "output\gta-CLIP-ID" --publish --unattended --scheduled-for "FUTURE_ISO_TIME"`. To post to many channels with an equal share, use [GTA Auto Sender](https://github.com/AnIntellectualBeing/GTA-Auto-Sender).

The publisher stores the Zernio post ID and an idempotency key in the metadata. If an API call fails, check the Zernio dashboard before retrying.

## Use with any AI assistant

Copy [GTA-CLIPPING-PROMPT.txt](GTA-CLIPPING-PROMPT.txt) into ChatGPT, Claude, Gemini, or another AI assistant. The prompt itself needs no API key, plugin, or special setup. If your AI can access your video and run local tools, it can help operate the clipper; otherwise it will tell you what it can do and guide you one step at a time. Automatic clipping still needs the free tool installed. YouTube chat scoring uses the same optional YouTube API key as live search; without it, audio and speech scoring still works.

For an AI that can access this project folder, [AI_WORKFLOW.md](AI_WORKFLOW.md) gives the detailed tool workflow. Never paste credentials into a prompt.

## Rights and platform notes

This release has no creator allowlist; the user chooses the source. You are responsible for obtaining rights and permissions to record, edit, and publish the footage. Creator credit does not replace permission. YouTube search ranking does not report a verified live concurrent-viewer leaderboard. This independent fan project is not affiliated with Rockstar Games, Take-Two Interactive, YouTube, Instagram, Meta, or Zernio.

## License

MIT. See [LICENSE](LICENSE). No OpenShorts application code or AutoCrop-Vertical code is bundled in this focused release.

## Several streams, several AI agents, several channels

See [docs/MULTI-AGENT.md](docs/MULTI-AGENT.md) for the roles (capture runner, checker, editor), running one capture per stream, the checker's veto rules, and the YouTube/Instagram daily limits. Posting to many channels with an equal share: [GTA Auto Sender](https://github.com/AnIntellectualBeing/GTA-Auto-Sender).
