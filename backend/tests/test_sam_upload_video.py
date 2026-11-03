"""The SAM upload is bounded in fps, silent, and separate from the replay video."""

import hashlib
import json
import shutil
import subprocess

import pytest

from app.services.video.ffmpeg import inspect_video, prepare_sam_video


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg is unavailable")
def test_sam_copy_resamples_and_removes_audio_without_changing_original(tmp_path):
    original = tmp_path / "original.mp4"
    copy = tmp_path / "sam.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=64x96:rate=60",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
        "-t", "1.2", "-c:v", "libx264", "-c:a", "aac", "-metadata", "comment=private test metadata", str(original),
    ], check=True, capture_output=True)
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    metadata = prepare_sam_video(original, copy, 15)
    assert metadata["fps"] == 10
    assert metadata["duration"] == pytest.approx(1.2, abs=1 / 15)
    assert (metadata["width"], metadata["height"]) == (64, 96)
    streams = json.loads(subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(copy),
    ], check=True, capture_output=True, text=True).stdout)["streams"]
    assert [stream["codec_type"] for stream in streams] == ["video"]
    tags = json.loads(subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json", str(copy),
    ], check=True, capture_output=True, text=True).stdout)["format"].get("tags", {})
    assert "comment" not in tags
    assert inspect_video(original)["fps"] == 60
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg is unavailable")
def test_default_sam_copy_bounds_frame_rate_and_preserves_time_domain(tmp_path):
    original, copy = tmp_path / "source.mp4", tmp_path / "silent.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=64x96:rate=60", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "1.2", "-c:v", "libx264", "-c:a", "aac", str(original)], check=True, capture_output=True)
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    media = prepare_sam_video(original, copy)
    assert media["fps"] == 10
    assert media["duration"] == pytest.approx(inspect_video(original)["duration"], abs=1 / 10)
    def packet_times(path):
        return subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time", "-of", "csv=p=0", str(path)], check=True, capture_output=True).stdout
    assert packet_times(copy) != packet_times(original)
    assert media["duration"] * media["fps"] <= 600
    assert max(media["width"],media["height"])<=480
    assert media["sampling_policy"]=="max10fps_600frames_480px"
    streams = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(copy)], check=True, capture_output=True, text=True).stdout)["streams"]
    assert [stream["codec_type"] for stream in streams] == ["video"]
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg is unavailable")
def test_variable_fps_rotated_copy_preserves_clock_and_time_based_outline_matching(tmp_path):
    from app.services.meta.silhouettes import attach_silhouettes
    source, rotated, output = [tmp_path / x for x in ("vfr.mp4", "rotated.mp4", "bounded.mp4")]
    subprocess.run(["ffmpeg","-v","error","-y","-f","lavfi","-i","testsrc2=size=960x540:rate=60:duration=2",
        "-vf", "select=if(lt(t\\,1)\\,not(mod(n\\,2))\\,not(mod(n\\,5)))", "-fps_mode","vfr","-c:v","libx264",str(source)],check=True,capture_output=True)
    subprocess.run(["ffmpeg","-v","error","-y","-display_rotation:v","-90","-i",str(source),"-c","copy",str(rotated)],check=True,capture_output=True)
    metadata=prepare_sam_video(rotated,output)
    assert metadata["height"]==480 and metadata["width"]<metadata["height"]
    assert metadata["rotate"]==0 and metadata["fps"]==10
    def times(path):
        data=json.loads(subprocess.run(["ffprobe","-v","error","-show_frames","-show_entries","frame=best_effort_timestamp_time","-of","json",str(path)],check=True,capture_output=True,text=True).stdout)
        return [float(f["best_effort_timestamp_time"]) for f in data["frames"]]
    source_times=times(rotated); sample_times=times(output)
    # VFR/B-frame container duration can be shorter than the final presentation timestamp.
    assert metadata["duration"]==pytest.approx(source_times[-1]+(source_times[-1]-source_times[-2]),abs=.1)
    assert len({round(b-a,3) for a,b in zip(source_times,source_times[1:])})>1
    assert sample_times[0]==0 and sample_times[-1]<=source_times[-1]+.1
    polygons=[[{"x":.1+i*.01,"y":.1},{"x":.2,"y":.2},{"x":.1,"y":.3}] for i in range(len(sample_times))]
    masks=[{"t":t,"frame_index":i,"polygon":polygons[i]} for i,t in enumerate(sample_times)]
    # VFR pose indexes and SAM-copy indexes differ; corresponding source times must win.
    overlay={"frames":[{"t":t,"current":[],"active_rep":None} for t in source_times]}
    result=attach_silhouettes(overlay,{"fps":10,"source":"fixture","tracks":[{"concept":"person","object_id":"fictional","frames":masks}]},None)
    for f in result["frames"]:
        index=min(range(len(sample_times)),key=lambda i:abs(sample_times[i]-f["t"]))
        assert f["silhouette"]==polygons[index]
