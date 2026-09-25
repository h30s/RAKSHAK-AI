"""Download the demo footage and model weights.

Footage: free stock clips from Pexels (Pexels License — free to use, no attribution required).
Each clip is center-cropped to 16:9, scaled to 640x360, resampled to the feed frame rate and
trimmed, so the server only has to loop small files.

Journey-tracking footage: five cameras of the MEVA dataset (https://mevadata.org, CC BY 4.0)
inside and around one school building, recorded at the same moment. The same 3-minute window is
cut from each so the feeds can be played in lockstep.

Weapon model: Subh775/Threat-Detection-YOLOv8n on Hugging Face (MIT).
Person re-identification model: OSNet-x0.25 trained on MSMT17, kaiyangzhou/osnet on Hugging Face
(MIT; the MSMT17 training data is for non-commercial research use), converted to ONNX.

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

# output file -> (MEVA recording, start second within it, crop box as fractions or None)
MEVA_URL = "https://mevadata-public-01.s3.amazonaws.com/drops-123-r13/2018-03-09/10/"
SITE_FOOTAGE = {
    # recordings starting at 10:10:01 are cut one second earlier to line up with the 10:10:00 ones
    "school_plaza.mp4": ("2018-03-09.10-10-01.10-15-01.school.G638.r13.avi", 119, (0.15, 0.25, 0.85, 0.955)),
    "school_lobby.mp4": ("2018-03-09.10-10-01.10-15-01.school.G420.r13.avi", 119, None),
    "school_stairwell.mp4": ("2018-03-09.10-10-00.10-15-00.school.G419.r13.avi", 120, None),
    "school_cafeteria.mp4": ("2018-03-09.10-10-00.10-15-00.school.G421.r13.avi", 120, None),
    "school_hallway.mp4": ("2018-03-09.10-10-00.10-15-00.school.G423.r13.avi", 120, (0.2, 0.08, 0.8, 0.685)),
}
SITE_SECONDS = 180

REID_REPO = "kaiyangzhou/osnet"
REID_FILE = ("osnet_x0_25_msmt17_combineall_256x128_amsgrad_ep150_stp60_lr0.0015_b64_fb10_softmax_"
             "labelsmooth_flip_jitter.pth")


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def transcode(src, dest, start=0, seconds=MAX_SECONDS, crop=None):
    """crop: (x0, y0, x1, y1) as fractions of the frame (should be 16:9); default center 16:9."""
    cap = cv2.VideoCapture(str(src))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    w, h = cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    if crop:
        x0, y0 = int(crop[0] * w), int(crop[1] * h)
        cw, ch = int((crop[2] - crop[0]) * w), int((crop[3] - crop[1]) * h)
    else:  # center crop to 16:9
        if w / h > 16 / 9:
            cw, ch = int(h * 16 / 9), int(h)
        else:
            cw, ch = int(w), int(w * 9 / 16)
        x0, y0 = int((w - cw) // 2), int((h - ch) // 2)
    if start:
        cap.set(cv2.CAP_PROP_POS_FRAMES, round(start * src_fps))

    out = cv2.VideoWriter(str(dest), cv2.VideoWriter_fourcc(*"mp4v"), config.FEED_FPS,
                          (config.FRAME_W, config.FRAME_H))
    written, i = 0, 0
    while written < seconds * config.FEED_FPS:
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

        for name, (recording, start, crop) in SITE_FOOTAGE.items():
            dest = config.VIDEO_DIR / name
            if dest.exists() and not force:
                print(f"✓ {name} (exists)")
                continue
            raw = Path(tmp) / recording
            print(f"↓ {name}  ← MEVA {recording}")
            download(MEVA_URL + recording, raw)
            frames = transcode(raw, dest, start, SITE_SECONDS, crop)
            raw.unlink()
            print(f"  {frames} frames @ {config.FEED_FPS:g} fps")

    if not config.REID_MODEL.exists() or force:
        from huggingface_hub import hf_hub_download
        from app.tracking.reid import export_onnx
        print(f"↓ person re-identification model  ← {REID_REPO}")
        export_onnx(hf_hub_download(REID_REPO, REID_FILE), config.REID_MODEL)
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
    # ONNX exports of both detectors: identical results, ~1.5x faster on CPU (see app/detector.py)
    from app.detector import onnx_path
    for pt, imgsz in ((general, config.GENERAL_IMGSZ), (config.THREAT_MODEL, config.THREAT_IMGSZ)):
        target = onnx_path(pt, imgsz)
        if not target.exists() or force:
            from ultralytics import YOLO
            print(f"⚙ {target.name}")
            exported = YOLO(str(pt)).export(format="onnx", imgsz=imgsz, dynamic=True, batch=16, verbose=False)
            shutil.move(exported, target)
    print("Done.")


if __name__ == "__main__":
    main()
