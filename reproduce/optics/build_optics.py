"""Rebuild two co-registered Rontu natural-colour views using anonymous HTTPS.

Dependencies: NumPy, requests, rasterio, Pillow. The HTTP code reads whole small
SCL masks and downloads only native TIFF tiles needed for the RGB area.
GDAL opens local files only. STAC scene item identifiers are retained in output.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse
import hashlib
import json
import struct
import math
import time
from urllib.parse import urlparse

import requests
import numpy as np
import rasterio
from rasterio.windows import Window
from PIL import Image

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
OUT = HERE / "data"
WEST, SOUTH, EAST, NORTH = 688190, 9045770, 711010, 9071330
WIDTH, HEIGHT = (EAST - WEST) // 10, (NORTH - SOUTH) // 10
XS = WEST + 5 + np.arange(WIDTH) * 10
YS = NORTH - 5 - np.arange(HEIGHT) * 10
VALID_CLEAR = [4, 5, 6]
SCL_BAD = [3, 8, 9, 10]
HOSTS = {
    "sentinel-cogs.s3.us-west-2.amazonaws.com",
    "e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com",
}


def get(url, headers=None):
    if urlparse(url).hostname not in HOSTS:
        raise ValueError("Unexpected asset host")
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=(15, 90))
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def ranged(url, lo, hi):
    r = get(url, {"Range": f"bytes={lo}-{hi}"})
    length = len(r.content)
    if (
        r.status_code != 206
        or not r.headers.get("Content-Range", "").startswith(f"bytes {lo}-{hi}/")
        or length != hi - lo + 1
    ):
        raise OSError(
            f"Invalid range at {lo} for {url} (HTTP {r.status_code}, {length} bytes)"
        )
    return r.content, int(r.headers["Content-Range"].split("/")[-1])


def tags(header):
    endian = "<" if header[:2] == b"II" else ">"
    if struct.unpack_from(endian + "H", header, 2)[0] != 42:
        raise ValueError("Expected TIFF")
    ifd = struct.unpack_from(endian + "I", header, 4)[0]
    n = struct.unpack_from(endian + "H", header, ifd)[0]
    result = {}
    for idx in range(n):
        pos = ifd + 2 + 12 * idx
        tag, ty, nv = struct.unpack_from(endian + "HHI", header, pos)
        fmt = {3: "H", 4: "I"}.get(ty)
        if not fmt:
            continue
        size = struct.calcsize(fmt) * nv
        start = (
            pos + 8
            if size <= 4
            else struct.unpack_from(endian + "I", header, pos + 8)[0]
        )
        result[tag] = struct.unpack_from(endian + str(nv) + fmt, header, start)
    return result


def local_tci(f):
    a = f["assets"]["visual"]
    u = a["href"]
    path = CACHE / (f["id"] + "-roi.tif")
    if path.exists():
        return path
    head, total = ranged(u, 0, 262143)
    t = tags(head)
    if t.get(284, (1,))[0] != 1:
        raise ValueError("Expected interleaved three-band RGB")
    x0, y0 = a["proj:transform"][2], a["proj:transform"][5]
    tw, th = t[322][0], t[323][0]
    nx, ny = t[256][0], t[257][0]
    cols = math.ceil(nx / tw)
    col0 = int(max(0, (WEST - x0) // (tw * 10)))
    col1 = int(min(cols - 1, (EAST - 1 - x0) // (tw * 10)))
    row0 = int(max(0, (y0 - NORTH) // (th * 10)))
    row1 = int(min(math.ceil(ny / th) - 1, (y0 - SOUTH - 1) // (th * 10)))
    offsets, counts = t[324], t[325]
    spans = []
    for y in range(row0, row1 + 1):
        indices = [y * cols + x for x in range(col0, col1 + 1) if counts[y * cols + x]]
        if indices:
            starts = [offsets[i] for i in indices]
            ends = [offsets[i] + counts[i] - 1 for i in indices]
            spans.append((min(starts), max(ends)))
    with ThreadPoolExecutor(max_workers=5) as pool:
        parts = list(pool.map(lambda p: ranged(u, *p)[0], spans))
    temp = path.with_suffix(".partial")
    with temp.open("wb") as fp:
        fp.write(head)
        fp.truncate(total)
        for (lo, hi), chunk in zip(spans, parts):
            fp.seek(lo)
            fp.write(chunk)
    temp.replace(path)
    return path


def get_window(f, key):
    a = f["assets"][key]
    trans = a["proj:transform"]
    step, x0, y0 = trans[0], trans[2], trans[5]
    if f["properties"].get("proj:epsg", 32750) != 32750:
        raise ValueError("Unexpected source projection")
    H, W = a["proj:shape"]
    xi = ((XS - x0) // step).astype(int)
    yi = ((y0 - YS) // step).astype(int)
    xv = (xi >= 0) & (xi < W)
    yv = (yi >= 0) & (yi < H)
    sx, ex = xi[xv][0], xi[xv][-1] + 1
    sy, ey = yi[yv][0], yi[yv][-1] + 1
    if key == "scl":
        path = CACHE / (f["id"] + "-scl.tif")
        if not path.exists():
            path.write_bytes(get(a["href"]).content)
    else:
        path = local_tci(f)
    with rasterio.open(path) as ds:
        if ds.crs.to_epsg() != 32750:
            raise ValueError(f"{ds.crs}")
        a = ds.read(window=Window(int(sx), int(sy), int(ex - sx), int(ey - sy)))
    indices = np.ix_(yi[yv] - sy, xi[xv] - sx)
    win = a[:, indices[0], indices[1]]
    return np.flatnonzero(xv), np.flatnonzero(yv), win


def assemble(fs, key):
    is_scl = key == "scl"
    output = np.zeros((1 if is_scl else 3, HEIGHT, WIDTH), dtype=np.uint8)
    for f in sorted(fs, key=lambda x: "50LPR" not in x["id"]):
        xx, yy, roi = get_window(f, key)
        subset = output[:, yy[0] : yy[-1] + 1, xx[0] : xx[-1] + 1]
        use = np.all(subset == 0, axis=0)
        subset[:, use] = roi[:, use]
    return output


def metrics(pair, mask):
    scl = assemble(pair, "scl")[0]
    valid = np.isin(scl, VALID_CLEAR)
    return {
        "clearPct": round(float(valid[mask].mean() * 100), 4),
        "cloudShadowPct": round(float(np.isin(scl[mask], SCL_BAD).mean() * 100), 4),
        "otherOrMissingPct": round(
            float((~np.isin(scl[mask], VALID_CLEAR + SCL_BAD)).mean() * 100), 4
        ),
        "clearFullRectanglePct": round(float(valid.mean() * 100), 4),
        "classHistogram": np.bincount(scl[mask], minlength=12).tolist(),
    }


# These dates have 0.14% and 3.11% cloud/cirrus/cloud-shadow pixels inside the local mask.
SCENES = (
    (
        "2017-09-17",
        "sentinel-2-l2a",
        ("S2A_50LPR_20170917_0_L2A", "S2A_50LQR_20170917_0_L2A"),
    ),
    (
        "2025-08-31",
        "sentinel-2-c1-l2a",
        ("S2B_T50LPR_20250831T022436_L2A", "S2B_T50LQR_20250831T022436_L2A"),
    ),
)


def item(collection, item_id):
    cached = CACHE / (item_id + ".json")
    if not cached.exists():
        url = f"https://earth-search.aws.element84.com/v1/collections/{collection}/items/{item_id}"
        response = requests.get(url, timeout=(15, 60))
        response.raise_for_status()
        cached.write_text(json.dumps(response.json()), encoding="utf-8")
    with cached.open(encoding="utf-8") as fp:
        record = json.load(fp)
    if record["id"] != item_id:
        raise ValueError("Unexpected catalog item")
    return record


def main():
    global CACHE, OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mask",
        required=True,
        type=Path,
        help="PNG of the working area on the 2282 x 2556 grid; nonzero pixels are inside.",
    )
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--cache", type=Path, default=CACHE)
    args = parser.parse_args()
    CACHE, OUT = args.cache, args.output
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    mask = np.asarray(Image.open(args.mask)) > 0
    if mask.shape != (HEIGHT, WIDTH) or not np.any(mask):
        raise ValueError(
            "Mask must be a single-channel 2282 x 2556 raster with nonzero values."
        )
    data = {
        "crs": "EPSG:32750",
        "bounds": [WEST, SOUTH, EAST, NORTH],
        "pixelSizeM": 10,
        "width": WIDTH,
        "height": HEIGHT,
        "method": "Mosaik dua tile pada lintasan yang sama. Komposit warna alami bawaan Sentinel-2 Level-2A (kanal B4, B3, B2). Jendela piksel 10 m dipotong pada grid UTM 50S dan dikompresi menjadi JPEG. Awan dipertahankan. Mutu dinilai di dalam batas kerja Rontu memakai SCL 20 m. Kelas 4/5/6 menyatakan vegetasi/tanah/air. Kelas 3/8/9/10 menyatakan bayangan awan atau awan/sirus. Kelas lainnya masuk kategori lain/tanpa data.",
        "attribution": "Contains modified Copernicus Sentinel data (2017 and 2025). Distributed via Element 84 Earth Search.",
        "terms": "https://dataspace.copernicus.eu/terms-and-conditions",
        "scenes": [],
    }
    for key, (day, collection, item_ids) in zip(("before", "after"), SCENES):
        items = [item(collection, item_id) for item_id in item_ids]
        quality = metrics(items, mask)
        arr = assemble(items, "visual")
        image = Image.fromarray(arr.transpose(1, 2, 0))
        dest = OUT / (key + ".jpg")
        for q in (83, 78, 73, 68, 60):
            image.save(dest, quality=q, subsampling=2, optimize=True)
            if dest.stat().st_size < 1000000:
                break
        sources = [
            {
                "id": f["id"],
                "datetimeUtc": f["properties"]["datetime"],
                "url": next(x["href"] for x in f["links"] if x["rel"] == "self"),
                "rgb": f["assets"]["visual"]["href"],
                "scl": f["assets"]["scl"]["href"],
            }
            for f in items
        ]
        data["scenes"].append(
            dict(
                date=day,
                file=dest.name,
                quality=quality,
                items=sources,
                bytes=dest.stat().st_size,
                sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
            )
        )
        print(key, day, dest.stat().st_size, flush=True)
    (OUT / "optics.json").write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
