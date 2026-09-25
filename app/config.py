"""Central configuration for the CCTV detection prototype."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIDEO_DIR = ROOT / "videos"
MODEL_DIR = ROOT / "models"
STATIC_DIR = ROOT / "static"

# (camera id, display name, video file in VIDEO_DIR)
CAMERAS = [
    ("gf-1", "Ground Floor — Camera 1", "ground_floor_1.mp4"),
    ("gf-2", "Ground Floor — Camera 2", "ground_floor_2.mp4"),
    ("ff-1", "First Floor — Camera 1", "first_floor_1.mp4"),
    ("ff-2", "First Floor — Camera 2", "first_floor_2.mp4"),
    ("pk-1", "Parking — Camera 1", "parking_1.mp4"),
    ("pk-2", "Parking — Camera 2", "parking_2.mp4"),
    ("en-1", "Entrance — Camera 1", "entrance_1.mp4"),
    ("en-2", "Entrance — Camera 2", "entrance_2.mp4"),
]

# Frame size every feed is normalised to (the fetch script already encodes at this size).
FRAME_W, FRAME_H = 640, 360
# Playback frame rate of each feed.
FEED_FPS = float(os.getenv("FEED_FPS", 12))
# JPEG quality of the frames streamed to the browser.
JPEG_QUALITY = 80

# General-purpose COCO model (person, car, bag, knife, ... 80 classes).
GENERAL_MODEL = os.getenv("GENERAL_MODEL", "yolov8n.pt")  # file in MODEL_DIR
GENERAL_IMGSZ = int(os.getenv("GENERAL_IMGSZ", 416))
GENERAL_CONF = float(os.getenv("GENERAL_CONF", 0.40))

# Weapon model (Gun, Explosion, Grenade, Knife) — Subh775/Threat-Detection-YOLOv8n, MIT.
THREAT_MODEL = MODEL_DIR / "threat_yolov8n.pt"
THREAT_IMGSZ = int(os.getenv("THREAT_IMGSZ", 480))
THREAT_CONF = float(os.getenv("THREAT_CONF", 0.55))
# The weapon model occasionally fires with high confidence on a single frame (phones, car
# parts...). A weapon is only reported when it scores >= THREAT_CONF and a same-class box at
# >= THREAT_CANDIDATE_CONF overlapped it on the previous detection pass of that camera.
THREAT_CANDIDATE_CONF = float(os.getenv("THREAT_CANDIDATE_CONF", 0.35))
# Hand-held weapons must also lie mostly inside a detected person (someone is holding them).
# This removes the model's frequent false "guns" on cars, pavement and whole-scene boxes.
HELD_CLASSES = {"gun", "knife", "grenade"}
HELD_MIN_OVERLAP = 0.3

# On CPU one detection pass over all feeds takes ~1-1.5 s. The displayed video is delayed by
# this many seconds so that, for every shown frame, the detection passes just before *and*
# just after it are already available; boxes are interpolated between them and stay aligned
# with moving objects. Keep it above ~2.2x the logged detection cycle time.
DISPLAY_DELAY = float(os.getenv("DISPLAY_DELAY", 4.0))

# Classes treated as threats (red boxes, listed first, flagged on the dashboard tile).
THREAT_CLASSES = {"gun", "knife", "grenade", "explosion"}

DESCRIPTIONS = {
    "gun": "Potential firearm detected in the camera feed.",
    "knife": "Potential bladed weapon detected in the camera feed.",
    "grenade": "Potential grenade detected in the camera feed.",
    "explosion": "Possible explosion or blast detected in the camera feed.",
    "person": "Person present in the monitored area.",
}
