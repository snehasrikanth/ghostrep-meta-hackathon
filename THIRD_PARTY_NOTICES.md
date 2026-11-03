# Third-party assets and software

GhostRep's repository-level license is not specified. Public visibility alone does not grant a general open-source license. The owner must select any desired license before distribution; this repair does not assign rights on their behalf.

## Fonts

The app uses Sora, Syne, and IBM Plex Mono through next/font/google. Their SIL Open Font License 1.1 notices are redistributed in docs/licenses/sora-OFL.txt, syne-OFL.txt, and ibmplexmono-OFL.txt. Unmodified notices were fetched from the official google/fonts repository on October 31, 2026. Preserve them when distributing self-hosted font bundles. Sources: https://github.com/google/fonts/tree/main/ofl/sora ; https://github.com/google/fonts/tree/main/ofl/syne ; https://github.com/google/fonts/tree/main/ofl/ibmplexmono .

## Source dependencies

Exact versions are pinned by frontend/package-lock.json and backend/uv.lock. Frontend runtime libraries include Next.js, React, react-dom, lucide-react, Recharts, react-hook-form, Zod, clsx, and tailwind-merge. Backend libraries include FastAPI, SQLAlchemy, Pydantic, NumPy, SciPy, OpenCV, MediaPipe, HTTPX, OpenAI's SDK, and meta-sam-parser. Their package distributions include their own license notices; retain those when distributing installed dependencies. This source snapshot does not vendor dependencies or claim ownership of them.

FFmpeg/FFprobe are external prerequisites; licensing depends on the installed build and enabled codecs. The repository does not redistribute those binaries. The MediaPipe pose model downloads separately from Google's model host; it is not included in the source snapshot. Review Google's applicable model terms for a hosted distribution.

## Project graphics and fixtures

frontend/public contains the GhostRep brand SVGs and derived app icons; the optional supplied squat example is the only intentionally allowlisted video asset. The scan establishes repository contents, not authorship or trademark clearance. Owner confirmation of rights in the project name/graphics remains necessary. fixtures/meta contains illustrative JSON, not private video or a claim that every fixture is a real model result. Private videos, databases, downloaded models, recordings, and developer inference artifacts are excluded by the submission packager.

