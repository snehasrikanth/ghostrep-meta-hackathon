from __future__ import annotations

from pathlib import Path
from urllib.request import urlopen

import cv2
import numpy as np

from app.config import Settings
from app.services.movement.geometry import LANDMARK_NAMES

POSE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)


class PoseExtractor:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_path = settings.models_dir / "pose_landmarker_lite.task"

    def extract(self, video_path: Path, timestamps: list[float] | None = None) -> list[dict]:
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
        except ImportError as exc:
            raise RuntimeError(
                "MediaPipe is not installed. Run `uv sync --extra pose` or analyze synthetic fixtures."
            ) from exc

        self._ensure_model()
        options = vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(self.model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.4,
            min_pose_presence_confidence=0.4,
            min_tracking_confidence=0.4,
        )
        landmarker = vision.PoseLandmarker.create_from_options(options)
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError("OpenCV could not open the normalized video.")

        native_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if native_fps <= 1 or native_fps > 240:
            native_fps = 30.0
        interval = 1.0 / max(self.settings.target_analysis_fps, 1.0)
        next_t = 0.0
        frames: list[dict] = []
        index = 0
        last_ms = -1
        try:
            while True:
                ok, bgr = cap.read()
                if not ok:
                    break
                msec = cap.get(cv2.CAP_PROP_POS_MSEC)
                if msec and msec > 0:
                    t = msec / 1000.0
                else:
                    t = index / native_fps
                index += 1
                if frames and t <= frames[-1]["timestamp"]:
                    t = frames[-1]["timestamp"] + 1.0 / native_fps
                if t + 1e-6 < next_t:
                    continue
                next_t = t + interval
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                stamp_ms = int(round(t * 1000))
                if stamp_ms <= last_ms:
                    stamp_ms = last_ms + 1
                last_ms = stamp_ms
                result = landmarker.detect_for_video(mp_image, stamp_ms)
                frames.append(_pack_frame(result, t, bgr.shape[1], bgr.shape[0]))
        finally:
            cap.release()
            landmarker.close()
        return frames

    def _ensure_model(self) -> None:
        if self.model_path.exists() and self.model_path.stat().st_size > 1000:
            return
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(POSE_MODEL_URL, timeout=60) as response, self.model_path.open("wb") as handle:
            handle.write(response.read())


def _pack_frame(result, timestamp: float, width: int, height: int) -> dict:
    landmarks = {}
    confidence = 0.0
    if result.pose_landmarks:
        pose = result.pose_landmarks[0]
        scores = []
        for i, lm in enumerate(pose):
            name = LANDMARK_NAMES[i] if i < len(LANDMARK_NAMES) else f"lm_{i}"
            vis = float(getattr(lm, "visibility", getattr(lm, "presence", 0.0)) or 0.0)
            landmarks[name] = {"name": name, "x": float(lm.x), "y": float(lm.y), "visibility": vis}
            scores.append(vis)
        confidence = float(np.mean(scores)) if scores else 0.0
    return {
        "timestamp": timestamp,
        "width": width,
        "height": height,
        "tracking_confidence": confidence,
        "landmarks": landmarks,
    }


def frames_from_dicts(raw: list[dict]) -> list[dict]:
    return raw
