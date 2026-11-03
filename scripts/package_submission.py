#!/usr/bin/env python3
"""Export a runnable source snapshot without credentials, local assets, or Git history."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    ".env.example", ".gitignore", "README.md", "Makefile",
    "backend/.python-version", "backend/pyproject.toml", "backend/uv.lock",
    "frontend/.gitignore", "frontend/eslint.config.mjs", "frontend/next.config.ts",
    "frontend/package.json", "frontend/package-lock.json", "frontend/tsconfig.json",
    "THIRD_PARTY_NOTICES.md",
    "fixtures/videos/.gitkeep",
    "scripts/package_submission.py",
}


def public_file(name: str) -> bool:
    path = Path(name)
    # The one supplied exercise example is intentionally distributed. All other
    # videos, recordings, databases and private media remain excluded.
    if name == "frontend/public/demos/squat-example.mp4":
        return True
    if name in FILES:
        return True
    if name.startswith("docs/licenses/") and path.suffix == ".txt":
        return True
    if any(name.startswith(prefix) for prefix in ("backend/app/", "backend/tests/")):
        return path.suffix == ".py"
    if any(name.startswith(prefix) for prefix in ("frontend/app/", "frontend/components/", "frontend/lib/")):
        return path.suffix in {".ts", ".tsx", ".css", ".ico"}
    if name.startswith("frontend/public/"):
        return path.suffix in {".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico"}
    return name.startswith("fixtures/meta/") and path.suffix == ".json"


def local_keys() -> list[bytes]:
    """Compare output against local key values without logging or exporting them."""
    values = []
    for env in (ROOT / ".env", ROOT / "backend/.env", ROOT / "frontend/.env.local"):
        if not env.is_file():
            continue
        for line in env.read_text().splitlines():
            match = re.match(r"\s*(?:export\s+)?([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD))\s*=\s*(.+)", line)
            if match:
                value = match[2].strip().strip("\"'")
                if len(value) >= 16:
                    values.append(value.encode())
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/GhostRep-submission.zip")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.exists():
        parser.error("Output exists. Choose a new --output path to preserve the previous snapshot.")
    # Include modified/new source; an extracted source snapshot also works without Git.
    in_git = shutil.which("git") and subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"], cwd=ROOT, capture_output=True,
    ).returncode == 0
    if in_git:
        listed = subprocess.check_output(["git", "ls-files", "-c", "-o", "--exclude-standard", "-z"], cwd=ROOT)
        candidates = listed.decode().split("\0")
        # Include the selected setup files even under a local ignore policy.
        candidates.extend(FILES)
    else:
        candidates = list(FILES)
        for prefix in ("backend/app", "backend/tests", "frontend/app", "frontend/components", "frontend/lib", "frontend/public", "fixtures/meta", "docs/licenses"):
            candidates.extend(str(path.relative_to(ROOT)) for path in (ROOT / prefix).rglob("*") if path.is_file())
    names = sorted({name for name in candidates if name and public_file(name)})
    required = {"README.md", ".env.example", "backend/app/main.py", "backend/uv.lock", "frontend/package-lock.json"}
    if not required.issubset(names) or any(not (ROOT / name).is_file() for name in required):
        parser.error("Required source/setup files are missing.")
    keys = local_keys()
    sources = []
    for name in names:
        path = ROOT / name
        if not path.exists():
            continue
        if path.is_symlink():
            parser.error(f"Refusing a symlink in the submission: {name}")
        data = path.read_bytes()
        private_key_marker = b"-----BEGIN " + b"PRIVATE KEY-----"
        if any(key in data for key in keys) or private_key_marker in data:
            parser.error(f"Credential material detected in {name}; no archive was written.")
        sources.append((name, path))
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in sources:
            archive.write(path, f"GhostRep/{name}")
    print(f"Created {output} ({len(sources)} source/setup files)")
    print("No Git history, local recordings/data, dependencies, cached models, or internal notes included.")
    print("This snapshot does not remove data already present in the original repository's history.")


if __name__ == "__main__":
    main()
