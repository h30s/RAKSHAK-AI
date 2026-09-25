"""Download the demo footage and model weights.

Footage: free stock clips from Pexels (Pexels License — free to use, no attribution required).
Each clip is center-cropped to 16:9, scaled to 640x360, resampled to the feed frame rate and
trimmed, so the server only has to loop small files.

Weapon model: Subh775/Threat-Detection-YOLOv8n on Hugging Face (MIT).

Usage:  python scripts/fetch_assets.py [--force]
"""
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402

# output file -> Pexels video id (https://www.pexels.com/video/<id>/)
FOOTAGE = {
    "ground_floor_1.mp4": 5762612,   # shopping-centre ground floor, people walking
    "ground_floor_2.mp4": 4750042,   # shopping aisle with trolleys
    "first_floor_1.mp4": 854665,     # upper-level walkway
    "first_floor_2.mp4": 4750049,    # escalator up to the first floor
    "parking_1.mp4": 34765009,       # car park at night, high angle
    "parking_2.mp4": 6092110,        # man holding a rifle (gun detection test)
    "entrance_1.mp4": 30243320,      # plaza in front of a building entrance
    "entrance_2.mp4": 8094256,       # person holding a knife (knife detection test)
}
MAX_SECONDS = 30


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def transcode(src, dest):
    cap = cv2.VideoCapture(str(src))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    w, h = cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    # center crop to 16:9
    if w / h > 16 / 9:
        cw, ch = int(h * 16 / 9), int(h)
    else:
        cw, ch = int(w), int(w * 9 / 16)
    x0, y0 = int((w - cw) // 2), int((h - ch) // 2)

    out = cv2.VideoWriter(str(dest), cv2.VideoWriter_fourcc(*"mp4v"), config.FEED_FPS,
                          (config.FRAME_W, config.FRAME_H))
    written, i = 0, 0
    while written < MAX_SECONDS * config.FEED_FPS:
        ok, frame = cap.read()
        if not ok:
            break
        # keep the source frames that fall on the output frame-rate grid
        if i >= round(written * src_fps / config.FEED_FPS):
            frame = cv2.resize(frame[y0:y0 + ch, x0:x0 + cw], (config.FRAME_W, config.FRAME_H),
                               interpolation=cv2.INTER_AREA)
            out.write(frame)
            written += 1
        i += 1
    out.release()
    return written


def main():
    force = "--force" in sys.argv
    config.VIDEO_DIR.mkdir(exist_ok=True)
    config.MODEL_DIR.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        for name, pexels_id in FOOTAGE.items():
            dest = config.VIDEO_DIR / name
            if dest.exists() and not force:
                print(f"✓ {name} (exists)")
                continue
            raw = Path(tmp) / f"{pexels_id}.mp4"
            print(f"↓ {name}  ← pexels {pexels_id}")
            download(f"https://www.pexels.com/download/video/{pexels_id}/", raw)
            frames = transcode(raw, dest)
            print(f"  {frames} frames @ {config.FEED_FPS:g} fps")

    if not config.THREAT_MODEL.exists() or force:
        from huggingface_hub import hf_hub_download
        print("↓ weapon model  ← Subh775/Threat-Detection-YOLOv8n")
        shutil.copy(hf_hub_download("Subh775/Threat-Detection-YOLOv8n", "weights/best.pt"), config.THREAT_MODEL)
    general = config.MODEL_DIR / config.GENERAL_MODEL
    if not general.exists():
        from ultralytics import YOLO
        print(f"↓ {config.GENERAL_MODEL}")
        YOLO(config.GENERAL_MODEL)  # ultralytics downloads it into the working directory
        shutil.move(config.GENERAL_MODEL, general)
    print("Done.")


if __name__ == "__main__":
    main()
