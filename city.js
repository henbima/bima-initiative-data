import { fileCSV, table } from "./detail.js";
const $ = (id) => document.getElementById(id);
const fmt = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 });
const show = (n) => fmt.format(n);
const signed = (n) => (n > 0 ? "+" : "") + show(n);
const opt = (v, n) => new Option(n, String(v));
export async function initCity(read) {
  const { areas, classes, years, source } = await read("kota/city.json");
  const root = areas.find((v) => v.level === "kota"),
    byId = new Map(areas.map((v) => [String(v.id), v]));
  const districts = areas.filter((v) => v.level === "kecamatan");
  const params = new URLSearchParams(location.search),
    initial = byId.get(params.get("wilayah")) || root;
  const dc = $("cityDistrict"),
    wc = $("cityWard"),
    c = $("cityClass"),
    from = $("cityFrom"),
    to = $("cityTo");
  dc.replaceChildren(
    opt(root.id, "Seluruh Kota Bima"),
    ...districts.map((d) => opt(d.id, d.name)),
  );
  dc.value = initial.level === "kelurahan" ? initial.parent : initial.id;
  function wards(selected) {
    const options = areas.filter(
      (v) => v.level === "kelurahan" && String(v.parent) === dc.value,
    );
    wc.replaceChildren(
      opt("", "Semua kelurahan"),
      ...options.map((v) => opt(v.id, v.name)),
    );
    wc.disabled = !options.length;
    if (selected && options.some((v) => String(v.id) === String(selected)))
      wc.value = selected;
  }
  wards(initial.level === "kelurahan" ? initial.id : null);
  c.replaceChildren(
    ...classes.map((x) => opt(x.id, (x.parent == null ? "" : "↳ ") + x.label)),
  );
  c.value = classes.some((k) => String(k.id) === params.get("kelas"))
    ? params.get("kelas")
    : "1";
  from.replaceChildren(...years.slice(0, -1).map((y) => opt(y, y)));
  to.replaceChildren(...years.slice(1).map((y) => opt(y, y)));
  const lo = +params.get("awal"),
    hi = +params.get("akhir");
  from.value = years.includes(lo) && lo < years.at(-1) ? lo : years[0];
  to.value = years.includes(hi) && hi > +from.value ? hi : years.at(-1);
  function render() {
    const a = byId.get(wc.value || dc.value),
      k = c.value,
      i = years.indexOf(+from.value),
      j = years.indexOf(+to.value);
    const yr0 = years[i],
      yr1 = years[j],
      cls = classes.find((x) => String(x.id) === k),
      v = a.series[k],
      delta = v[j] - v[i];
    $("cityTitle").textContent =
      a.level === "kota"
        ? "Kota Bima"
        : (a.level === "kecamatan" ? "Kecamatan " : "Kelurahan ") + a.name;
    $("cityStory").textContent =
      cls.label +
      " tercatat " +
      show(v[i]) +
      " ha pada " +
      yr0 +
      " dan " +
      show(v[j]) +
      " ha pada " +
      yr1 +
      ". Selisih " +
      signed(delta) +
      " ha.";
    $("cityExtent").textContent =
      "Luas wilayah dalam katalog " +
      show(a.areaHa) +
      " ha · batas administrasi 2023.";
    const chart = $("citybars"),
      span = years.slice(i, j + 1);
    const high = Math.max(...v.slice(i, j + 1), 1);
    chart.replaceChildren(
      ...span.map((y, index) => {
        const bar = document.createElement("span");
        bar.className = "bar" + (y === yr0 || y === yr1 ? " sel" : "");
        bar.style.height = Math.max(0, (100 * v[i + index]) / high) + "%";
        bar.title = y + " · " + show(v[i + index]) + " ha";
        return bar;
      }),
    );
    chart.style.gridTemplateColumns = "repeat(" + span.length + ",1fr)";
    chart.ariaLabel =
      cls.label +
      ", " +
      yr0 +
      " sampai " +
      yr1 +
      ". Rincian tersedia dalam tabel tahunan.";
    $("cityChartEnds").replaceChildren(
      String(yr0),
      Object.assign(document.createElement("span"), { textContent: yr1 }),
    );
    $("cityYears").replaceChildren(
      table(
        ["Tahun", cls.label + " (ha)", "Selisih tahunan (ha)"],
        span.map((y, n) => [
          y,
          show(v[i + n]),
          n ? signed(v[i + n] - v[i + n - 1]) : "—",
        ]),
      ),
    );
    const majors = classes.filter(
      (v) => v.parent == null || [24, 40].includes(v.id),
    );
    $("cityCover").replaceChildren(
      table(
        ["Kelas", yr0 + " (ha)", yr1 + " (ha)", "Selisih (ha)"],
        majors.map((q) => {
          const values = a.series[q.id];
          return [
            (q.parent == null ? "" : "↳ ") + q.label,
            show(values[i]),
            show(values[j]),
            signed(values[j] - values[i]),
          ];
        }),
      ),
    );
    const group =
      a.level === "kota"
        ? districts
        : areas.filter(
            (x) =>
              x.level === "kelurahan" &&
              String(x.parent) ===
                String(a.level === "kelurahan" ? a.parent : a.id),
          );
    $("cityRankTitle").textContent =
      a.level === "kota"
        ? "Bandingkan lima kecamatan"
        : "Bandingkan kelurahan di " +
          byId.get(String(a.level === "kelurahan" ? a.parent : a.id)).name;
    $("cityRankSub").textContent =
      cls.label +
      " · " +
      yr0 +
      "–" +
      yr1 +
      " · urut dari selisih terkecil ke terbesar.";
    $("cityRank").replaceChildren(
      table(
        ["Wilayah", yr0 + " (ha)", yr1 + " (ha)", "Selisih (ha)"],
        group
          .slice()
          .sort(
            (l, r) =>
              l.series[k][j] -
              l.series[k][i] -
              (r.series[k][j] - r.series[k][i]),
          )
          .map((g) => {
            const btn = document.createElement("button");
            btn.className = "textbutton";
            btn.textContent = g.name;
            btn.onclick = () => {
              if (g.level === "kecamatan") {
                dc.value = g.id;
                wards();
              } else wc.value = g.id;
              render();
              $("cityTitle").scrollIntoView({
                block: "center",
                behavior: "smooth",
              });
            };
            return [
              btn,
              show(g.series[k][i]),
              show(g.series[k][j]),
              signed(g.series[k][j] - g.series[k][i]),
            ];
          }),
      ),
    );
    $("cityCSV").onclick = () =>
      fileCSV("Bima-MapBiomas-" + a.id + "-" + yr0 + "-" + yr1 + ".csv", [
        [
          "wilayah",
          "kode_wilayah",
          "tingkat",
          "tahun",
          "kode_kelas",
          "kelas",
          "kode_induk",
          "luas_ha",
          "koleksi",
        ],
        ...span.flatMap((y, n) =>
          classes.map((q) => [
            a.name,
            a.id,
            a.level,
            y,
            q.id,
            q.label,
            q.parent ?? "",
            a.series[q.id][i + n].toFixed(2),
            "MapBiomas Indonesia 5",
          ]),
        ),
      ]);
    const u = new URL(location.href);
    for (const [key, value] of Object.entries({
      wilayah: a.id,
      kelas: k,
      awal: yr0,
      akhir: yr1,
    }))
      u.searchParams.set(key, value);
    u.hash = "kota";
    $("cityLink").href = u.href;
    if (location.hash === "#kota") history.replaceState(null, "", u.href);
  }
  dc.onchange = () => {
    wards();
    render();
  };
  wc.onchange = c.onchange = render;
  from.onchange = () => {
    if (+from.value >= +to.value) to.value = +from.value + 1;
    render();
  };
  to.onchange = () => {
    if (+to.value <= +from.value) from.value = +to.value - 1;
    render();
  };
  $("citySource").href = source.portal;
  $("cityDate").textContent = source.retrieved;
  $("cityCount").textContent =
    districts.length +
    " kecamatan dan " +
    areas.filter((v) => v.level === "kelurahan").length +
    " kelurahan";
  render();
}
