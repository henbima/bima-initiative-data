"""Rebuild the historical case from the NASA and ASF public services."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
import json
import math
import time

import requests


ROOT = Path(__file__).resolve().parent
WITA = timezone(timedelta(hours=8))
START = datetime(2021, 2, 1, tzinfo=WITA)
CASE_START = datetime(2021, 2, 2, 13, 45, tzinfo=WITA)
CASE_END = datetime(2021, 2, 2, 19, 0, tzinfo=WITA)
RAIN = "https://gis.earthdata.nasa.gov/portal/rest/services/GESDISC/GPM_3IMERGHH/ImageServer"
RADAR = "https://api.daac.asf.alaska.edu/services/search/param"
CELLS = [
    ("kota", "Sel Kota Bima", 118.75, -8.45),
    ("tenggara", "Sel tenggara Kota Bima", 118.85, -8.55),
]
SOURCE_EVENT = "https://siaga.ntbprov.go.id/info-kebencanaan/bencana-banjir-3-kabupaten-kota-di-provinsi-ntb"
SOURCE_BAPPEDA = "https://bappeda.bimakota.go.id/upload/download/1753668548_00e2264c7b94e7e04110.pdf"


def json_request(url, params):
    for attempt in range(3):
        try:
            response = requests.get(url, params=params, timeout=(12, 55))
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                raise ValueError(str(data["error"]))
            return data
        except (ValueError, requests.RequestException):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def stamp(dt):
    return int(dt.timestamp() * 1000)


def rain_slice(job):
    key, lon, lat, start = job
    times = {stamp(start + timedelta(minutes=i * 30)) for i in range(16)}
    point = json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}})
    params = {
        "geometryType": "esriGeometryPoint", "geometry": point,
        "f": "json", "time": f"{min(times)},{max(times)}",
        "returnFirstValueOnly": "false", "outFields": "StdTime,Name",
        "interpolation": "RSP_NearestNeighbor",
    }
    rows = json_request(RAIN + "/getSamples", params)["samples"]
    values = {}
    for row in rows:
        ms = row["attributes"]["stdtime"]
        if ms not in times or ms in values:
            raise ValueError("Unexpected or duplicate IMERG time")
        if abs(row["location"]["x"] - lon) > 1e-5 or abs(row["location"]["y"] - lat) > 1e-5:
            raise ValueError("Unexpected IMERG position")
        value = row["value"]
        if value in ("NoData", "", None):
            continue
        rate = float(value)
        if not math.isfinite(rate) or rate < 0:
            raise ValueError("Unexpected rate")
        values[ms] = round(rate, 4)
    return key, values


def rain_data():
    rates = {key: {} for key, *_ in CELLS}
    jobs = [(key, lon, lat, START + timedelta(hours=h)) for key, _, lon, lat in CELLS for h in range(0, 72, 8)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for key, data in pool.map(rain_slice, jobs):
            rates[key].update(data)
    dates = [START + timedelta(minutes=30 * i) for i in range(144)]
    series = []
    for key, label, lon, lat in CELLS:
        samples = [rates[key].get(stamp(dt)) for dt in dates]
        if all(value is None for value in samples):
            raise ValueError(f"No valid samples for {key}")
        days = []
        for offset in range(0, 144, 48):
            window = samples[offset:offset + 48]
            valid = sum(x is not None for x in window)
            days.append({"date": dates[offset].date().isoformat(), "valid": valid,
                         "total_mm": round(sum(window) * 0.5, 2) if valid == 48 else None})
        series.append({"id": key, "label": label, "longitude": lon, "latitude": lat,
                       "rates_mm_h": samples, "valid": sum(x is not None for x in samples),
                       "daily": days})
    return {"source": RAIN, "product": "GPM IMERG Final V07", "variables": "precipitation",
            "source_description": "https://gis.earthdata.nasa.gov/portal/home/item.html?id=cfa9a890b89b49d884871567844e9080",
            "grid_degrees": 0.1, "slot_minutes": 30,
            "timestamps_wita": [dt.isoformat(timespec="minutes") for dt in dates], "cells": series}


def radar_data():
    params = {"platform": "S1", "processingLevel": "GRD_HD", "intersectsWith": "POINT(118.73 -8.46)",
              "start": "2021-01-26T00:00:00Z", "end": "2021-02-10T00:00:00Z", "output": "geojson"}
    scenes = []
    for feature in json_request(RADAR, params)["features"]:
        p = feature["properties"]
        begin = datetime.fromisoformat(p["startTime"].replace("Z", "+00:00")).astimezone(WITA)
        until = datetime.fromisoformat(p["stopTime"].replace("Z", "+00:00")).astimezone(WITA)
        scenes.append({"id": p["sceneName"], "start_wita": begin.isoformat(), "end_wita": until.isoformat(),
                       "direction": p["flightDirection"], "path": p["pathNumber"],
                       "overlaps_local_report_window": begin <= CASE_END and until >= CASE_START})
    extent = [118.68, -8.61, 118.93, -8.33]
    west, south, east, north = extent
    polygon = f"POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))"
    regional = dict(params, intersectsWith=polygon, start="2021-02-01T16:00:00Z", end="2021-02-02T15:59:59Z")
    day_search = json_request(RADAR, regional)
    return {"source_query": RADAR + "?" + urlencode(params), "query_point": [118.73, -8.46], "product": "Sentinel-1 GRD_HD",
            "event_day_search": {"bbox": extent, "date_wita": "2021-02-02",
                                 "scene_count": len(day_search["features"]), "source_query": RADAR + "?" + urlencode(regional)},
            "scenes": sorted(scenes, key=lambda i: i["start_wita"])}


def main():
    radar = radar_data()
    rain = rain_data()
    result = {
        "id": "bima-2021-02-02", "date": "2021-02-02", "timezone": "Asia/Makassar",
        "sources": {"chronology": SOURCE_EVENT, "station": SOURCE_BAPPEDA},
        "timeline": [
            {"wita": "13.45", "place": "Kota Bima", "detail": "Hujan sedang hingga deras mulai dilaporkan."},
            {"wita": "14.00", "place": "Dara", "detail": "Air dari arah perbukitan menggenangi jalan."},
            {"wita": "16.07", "place": "Ule", "detail": "Sungai Te meluap. Kedalaman yang dilaporkan di beberapa lingkungan berkisar 10–100 cm."},
            {"wita": "18.15", "place": "Kota Bima", "detail": "Batas akhir periode hujan dalam kronologi SiAGA."},
            {"wita": "19.00", "place": "Jatiwangi", "detail": "Genangan sudah surut menurut laporan setempat."},
        ],
        "station": {"source": SOURCE_BAPPEDA, "reported_mm": 56.4, "name": "Stasiun BMKG Bima",
                    "note": "Bappeda mengutip angka 56,4 mm pada kejadian ini. Dokumen tidak merinci periode akumulasi dan koordinat pos pada bagian tersebut."},
        "rain": rain, "radar": radar
    }
    target = ROOT / "event-2021-02-02.json"
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(target)
    print(len(radar["scenes"]), [(c["id"], c["valid"], c["daily"]) for c in rain["cells"]])


if __name__ == "__main__":
    main()
