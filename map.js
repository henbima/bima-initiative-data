import { spatialGrid } from "./detail.js";
const changeKeys = [
  ["Beralih dari pohon", "#d35d38"],
  ["Beralih menjadi pohon", "#007b67"],
  ["Tetap pohon", "#759574"],
  ["Kelas lain", "#d7d3b9"],
  ["Tak terbaca", "#b3b6b2"],
];
function bitmap(uri) {
  return new Promise((ok, fail) => {
    const image = new Image();
    image.onload = () => ok(image);
    image.onerror = () => fail(new Error("Gambar gagal dimuat"));
    image.src = uri;
  });
}
function plane(w, h) {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return c;
}
function lookupColor(hex) {
  return [1, 3, 5].map((k) => parseInt(hex.slice(k, k + 2), 16));
}
const changeColors = changeKeys.map((row) => lookupColor(row[1]));
function nativePlane(im, w, h) {
  const stripe = plane(w, Math.min(h, 120)),
    g = stripe.getContext("2d", { willReadFrequently: true });
  const out = new Uint8Array(w * h);
  for (let j = 0; j < h; j += 120) {
    const n = Math.min(120, h - j);
    g.drawImage(im, 0, j, w, n, 0, 0, w, n);
    const d = g.getImageData(0, 0, w, n).data;
    for (let i = 0; i < w * n; i++) out[j * w + i] = d[i * 4];
  }
  return out;
}
export async function createMap(cfg, json, getImage, profile) {
  const colors = Object.fromEntries(
    Object.entries(profile.colors).map(([id, c]) => [id, lookupColor(c)]),
  );
  const valid = new Set(cfg.validClasses),
    forest = new Set(cfg.forestClasses ?? [2]);
  const className = (n) => profile.names[n] ?? "Tak terbaca";
  const keysChange = changeKeys.map(([n, c]) => [
    n.replace("pohon", profile.short),
    c,
  ]);
  const references = await json("petak.json");
  let photos = null,
    photoLoad = null;
  let grid = [],
    selected = null,
    full = [],
    tileCache = new Map();
  const canvas = document.querySelector("#map"),
    ctx = canvas.getContext("2d"),
    frame = document.querySelector("#frame"),
    legend = document.querySelector("#legend"),
    pin = document.querySelector("#pin");
  const [geo, terrain, relief] = await Promise.all([
    json("geo.json"),
    json("terrain.json"),
    bitmap("terrain.jpg"),
  ]);
  const [sx, , west, , , north] = cfg.transform,
    w = cfg.width,
    h = cfg.height;
  const ratio = Math.min(1, 1500 / Math.max(w, h)),
    rw = Math.ceil(w * ratio),
    rh = Math.ceil(h * ratio);
  const maskCanvas = plane(rw, rh),
    mc = maskCanvas.getContext("2d", { willReadFrequently: true });
  mc.imageSmoothingEnabled = false;
  const nativeMask = await getImage(cfg.mask),
    fullMask = nativePlane(nativeMask, w, h);
  mc.drawImage(nativeMask, 0, 0, rw, rh);
  const mask = mc.getImageData(0, 0, rw, rh).data;
  let years = [],
    rasters = [],
    paint = [],
    mode = "change",
    divider = 0.5,
    zoom = 1,
    ox = 0,
    oy = 0,
    token = 0;
  let width = 0,
    height = 0,
    base = 1,
    renderQueued = false;
  function screen(u, v) {
    return [
      width / 2 + ox + (u - w / 2) * base * zoom,
      height / 2 + oy + (v - h / 2) * base * zoom,
    ];
  }
  function rasterXY(x, y) {
    return [(x - west) / sx, (north - y) / sx];
  }
  function draw() {
    renderQueued = false;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const rect = frame.getBoundingClientRect();
    width = rect.width;
    height = rect.height;
    if (!width || !height) return;
    if (
      canvas.width !== Math.round(width * dpr) ||
      canvas.height !== Math.round(height * dpr)
    ) {
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = "#e3e8de";
    ctx.fillRect(0, 0, width, height);
    base = Math.min((width - 45) / w, (height - 45) / h);
    const size = base * zoom,
      k = screen(0, 0);
    ctx.save();
    ctx.translate(...k);
    ctx.scale(size, size);
    const [tw, ts, te, tn] = terrain.bounds;
    const [tx, ty] = rasterXY(tw, tn);
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(relief, tx, ty, (te - tw) / sx, (tn - ts) / sx);
    function overlay(i) {
      if (paint[i]) {
        ctx.imageSmoothingEnabled = false;
        ctx.globalAlpha = mode === "change" ? 0.84 : 0.83;
        if (zoom < 3 || ratio === 1) ctx.drawImage(paint[i], 0, 0, w, h);
        else {
          const colStart = Math.max(0, Math.floor(-k[0] / size / 256)),
            colEnd = Math.min(
              Math.ceil(w / 256),
              Math.ceil((width - k[0]) / size / 256),
            );
          const rowStart = Math.max(0, Math.floor(-k[1] / size / 256)),
            rowEnd = Math.min(
              Math.ceil(h / 256),
              Math.ceil((height - k[1]) / size / 256),
            );
          for (let ty = rowStart; ty < rowEnd; ty++)
            for (let tx = colStart; tx < colEnd; tx++)
              ctx.drawImage(tile(i, tx, ty), tx * 256, ty * 256);
        }
        ctx.globalAlpha = 1;
      }
    }
    if (mode === "photos") {
      if (photos) {
        const [u, v] = rasterXY(688190, 9071330);
        const paintPhoto = (im) =>
          ctx.drawImage(im, u, v, 22820 / sx, 25560 / sx);
        ctx.imageSmoothingEnabled = zoom < 4;
        paintPhoto(photos[0]);
        ctx.save();
        ctx.beginPath();
        ctx.rect((width * divider - k[0]) / size, -1e7, 1e7, 2e7);
        ctx.clip();
        paintPhoto(photos[1]);
        ctx.restore();
      }
    } else if (mode === "change") overlay(0);
    else {
      overlay(1);
      ctx.save();
      ctx.beginPath();
      ctx.rect((width * divider - k[0]) / size, -1e7, 1e7, 2e7);
      ctx.clip();
      overlay(2);
      ctx.restore();
    }
    ctx.strokeStyle = "#2c513e";
    ctx.lineWidth = 1.35 / size;
    for (const ring of geo.rings) {
      ctx.beginPath();
      ring.forEach(([x, y], i) => {
        const p = rasterXY(x, y);
        i ? ctx.lineTo(...p) : ctx.moveTo(...p);
      });
      ctx.closePath();
      ctx.stroke();
    }
    if (selected) {
      const [x, y] = rasterXY(selected.west, selected.south + 1000);
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 5 / size;
      ctx.strokeRect(x, y, 1000 / sx, 1000 / sx);
      ctx.strokeStyle = "#3a2538";
      ctx.lineWidth = 2.5 / size;
      ctx.strokeRect(x, y, 1000 / sx, 1000 / sx);
    }
    ctx.restore();
    ctx.lineJoin = "round";
    ctx.font = '600 12px "Segoe UI",sans-serif';
    ctx.textBaseline = "middle";
    const boxes = [];
    for (const p of geo.labels) {
      const [x, y] = screen(...rasterXY(...p.xy)),
        tw = ctx.measureText(p.name).width,
        box = [x + 4, y - 8, x + 8 + tw, y + 8];
      if (
        boxes.some(
          (b) =>
            box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1],
        )
      )
        continue;
      boxes.push(box);
      ctx.beginPath();
      ctx.arc(x, y, 2.4, 0, Math.PI * 2);
      ctx.fillStyle = "#233f37";
      ctx.fill();
      ctx.lineWidth = 3.5;
      ctx.strokeStyle = "#fffcf0";
      ctx.strokeText(p.name, x + 5, y);
      ctx.fillText(p.name, x + 5, y);
    }
    if (mode === "swipe" || mode === "photos") {
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(width * divider, 0);
      ctx.lineTo(width * divider, height);
      ctx.stroke();
      ctx.fillStyle = "#234b40";
      ctx.beginPath();
      ctx.arc(width * divider, height * 0.55, 14, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "#fff";
      ctx.textAlign = "center";
      ctx.fillText("↔", width * divider, height * 0.55);
      ctx.textAlign = "left";
    }
    const km =
      [0.1, 0.2, 0.5, 1, 2, 5, 10]
        .filter((v) => ((v * 1000) / sx) * size <= 100)
        .pop() || 0.1;
    const bar = document.querySelector("#scale");
    bar.style.width = ((km * 1000) / sx) * size + "px";
    bar.textContent = km < 1 ? km * 1000 + " m" : km + " km";
  }
  function schedule() {
    if (!renderQueued) {
      renderQueued = true;
      requestAnimationFrame(draw);
    }
  }
  function setMode(value) {
    mode = value;
    document
      .querySelector("#change")
      .setAttribute("aria-pressed", String(mode === "change"));
    document
      .querySelector("#swipe")
      .setAttribute("aria-pressed", String(mode === "swipe"));
    const showingPhoto = mode === "photos";
    document
      .querySelector("#photos")
      .setAttribute("aria-pressed", String(showingPhoto));
    document.querySelector("#dragbar").hidden = mode === "change";
    document.querySelector("#stamp").textContent = showingPhoto
      ? "SENTINEL-2 · WARNA ALAMI"
      : "DAS RONTU · " + sx + " M";
    document.querySelector("#yl").textContent = showingPhoto
      ? "17 Sep 2017"
      : (years[0] ?? "");
    document.querySelector("#yr").textContent = showingPhoto
      ? "31 Agu 2025"
      : (years[1] ?? "");
    if (showingPhoto) {
      legend.textContent = photos
        ? "Citra 10 m · kiri 17 September 2017, kanan 31 Agustus 2025. Tanggal foto tetap."
        : "Memuat dua citra Sentinel-2.";
      if (!photoLoad)
        photoLoad = Promise.all([
          bitmap("optik/before.jpg"),
          bitmap("optik/after.jpg"),
        ])
          .then((ims) => {
            photos = ims;
            if (mode === "photos") setMode("photos");
          })
          .catch(() => {
            photoLoad = null;
            if (mode === "photos")
              legend.textContent =
                "Citra gagal dimuat. Tekan Citra asli untuk mencoba lagi.";
          });
      schedule();
      return;
    }
    const keys = mode === "change" ? keysChange : profile.legend;
    legend.replaceChildren(
      ...keys.map(([label, color]) => {
        const s = document.createElement("span"),
          i = document.createElement("i");
        i.style.background = color;
        s.append(i, label);
        return s;
      }),
    );
    schedule();
  }
  function paintPixel(out, i, a, b, layer, x, y) {
    const missing = !valid.has(a) || !valid.has(b);
    const cls = missing
      ? 4
      : forest.has(a)
        ? forest.has(b)
          ? 2
          : 0
        : forest.has(b)
          ? 1
          : 3;
    const code = layer === 1 ? a : b;
    const color = layer === 0 ? changeColors[cls] : colors[code] || colors[0];
    const hatch =
      (layer === 0 ? missing : !valid.has(code)) && (x + y) % 9 < 3 ? 52 : 0;
    out[i] = color[0] - hatch;
    out[i + 1] = color[1] - hatch;
    out[i + 2] = color[2] - hatch;
    out[i + 3] = layer === 0 && cls > 1 ? 155 : 240;
  }
  function tile(layer, tx, ty) {
    const key = layer + "-" + tx + "-" + ty;
    if (tileCache.has(key)) return tileCache.get(key);
    const x = tx * 256,
      y = ty * 256,
      tw = Math.min(256, w - x),
      th = Math.min(256, h - y);
    const c = plane(tw, th),
      g = c.getContext("2d"),
      pixels = g.createImageData(tw, th);
    for (let j = 0; j < th; j++)
      for (let i = 0; i < tw; i++) {
        const z = (j + y) * w + x + i;
        if (fullMask[z])
          paintPixel(
            pixels.data,
            (j * tw + i) * 4,
            full[0][z],
            full[1][z],
            layer,
            x + i,
            y + j,
          );
      }
    g.putImageData(pixels, 0, 0);
    tileCache.set(key, c);
    if (tileCache.size > 80) tileCache.delete(tileCache.keys().next().value);
    return c;
  }
  async function setYears(a, b) {
    const revision = ++token;
    const images = await Promise.all([getImage(a.file), getImage(b.file)]);
    if (token !== revision) return false;
    const samples = images.map((im) => {
      const c = plane(rw, rh),
        g = c.getContext("2d", { willReadFrequently: true });
      g.imageSmoothingEnabled = false;
      g.drawImage(im, 0, 0, rw, rh);
      return g.getImageData(0, 0, rw, rh).data;
    });
    const layers = [0, 1, 2].map(() => plane(rw, rh)),
      pixels = layers.map((c) => c.getContext("2d").createImageData(rw, rh));
    for (let i = 0; i < mask.length; i += 4) {
      if (!mask[i]) continue;
      for (let j = 0; j < 3; j++)
        paintPixel(
          pixels[j].data,
          i,
          samples[0][i],
          samples[1][i],
          j,
          (i / 4) % rw,
          Math.floor(i / 4 / rw),
        );
    }
    full = images.map((im) => nativePlane(im, w, h));
    grid = spatialGrid(full[0], full[1], fullMask, cfg, references);
    tileCache.clear();
    selected = null;
    layers.forEach((c, i) => c.getContext("2d").putImageData(pixels[i], 0, 0));
    years = [a.year, b.year];
    rasters = images;
    paint = layers;
    pin.hidden = true;
    if (mode !== "photos") {
      document.querySelector("#yl").textContent = a.year;
      document.querySelector("#yr").textContent = b.year;
    }
    schedule();
    return true;
  }
  function magnify(factor, x = width / 2, y = height / 2) {
    let z = Math.max(0.75, Math.min(14, zoom * factor)),
      r = z / zoom;
    ox = (ox + width / 2 - x) * r + x - width / 2;
    oy = (oy + height / 2 - y) * r + y - height / 2;
    zoom = z;
    pin.hidden = true;
    schedule();
  }
  document.querySelector("#plus").onclick = () => magnify(1.5);
  document.querySelector("#minus").onclick = () => magnify(1 / 1.5);
  document.querySelector("#fit").onclick = () => {
    zoom = 1;
    selected = null;
    const share = document.querySelector("#mapShare");
    if (share.href) {
      const u = new URL(share.href);
      u.searchParams.delete("petak");
      share.href = u.href;
    }
    ox = oy = 0;
    pin.hidden = true;
    schedule();
  };
  document.querySelector("#change").onclick = () => setMode("change");
  document.querySelector("#photos").onclick = () => setMode("photos");
  document.querySelector("#seePhotos").onclick = () => {
    setMode("photos");
    frame.scrollIntoView({ behavior: "smooth", block: "center" });
  };
  document.querySelector("#swipe").onclick = () => setMode("swipe");
  const slider = document.querySelector("#divider");
  function slide(v) {
    divider = Math.max(0.02, Math.min(0.98, v));
    slider.value = Math.round(divider * 100);
    schedule();
  }
  slider.oninput = () => slide(slider.value / 100);
  const one = plane(1, 1).getContext("2d", { willReadFrequently: true });
  function value(im, i, j) {
    one.clearRect(0, 0, 1, 1);
    one.drawImage(im, i, j, 1, 1, 0, 0, 1, 1);
    return one.getImageData(0, 0, 1, 1).data[0];
  }

  function pick(x, y) {
    if (!rasters.length) return;
    const [x0, y0] = screen(0, 0),
      i = Math.floor((x - x0) / (base * zoom)),
      j = Math.floor((y - y0) / (base * zoom));
    pin.hidden = false;
    if (i < 0 || j < 0 || i >= w || j >= h || !value(nativeMask, i, j)) {
      pin.textContent = "Di luar batas analisis";
      return;
    }
    pin.textContent =
      (mode === "photos" ? "Klasifikasi tahunan · " : "") +
      years
        .map((year, n) => year + " · " + className(value(rasters[n], i, j)))
        .join("  /  ");
  }
  let drag = null;
  canvas.onpointerdown = (e) => {
    if (drag) return;
    const r = canvas.getBoundingClientRect();
    drag = {
      id: e.pointerId,
      x: e.clientX,
      y: e.clientY,
      ox,
      oy,
      divider:
        mode !== "change" &&
        Math.abs(e.clientX - r.left - width * divider) < 18,
    };
    canvas.setPointerCapture(e.pointerId);
  };
  canvas.onpointermove = (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const r = canvas.getBoundingClientRect();
    if (drag.divider) {
      slide((e.clientX - r.left) / width);
      return;
    }
    ox = drag.ox + e.clientX - drag.x;
    oy = drag.oy + e.clientY - drag.y;
    pin.hidden = true;
    schedule();
  };
  canvas.onpointerup = (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const r = canvas.getBoundingClientRect();
    if (!drag.divider && Math.hypot(e.clientX - drag.x, e.clientY - drag.y) < 5)
      pick(e.clientX - r.left, e.clientY - r.top);
    drag = null;
  };
  canvas.onpointercancel = () => (drag = null);
  canvas.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      const r = canvas.getBoundingClientRect();
      magnify(
        e.deltaY < 0 ? 1.16 : 0.862,
        e.clientX - r.left,
        e.clientY - r.top,
      );
    },
    { passive: false },
  );
  canvas.onkeydown = (e) => {
    const moves = {
      ArrowLeft: [45, 0],
      ArrowRight: [-45, 0],
      ArrowUp: [0, 45],
      ArrowDown: [0, -45],
    };
    if (moves[e.key]) {
      e.preventDefault();
      ox += moves[e.key][0];
      oy += moves[e.key][1];
      schedule();
    } else if (e.key === "+" || e.key === "=") magnify(1.5);
    else if (e.key === "-") magnify(1 / 1.5);
  };
  new ResizeObserver(schedule).observe(frame);
  setMode("change");
  function focus(g) {
    if (!width || !height) draw();
    selected = g;
    zoom = 5;
    const [x, y] = rasterXY(g.west + 500, g.south + 500);
    ox = -(x - w / 2) * base * zoom;
    oy = -(y - h / 2) * base * zoom;
    pin.textContent =
      "Petak " +
      g.id +
      " · " +
      g.reference +
      " · " +
      (g.loss * cfg.pixelHa).toLocaleString("id-ID", {
        maximumFractionDigits: 2,
      }) +
      " ha keluar" +
      (g.lat != null ? " · " + g.lat.toFixed(5) + ", " + g.lon.toFixed(5) : "");
    pin.hidden = false;
    schedule();
  }
  return {
    setYears,
    schedule,
    focus,
    get grid() {
      return grid;
    },
  };
}
