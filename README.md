# GhostRep

**Your best rep becomes your coach.**

GhostRep combines a personalized training week, workout logging, squat-video movement comparisons, and evidence-grounded coaching. It runs locally with a Next.js frontend and FastAPI backend.

## Meta AI integration

- **Muse Spark** uses training goals, experience, schedule, equipment, and exercise preferences to generate a structured weekly plan, including warm-ups and exercise doses. The app validates the response before offering the plan for review.
- **Muse Spark coaching / Ask your coach** explains owned, structured set evidence and relevant next-set suggestions. Verified facts and replay references constrain displayed answers. Without consent or an available live provider, the app labels its basic saved-evidence summaries.
- **SAM 3.1** segments the athlete to create outlines for current/reference replay. SAM does not count reps or certify technique.
- **MediaPipe and local algorithms** track joints, detect repetitions, select an observed personal reference, and align movement phases for comparison.

The user reviews proposed target changes before they take effect. Opening a page or replaying a saved result does not make a fresh model call.

## Requirements

- Python **3.13** and [uv](https://docs.astral.sh/uv/)
- Node.js **22.18 or newer**, npm, and Make
- FFmpeg **and FFprobe** on `PATH`
- Internet access for dependency installation, Next.js Google Fonts, and the first MediaPipe pose-model download
- A Meta Model API key with access to the configured models for live planning, coaching, and outlines

Install FFmpeg on macOS with `brew install ffmpeg`, or on Debian/Ubuntu with `sudo apt-get install ffmpeg`. The archive contains source and lockfiles, not installed dependencies or downloaded models.

## Quick start

From this directory:

```bash
cp .env.example .env
make setup
```

Start the backend and frontend in **two separate terminals**:

```bash
make backend
```

```bash
make frontend
```

Open **http://localhost:3000**. The API listens on **http://localhost:8000**; its health endpoint is `/health`. Keep a consistent hostname when using both servers. Stop a process with Ctrl+C. Restart the backend after Python or environment changes; `make backend-dev` enables development reload instead.

The app creates a new local database and media directories. No personal training data, account, recording, or saved live response is required. Camera recording needs localhost or HTTPS; a physical phone cannot access a Mac server through the phone's own `localhost`.

## Enable the Meta models

The example configuration uses local providers and disables paid inference. In your private `.env`, set:

```dotenv
MODEL_API_KEY=your_private_meta_model_api_key
ENABLE_META_API=true
WORKOUT_PROVIDER=meta_live
COACHING_PROVIDER=meta_live
SEGMENTATION_PROVIDER=meta_live
MUSE_MODEL=muse-spark-1.3
SAM_MODEL=sam-3.1
```

Restart the backend. Keep the normal consent/approval controls enabled. Training-profile submission, video analysis, and coach questions have their relevant consent flows. Never put a key in a `NEXT_PUBLIC_` variable, commit `.env`, or embed evaluation credentials in the README. Live calls use the operator's Meta account and credits; optional usage controls are documented in `.env.example` and `backend/app/config.py`.

Without live Meta access, profile setup, local planning, manual logging, replay, local pose analysis, and labelled basic coaching remain available. A failed optional outline stage falls back to skeleton replay. Live model latency varies; processing stages and recovery controls expose progress rather than promising an instant result.

## Try the main workflow

1. Choose **Start training / Profile**. Enter goals, experience, days, session length, available equipment, and exercise preferences. Review and generate the week.
2. Preview sessions, warm-ups, exercises, sets, reps, and rest. Choose **Use this plan**. To explore supported video coaching, choose compatible lower-body goals and equipment; the app currently analyzes **barbell squats**.
3. Start a workout. Log a set and use the rest timer. **Watch squat demo** opens an optional example; it is separate from personal analysis and the selected reference.
4. Choose **Record workout**. Enable the camera and record a set, or upload a clip. Use a stable side view, show the whole body, and keep rack posts clear of joints. Supported uploads are MP4, MOV, M4V, or WebM; stay below 80 MB and 90 seconds.
5. Review the clip, optionally add load and reported effort, give consent, and choose **Analyze my set**. **Save video only** stores a replay without starting analysis. Other exercises support logging/replay, rather than the squat analysis pipeline.
6. Review detected/planned/logged counts, the selected reference, rep replay, and any next-set suggestion. Correcting a logged count preserves the measured result. Review a proposed change before accepting it.
7. Open **Ask your coach**, consent separately, and submit a starter question or follow-up. Questions use saved evidence; they do not rerun video analysis or SAM. Review the explanation of any rest suggestion; reported maximum effort is not a measured fatigue diagnosis.
8. Revisit **Progress**, or use the desktop's mobile-preview icon to inspect the responsive layout. Meta Ray-Ban glasses integration is a future idea, not a delivered feature.

## Optional examples and fixtures

```bash
make demo
```

Then open **http://localhost:3000/dev/demo** and choose **Open demo account**. This explicitly labelled, isolated synthetic account is a development-only review aid; **Back to my account** restores the previous identity. `/record?demo=1` provides a synthetic sample analysis without live inference. Samples do not change workout targets or count as performed training.

`fixtures/meta/*.json` are required example/test inputs, not proof of fresh model calls. The single distributed product video is `frontend/public/demos/squat-example.mp4`; retain it for **Watch squat demo**, subject to the publication-rights notice below. Video-editing scripts, narration, final submission videos, internal demo scripts, and development reports are not needed to run the app and are excluded.

## Tests

```bash
make test
make check
```

`make test` runs backend and frontend tests. `make check` runs lint, TypeScript, and a production build. Automated provider tests use fake transports/local evidence and block Meta network access. Optional private-video/landmark tests may skip when their assets are absent; this snapshot does not distribute those assets or claim a real-video accuracy benchmark.

## Limits and data handling

Monocular pose estimates can miss or misalign reps, especially with occlusion or poor framing. Detected reps, reported effort, logged reps, and planned targets remain distinct. A personal reference is an observed repetition, not an ideal-form standard. Closeness to image vertical is not a diagnosis of forward lean or incorrect technique. Faster timing or a reference difference alone is not proof of improvement, safety, fatigue, or injury risk.

Saved replays and the training journal are local until the user explicitly submits data for a configured provider workflow. Coach questions share bounded structured evidence, not the raw video. The app offers deletion controls; local saved-media expiry is not automatically scheduled. Provider deletion is requested after processing, but remote cleanup can remain unconfirmed after a network failure. The current SQLite/in-process worker architecture is intended for local evaluation, not multi-user production hosting.

## Source, assets, and development history

Dependency versions are pinned in `backend/uv.lock` and `frontend/package-lock.json`. Keep [third-party notices](THIRD_PARTY_NOTICES.md) and `docs/licenses/` with the source. The supplied squat example has a publication-rights notice in THIRD_PARTY_NOTICES.md; resolve its stated redistribution status before publishing that asset. No repository-level open-source license has been selected by this export.

This is a clean source snapshot of the current application, not the original development repository. Original local Git history begins on October 26, 2026 and is preserved separately by the owner. This snapshot intentionally excludes `.git`, credentials, private recordings/databases, generated builds, installed dependencies, model caches, and internal working artifacts. A new snapshot commit records packaging time; it does not establish when every feature was first developed. Any event eligibility requirements remain governed by the organizers' official rules.
