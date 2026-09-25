"""Camera feeds and the detection loop.

Each Camera thread plays its video file in real time (looping, like a live feed) and keeps a
short frame buffer. A single detection thread repeatedly takes the newest frame of every
camera and runs the models on all of them in one batch. The frame shown to viewers is
DISPLAY_DELAY seconds behind the newest one, so it can be paired with detections computed on
(nearly) the same frame.
"""
import base64
import bisect
import itertools
import json
import logging
import struct
import threading
import time
from collections import deque

import cv2

from . import config
from .detector import Detector, coverage, iou

log = logging.getLogger(__name__)


class ObjectLog:
    """Groups repeated detections of the same object into one entry for the info panel."""

    KEEP_SECONDS = 5  # an ordinary object disappears from the panel after this long unseen
    KEEP_THREAT_SECONDS = 30  # weapons stay listed longer

    def __init__(self):
        self._entries = []
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def update(self, idx, frame, dets):
        with self._lock:
            unmatched = list(self._entries)
            for d in sorted(dets, key=lambda d: -d["conf"]):
                match = max((e for e in unmatched if e["label"] == d["label"]),
                            key=lambda e: iou(e["box"], d["box"]), default=None)
                if match is not None and iou(match["box"], d["box"]) > 0.2:
                    unmatched.remove(match)
                    match["box"], match["last_idx"] = d["box"], idx
                    if d["conf"] > match["conf"]:
                        match["conf"], match["thumb"] = d["conf"], _thumbnail(frame, d["box"])
                else:
                    self._entries.append({
                        "id": next(self._ids), "label": d["label"], "conf": d["conf"],
                        "threat": d["threat"], "box": d["box"], "first_idx": idx, "last_idx": idx,
                        "thumb": _thumbnail(frame, d["box"]),
                    })
            # Drop entries long gone (relative to the newest processed frame).
            self._entries = [e for e in self._entries if idx - e["last_idx"] <= self._keep_frames(e)]

    def _keep_frames(self, e):
        return (self.KEEP_THREAT_SECONDS if e["threat"] else self.KEEP_SECONDS) * config.FEED_FPS

    def snapshot(self, display_idx):
        """Entries visible at the currently displayed frame, weapons first."""
        with self._lock:
            items = [e for e in self._entries
                     if e["first_idx"] <= display_idx and display_idx - e["last_idx"] <= self._keep_frames(e)]
            items.sort(key=lambda e: (not e["threat"], -e["conf"]))
            return [{
                "id": e["id"],
                "label": e["label"].title(),
                "confidence": round(e["conf"] * 100),
                "threat": e["threat"],
                "in_view": display_idx - e["last_idx"] <= 2 * config.FEED_FPS,
                "seconds_ago": max(0, round((display_idx - e["last_idx"]) / config.FEED_FPS)),
                "details": config.DESCRIPTIONS.get(e["label"], f"{e['label'].title()} detected in the camera feed."),
                "thumbnail": e["thumb"],
            } for e in items]


def interpolate(before, after, idx):
    """Move each box linearly from its position in `before` to its match in `after`.

    Detection only runs on some frames, so without this boxes would jump every pass and
    trail behind moving people in between.
    """
    (ia, da), (ib, db) = before, after
    t = (idx - ia) / (ib - ia)
    remaining = list(db)
    out = []
    for a in da:
        b = max((d for d in remaining if d["label"] == a["label"]),
                key=lambda d: iou(a["box"], d["box"]), default=None)
        if b is not None and iou(a["box"], b["box"]) > 0.1:
            remaining.remove(b)
            out.append({**a, "conf": a["conf"] + (b["conf"] - a["conf"]) * t,
                        "box": tuple(pa + (pb - pa) * t for pa, pb in zip(a["box"], b["box"]))})
        elif t < 0.5:  # object leaves before the next pass: keep it for the first half
            out.append(a)
    if t >= 0.5:  # new objects appear for the second half
        out.extend(remaining)
    return out


def _thumbnail(frame, box, size=160):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = box
    pad_x, pad_y = (x2 - x1) * 0.15, (y2 - y1) * 0.15
    x1, y1 = int(max(0, x1 - pad_x)), int(max(0, y1 - pad_y))
    x2, y2 = int(min(w, x2 + pad_x)), int(min(h, y2 + pad_y))
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    scale = size / max(crop.shape[:2])
    if scale < 1:
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode() if ok else None


class Camera(threading.Thread):
    def __init__(self, index, cam_id, name, path):
        super().__init__(daemon=True, name=f"cam-{cam_id}")
        self.index, self.id, self.name, self.path = index, cam_id, name, path
        self.delay_frames = int(config.DISPLAY_DELAY * config.FEED_FPS)
        self.frames = deque(maxlen=self.delay_frames + 1)  # (idx, raw frame, jpeg)
        self.latest = None  # (idx, raw frame) for the detector
        self.det_idx, self.det_lists = [], []  # detection results, sorted by frame idx
        self.objects = ObjectLog()
        self.prev_threats = []  # weapon candidates from the previous detection pass
        self.packet, self.packet_idx, self.display_idx = None, -1, -1
        self.lock = threading.Lock()

    # --- called from the detector thread ---
    def add_detections(self, idx, frame, dets):
        # Weapon false-positive filter: a hand-held weapon must sit on a person, and it must
        # also have been a candidate at the same spot on the previous pass (see config).
        persons =[d["box"] for d in dets if d["label"] == "person"]
        candidates = [d for d in dets if d["threat"] and (
            d["label"] not in config.HELD_CLASSES
            or any(coverage(d["box"], p) >= config.HELD_MIN_OVERLAP for p in persons))]
        dets = [d for d in dets if not d["threat"]] + [
            d for d in candidates if d["conf"] >= config.THREAT_CONF
            and any(p["label"] == d["label"] and iou(p["box"], d["box"]) > 0.2 for p in self.prev_threats)]
        self.prev_threats = candidates
        with self.lock:
            self.det_idx.append(idx)
            self.det_lists.append(dets)
            if len(self.det_idx) > 200:
                del self.det_idx[:100], self.det_lists[:100]
        self.objects.update(idx, frame, dets)

    def _detections_for(self, idx):
        """Detections for frame idx, interpolated between the processed frames around it."""
        max_gap = config.FEED_FPS * 3
        with self.lock:
            i = bisect.bisect_right(self.det_idx, idx)
            before = (self.det_idx[i - 1], self.det_lists[i - 1]) if i > 0 else None
            after = (self.det_idx[i], self.det_lists[i]) if i < len(self.det_idx) else None
        if before and idx - before[0] > max_gap:
            before = None
        if after and after[0] - idx > max_gap:
            after = None
        if not before or not after:
            return (before or after or (0, []))[1]
        return interpolate(before, after, idx)

    def run(self):
        cap = cv2.VideoCapture(str(self.path))
        if not cap.isOpened():
            log.error("Cannot open %s", self.path)
            return
        period = 1.0 / config.FEED_FPS
        next_t = time.monotonic()
        for idx in itertools.count():
            ok, frame = cap.read()
            if not ok:  # loop the recording so it behaves like a continuous feed
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = cap.read()
                if not ok:
                    log.error("Cannot read %s", self.path)
                    return
            if frame.shape[1] != config.FRAME_W or frame.shape[0] != config.FRAME_H:
                frame = cv2.resize(frame, (config.FRAME_W, config.FRAME_H), interpolation=cv2.INTER_AREA)
            _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY])
            self.frames.append((idx, frame, jpeg.tobytes()))
            self.latest = (idx, frame)
            self._publish()

            next_t += period
            delay = next_t - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_t = time.monotonic()  # fell behind; don't try to catch up in a burst

    def _publish(self):
        """Build the binary message for the frame that is currently on display."""
        idx, _, jpeg = self.frames[0]
        dets = self._detections_for(idx)
        meta = json.dumps({
            "idx": idx,
            "time": time.time() - config.DISPLAY_DELAY,
            "dets": [[round(d["box"][0] / config.FRAME_W, 4), round(d["box"][1] / config.FRAME_H, 4),
                      round(d["box"][2] / config.FRAME_W, 4), round(d["box"][3] / config.FRAME_H, 4),
                      d["label"].title(), round(d["conf"] * 100), int(d["threat"])] for d in dets],
        }, separators=(",", ":")).encode()
        # [uint8 camera index][uint16 meta length][meta json][jpeg]
        self.packet = struct.pack(">BH", self.index, len(meta)) + meta + jpeg
        self.packet_idx = self.display_idx = idx


class DetectionLoop(threading.Thread):
    def __init__(self, cameras):
        super().__init__(daemon=True, name="detector")
        self.cameras = cameras
        self.detector = Detector()
        self.cycle_time = 0.0

    def run(self):
        done = {}
        last_log = time.monotonic()
        while True:
            batch = [(cam, *cam.latest) for cam in self.cameras
                     if cam.latest is not None and done.get(cam.id) != cam.latest[0]]
            if not batch:
                time.sleep(0.01)
                continue
            t0 = time.monotonic()
            try:
                results = self.detector.detect([frame for _, _, frame in batch])
            except Exception:
                log.exception("Detection failed")
                time.sleep(1)
                continue
            for (cam, idx, frame), dets in zip(batch, results):
                cam.add_detections(idx, frame, dets)
                done[cam.id] = idx
            dt = time.monotonic() - t0
            self.cycle_time = dt if not self.cycle_time else 0.8 * self.cycle_time + 0.2 * dt
            if time.monotonic() - last_log > 30:
                last_log = time.monotonic()
                level = logging.WARNING if self.cycle_time * 2.2 > config.DISPLAY_DELAY else logging.INFO
                log.log(level, "Detection cycle %.2fs for %d feeds (DISPLAY_DELAY %.1fs)",
                        self.cycle_time, len(batch), config.DISPLAY_DELAY)
