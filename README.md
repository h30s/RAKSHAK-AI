# CCTV Object Detection — prototype

A simple CCTV monitoring website: 13 camera feeds, real-time object and weapon detection on
every feed, and person journey tracking. Every person gets an ID (P-001, …) and the system
records where they go from camera to camera.

```
Video files ──► Camera threads ──► Detection thread (YOLOv8n COCO + YOLOv8n weapons)
                     │                    │
                     │                    ▼
                     │          Journey tracker (per-camera tracks + OSNet re-identification)
                     │                    │
                     └── frames + boxes + person IDs
                               │  WebSocket / REST
                               ▼
      Browser: Cameras tab (grid ─► large view + detected objects)
               People tab  (list/search ─► live location + journey)
```

## Run

Requires Python 3.10+. Tested on a laptop CPU (no GPU).

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python scripts/fetch_assets.py    # downloads the 13 demo clips and 3 models (~1.3 GB download, ~110 MB kept)
uvicorn app.server:app --port 8000
```

Open http://localhost:8000.

## What it does

- **Cameras tab**: two groups of feeds. *Main Building* has 8 feeds (Ground Floor, First Floor,
  Parking and Entrance, two cameras each). *School Building* has 5 synchronised cameras
  (Plaza, Lobby, Stairwell, Cafeteria, Hallway) that people walk between. Every feed shows
  bounding boxes with class name and confidence. People are green, other objects are amber and
  weapons are red. Each person box carries its Person ID in the bottom-left corner. A tile gets
  a red border and a "Gun detected" badge while a weapon is in view.
- **Camera detail**: click a tile (or open `/#cam=pk-2`). The feed opens large with live boxes.
  The side panel lists the detected objects, weapons first, each with a cropped thumbnail,
  name, confidence and a short description. Click a person in the video to open their journey.
  `Esc` or "All cameras" goes back.
- **People tab** (`/#people`, or `/#person=P-004` for one person): a searchable list of Person IDs.
  Search by ID or location (Enter on an ID jumps to it). Filter by *Active*, *Journeys* (seen in
  2+ locations) or *All*. Each row shows the current or last location and "Active" or
  "last seen … ago". Selecting a person shows:
  - status (currently detected / last seen), first-seen time and the route
    (`Plaza → Lobby → Stairwell`);
  - **Current location**: area, camera and since when, next to the live feed of that camera
    with the person highlighted in blue and everyone else dimmed;
  - **Journey**: every location in order, with camera, arrival time, time spent there and the
    time between locations.

## Detection

| Model | Classes | Source |
|---|---|---|
| YOLOv8n (COCO) | person, car, handbag, knife, … 80 classes | Ultralytics |
| YOLOv8n threat model | Gun, Knife, Grenade, Explosion | [Subh775/Threat-Detection-YOLOv8n](https://huggingface.co/Subh775/Threat-Detection-YOLOv8n) (MIT) |

Both models run on every feed, through ONNX Runtime (same results as PyTorch, about 1.5× faster
on CPU). On this laptop CPU one batched pass over all 13 feeds takes about 2 s, of which about
0.2 s is tracking. The displayed video runs a few seconds behind. That way, for each displayed frame,
the detection passes just before and just after it are already done. Boxes are interpolated
between those two passes, so they follow moving people smoothly instead of jumping. The delay
follows the measured cycle time (2.3× the cycle, 4–10 s), so it grows when the machine is busy.

The weapon model gives confident false positives on ordinary scenes (phones, car parts,
whole-frame boxes). A weapon is only shown if all of these hold:
1. its confidence is ≥ 0.55,
2. for gun, knife and grenade, at least 30% of its box lies inside a detected person, and the
   box is at most 0.75× the area of that person's box (the model sometimes labels whole
   people "Gun"),
3. it was also a candidate at the same spot on the previous detection pass, at most 1.6 s
   earlier. A new candidate is re-checked right away on the frame 1.25 s later, which is
   still in the camera's display buffer, so confirmation doesn't wait for the next full
   cycle. A weapon that is already confirmed stays shown while it keeps being detected.

All thresholds are in [app/config.py](app/config.py) and can be overridden with environment variables.

## Person journey tracking

Code: [app/tracking/](app/tracking/). The module is separate from detection. It receives each
detection pass through a callback and adds a person ID to each person box. Nothing else in the
detection pipeline changes.

1. **Within a camera**: person detections are linked from one pass to the next by predicted
   position (constant velocity, gated by the person's size). In multi-camera sites, appearance
   is combined with position. A person lost for a few seconds (occlusion, crowd) is re-attached
   by appearance.
2. **Appearance**: each person crop is converted to a 512-dimensional appearance fingerprint
   (embedding) by [OSNet-x0.25](https://huggingface.co/kaiyangzhou/osnet) (person
   re-identification, trained on MSMT17), run with ONNX Runtime at about 15 ms per crop.
3. **Across cameras**: a new track is given an existing Person ID when its appearance matches
   that person (similarity ≥ `REID_THRESHOLD` and clearly better than the next candidate), the
   person was last seen within `REID_WINDOW_S` in a camera of the same **site**, and the person
   is not currently being seen in another camera that doesn't overlap this one. Otherwise, after
   two sightings, it gets a new ID. For its first 10 s a new ID is provisional. If closer views
   then match an earlier person strongly (≥ `REID_MERGE_THRESHOLD`), the two are merged, and the
   old ID keeps working as an alias.
4. **Journey**: a move to another camera is recorded once the person has been seen there on two
   passes and the previous camera has lost them. Views that overlap (Lobby/Stairwell) therefore
   don't make the journey flicker.
5. **Timing**: the API reports journeys as of the moment currently on screen (the video is
   a few seconds behind), so the panel never shows someone arriving before the video does.

Sites and overlapping camera pairs are declared in `TRACKING_SITES` / `TRACKING_OVERLAPS` in
`app/config.py`. People are never linked between cameras of different sites. The 8 Main
Building clips are unrelated stock footage, so each of those cameras is its own site: people
there get IDs and are tracked, and are re-identified when they reappear in the same camera.

API: `GET /api/persons?status=active|moved|all&q=…`, `GET /api/persons/{id}`,
`GET /api/persons/summary`.

**Accuracy and limits.** In an offline run over the school footage, 6 of the 7 people linked
across cameras were checked by eye and were correct. The error was two people merged where the
Lobby and Stairwell views overlap. The tracker errs on the side of *not* merging: people whose
first views are small or blurry (the far end of the Hallway, the Plaza) often receive a new ID
when they enter the next camera instead of keeping their old one. Raising the resolution of the
feeds, a GPU with a larger re-identification model (OSNet-x1.0), or camera-transition
statistics would all improve this. The demo footage loops every 3 minutes. A replayed person
usually gets a new ID, and if they are re-identified, their journey jumps back to the start
location.

## Footage

Free clips from [Pexels](https://www.pexels.com) (Pexels License). They are converted to
640×360 at 12 fps and loop like live feeds. The mapping is in
[scripts/fetch_assets.py](scripts/fetch_assets.py). Two feeds are weapon test clips:
**Parking — Camera 2** (man holding a rifle) and **Entrance — Camera 2** (person holding a knife).
Free footage of weapons in a real CCTV setting is hard to find, so these two look more like
film than surveillance footage.

The **School Building** feeds come from the [MEVA dataset](https://mevadata.org)
(CC BY 4.0). This is real CCTV from a training facility: five cameras recorded simultaneously on
9 March 2018, 10:12–10:15. People cross the plaza, enter through the lobby doors, take the stairs
and go to the cafeteria. The same 3-minute window is cut from each recording, and the five feeds
play in lockstep (`app/tracking/feeds.py`), so a person leaving one view appears in the next at
the right moment. The slot was chosen with MEVA's activity annotations ("person enters/exits
scene"): it has the most traffic between these cameras.

To use your own footage, put `.mp4` files in `videos/` and edit `CAMERAS` in `app/config.py`.
Replacing the file reader with an RTSP URL (`cv2.VideoCapture("rtsp://…")`) turns a feed into a
real camera stream.

## Layout

```
app/config.py      cameras, model settings, thresholds (tracking settings at the end)
app/detector.py    runs both YOLO models on a batch of frames and merges the results
app/pipeline.py    camera playback threads, detection loop, weapon filter, box interpolation, object log
app/server.py      FastAPI: page, /api/cameras, /api/cameras/{id}/objects, /ws frame stream
app/tracking/      person journey tracking
  tracker.py       per-camera tracks, cross-camera re-identification, journeys
  reid.py          OSNet appearance embeddings (ONNX Runtime) + ONNX export
  osnet.py         OSNet network definition (from torchreid, MIT)
  feeds.py         lockstep playback for cameras of one site
  api.py           /api/persons endpoints
static/            dashboard (plain HTML/CSS/JS, canvas rendering)
scripts/fetch_assets.py   downloads footage and model weights
```
