"use strict";

const COLORS = { threat: "#ff4d4f", person: "#3fb68b", other: "#f5b83d" };

const gridView = document.getElementById("grid-view");
const detailView = document.getElementById("detail-view");
const detailCanvas = document.getElementById("detail-canvas");
const detailTime = document.getElementById("detail-time");
const objectsList = document.getElementById("objects");
const objectsEmpty = document.getElementById("objects-empty");
const connEl = document.getElementById("conn");

let cameras = [];        // [{index, id, name, tile, canvas, time, badge, summary, frame}]
let selected = null;     // camera shown in the detail view
let objectsTimer = null;

// ---------- Rendering ----------

function fitCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const w = Math.round(canvas.clientWidth * dpr), h = Math.round(canvas.clientHeight * dpr);
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  return dpr;
}

function draw(canvas, frame) {
  if (!frame || !canvas.clientWidth) return;
  const dpr = fitCanvas(canvas);
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  ctx.drawImage(frame.image, 0, 0, W, H);

  const big = canvas === detailCanvas;
  const font = Math.round((big ? 14 : 11) * dpr);
  const pad = Math.round(4 * dpr);
  ctx.lineWidth = Math.max(1.5, (big ? 2.5 : 1.75) * dpr);
  ctx.font = `600 ${font}px "Segoe UI", system-ui, sans-serif`;
  ctx.textBaseline = "top";

  // Draw threats last so they sit on top.
  const dets = [...frame.dets].sort((a, b) => a[6] - b[6]);
  for (const [x1, y1, x2, y2, label, conf, threat] of dets) {
    const color = threat ? COLORS.threat : label === "Person" ? COLORS.person : COLORS.other;
    const x = x1 * W, y = y1 * H, w = (x2 - x1) * W, h = (y2 - y1) * H;
    ctx.strokeStyle = color;
    ctx.strokeRect(x, y, w, h);

    const text = `${label} ${conf}%`;
    const tw = ctx.measureText(text).width + pad * 2, th = font + pad * 1.5;
    const ty = y - th >= 0 ? y - th : y;          // above the box, or inside if at the top edge
    const tx = Math.min(x, W - tw);
    ctx.fillStyle = color;
    ctx.fillRect(tx, ty, tw, th);
    ctx.fillStyle = threat ? "#fff" : "#0d1014";
    ctx.fillText(text, tx + pad, ty + pad * 0.75);
  }
}

const fmtTime = (t) => new Date(t * 1000).toLocaleTimeString([], { hour12: false });

function updateTile(cam) {
  const { dets, time } = cam.frame;
  cam.time.textContent = fmtTime(time);
  const threats = dets.filter((d) => d[6]);
  const people = dets.filter((d) => d[4] === "Person").length;
  cam.tile.classList.toggle("threat", threats.length > 0);
  cam.badge.hidden = threats.length === 0;
  if (threats.length) cam.badge.textContent = `⚠ ${[...new Set(threats.map((d) => d[4]))].join(", ")} detected`;
  cam.summary.textContent = `${people} ${people === 1 ? "person" : "people"} · ${dets.length} objects`;
}

// ---------- Stream ----------

function connect() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => { connEl.textContent = "● Live"; connEl.className = "conn ok"; };
  ws.onclose = () => {
    connEl.textContent = "Disconnected — retrying…"; connEl.className = "conn bad";
    setTimeout(connect, 2000);
  };
  ws.onmessage = async (ev) => {
    // [uint8 camera index][uint16 meta length][meta json][jpeg]
    const view = new DataView(ev.data);
    const cam = cameras[view.getUint8(0)];
    if (!cam) return;
    const metaLen = view.getUint16(1);
    const meta = JSON.parse(new TextDecoder().decode(new Uint8Array(ev.data, 3, metaLen)));
    const inDetail = selected !== null;
    if (inDetail && cam !== selected) { cam.frame = { ...meta, image: cam.frame?.image }; return; }

    const image = await createImageBitmap(new Blob([new Uint8Array(ev.data, 3 + metaLen)], { type: "image/jpeg" }));
    cam.frame?.image?.close?.();
    cam.frame = { ...meta, image };
    if (selected === cam) {
      draw(detailCanvas, cam.frame);
      detailTime.textContent = fmtTime(meta.time);
    } else if (!selected) {
      draw(cam.canvas, cam.frame);
      updateTile(cam);
    }
  };
}

// ---------- Detail view ----------

function renderObjects(items) {
  objectsEmpty.hidden = items.length > 0;
  document.getElementById("obj-count").textContent = items.length ? `(${items.length})` : "";
  objectsList.innerHTML = "";
  for (const o of items) {
    const li = document.createElement("li");
    li.className = "obj" + (o.threat ? " threat" : "");
    const img = o.thumbnail ? document.createElement("img") : document.createElement("div");
    if (o.thumbnail) { img.src = o.thumbnail; img.alt = o.label; } else img.className = "noimg";
    const body = document.createElement("div");
    body.className = "obj-body";
    body.innerHTML = `
      <div class="obj-title"><span class="obj-name"></span><span class="obj-seen"></span></div>
      <div class="obj-conf">Confidence: <b></b></div>
      <div class="obj-details"></div>`;
    body.querySelector(".obj-name").textContent = o.label;
    body.querySelector(".obj-seen").textContent = o.in_view ? "In view" : `${o.seconds_ago}s ago`;
    body.querySelector(".obj-conf b").textContent = `${o.confidence}%`;
    body.querySelector(".obj-details").textContent = o.details;
    li.append(img, body);
    objectsList.append(li);
  }
}

async function pollObjects() {
  if (!selected) return;
  const cam = selected;
  try {
    const res = await fetch(`/api/cameras/${cam.id}/objects`);
    if (res.ok && selected === cam) renderObjects(await res.json());
  } catch { /* server restarting; next poll retries */ }
}

function openCamera(cam) {
  selected = cam;
  document.getElementById("detail-title").textContent = cam.name;
  gridView.hidden = true;
  detailView.hidden = false;
  renderObjects([]);
  draw(detailCanvas, cam.frame);
  pollObjects();
  objectsTimer = setInterval(pollObjects, 1000);
}

function closeCamera() {
  selected = null;
  clearInterval(objectsTimer);
  detailView.hidden = true;
  gridView.hidden = false;
}

function route() {
  const id = new URLSearchParams(location.hash.slice(1)).get("cam");
  const cam = cameras.find((c) => c.id === id);
  if (cam && cam !== selected) { if (selected) closeCamera(); openCamera(cam); }
  else if (!cam && selected) closeCamera();
}

// ---------- Setup ----------

async function init() {
  const list = await (await fetch("/api/cameras")).json();
  const tpl = document.getElementById("tile-template");
  cameras = list.map((c) => {
    const tile = tpl.content.firstElementChild.cloneNode(true);
    tile.querySelector(".tile-name").textContent = c.name;
    tile.setAttribute("aria-label", `Open ${c.name}`);
    tile.addEventListener("click", () => { location.hash = `cam=${c.id}`; });
    gridView.append(tile);
    return {
      ...c, tile, frame: null,
      canvas: tile.querySelector("canvas"),
      time: tile.querySelector(".feed-time"),
      badge: tile.querySelector(".alert-badge"),
      summary: tile.querySelector(".tile-summary"),
    };
  });
  document.getElementById("back").addEventListener("click", () => { location.hash = ""; });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && selected) location.hash = ""; });
  window.addEventListener("hashchange", route);
  route();
  connect();
}

setInterval(() => {
  document.getElementById("clock").textContent = new Date().toLocaleString([], { hour12: false });
}, 1000);

init();
