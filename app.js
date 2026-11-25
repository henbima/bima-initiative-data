import { profileFor } from "./series.js";
import { showDetails } from "./detail.js";
import { createMap } from "./map.js";
const $ = (id) => document.getElementById(id);
const num = (n, d = 2) =>
  new Intl.NumberFormat("id-ID", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  }).format(n);
const ha = (n) => num(n * cfg.pixelHa) + " ha";
const read = async (path) => {
  const r = await fetch(path, { signal: AbortSignal.timeout(18000) });
  if (!r.ok) throw Error("HTTP " + r.status);
  return r.json();
};
const repo = "https://raw.githubusercontent.com/henbima/bima-initiative-data/";
const historical =
  new URLSearchParams(location.search).get("seri") !== "detail";
let profile,
  initialPair = true;
let active = historical ? "historis/" : "data/",
  cfg,
  rows,
  atlas,
  pair,
  images = new Map(),
  version = 0,
  latestChecked = "";
let cityTask;
function nav() {
  let id = location.hash.slice(1);
  if (!["peta", "kota", "banjir", "metode"].includes(id)) id = "peta";
  for (const section of document.querySelectorAll(".view"))
    section.hidden = section.id !== id;
  for (const a of document.querySelectorAll("nav a")) {
    const on = a.hash === "#" + id;
    a.classList.toggle("active", on);
    if (on) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
  if (id === "peta") atlas?.schedule();
  if (id === "kota" && !cityTask)
    cityTask = import("./city.js")
      .then((m) => m.initCity(read))
      .catch(() => {
        $("cityStory").textContent =
          "Statistik gagal dimuat. Buka ulang halaman untuk mencoba lagi.";
        cityTask = null;
      });
}
window.addEventListener("hashchange", nav);
nav();
function options(items) {
  return items.map((y) => new Option(String(y), String(y)));
}
function fillYears(initial = false, fromStart = true) {
  const ys = cfg.years.map((x) => x.year),
    oldA = Number($("start").value),
    oldB = Number($("end").value);
  let a = initial ? ys[0] : oldA,
    b = initial ? ys.at(-1) : oldB;
  if (a >= b) {
    if (fromStart) b = ys.find((y) => y > a);
    else a = ys.filter((y) => y < b).at(-1);
  }
  $("start").replaceChildren(...options(ys.slice(0, -1)));
  $("end").replaceChildren(...options(ys.slice(1)));
  $("start").value = a;
  $("end").value = b;
}
function mapUrl(a, b, grid) {
  const u = new URL(location.pathname, location.origin);
  u.searchParams.set("seri", historical ? "arsip" : "detail");
  u.searchParams.set("dari", a);
  u.searchParams.set("ke", b);
  if (grid) u.searchParams.set("petak", grid.id);
  u.hash = "peta";
  $("mapShare").href = u.href;
}
function getImage(path) {
  const url = active + path;
  if (images.has(url)) return images.get(url);
  const promise = (async () => {
    const r = await fetch(url, { signal: AbortSignal.timeout(20000) });
    if (!r.ok) throw Error("Peta tidak tersedia");
    const bytes = await r.arrayBuffer();
    const expected = cfg.years.find((y) => y.file === path)?.sha256;
    if (expected) {
      const digest = Array.from(
        new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
        (x) => x.toString(16).padStart(2, "0"),
      ).join("");
      if (digest !== expected) throw Error("Sidik berkas berbeda");
    }
    const obj = URL.createObjectURL(new Blob([bytes], { type: "image/png" }));
    try {
      const im = new Image();
      im.src = obj;
      await im.decode();
      if (im.width !== cfg.width || im.height !== cfg.height)
        throw Error("Ukuran berbeda");
      return im;
    } finally {
      URL.revokeObjectURL(obj);
    }
  })();
  images.set(url, promise);
  if (images.size > 5) images.delete(images.keys().next().value);
  promise.catch(() => images.delete(url));
  return promise;
}
function chart(a, b) {
  const ys = cfg.years.map((y) => y.year),
    annual = ys.map((y) => rows[y + "-" + y].treeBeforePixels),
    mx = Math.max(...annual);
  const bars = document.createElement("div");
  bars.className = "chartbars";
  bars.style.gridTemplateColumns =
    "repeat(" + (ys.at(-1) - ys[0] + 1) + ",1fr)";
  const vals = [];
  ys.forEach((y, i) => {
    const bar = document.createElement("span");
    bar.className = "bar" + ([a, b].includes(y) ? " sel" : "");
    bar.style.height = (annual[i] / mx) * 100 + "%";
    bar.title = y + " · " + ha(annual[i]);
    bar.style.gridColumn = String(y - ys[0] + 1);
    bars.append(bar);
    vals.push(bar.title);
  });
  const ends = document.createElement("div");
  ends.className = "chartends";
  ends.append(
    String(ys[0]),
    Object.assign(document.createElement("span"), {
      textContent: String(ys.at(-1)),
    }),
  );
  $("chart").replaceChildren(bars, ends);
  $("chart").ariaLabel = vals.join(", ");
  $("chart").role = "img";
}
async function renderComparison() {
  const v = ++version,
    a = +$("start").value,
    b = +$("end").value,
    row = rows[a + "-" + b];
  $("csv").disabled = true;
  $("gridTable").closest(".analysis").inert = true;
  $("finding").textContent = "Memuat perbandingan " + a + "–" + b + ".";
  $("mapStatus").hidden = false;
  $("mapStatus").textContent = "Memuat perbandingan…";
  try {
    const ok = await atlas.setYears(
      cfg.years.find((y) => y.year === a),
      cfg.years.find((y) => y.year === b),
    );
    if (!ok || v !== version) return;
    pair = { a, b, row };
    $("net").textContent =
      (row.netPixels > 0 ? "+" : "") + ha(row.netPixels).replace("-", "−");
    $("lost").textContent = ha(row.lossPixels);
    $("gained").textContent = ha(row.gainPixels);
    const valid = row.validPixels / row.insidePixels;
    $("coverage").textContent =
      (valid < 0.9 ? "Cakupan terbatas · " : "Terbaca di kedua tahun · ") +
      num(valid * 100, 3) +
      "%";
    $("areaHint").textContent = ha(row.insidePixels) + " · wilayah analisis";
    $("chartnote").textContent =
      a +
      " · " +
      ha(row.treeBeforePixels) +
      "   /   " +
      b +
      " · " +
      ha(row.treeAfterPixels);
    const totals = atlas.grid.reduce(
      (t, g) => [t[0] + g.loss, t[1] + g.gain, t[2] + g.valid],
      [0, 0, 0],
    );
    if (
      totals[0] !== row.lossPixels ||
      totals[1] !== row.gainPixels ||
      totals[2] !== row.validPixels
    )
      throw Error("Jumlah piksel tidak cocok");
    const focus = (g) => {
      atlas.focus(g);
      mapUrl(a, b, g);
    };
    mapUrl(a, b, null);
    if (initialPair && location.hash !== "#kota") {
      const gridId = new URLSearchParams(location.search).get("petak");
      const chosen = atlas.grid.find((t) => t.id === gridId);
      if (chosen) focus(chosen);
    }
    initialPair = false;
    $("gridTable").closest(".analysis").inert = false;
    showDetails(cfg, rows, a, b, profile, atlas.grid, focus, (x, y) => {
      $("start").value = x;
      $("end").value = y;
      renderComparison().catch(onError);
      $("frame").scrollIntoView({ behavior: "smooth", block: "center" });
    });
    chart(a, b);
    $("mapStatus").hidden = true;
    $("csv").disabled = false;
  } catch (e) {
    if (v !== version) return;
    throw e;
  }
}
function csv() {
  if (!pair) return;
  const { a, b, row: r } = pair,
    data = [
      [
        "seri",
        "kelas",
        "resolusi_m",
        "wilayah",
        "kode_das",
        "tahun_awal",
        "tahun_akhir",
        "luas_wilayah_grid_ha",
        "area_valid_bersama_ha",
        "cakupan_persen",
        "kelas_awal_ha",
        "kelas_akhir_ha",
        "keluar_ha",
        "masuk_ha",
        "neto_ha",
        "versi_batas_sha256",
        "tanggal_proses_utc",
        "sumber_awal",
        "sumber_akhir",
      ],
      [
        cfg.seriesId,
        profile.short,
        cfg.transform[0],
        "Rontu",
        "DAS420446",
        a,
        b,
        ...[r.insidePixels, r.validPixels].map((n) =>
          (n * cfg.pixelHa).toFixed(2),
        ),
        ((r.validPixels / r.insidePixels) * 100).toFixed(5),
        ...[
          r.treeBeforePixels,
          r.treeAfterPixels,
          r.lossPixels,
          r.gainPixels,
          r.netPixels,
        ].map((n) => (n * cfg.pixelHa).toFixed(2)),
        cfg.boundarySha256,
        cfg.processedUtc ?? "",
        ...[a, b].map((yr) => cfg.years.find((y) => y.year === yr).source),
      ],
    ];
  const url = URL.createObjectURL(
    new Blob(["\uFEFF" + data.map((v) => v.join(",")).join("\r\n")], {
      type: "text/csv;charset=utf-8",
    }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = "Rontu-" + cfg.seriesId + "-" + a + "-" + b + ".csv";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
function onError() {
  const s = $("mapStatus");
  s.hidden = false;
  s.textContent = "Data untuk pilihan ini gagal dibuka. ";
  const retry = document.createElement("button");
  retry.textContent = "Coba lagi";
  retry.onclick = () => location.reload();
  s.append(retry);
  $("net").textContent = "—";
  $("lost").textContent = "—";
  $("gained").textContent = "—";
  $("csv").disabled = true;
}
function method() {
  const years = cfg.years.map((v) => v.year);
  $("method").innerHTML =
    `<article><h2>Batas DAS Rontu</h2><p>Wilayah kerja mencakup daerah tangkapan hingga hilir. Poligon DAS420446 dicocokkan dengan Gambar 3.10 pada dokumen Bappeda. Katalog mencatat 25.874,17 ha. Studi di dua titik jembatan mencakup 25.263 ha, dengan batas keluar air yang berbeda. Kolom nama pada rekaman poligon kosong.</p><a href="https://www.arcgis.com/home/item.html?id=630d72ebe4cf47108c463501d5f47c81">Rekaman batas</a> · <a href="https://bappeda.bimakota.go.id/upload/download/1753668548_00e2264c7b94e7e04110.pdf#page=58">Peta pembanding</a> · <a href="https://scholarhub.ui.ac.id/jglitrop/vol2/iss2/2/">Kajian hidrologi</a></article>
 <article><h2>Kelas tutupan pohon</h2><p>Klasifikasi tahunan Sentinel-2 berasal dari Impact Observatory, Microsoft, dan Esri. Kelas pohon dapat mencakup berbagai jenis vegetasi berpohon. Perubahan kelas antar-tahun bisa dipengaruhi kondisi citra dan klasifikasi. Peta ini mengukur perubahan yang teramati. Penetapan pembalakan, pelaku, atau penyebab banjir memerlukan bukti tambahan.</p><a href="https://registry.opendata.aws/io-lulc/">Arsip asli</a> · <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a></article>
 <article><h2>Cara menghitung luas</h2><p>Grid UTM 50S memakai piksel 10 × 10 m atau 0,01 ha. Piksel tepi masuk jika pusatnya berada di dalam poligon. Awan dan data kosong dikeluarkan dari kedua tahun. Angka bersih adalah luas masuk ke kelas pohon dikurangi luas keluar. Grafik tahunan menggunakan area valid masing-masing tahun.</p><p>Relief dasar berasal dari Mapzen Terrain Tiles, dengan data elevasi USGS dan NOAA. <a href="https://github.com/tilezen/joerd/blob/master/docs/attribution.md">Atribusi relief</a>. Nama lokasi berasal dari <a href="https://www.geonames.org/">GeoNames</a> (CC BY 4.0).</p></article>
 <article><h2>Pembaruan dan unduhan</h2><p>Seri yang tersedia <b>${years[0]}–${years.at(-1)}</b>. Halaman utama menyediakan CSV per pasangan tahun. Pemeriksaan arsip bulanan mencatat rilis baru dan revisi sumber. <span id="checked"></span></p><a id="manifestlink">Manifest data aktif</a> · <a href="https://github.com/henbima/bima-initiative-data">Data dan proses pengolahan</a></article>`;
  const articles = $("method").querySelectorAll("article");
  const check = document.createElement("p");
  check.innerHTML =
    'Sebagai pembanding, batas bernama RONTU pada katalog DAS 2024 yang disajikan MapBiomas mencakup sekitar 99,26% wilayah kerja. Luas batas pembanding tercatat 26.057,60 ha. Semua perhitungan pada peta memakai poligon kerja yang sama. <a href="reproduce/boundary/rontu-boundary-check.json">Hasil uji tumpang tindih dan sumber geometri</a>.';
  articles[0].append(check);
  articles[1].innerHTML = historical
    ? '<h2>Kelas hutan Landsat</h2><p>GLC_FCS30D v2, karya Liangyun Liu, Xiao Zhang, dan Zhehua Li, memakai sepuluh kelas hutan terbuka dan rapat (kode 51–92). Mangrove, rawa berpohon dan kebun berkayu memiliki kelas tersendiri. Vegetasi jarang adalah kode 150. Kelas tujuan memberi petunjuk tutupan permukaan. Jenis tanaman, pelaku dan penyebab perubahan memerlukan bukti tambahan.</p><a href="https://zenodo.org/records/15063683">Arsip sumber</a> · <a href="https://essd.copernicus.org/articles/16/1353/2024/">Metode ilmiah</a> · <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>'
    : articles[1].innerHTML;
  articles[2].querySelector("p").textContent =
    "Grid UTM 50S memakai piksel " +
    cfg.transform[0] +
    " × " +
    cfg.transform[0] +
    " m (" +
    num(cfg.pixelHa) +
    " ha). Piksel masuk jika pusatnya berada dalam poligon DAS. Perbandingan memakai lokasi valid di kedua tahun. Perubahan bersih adalah luas masuk dikurangi luas keluar. Tabel tahunan memakai semua piksel valid tiap tahun. Petak berukuran 1 × 1 km dengan titik acuan permukiman dari GeoNames. Petak tepi hanya menghitung bagian di dalam DAS.";
  if (historical)
    articles[3].querySelector("p").innerHTML =
      'Arsip tetap versi 2 mencakup 26 pengamatan. Tahun 1985, 1990 dan 1995 merupakan pusat jendela lima tahun. Data tahunan tersedia pada 2000–2022. <a href="https://github.com/henbima/bima-initiative-data/tree/observatorium/reproduce/historical">Kode pengolahan dan verifikasi</a>.';
  $("manifestlink").href = active + "manifest.json";
  if ($("checked"))
    $("checked").textContent = latestChecked
      ? "Pemeriksaan terakhir " + latestChecked + "."
      : "";
}
async function setup(base, conf) {
  active = base;
  cfg = conf;
  cfg.seriesId = historical ? "GLC-FCS30D" : "Esri";
  profile = profileFor(cfg, historical);
  $(historical ? "tabOld" : "tabNew").setAttribute("aria-current", "true");
  $("resolution").textContent = profile.source;
  $("stamp").textContent = "DAS RONTU · " + cfg.transform[0] + " M";
  $("metricTitle").textContent = "Perubahan bersih kelas " + profile.short;
  $("chartTitle").textContent = "Luas " + profile.short + " per pengamatan";
  $("lostLabel").textContent = "Keluar dari kelas " + profile.short;
  $("gainLabel").textContent = "Masuk ke kelas " + profile.short;
  $("timeNote").textContent = historical
    ? "1985, 1990 dan 1995 mewakili jendela lima tahun. Pengamatan tersedia setiap tahun mulai 2000."
    : "Satu peta klasifikasi per tahun. Setiap piksel mewakili 10 × 10 meter.";
  if (!historical)
    $("recentSpan").textContent =
      cfg.years[0].year + "–" + cfg.years.at(-1).year + " · Sentinel-2 · 10 m";
  rows = await read(active + cfg.summary);
  fillYears(true);
  if (initialPair) {
    const q = new URLSearchParams(location.search),
      a = +q.get("dari"),
      b = +q.get("ke");
    if (a < b && rows[a + "-" + b]) {
      $("start").value = a;
      $("end").value = b;
    }
  }
  method();
  if (!atlas) atlas = await createMap(cfg, read, getImage, profile);
  await renderComparison();
}
async function main() {
  const local = await read(active + "manifest.json");
  await setup(active, local);
  $("start").onchange = () => {
    fillYears(false, true);
    renderComparison().catch(onError);
  };
  $("end").onchange = () => {
    fillYears(false, false);
    renderComparison().catch(onError);
  };
  $("csv").onclick = csv;
  if (historical) return;
  try {
    const s = await read(repo + "main/status.json");
    if (!/^[a-f0-9]{40}$/.test(s.dataCommit)) return;
    latestChecked = new Date(s.checkedUtc).toLocaleDateString("id-ID", {
      timeZone: "Asia/Makassar",
      day: "numeric",
      month: "long",
      year: "numeric",
    });
    method();
    const base = repo + s.dataCommit + "/data/",
      remote = await read(base + "manifest.json");
    if (
      remote.boundarySha256 !== local.boundarySha256 ||
      remote.validClasses.join() !== local.validClasses.join() ||
      remote.treeClass !== local.treeClass ||
      remote.pixelHa !== local.pixelHa ||
      remote.width !== local.width ||
      remote.height !== local.height ||
      remote.years.length < local.years.length ||
      remote.transform.join() !== local.transform.join()
    )
      return;
    if (remote.years.every((v, i) => v.sha256 === local.years[i]?.sha256))
      return;
    try {
      await setup(base, remote);
    } catch {
      await setup("data/", local);
    }
  } catch {
    /* The bundled validated release remains available. */
  }
}
main().catch(onError);
import { loadEvent } from "./event.js";
loadEvent(read).catch(() => {
  $("event-body").textContent =
    "Arsip gagal dibaca. Muat ulang halaman untuk mencoba kembali.";
});
