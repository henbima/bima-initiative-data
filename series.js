const oldGroups = [
  ["Hutan", "#266244", [51, 52, 61, 62, 71, 72, 81, 82, 91, 92]],
  ["Pertanian", "#e6b766", [10, 11, 12, 20]],
  ["Semak dan rumput", "#97ad76", [120, 121, 122, 130, 140]],
  ["Vegetasi jarang", "#c6b894", [150, 152, 153]],
  ["Lahan basah", "#6eaba3", [181, 182, 183, 184, 185, 186, 187]],
  ["Kedap air", "#bd7769", [190]],
  ["Lahan terbuka", "#d1ae8e", [200, 201, 202]],
  ["Badan air", "#639eb6", [210]],
  ["Es / salju", "#e6eff0", [220]],
];
const newGroups = [
  ["Air", "#629ab0", [1]],
  ["Pohon", "#255942", [2]],
  ["Vegetasi tergenang", "#6bb2a0", [4]],
  ["Tanaman budidaya", "#e9bd69", [5]],
  ["Terbangun", "#ba7263", [7]],
  ["Tanah terbuka", "#c8a77d", [8]],
  ["Salju / es", "#e6eff0", [9]],
  ["Rumput / semak", "#a5b782", [11]],
];
export function profileFor(cfg, old) {
  const groups = old ? oldGroups : newGroups;
  const names = {
      0: "Tak terbaca",
      250: "Tak terbaca",
      255: "Tak terbaca",
      ...cfg.classNames,
    },
    colors = { 0: "#bec5bf", 10: "#bec5bf" };
  if (!old) names[10] = "Awan";
  for (const [label, color, ids] of groups)
    for (const id of ids) {
      names[id] ??= label;
      colors[id] = color;
    }
  return {
    names,
    colors,
    legend: [...groups.map(([n, c]) => [n, c]), ["Tak terbaca", "#bec5bf"]],
    metric: old ? "Luas kelas hutan" : "Luas tutupan pohon",
    short: old ? "hutan" : "pohon",
    source: old
      ? "GLC_FCS30D · Landsat 30 m"
      : "Impact Observatory / Esri · Sentinel-2 10 m",
  };
}
