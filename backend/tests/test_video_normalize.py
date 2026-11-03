import shutil
import subprocess
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.video.ffmpeg import MediaError, inspect_video, normalize_video


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")
def test_rotation_metadata_is_applied(tmp_path: Path):
    landscape = tmp_path / "landscape.mp4"
    src = tmp_path / "sideways.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=320x180:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(landscape)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-display_rotation:v", "-90", "-i", str(landscape), "-c", "copy", str(src)],
        check=True,
        capture_output=True,
    )
    before = inspect_video(src)
    out = normalize_video(src, tmp_path / "upright.mp4")
    assert before["rotate"] == 90
    assert out["width"] == 720
    assert out["rotate"] == 0
    assert out["height"] > out["width"]


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg is not installed")
def test_streaming_webm_without_duration_is_inspected_and_normalized(tmp_path: Path):
    src = tmp_path / "camera.webm"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=10:duration=2",
         "-c:v", "libvpx-vp9", "-live", "1", str(src)],
        check=True, capture_output=True,
    )
    metadata = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-of", "json", str(src)],
        check=True, capture_output=True, text=True,
    ).stdout)
    assert "duration" not in metadata["format"]
    assert inspect_video(src)["duration"] == pytest.approx(2, abs=0.1)
    normalized = normalize_video(src, tmp_path / "camera.mp4")
    assert normalized["duration"] == pytest.approx(2, abs=0.1)
    assert normalized["fps"] == pytest.approx(10)


@pytest.mark.parametrize("packets", [[], [{"pts_time": "N/A"}], [{"pts_time": "nan"}]])
def test_missing_duration_and_unusable_timestamps_give_actionable_error(tmp_path, packets):
    metadata = {"streams": [{"codec_type": "video"}], "format": {}}
    responses = [subprocess.CompletedProcess([], 0, json.dumps(value), "") for value in
                 (metadata, {"packets": packets})]
    with patch("app.services.video.ffmpeg.require_ffmpeg"), patch(
        "app.services.video.ffmpeg.subprocess.run", side_effect=responses
    ), pytest.raises(MediaError, match="original recording"):
        inspect_video(tmp_path / "invalid.webm")


def test_timestamp_fallback_obeys_inspection_deadline(tmp_path):
    metadata = {"streams": [{"codec_type": "video"}], "format": {}}
    with patch("app.services.video.ffmpeg.require_ffmpeg"), patch(
        "app.services.video.ffmpeg.subprocess.run",
        side_effect=[subprocess.CompletedProcess([], 0, json.dumps(metadata), ""),
                     subprocess.TimeoutExpired("ffprobe", 1)],
    ), pytest.raises(MediaError, match="deadline"):
        inspect_video(tmp_path / "camera.webm", timeout_seconds=1)
