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
    # School building: five synchronised cameras from the MEVA dataset, used for journey tracking
    ("sc-plaza", "Plaza — Camera 1", "school_plaza.mp4"),
    ("sc-lobby", "Lobby — Camera 1", "school_lobby.mp4"),
    ("sc-stairs", "Stairwell — Camera 1", "school_stairwell.mp4"),
    ("sc-cafe", "Cafeteria — Camera 1", "school_cafeteria.mp4"),
    ("sc-hall", "Hallway — Camera 1", "school_hallway.mp4"),
]
# Dashboard section for cameras that are not part of a tracking site.
DEFAULT_GROUP = "Main Building"

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
# ...and be clearly smaller than that person: the model sometimes labels whole people "Gun".
HELD_MAX_AREA_RATIO = 0.75
# The two sightings that confirm a new weapon must be at most this far apart (a weapon that is
# already confirmed stays confirmed while it keeps being detected). A new candidate is
# re-checked on the frame THREAT_RECHECK_S later, taken from the display buffer, instead of
# waiting for the next full detection cycle (which takes ~2 s with 13 feeds).
THREAT_CONFIRM_GAP_S = 1.6
THREAT_RECHECK_S = 1.25

# On CPU one detection pass over all 13 feeds takes ~2 s (more when the machine is busy). The
# displayed video runs behind so that, for every shown frame, the detection passes just before
# *and* just after it are already available; boxes are interpolated between them and stay
# aligned with moving objects. The delay follows the measured cycle time (DELAY_PER_CYCLE x
# cycle), within [DISPLAY_DELAY, MAX_DISPLAY_DELAY] seconds.
DISPLAY_DELAY = float(os.getenv("DISPLAY_DELAY", 4.0))
MAX_DISPLAY_DELAY = float(os.getenv("MAX_DISPLAY_DELAY", 10.0))
DELAY_PER_CYCLE = 2.3

# Classes treated as threats (red boxes, listed first, flagged on the dashboard tile).
THREAT_CLASSES = {"gun", "knife", "grenade", "explosion"}

DESCRIPTIONS = {
    "gun": "Potential firearm detected in the camera feed.",
    "knife": "Potential bladed weapon detected in the camera feed.",
    "grenade": "Potential grenade detected in the camera feed.",
    "explosion": "Possible explosion or blast detected in the camera feed.",
    "person": "Person present in the monitored area.",
}

# --- Person journey tracking -------------------------------------------------------------
# Every person gets an ID (P-001, ...) and is followed within each camera. Across cameras,
# identities are linked only inside a site: cameras a person can walk between, recorded at the
# same time (these feeds are also played in lockstep).
TRACKING_SITES = {
    "School Building": ["sc-plaza", "sc-lobby", "sc-stairs", "sc-cafe", "sc-hall"],
}
# Camera pairs whose views overlap: a person may be visible in both at once.
TRACKING_OVERLAPS = [("sc-lobby", "sc-stairs")]
CO_OCCUR_S = 2.5              # seen in a non-overlapping camera this recently = cannot be here too
# OSNet-x0.25 person re-identification model (appearance embeddings), exported to ONNX.
REID_MODEL = MODEL_DIR / "osnet_x0_25_msmt17.onnx"
REID_MIN_HEIGHT = 40          # px; smaller people are tracked by position only
REID_BUDGET = 32              # max embeddings per detection pass (CPU cost ~15 ms each)
REID_THRESHOLD = float(os.getenv("REID_THRESHOLD", 0.66))  # similarity to re-identify a person
REID_MERGE_THRESHOLD = 0.72   # stricter bar for folding a provisional ID into an earlier person
REID_MARGIN = 0.04            # ... and at least this much better than the next candidate
REID_WINDOW_S = 120           # a person can be re-identified up to this long after last seen
PROVISIONAL_S = 10            # a new ID may still be merged into an earlier person this long
TRACK_MOTION_S = 5            # link detections by position if the track was seen this recently
TRACK_MIN_SIM = 0.45          # appearance veto for position-based linking (when both known)
TRACK_RECOVER_SIM = 0.62      # re-attach a lost track in the same camera by appearance
TRACK_LOST_S = 20             # forget a camera track after this long unseen
MOVE_CONFIRM_S = 1.5          # a move to another camera is recorded once the old one lost them this long
PERSON_ACTIVE_S = 6           # "Active" while seen within this many seconds
PERSON_RETENTION_S = 3600     # drop people not seen for an hour
MAX_JOURNEY_STEPS = 200
