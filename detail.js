const nfmt = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 });
const fmt = (n) => nfmt.format(n);
const $ = (id) => document.getElementById(id);
function el(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}
export function table(head, rows) {
  const t = el("table");
  const h = t.createTHead().insertRow();
  for (const k of head) {
    const th = el("th", k);
    th.scope = "col";
    h.append(th);
  }
  const b = t.createTBody();
  for (const cells of rows) {
    const r = b.insertRow();
    for (const x of cells) {
      const cell = r.insertCell();
      if (x instanceof Node) cell.append(x);
      else cell.textContent = x;
    }
  }
  return t;
}
export function fileCSV(name, rows) {
  const lines = rows
    .map((r) =>
      r.map((v) => '"' + String(v).replaceAll('"', '""') + '"').join(","),
    )
    .join("\r\n");
  const u = URL.createObjectURL(
    new Blob(["\uFEFF" + lines], { type: "text/csv;charset=utf-8" }),
  );
  const a = el("a");
  a.href = u;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(u), 2000);
}
function timeline(cfg, rows, first, last, selectPair) {
  const years = cfg.years.map((y) => y.year),
    ha = cfg.pixelHa,
    intervals = [];
  for (let i = 1; i < years.length; i++) {
    const a = years[i - 1],
      b = years[i];
    const r = rows[a + "-" + b];
    intervals.push({
      a,
      b,
      delta: r.netPixels * ha,
      rate: (r.netPixels * ha) / (b - a),
    });
  }
  const subset = intervals.filter((v) => v.a >= first && v.b <= last);
  const steep = [...subset].sort((a, b) => a.rate - b.rate)[0];
  $("intervalNote").textContent =
    steep?.rate < 0
      ? "Penurunan bersih terbesar per tahun dalam periode pilihan teramati antara " +
        steep.a +
        " dan " +
        steep.b +
        ", rata-rata " +
        fmt(-steep.rate) +
        " ha/tahun."
      : "Tidak ada interval dengan penurunan bersih pada periode pilihan.";
  const full = [
    [
      "tahun",
      "luas_kelas_ha",
      "cakupan_valid_ha",
      "awal_interval",
      "perubahan_bersih_interval_ha",
    ],
  ];
  const body = years.map((y, i) => {
    const r = rows[y + "-" + y],
      d = i ? intervals[i - 1] : null;
    const select = el("button", d ? d.a + "–" + d.b : "—", "textbutton");
    select.type = "button";
    select.disabled = !d;
    select.onclick = () => selectPair(d.a, d.b);
    full.push([
      y,
      (r.treeBeforePixels * ha).toFixed(2),
      (r.validPixels * ha).toFixed(2),
      d?.a || "",
      d ? d.delta.toFixed(2) : "",
    ]);
    return [
      y,
      fmt(r.treeBeforePixels * ha),
      d ? (d.delta > 0 ? "+" : "") + fmt(d.delta) : "—",
      select,
    ];
  });
  $("yearTable").replaceChildren(
    table(["Tahun", "Luas (ha)", "Δ interval (ha)", "Lihat peta"], body),
  );
  $("yearCSV").onclick = () =>
    fileCSV("Rontu-" + cfg.seriesId + "-tahunan.csv", full);
}
export function showDetails(cfg, rows, a, b, profile, grid, focus, selectPair) {
  const r = rows[a + "-" + b],
    trees = new Set(cfg.forestClasses ?? [2]),
    name = (k) => profile.names[k] ?? "Kelas " + k,
    area = (p) => fmt(p * cfg.pixelHa) + " ha";
  const losses = {},
    gains = {};
  for (const [x, y, count] of r.transitions) {
    if (trees.has(x) && !trees.has(y)) losses[y] = (losses[y] || 0) + count;
    if (!trees.has(x) && trees.has(y)) gains[x] = (gains[x] || 0) + count;
  }
  const order = (obj) => Object.entries(obj).sort((a, b) => b[1] - a[1]);
  const loss = order(losses),
    gain = order(gains);
  $("detailTitle").textContent = "Perubahan " + a + "–" + b;
  const delta = r.netPixels * cfg.pixelHa;
  $("finding").textContent =
    profile.metric +
    " berubah dari " +
    area(r.treeBeforePixels) +
    " menjadi " +
    area(r.treeAfterPixels) +
    ". " +
    (loss.length
      ? "Tujuan perubahan terluas adalah " +
        name(loss[0][0]).toLowerCase() +
        " (" +
        area(loss[0][1]) +
        ", " +
        fmt((100 * loss[0][1]) / r.lossPixels) +
        "% dari luas yang keluar)."
      : "Seluruh piksel dalam kelas awal bertahan pada perbandingan ini.");
  $("deltaPct").textContent = r.treeBeforePixels
    ? fmt((100 * Math.abs(r.netPixels)) / r.treeBeforePixels) +
      "% " +
      (delta < 0 ? "lebih rendah" : delta > 0 ? "lebih tinggi" : "perubahan") +
      " dibanding " +
      a
    : "Basis awal kosong";
  const records = r.transitions.map(([x, y, k]) => [
    a,
    b,
    x,
    name(x),
    y,
    name(y),
    k,
    (k * cfg.pixelHa).toFixed(2),
  ]);
  $("transCSV").onclick = () =>
    fileCSV("Rontu-" + cfg.seriesId + "-" + a + "-" + b + "-transisi.csv", [
      [
        "awal",
        "akhir",
        "kode_awal",
        "kelas_awal",
        "kode_akhir",
        "kelas_akhir",
        "piksel",
        "hektare",
      ],
      ...records,
    ]);
  function renderFlows(data, total, element) {
    const all = data.map(([key, count]) => [
      name(key),
      area(count),
      fmt((100 * count) / total) + "%",
    ]);
    $(element).replaceChildren(
      all.length
        ? table(["Kelas", "Luas", "Porsi"], all)
        : el("p", "Tidak ada perubahan arah ini."),
    );
  }
  renderFlows(loss, r.lossPixels, "lossTable");
  renderFlows(gain, r.gainPixels, "gainTable");
  timeline(cfg, rows, a, b, selectPair);
  const card = $("gridTable");
  card.replaceChildren();
  const top = grid
    .filter((g) => g.loss > 0)
    .sort((l, r) => r.loss - l.loss || l.west - r.west || l.south - r.south);
  $("gridCSV").disabled = false;
  const topRows = top.slice(0, 5).map((g, i) => {
    const button = el("button", i + 1 + ". " + g.reference, "textbutton");
    button.type = "button";
    button.title = "Perbesar petak " + g.id;
    button.onclick = () => {
      focus(g);
      $("frame").scrollIntoView({ behavior: "smooth", block: "center" });
    };
    const dst = order(g.dest)[0];
    return [button, area(g.loss), dst ? name(dst[0]) : "—"];
  });
  card.append(
    top.length
      ? table(["Pusat petak 1 km", "Keluar", "Tujuan utama"], topRows)
      : el(
          "p",
          "Tidak ada petak yang kehilangan kelas ini pada periode pilihan.",
        ),
  );
  $("gridCSV").onclick = () =>
    fileCSV("Rontu-" + cfg.seriesId + "-" + a + "-" + b + "-petak.csv", [
      [
        "grid_utm_50s",
        "lokasi_relatif",
        "lintang_pusat",
        "bujur_pusat",
        "batas_barat_m",
        "batas_selatan_m",
        "luas_valid_ha",
        "keluar_ha",
        "masuk_ha",
        "neto_ha",
        "kelas_tujuan_utama",
      ],
      ...grid.map((g) => [
        g.id,
        g.reference,
        g.lat ?? "",
        g.lon ?? "",
        g.west,
        g.south,
        (g.valid * cfg.pixelHa).toFixed(2),
        (g.loss * cfg.pixelHa).toFixed(2),
        (g.gain * cfg.pixelHa).toFixed(2),
        ((g.gain - g.loss) * cfg.pixelHa).toFixed(2),
        order(g.dest)[0] ? name(order(g.dest)[0][0]) : "",
      ]),
    ]);
}
export function spatialGrid(before, after, mask, cfg, references) {
  const w = cfg.width,
    h = cfg.height,
    [step, , west, , , north] = cfg.transform;
  const trees = new Uint8Array(256),
    valid = new Uint8Array(256);
  for (const k of cfg.forestClasses ?? [2]) trees[k] = 1;
  for (const k of cfg.validClasses) valid[k] = 1;
  const eastIndex = new Int32Array(w);
  for (let i = 0; i < w; i++)
    eastIndex[i] = Math.floor((west + (i + 0.5) * step) / 1000);
  const groups = new Map();
  for (let j = 0; j < h; j++) {
    const northIndex = Math.floor((north - (j + 0.5) * step) / 1000);
    let prev = -1,
      g = null;
    for (let i = 0, k = j * w; i < w; i++, k++) {
      const z = k;
      if (!mask[z] || !valid[before[z]] || !valid[after[z]]) continue;
      const col = eastIndex[i];
      if (prev !== col) {
        prev = col;
        const key = col + "-" + northIndex;
        if (!groups.has(key))
          groups.set(key, {
            id: key,
            west: col * 1000,
            south: northIndex * 1000,
            valid: 0,
            loss: 0,
            gain: 0,
            dest: {},
          });
        g = groups.get(key);
      }
      const x = before[z],
        y = after[z];
      g.valid++;
      if (trees[x] && !trees[y]) {
        g.loss++;
        g.dest[y] = (g.dest[y] || 0) + 1;
      } else if (!trees[x] && trees[y]) g.gain++;
    }
  }
  for (const g of groups.values()) {
    const ref = references[g.id];
    g.reference = ref
      ? ref[2] < 0.1
        ? "Dekat " + ref[4]
        : fmt(ref[2]) + " km " + ref[3] + " dari " + ref[4]
      : "Petak " + g.id;
    if (ref) {
      g.lat = ref[0];
      g.lon = ref[1];
    }
  }
  return [...groups.values()];
}
