"""Build local gross forest-exit detail for one aligned classified raster series.

All measures are counts of native pixel centres in a 1 km UTM square and the
study footprint. Multiply by manifest.pixelHa for hectares. Inputs are the
published classified grids, boundary mask, per-pair summary, and GeoNames
settlement point extract. pyproj, Pillow, and numpy are the only dependencies.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image
from pyproj import Transformer

SIZE = 1000
DIR_NAMES = ["utara", "timur laut", "timur", "tenggara", "selatan", "barat daya", "barat", "barat laut"]


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def histogram(values):
    unique, counts = np.unique(values, return_counts=True)
    return sorted([[int(code), int(n)] for code, n in zip(unique, counts)], key=lambda r: (-r[1], r[0]))


def anchors(path, to_utm):
    points = []
    with path.open(encoding="utf-8") as f:
        for r in csv.reader(f, delimiter="\t"):
            if r[6] != "P" or r[7] not in {"PPL", "PPLA", "PPLA2", "PPLA3", "PPLA4"}:
                continue
            x, y = to_utm.transform(float(r[5]), float(r[4]))
            points.append((x, y, r[1], r[0]))
    if not points:
        raise ValueError("No gazetteer settlement anchors found")
    return points


def nearest_reference(points, x, y):
    px, py, name, record = min(points, key=lambda p: ((x-p[0])**2+(y-p[1])**2, p[3]))
    dx, dy = x-px, y-py
    ring = int(math.floor((math.degrees(math.atan2(dx, dy)) + 22.5) / 45)) % 8
    return {"name": name, "geoNamesId": record, "km": round(math.hypot(dx, dy)/1000, 2), "direction": DIR_NAMES[ring]}


def geo_fields(to_lonlat, x, y):
    lon, lat = to_lonlat.transform(x, y)
    return {"x": round(x, 1), "y": round(y, 1), "lon": round(lon, 6), "lat": round(lat, 6)}


class Grid:
    def __init__(self, cfg, mask, gazetteer):
        step, x_rot, west, y_rot, ystep, north = cfg["transform"]
        if (x_rot, y_rot, ystep) != (0, 0, -step) or cfg["crs"].upper() != "EPSG:32750":
            raise ValueError("Requires a north-up, square grid in the local Bima UTM CRS")
        rows, cols = np.nonzero(mask)
        x = west + (cols + .5) * step
        y = north - (rows + .5) * step
        east_id = np.floor_divide(x, SIZE).astype("int64")
        north_id = np.floor_divide(y, SIZE).astype("int64")
        # ID is unique over this UTM zone. Sort once to group each cell contiguously.
        keys = east_id * 100_000 + north_id
        order = np.argsort(keys, kind="stable")
        self.rows, self.cols = rows[order], cols[order]
        self.x, self.y = x[order], y[order]
        self.keys, self.starts, self.inside = np.unique(keys[order], return_index=True, return_counts=True)
        self.groups = np.repeat(np.arange(len(self.keys), dtype="int32"), self.inside)
        self.names = [f"{key//100000}-{key%100000}" for key in self.keys]
        self.to_lonlat = Transformer.from_crs(cfg["crs"], 4326, always_xy=True)
        self.anchors = anchors(gazetteer, Transformer.from_crs(4326, cfg["crs"], always_xy=True))
        self.cells = {}
        for key, name in zip(self.keys, self.names):
            w = int(key//100000)*SIZE
            s = int(key%100000)*SIZE
            x, y = w+SIZE/2, s+SIZE/2
            self.cells[name] = {
                "west": w, "south": s, "east": w+SIZE, "north": s+SIZE,
                **geo_fields(self.to_lonlat, x, y),
                "reference": nearest_reference(self.anchors, x, y),
            }

    def bincount(self, where):
        return np.bincount(self.groups[where], minlength=len(self.keys))

    def slice(self, group):
        return slice(self.starts[group], self.starts[group]+self.inside[group])


def load_series(data, cfg, mask, grid):
    lookup_valid = np.zeros(256, dtype=bool)
    lookup_valid[cfg["validClasses"]] = True
    lookup_forest = np.zeros(256, dtype=bool)
    forest = cfg.get("forestClasses") or [cfg["treeClass"]]
    lookup_forest[forest] = True
    years = []
    layers, valid, forested, spells = [], [], [], []
    for i, obs in enumerate(cfg["years"]):
        p = data / obs["file"]
        if obs.get("sha256") and hashlib.sha256(p.read_bytes()).hexdigest() != obs["sha256"]:
            raise ValueError(f"Data integrity failure: {p}")
        image = np.asarray(Image.open(p))
        if image.shape != mask.shape:
            raise ValueError("Mask and class raster have different dimensions")
        a = image[grid.rows,grid.cols]
        ok = lookup_valid[a]
        tree = lookup_forest[a] & ok
        non = ok & ~tree
        if i:
            # Index i means the run starts at this observation immediately after
            # the preceding forest observation. Code zero is unverifiable.
            first = np.where(non, np.where(forested[-1], i, spells[-1]), 0).astype("uint16")
        else:
            first = np.zeros(len(a), dtype="uint16")
        spells.append(first)
        years.append(int(obs["year"]))
        layers.append(a)
        valid.append(ok)
        forested.append(tree)
    if years != sorted(set(years)):
        raise ValueError("Years must be unique and ascending")
    return years, layers, valid, forested, spells


def check_totals(reference, valid, before, after, loss, gain):
    result = {"validPixels":int(valid.sum()),"treeBeforePixels":int(before.sum()),
              "treeAfterPixels":int(after.sum()),"lossPixels":int(loss.sum()),"gainPixels":int(gain.sum())}
    for k, v in result.items():
        if k in reference and reference[k] != v:
            raise ValueError(f"Published summary and local grid differ: {k} = {reference[k]} vs {v}")


def summarize(grid, series, ia, ib, summary, csv_writer):
    years, layers, valid, forested, spells = series
    year_a, year_b = years[ia], years[ib]
    common = valid[ia] & valid[ib]
    before = common & forested[ia]
    after = common & forested[ib]
    lost = before & ~after
    gain = after & ~before
    loss_counts = grid.bincount(lost)
    gain_counts = grid.bincount(gain)
    valid_counts = grid.bincount(common)
    start_counts = grid.bincount(before)
    check_totals(summary, common, before, after, lost, gain)
    dest = histogram(layers[ib][lost])
    if sum(n for _,n in dest) != int(loss_counts.sum()):
        raise ValueError("Destinations failed reconciliation")
    # Persistence is reported only when the preceding calendar year lies strictly inside the pair.
    has_prior = ib-1>ia and years[ib-1]+1==year_b
    prev_ok = valid[ib-1] & lost if has_prior else None
    still_non = prev_ok & ~forested[ib-1] if has_prior else None
    times = histogram(spells[ib][lost])
    windows = [[years[code-1] if code else None, years[code] if code else None,n] for code,n in times]
    order = sorted(np.flatnonzero(loss_counts).tolist(), key=lambda i:(-loss_counts[i],grid.names[i]))[:10]
    top = []
    for i in order:
        span = grid.slice(i)
        local = lost[span]
        x, y = grid.x[span][local], grid.y[span][local]
        best = np.argmin((x-x.mean())**2+(y-y.mean())**2)
        px, py = x[best], y[best]
        top.append({
            "cell":grid.names[i],"loss":int(loss_counts[i]),"gain":int(gain_counts[i]),
            "net":int(gain_counts[i]-loss_counts[i]),"valid":int(valid_counts[i]),"inside":int(grid.inside[i]),
            "start":int(start_counts[i]), **geo_fields(grid.to_lonlat,px,py),
            "dest":histogram(layers[ib][span][local]),
            "previousValidLoss":int(prev_ok[span].sum()) if has_prior else None,
            "lastTwoNonTree":int(still_non[span].sum()) if has_prior else None,
        })
    for i,name in enumerate(grid.names):
        csv_writer.writerow([year_a,year_b,name,int(grid.inside[i]),int(valid_counts[i]),int(start_counts[i]),
                             int(start_counts[i]+gain_counts[i]-loss_counts[i]),int(loss_counts[i]),int(gain_counts[i]),
                             int(gain_counts[i]-loss_counts[i])])
    return {"topLoss":top,"lossDest":dest,"observedChangeWindows":windows,
            "previousValidLoss":int(prev_ok.sum()) if has_prior else None,
            "lastTwoNonTree":int(still_non.sum()) if has_prior else None}


def run(data, gazetteer, out):
    cfg = read(data/'manifest.json')
    mask = np.asarray(Image.open(data/cfg.get("mask","mask.png"))) != 0
    grid = Grid(cfg,mask,gazetteer)
    series = load_series(data,cfg,mask,grid)
    years=series[0]
    summaries=read(data/cfg.get("summary","summary.json"))
    out.mkdir(parents=True,exist_ok=True)
    for ia,year in enumerate(years[:-1]):
        by_end={}
        buffer=io.StringIO(newline="")
        writer=csv.writer(buffer)
        writer.writerow(["start","end","utm_1km_id","inside_px","common_valid_px","forest_start_px","forest_end_px",
                         "exit_px","enter_px","net_px"])
        for ib in range(ia+1,len(years)):
            by_end[str(years[ib])]=summarize(grid,series,ia,ib,summaries[f"{year}-{years[ib]}"],writer)
        dump(out/f"{year}.json", by_end)
        with zipfile.ZipFile(out/f"{year}-grid.csv.zip","w",compression=zipfile.ZIP_DEFLATED) as archive:
            info=zipfile.ZipInfo(f"rontu-grid-{year}.csv",date_time=(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,buffer.getvalue())
    index={"schemaVersion":1, "crs":cfg["crs"], "pixelHa":cfg["pixelHa"],"cellSizeM":SIZE,
           "boundarySha256":cfg.get("boundarySha256"),"sourceManifestSha256":hashlib.sha256((data/"manifest.json").read_bytes()).hexdigest(),
           "sourceYears":years,"sourceState":[[v["year"],v.get("sha256")] for v in cfg["years"]],
           "files":{str(y):f"{y}.json" for y in years[:-1]},
           "csv":{str(y):f"{y}-grid.csv.zip" for y in years[:-1]},
           "classGroup":cfg.get("forestClasses") or [cfg["treeClass"]],
           "cells":grid.cells,"referenceSource":"https://download.geonames.org/export/dump/ID.zip",
           "referenceAttribution":"GeoNames, CC BY 4.0"}
    dump(out/'index.json',index)
    print(f"{len(years)} years, {len(grid.cells)} cells, {len(years)*(len(years)-1)//2} pairs",flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data",type=Path,required=True)
    parser.add_argument("--gazetteer",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    run(args.data,args.gazetteer,args.out)

