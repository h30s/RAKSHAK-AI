# CCTV Object Detection — prototype

A simple CCTV monitoring website: 8 camera feeds, real-time object detection on every feed,
and a detail view that lists what was detected.

```
Video files ──► Camera threads ──► Detection thread (YOLOv8n COCO + YOLOv8n weapons)
                     │                         │
                     └──── frames + boxes ◄────┘
                               │  WebSocket
                               ▼
                 Browser: 8-tile dashboard ─► click ─► large view + detected-objects panel
```

## Run

Requires Python 3.10+. Tested on a laptop CPU (no GPU).

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python scripts/fetch_assets.py    # downloads the 8 demo clips and both models (~0.7 GB download, ~15 MB kept)
uvicorn app.server:app --port 8000
```

Open http://localhost:8000.

## What it does

- **Dashboard**: 8 feeds (Ground Floor, First Floor, Parking and Entrance, two cameras each). Every
  feed shows bounding boxes with class name and confidence. People are green, other objects are
  amber and weapons are red. A tile gets a red border and a "Gun detected" badge while a weapon
  is in view.
- **Detail view**: click a tile (or open `/#cam=pk-2`). The feed opens large with live boxes.
  The side panel lists the detected objects, weapons first, each with a cropped thumbnail,
  name, confidence and a short description. `Esc` or "All cameras" goes back.

## Detection

| Model | Classes | Source |
|---|---|---|
| YOLOv8n (COCO) | person, car, handbag, knife, … 80 classes | Ultralytics |
| YOLOv8n threat model | Gun, Knife, Grenade, Explosion | [Subh775/Threat-Detection-YOLOv8n](https://huggingface.co/Subh775/Threat-Detection-YOLOv8n) (MIT) |

Both models run on every feed. On CPU a single batched pass over all 8 feeds takes ~1–1.5 s.
The displayed video is delayed by `DISPLAY_DELAY` (4 s). That way, for each displayed frame,
the detection passes just before and just after it are already done. Boxes are interpolated
between those two passes, so they follow moving people smoothly instead of jumping.

The weapon model gives confident false positives on ordinary scenes (phones, car parts,
whole-frame boxes). A weapon is only shown if all of these hold:
1. its confidence is ≥ 0.55,
2. for gun, knife and grenade, at least 30% of its box lies inside a detected person,
3. it was also a candidate at the same spot on the previous detection pass.

All thresholds are in [app/config.py](app/config.py) and can be overridden with environment variables.

## Footage

Free clips from [Pexels](https://www.pexels.com) (Pexels License). They are converted to
640×360 at 12 fps and loop like live feeds. The mapping is in
[scripts/fetch_assets.py](scripts/fetch_assets.py). Two feeds are weapon test clips:
**Parking — Camera 2** (man holding a rifle) and **Entrance — Camera 2** (person holding a knife).
Free footage of weapons in a real CCTV setting is hard to find, so these two look more like
film than surveillance footage.

To use your own footage, put `.mp4` files in `videos/` and edit `CAMERAS` in `app/config.py`.
Replacing the file reader with an RTSP URL (`cv2.VideoCapture("rtsp://…")`) turns a feed into a
real camera stream.

## Layout

```
app/config.py      cameras, model settings, thresholds
app/detector.py    runs both YOLO models on a batch of frames and merges the results
app/pipeline.py    camera playback threads, detection loop, weapon filter, box interpolation, object log
app/server.py      FastAPI: page, /api/cameras, /api/cameras/{id}/objects, /ws frame stream
static/            dashboard (plain HTML/CSS/JS, canvas rendering)
scripts/fetch_assets.py   downloads footage and model weights
```
