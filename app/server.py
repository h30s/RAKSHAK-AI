"""FastAPI server: serves the dashboard, streams feeds over one WebSocket, exposes detected objects."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .pipeline import Camera, DetectionLoop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("cctv")

cameras: list[Camera] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    missing = [f for _, _, f in config.CAMERAS if not (config.VIDEO_DIR / f).exists()]
    if missing:
        raise RuntimeError(f"Missing videos {missing} in {config.VIDEO_DIR} — run scripts/fetch_assets.py first")
    for i, (cam_id, name, file) in enumerate(config.CAMERAS):
        cameras.append(Camera(i, cam_id, name, config.VIDEO_DIR / file))
    loop = DetectionLoop(cameras)  # loads the models before any feed starts
    for cam in cameras:
        cam.start()
    loop.start()
    log.info("Started %d cameras", len(cameras))
    yield


app = FastAPI(title="CCTV Object Detection", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(config.STATIC_DIR / "index.html")


@app.get("/api/cameras")
def list_cameras():
    return [{"index": c.index, "id": c.id, "name": c.name} for c in cameras]


@app.get("/api/cameras/{cam_id}/objects")
def camera_objects(cam_id: str):
    cam = next((c for c in cameras if c.id == cam_id), None)
    if cam is None:
        raise HTTPException(404, "Unknown camera")
    return cam.objects.snapshot(cam.display_idx)


@app.websocket("/ws")
async def stream(ws: WebSocket):
    """Pushes every camera's latest frame + detections as binary messages."""
    await ws.accept()
    sent = [-1] * len(cameras)
    try:
        while True:
            for cam in cameras:
                if cam.packet is not None and cam.packet_idx != sent[cam.index]:
                    sent[cam.index] = cam.packet_idx
                    await ws.send_bytes(cam.packet)
            await asyncio.sleep(0.5 / config.FEED_FPS)
    except (WebSocketDisconnect, RuntimeError):
        pass
