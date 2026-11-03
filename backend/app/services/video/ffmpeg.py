from __future__ import annotations

import json
import math
import shutil
import subprocess
import time
from pathlib import Path


class MediaError(RuntimeError):
    pass


def require_ffmpeg() -> None:
    if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
        raise MediaError("FFmpeg/FFprobe is required on PATH.")


def inspect_video(path: Path, *, timeout_seconds: float = 60) -> dict:
    require_ffmpeg()
    deadline = time.monotonic() + timeout_seconds
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        raise MediaError("Local media inspection/preparation exceeded 60 seconds.") from exc
    if proc.returncode != 0:
        raise MediaError(f"FFprobe rejected the file: {proc.stderr.strip()[:300]}")
    data = json.loads(proc.stdout)
    video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video_stream:
        raise MediaError("No video stream found.")
    duration = _positive_number(data.get("format", {}).get("duration")) or _positive_number(video_stream.get("duration"))
    if not duration:
        # MediaRecorder WebM commonly has no finalized container duration.
        # Read actual video timestamps rather than rejecting it as an empty clip.
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise MediaError("Local media inspection exceeded its deadline.")
        try:
            packets = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "packet=pts_time,duration_time", "-of", "json", str(path)],
                capture_output=True, text=True, check=False, timeout=remaining,
            )
        except subprocess.TimeoutExpired as exc:
            raise MediaError("Local media inspection exceeded its deadline.") from exc
        if packets.returncode != 0:
            raise MediaError("Could not read video timestamps. Try uploading the original recording again.")
        spans = []
        for packet in json.loads(packets.stdout).get("packets", []):
            try:
                start = float(packet.get("pts_time", "nan"))
            except (TypeError, ValueError):
                continue
            if math.isfinite(start):
                spans.append((start, start + _positive_number(packet.get("duration_time"))))
        if spans:
            duration = max(end for _, end in spans) - min(start for start, _ in spans)
        if not duration or not math.isfinite(duration):
            raise MediaError("Could not determine a playable video duration. Try uploading the original recording again.")
    fps = _parse_fps(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate"))
    return {
        "duration": duration,
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "fps": fps,
        "codec": video_stream.get("codec_name"),
        "rotate": _rotation_degrees(video_stream),
        "size_bytes": int(data.get("format", {}).get("size") or path.stat().st_size),
    }


def _positive_number(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) and number > 0 else 0.0


def normalize_video(src: Path, dest: Path) -> dict:
    """Bake display rotation into pixels and produce an H.264 MP4.

    Timestamps stay on the source clock. Frame rate is not resampled, so
    variable-frame-rate phone video keeps its original timing.
    """
    require_ffmpeg()
    dest.parent.mkdir(parents=True, exist_ok=True)
    rotation = int(inspect_video(src).get("rotate") or 0) % 360
    filters = _rotation_filters(rotation) + ["scale=720:-2", "setsar=1"]
    cmd = [
        "ffmpeg",
        "-y",
        "-noautorotate",
        "-i",
        str(src),
        "-map_metadata",
        "0",
        "-vf",
        ",".join(filters),
        "-metadata:s:v:0",
        "rotate=0",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-an",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        str(dest),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)
    except subprocess.TimeoutExpired as exc:
        raise MediaError("Local media inspection/preparation exceeded 60 seconds.") from exc
    if proc.returncode != 0:
        raise MediaError(f"FFmpeg failed to normalize the video: {proc.stderr.strip()[:400]}")
    return inspect_video(dest)


def prepare_sam_video(src: Path, dest: Path, fps: int | None = None) -> dict:
    """Bound optional outlines to 10fps/600 frames and a 480px long edge.

    Original replay is untouched. Frame timestamps stay in source seconds;
    mask/pose association must use time, never matching frame indexes.
    """
    require_ffmpeg()
    deadline=time.monotonic()+45
    def remaining():
        left=deadline-time.monotonic()
        if left <= 0:
            raise MediaError("Optional outline preparation exceeded its 45-second deadline.")
        return left
    source=inspect_video(src,timeout_seconds=remaining())
    duration=max(float(source["duration"]),.1)
    sampled_fps=min(float(fps or 10),10,599/duration)
    rotation=int(source.get("rotate") or 0)%360
    filters=_rotation_filters(rotation)+[f"fps={sampled_fps:.6f}","scale='min(480,iw)':'min(480,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2","setsar=1"]
    dest.parent.mkdir(parents=True,exist_ok=True)
    command=["ffmpeg","-y","-noautorotate","-i",str(src),"-map","0:v:0","-map_metadata","-1","-an",
        "-vf",",".join(filters),"-frames:v","600","-metadata:s:v:0","rotate=0","-c:v","libx264","-pix_fmt","yuv420p","-preset","veryfast","-crf","23",str(dest)]
    try: proc=subprocess.run(command,capture_output=True,text=True,check=False,timeout=remaining())
    except subprocess.TimeoutExpired as exc: raise MediaError("Optional outline preparation exceeded 45 seconds.") from exc
    if proc.returncode !=0: raise MediaError("Could not prepare optional outline video.")
    info=inspect_video(dest,timeout_seconds=remaining());info["source_duration"]=duration;info["sampling_policy"]="max10fps_600frames_480px"
    return info


def _rotation_degrees(stream: dict) -> int:
    """Clockwise degrees needed to display the frame upright."""
    tags = stream.get("tags") or {}
    raw = tags.get("rotate")
    if raw not in (None, ""):
        return int(round(float(raw))) % 360
    for side in stream.get("side_data_list") or []:
        if side.get("rotation") is not None:
            # Display-matrix rotation is the opposite direction of the rotate tag.
            return (-int(round(float(side["rotation"])))) % 360
    return 0


def _rotation_filters(rotation: int) -> list[str]:
    if rotation == 90:
        return ["transpose=1"]
    if rotation == 270:
        return ["transpose=2"]
    if rotation == 180:
        return ["transpose=1", "transpose=1"]
    return []


def _parse_fps(value: str | None) -> float:
    if not value or value == "0/0":
        return 0.0
    if "/" in value:
        num, den = value.split("/", 1)
        try:
            return float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0
