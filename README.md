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
      Browser: Overview tab (threat score, camera status, alerts + alarm, actions) ─► /reports
               Cameras tab (grid ─► large view + detected objects)
               People tab  (list/search ─► live location + journey)
               Camera Sources tab (webcam / USB camera / phone ──► frames sent into the same pipeline)
               /modes      (detection modes: night, thermal, fog, rain & snow)
```

## Run

Requires Python 3.10+. Tested on a laptop CPU (no GPU).

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python scripts/fetch_assets.py    # downloads the 23 demo clips and 3 models (~1.4 GB download, ~150 MB kept)
uvicorn app.server:app --port 8000
```

Open http://localhost:8000. It opens on the **Overview**; the live camera grid is the **Cameras** tab.

## What it does

- **Overview tab** (the start page): threat score, active threats, camera status, alerts with
  an alarm sound, and actions. See *Threat monitoring* below. **Reports** (`/reports`) has the full history.
- **Cameras tab** (`/#cameras`): two groups of feeds. *Main Building* has 8 feeds (Ground Floor, First Floor,
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
- **Camera Sources tab** (`/#sources`): connect a laptop webcam, a USB camera or a phone and run
  live detection on it. See below.
- **Detection modes** (`/modes`, "View Detection Modes" in the header): a separate page showing
  the same detection pipeline on footage recorded in different conditions. See below.

## Threat monitoring

The **Overview** tab answers five questions at a glance: are the cameras working, is there an
active threat, where is it, how serious is it, and is someone already handling it.

- **Summary cards**: overall threat score (0–100 with Low / Medium / High), active threats (with
  in-progress and resolved counts), cameras online and camera issues.
- **Alert banner**: the most serious threat nobody has taken on yet, with its camera, location,
  time and level, plus the actions.
- **Cameras**: every camera with its area, status (🟢 Online, 🟡 Signal problem, 🔴 Offline, with
  the reason), threat level, latest threat and last activity. They are sorted by risk; click one to watch it.
- **Recent alerts**, **threat level by camera**, **high-risk areas** and **recent activity**
  (detections, actions and camera problems).
- **Header**: system status ("All clear" / "2 active threats" / "1 camera issue"), the bell with the
  number of open threats, and the alarm sound on/off switch.

**Where threats come from.** `app/threats/monitor.py` reads what the detection pipeline
already produced: the confirmed weapons in each camera's object log, taken at the frame on screen,
so an alert never appears before the video shows the weapon. A new weapon opens an **incident**.
Further sightings of the same kind of weapon on that camera are added to the open incident, so a
weapon that stays in view raises one alert, not one per frame. The same weapon seen within 2 minutes
of its incident being resolved is noted on that incident instead of raising a new alarm
(`RESOLVED_QUIET_S`). Each incident stores a snapshot of the frame with the weapon boxed.

**Alerts.** A new incident shows a notification on every tab. A new *High* one also plays an
alarm, a tone generated in the browser, so no audio file is needed. Browsers only allow sound after
the user has clicked on the page once; until then the notification says so and the speaker icon
turns amber.

**Actions.** Every open threat has **Working on it** (🟡 In progress) and **Mark as resolved**
(🟢 Resolved); a resolved one can be reopened. The details view (click any alert) shows the type,
camera, location, time, score, status and snapshot, and a timeline of actions. An optional note can
be saved with an action or on its own, e.g. "guard sent to the entrance".

**Scores.** An incident's score is its weapon's severity (explosion 100, grenade 95, gun 90,
knife 80) × (0.75 + 0.25 × detection confidence). A camera's score is its highest open threat; a
threat in progress counts at 75%. The overall score is the highest camera score + 5 per extra open
threat. High ≥ 70, Medium ≥ 40, otherwise Low. An area (the part of the camera name before "—")
is at risk while it has an open threat, and is listed as Low for an hour after an incident.

**Camera health.** 🟡 Signal problem: no new frame for 5 s, a live source that is connected but
sends no video, or frames arriving but not analysed (detection stalled). 🔴 Offline: no frame for
15 s, or a live source that disconnected (shown for 10 minutes). Unused live source slots are not
listed.

**Reports** (`/reports`): every incident with date and time, camera, location, type, score, status,
the last action taken and when it was resolved (and how long it took). Search, filter by status
and period, open details, and **Export CSV**. Incidents and snapshots are saved in `data/` and survive
restarts.

With the demo footage, **Parking — Camera 2** (rifle) and **Entrance — Camera 2** (knife) raise
threats within a minute of starting. The other recorded feeds never go offline; to see a camera
problem, connect a phone in Camera Sources and then close its page.

API: `GET /api/threats/overview`, `GET /api/threats?status=&q=&days=`, `GET /api/threats/{id}`,
`GET /api/threats/{id}/snapshot.jpg`, `POST /api/threats/{id}/status` (`{"status": "in_progress" |
"resolved" | "active", "note": "..."}`), `POST /api/threats/{id}/note`, `GET /api/threats/export.csv`.

## Camera sources

The **Camera Sources** tab connects live cameras:

| Source | How it connects |
|---|---|
| Laptop Webcam | pick a camera in the list and press Connect (the browser asks for permission once) |
| USB / External Camera | USB webcams appear in the same kind of list when plugged in. An Android 14+ phone connected by cable with its USB mode set to **Webcam** appears there too |
| Mobile Camera via QR | scan the QR code with the phone (same Wi-Fi), accept the certificate warning once, tap **Start camera** |
| Mobile Camera via USB cable | Android with USB debugging on, plugged in with a data cable: **Via USB cable** runs `adb reverse` and opens the camera page on the phone (needs Android platform-tools). If the phone isn't found, the card shows the steps to enable USB debugging |

**One pipeline.** A source is not processed separately. The browser (or phone) sends JPEG frames
over a WebSocket (`static/capture.js`) to a `LiveCamera` (`app/sources/feeds.py`), which is an
ordinary dashboard camera. It plays the newest frame at the feed frame rate, so the same
`DetectionLoop`, weapon filter, re-check, object log, person IDs and alerts apply. Connected
sources show up on the Cameras tab under **Live Sources**. A weapon gives the same red tile
border and "Knife detected" badge as any feed, and weapons are listed first in the panel. The
Sources tab shows the processed feed of the selected source with the same alert.

**Switching.** Picking another camera in a card's list switches that source to it. A second
device connecting to a source takes it over (the first one is told it was replaced). Disconnect
stops a source; nothing needs a restart. Idle sources cost nothing, and each connected source
adds one feed to the detection batch.

**Phones need HTTPS.** Mobile browsers only allow camera access on secure pages, so the server
also listens on `https://<this computer's LAN IP>:8443` (`PHONE_PORT`), using a self-signed
certificate created in `certs/`. That listener only serves the phone page and the upload stream.
The dashboard stays on localhost. Uploads from the network must carry the pairing token that is
in the QR code (a new one every server start). Notes:
- the phone must be on the same network. On first start Windows asks whether Python may accept
  connections; allow it for private networks, or the phone can't reach the page;
- if the detected LAN address is wrong (VPNs, several adapters), set `PHONE_HOST`;
- iPhones can't be used as a USB camera on Windows; use the QR code.

Like every feed, the video is shown a few seconds behind live (the display delay), so the boxes
line up with the frames they were detected on. The Sources tab shows how far behind it is.
Frames are sent on a Web Worker timer, so a webcam keeps streaming while the dashboard tab is in
the background.

API: `GET /api/sources`, `GET /api/sources/qr.svg`, `POST /api/sources/{id}/disconnect`,
`POST /api/sources/usb-phone`, WebSocket `/ws/sources/{id}/publish` (binary JPEG frames), page
`/phone`.

## Detection modes

The `/modes` page has one card per condition. Selecting a card shows that condition's footage
with live detection boxes, next to a short description of what makes it hard, live counts
(people, vehicles, weapons, average confidence) and the detected-objects list.

| Mode | Footage | What makes it hard |
|---|---|---|
| Normal | city crossing from above, street corner (daylight) | crowds, occlusion |
| Night | night market, dark street | low light, glare, noise |
| Thermal | two views of a transit shelter from a **real thermal surveillance camera** (MEVA) | no colour, low resolution, small people |
| Fog | foggy square at night, misty park | washed-out contrast, silhouettes |
| Rain & Snow | rainy night street, snowfall | rain and snow noise, reflections |

Each mode has two clips (switch with the buttons above the video). None of them is used
anywhere else in the app. They run through the same `DetectionLoop`, weapon filter and object
log as the dashboard cameras, with nothing tuned per mode, so what you see is how the system
really copes with each condition.

The clips are not dashboard cameras: they are not in `/ws`, `/api/cameras` or journey tracking.
A clip only plays, and is only analysed, while someone watches it
(`app/modes/feeds.py`). Watching one adds one feed to the detection batch (~7% more detection
work); with the page closed or in a background tab it costs nothing. Each time a clip is opened
it restarts from the beginning, and the page shows "Starting live analysis…" for the few seconds
the display delay needs.

Measured on the clips (a detection pass every 2 s): ~7 people per pass by day, ~6 in the night
market, ~3 in the thermal views, 1–3 in fog, 2–6 in rain and snow. Replaying all clips through
the weapon filter at three timings gave no weapon alerts. The weapon model does fire on some of
them (e.g. "explosion" on snow spray behind cars), but not twice in the same place, so the
filter rejects it.

API: `GET /api/modes` (modes and clips), `GET /api/modes/clips/{id}/objects`,
`GET /api/modes/clips/{id}/poster.jpg`, WebSocket `/ws/modes/{id}` (same binary frames as `/ws`).

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

The **Detection modes** footage is 8 Pexels clips (night, fog, rain, snow and two daylight
clips) plus two recordings of MEVA's thermal infrared camera G476 (7 March 2018, a transit
shelter). The thermal camera is only 352×240, so its clips are cropped to where people walk,
which makes them large enough to detect.

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
app/threats/       threat monitoring (Overview tab, /reports)
  store.py         incidents, actions, scores; saved in data/threats.json
  monitor.py       camera health, weapons -> incidents, the Overview data
  api.py           /api/threats endpoints and the /reports page
app/sources/       camera sources (webcam, USB camera, phone)
  feeds.py         LiveCamera: a dashboard camera fed by a device's frames
  api.py           /api/sources, the upload stream, the HTTPS listener for phones
  network.py       LAN address, self-signed certificate, pairing token, adb (phone over USB)
app/modes/         detection modes page
  feeds.py         clips that only play while watched
  api.py           /api/modes endpoints and the /ws/modes/{id} stream
static/            dashboard and modes page (plain HTML/CSS/JS, canvas rendering)
scripts/fetch_assets.py   downloads footage and model weights
```
