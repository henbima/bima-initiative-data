const num = (n) =>
  new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(n);
const when = (s) =>
  new Date(s).toLocaleString("id-ID", {
    timeZone: "Asia/Makassar",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
export async function loadEvent(read) {
  const e = await read("event-2021-02-02.json"),
    out = document.querySelector("#event-body");
  const link = (url, label) => {
    const a = document.createElement("a");
    a.href = url;
    a.textContent = label;
    return a;
  };
  function el(tag, txt) {
    const n = document.createElement(tag);
    if (txt != null) n.textContent = txt;
    return n;
  }
  function panel(title) {
    const p = el("article");
    p.className = "panel";
    p.append(el("h2", title));
    return p;
  }
  function table(headers, rows) {
    const t = el("table"),
      tr = el("tr");
    for (const h of headers) tr.append(el("th", h));
    t.createTHead().append(tr);
    const body = t.createTBody();
    for (const row of rows) {
      const r = el("tr");
      for (const col of row) r.append(el("td", col));
      body.append(r);
    }
    return t;
  }
  const timeline = panel("Kronologi di lapangan");
  timeline.append(
    table(
      ["WITA", "Lokasi dan pengamatan"],
      e.timeline.map((v) => [v.wita, v.place + " · " + v.detail]),
    ),
    link(e.sources.chronology, "Baca laporan SiAGA NTB"),
  );
  const rain = panel("Hujan menurut satelit");
  rain.append(
    el(
      "p",
      "Estimasi NASA IMERG Final V07. Setiap nilai harian menjumlahkan 48 interval setengah jam dalam hari kalender WITA. Sel mencakup kawasan sekitar 10 × 10 km.",
    ),
  );
  const ds = e.rain.cells[0].daily;
  rain.append(
    table(
      ["Sel pengamatan", ...ds.map((d) => Number(d.date.slice(-2)) + " Feb")],
      e.rain.cells.map((c) => [
        c.label,
        ...c.daily.map((d) =>
          d.total_mm != null ? num(d.total_mm) + " mm" : "Data kurang",
        ),
      ]),
    ),
  );
  rain.append(
    el(
      "p",
      e.rain.cells
        .map((c) => c.label + " (" + c.latitude + "°, " + c.longitude + "°)")
        .join(" · "),
    ),
    link(e.rain.source, "Produk NASA IMERG"),
  );
  const radar = panel("Lintasan radar Sentinel-1");
  const tag = el("p", "Tidak teramati saat kejadian");
  tag.className = "big";
  radar.append(
    tag,
    el(
      "p",
      "Pencarian scene GRD resolusi tinggi di sekitar Kota Bima pada 2 Februari WITA menghasilkan nol citra. Dua lintasan terdekat pada titik kota mengapit tanggal kejadian.",
    ),
  );
  const before = e.radar.scenes
      .filter((s) => s.start_wita < "2021-02-02")
      .at(-1),
    after = e.radar.scenes.find((s) => s.start_wita > "2021-02-03");
  if (before && after)
    radar.append(
      table(
        ["Lintasan", "WITA"],
        [
          ["Sebelumnya", when(before.start_wita)],
          ["Berikutnya", when(after.start_wita)],
        ],
      ),
    );
  radar.append(
    link(
      e.radar.event_day_search.source_query,
      "Periksa pencarian saat kejadian",
    ),
    document.createTextNode(" · "),
    link(e.radar.source_query, "Lintasan di titik kota"),
  );
  const station = panel("Pengamatan stasiun");
  station.append(
    Object.assign(el("p", num(e.station.reported_mm) + " mm"), {
      className: "big",
    }),
    el(
      "p",
      e.station.name +
        ". " +
        e.station.note +
        " Angka stasiun dan rata-rata sel satelit mempunyai cakupan ruang dan waktu berbeda.",
    ),
    link(e.station.source, "Dokumen Bappeda §3.1.10"),
  );
  const div = el("div");
  div.className = "panels";
  div.append(timeline, rain, radar, station);
  out.append(div, el("p"));
  out.append(link("event-2021-02-02.json", "Unduh arsip data kejadian (JSON)"));
}
