"""Rebuild native 10 m Bima land-cover grids from the public source archive.

Install requirements.txt, then run:
python fetch_landcover.py --boundary input.geojson --output data --cache cache
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import time
import xml.etree.ElementTree as ET

import requests

BUCKET = "https://io-10m-annual-lulc.s3.us-west-2.amazonaws.com/"
ESRI_TILES = "https://lulctimeseries.blob.core.windows.net/lulctimeseriesv003"
ESRI_CATALOG = "https://ic.imagery1.arcgis.com/arcgis/rest/services/Sentinel2_10m_LandCover/ImageServer"
LICENSE = "https://creativecommons.org/licenses/by/4.0/"
TILE = "50L"
VALID = (1, 2, 4, 5, 7, 8, 9, 11)
METHOD_VERSION = "native-grid-v1"


def inventory():
    listing = requests.get(BUCKET, params={"list-type": "2", "prefix": TILE + "_"}, timeout=45)
    listing.raise_for_status()
    root = ET.fromstring(listing.content)
    if root.findtext("{*}IsTruncated") == "true":
        raise RuntimeError("Unexpected truncated tile inventory")
    result = []
    for item in root.findall("{*}Contents"):
        key = item.findtext("{*}Key")
        match = re.fullmatch(r"50L_(\d{4})\.tif", key)
        if match:
            result.append((int(match[1]), key, int(item.findtext("{*}Size")), item.findtext("{*}ETag").strip('"')))
    if not result:
        raise RuntimeError("Archive has no annual rasters for tile " + TILE)
    # Esri's public download archive can be ahead of the AWS mirror. All its
    # 2024+ GeoTIFF filenames use the calendar year's final day.
    latest = max(asset[0] for asset in result)
    response = requests.get(ESRI_CATALOG + "/query", params={
        "f": "json", "where": f"Category = 1 AND Year > {latest}", "geometry": "118.81,-8.51",
        "inSR": 4326, "geometryType": "esriGeometryPoint", "spatialRel": "esriSpatialRelIntersects",
        "outFields": "Year", "returnGeometry": "false"}, timeout=45)
    response.raise_for_status()
    record = response.json()
    if "features" not in record or record.get("exceededTransferLimit"):
        raise ValueError("Unexpected Esri raster catalog response")
    for year in sorted({int(feature["attributes"]["Year"]) for feature in record["features"]}):
        direct = f"{ESRI_TILES}/lc{year}/{TILE}_{year}0101-{year}1231.tif"
        published = requests.head(direct, timeout=45)
        if published.status_code == 404:
            # The catalog can announce a map before the public GeoTIFF exists.
            continue
        published.raise_for_status()
        result.append((year, direct, int(published.headers["Content-Length"]), published.headers["ETag"].strip('"')))
    return sorted(result)


def download(asset, cache):
    year, key, size, etag = asset
    path = cache / f"{TILE}_{year}.tif"
    tag_path = path.with_suffix(".etag")
    if path.exists() and path.stat().st_size == size and tag_path.exists() and tag_path.read_text() == etag:
        return path
    for attempt in range(3):
        try:
            url = key if key.startswith(ESRI_TILES + "/") else BUCKET + key
            with requests.get(url, stream=True, timeout=(30, 90)) as response:
                response.raise_for_status()
                if response.headers.get("ETag", "").strip('"') != etag:
                    raise ValueError(f"Source tag changed during download: {key}")
                with tempfile.NamedTemporaryFile(dir=cache, delete=False, suffix=".partial") as output:
                    partial = Path(output.name)
                    for chunk in response.iter_content(1024 * 1024):
                        output.write(chunk)
            if partial.stat().st_size != size:
                raise ValueError(f"Incomplete download for {key}")
            partial.replace(path)
            tag_path.write_text(etag)
            print(f"Cached {year} ({size:,} bytes)", flush=True)
            return path
        except (OSError, ValueError, requests.RequestException):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
        finally:
            if "partial" in locals():
                partial.unlink(missing_ok=True)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pair_summary(left, right, mask):
    import numpy as np
    valid = mask & np.isin(left, VALID) & np.isin(right, VALID)
    counts = np.bincount(left[valid].astype("int16") * 12 + right[valid], minlength=144).reshape(12, 12)
    total = int(counts.sum())
    if total == 0:
        raise ValueError("No comparable pixels")
    before = int(counts[2].sum())
    after = int(counts[:, 2].sum())
    lost = before - int(counts[2, 2])
    gained = after - int(counts[2, 2])
    assert after - before == gained - lost
    return dict(validPixels=total, insidePixels=int(mask.sum()), treeBeforePixels=before,
                treeAfterPixels=after, gainPixels=gained, lossPixels=lost, netPixels=gained-lost,
                transitions=[[a, b, int(counts[a, b])] for a in VALID for b in VALID if counts[a, b]])


def build(boundary, output, cache, assets):
    import numpy as np
    from PIL import Image
    import rasterio
    from rasterio.features import geometry_mask, bounds
    from rasterio.transform import from_origin
    from rasterio.warp import transform_geom, transform, transform_bounds, reproject, Resampling

    source = json.loads(boundary.read_text(encoding="utf-8-sig"))
    geoms = [f["geometry"] for f in source["features"]] if source["type"] == "FeatureCollection" else [source["geometry"]]
    crs = "EPSG:32750"
    projected = [transform_geom("EPSG:4326", crs, geom) for geom in geoms]
    extents = [bounds(geom) for geom in projected]
    west = math.floor(min(extent[0] for extent in extents) / 10) * 10
    east = math.ceil(max(extent[2] for extent in extents) / 10) * 10
    south = math.floor(min(extent[1] for extent in extents) / 10) * 10
    north = math.ceil(max(extent[3] for extent in extents) / 10) * 10
    grid = from_origin(west, north, 10, 10)
    height, width = (north - south) // 10, (east - west) // 10
    mask = geometry_mask(projected, (height, width), grid, invert=True, all_touched=False)
    if not mask.any():
        raise RuntimeError("Boundary has no inside pixels")
    Image.fromarray(mask.astype("uint8") * 255).save(output / "mask.png", optimize=True)
    lon, lat = transform(crs, "EPSG:4326", [west, east, east, west], [north, north, south, south])
    manifest = dict(width=width, height=height, crs=crs, transform=list(grid)[:6],
                    bounds4326=transform_bounds(crs, "EPSG:4326", west, south, east, north),
                    corners4326=list(map(list, zip(lon, lat))), mask="mask.png", pixelHa=0.01, treeClass=2,
                    invalidClasses=[0, 10], validClasses=list(VALID), years=[], boundary="boundary.geojson",
                    boundarySha256=sha256(boundary), attribution="Impact Observatory, Microsoft, and Esri",
                    archive=BUCKET, supplementaryArchive=ESRI_TILES, license=LICENSE,
                    summary="summary.json", methodVersion=METHOD_VERSION,
                    processedUtc=datetime.now(timezone.utc).isoformat())
    shutil.copyfile(boundary, output / "boundary.geojson")
    grids = {}
    for year, key, _, etag in assets:
        source_file = cache / f"{TILE}_{year}.tif"
        arr = np.zeros((height, width), dtype="uint8")
        with rasterio.open(source_file) as dataset:
            source_bounds = transform_bounds(dataset.crs, crs, *dataset.bounds)
            if (source_bounds[0] > west or source_bounds[1] > south or source_bounds[2] < east or source_bounds[3] < north):
                raise ValueError(f"Tile {key} does not cover full extent")
            reproject(rasterio.band(dataset, 1), arr, src_transform=dataset.transform, src_crs=dataset.crs,
                      dst_transform=grid, dst_crs=crs, src_nodata=dataset.nodata, dst_nodata=0,
                      resampling=Resampling.nearest, num_threads=2)
        arr[~mask] = 0
        classes = set(np.unique(arr).tolist())
        if classes - set(VALID) - {0, 10} or not np.isin(arr, VALID).any():
            raise ValueError(f"Unexpected classification in {year}: {classes}")
        png = output / f"{year}.png"
        Image.fromarray(arr).save(png, optimize=True)
        source_url = key if key.startswith(ESRI_TILES + "/") else BUCKET + key
        manifest["years"].append(dict(year=year, file=png.name, source=source_url, sourceETag=etag,
                                      sha256=sha256(png), bytes=png.stat().st_size))
        grids[year] = arr
    summaries = {f"{first}-{second}":pair_summary(grids[first], grids[second], mask)
                 for first in grids for second in grids if first <= second}
    write_json(output / "summary.json", summaries)
    write_json(output / "manifest.json", manifest)
    print(f"{width}×{height} grid, {int(mask.sum())} inside pixels; {len(assets)} years", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--years", type=int, nargs="+", help="Select years, default all published years")
    parser.add_argument("--download-only", action="store_true")
    args = parser.parse_args()
    if not args.download_only and not args.boundary.is_file():
        parser.error("A source boundary GeoJSON is required.")
    assets = inventory()
    if args.years:
        assets = [asset for asset in assets if asset[0] in args.years]
        if set(args.years) != {asset[0] for asset in assets}:
            parser.error("One or more requested years are absent from the archive.")
    existing = args.output / "manifest.json"
    if not args.download_only and existing.exists():
        current = json.loads(existing.read_text(encoding="utf-8"))
        previous = [(item["year"], item["sourceETag"]) for item in current["years"]]
        expected = [(year, etag) for year, _, _, etag in assets]
        files = [current["mask"], current["summary"], current["boundary"]]
        files.extend(item["file"] for item in current["years"])
        if (previous == expected and current.get("methodVersion") == METHOD_VERSION
                and current["boundarySha256"] == sha256(args.boundary)
                and all((args.output / name).is_file() for name in files)):
            print("No new source revision or boundary. Current publication remains available.")
            return
    args.cache.mkdir(exist_ok=True, parents=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda asset: download(asset, args.cache), assets))
    if args.download_only:
        return
    args.output.parent.mkdir(exist_ok=True, parents=True)
    with tempfile.TemporaryDirectory(dir=args.output.parent) as stage:
        staging = Path(stage)
        build(args.boundary, staging, args.cache, assets)
        # The website deploys this complete output as one immutable publication.
        args.output.mkdir(exist_ok=True)
        for path in sorted(staging.iterdir(), key=lambda p: p.name == "manifest.json"):
            path.replace(args.output / path.name)


if __name__ == "__main__":
    main()
