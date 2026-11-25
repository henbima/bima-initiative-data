"""Download and validate the public MapBiomas Indonesia Collection 5 statistics.

Requires Python 3.10+ and requests. Running this file writes data/city.json
alongside it. Requests match the public platform's historical-area chart.
"""
import datetime
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "mapbiomas-cache"
API = "https://prd.plataforma.mapbiomas.org/api/v1/indonesia"
THEME = "0aae29e6-97a9-44a1-9dd6-632461bbd0d8"
SUBTHEME = "6390af34-4335-4940-ade5-467bfadc56ba"
LEGEND = "42402370-8f97-4c11-9307-8446c133b7e8"
CITY = "4-95-202"


def read_api(name, path, **params):
    CACHE.mkdir(exist_ok=True, parents=True)
    file = CACHE / (name + ".json")
    if file.is_file():
        return json.loads(file.read_bytes())
    for attempt in range(16):
        response = None
        try:
            response = requests.get(f"{API}/{path}", params=params, headers={"tenant-id": "mapbiomas"}, timeout=90)
            response.raise_for_status()
            result = response.json()
            if not result.get("taskID"):
                file.write_bytes(response.content)
                return result
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError):
            if attempt == 15 or (response is not None and 400 <= response.status_code < 500 and response.status_code != 429):
                raise
        time.sleep(min(6 + attempt * 3, 35))
    raise RuntimeError(f"Provider could not finish {name}")


def flatten(items, parent=None):
    for item in items:
        yield {"id": item["pixelValue"], "label": item["name"]["id-ID"], "parent": parent, "color": item["color"]}
        yield from flatten(item.get("children", []), item["pixelValue"])


def children(territory, category):
    data = read_api(f"{territory['id']}-children-{category}", "territories", parentId=territory["id"], categoryId=category, pageSize=100)
    assert data["numberOfPages"] == 1
    return data["territories"]


def collect_area(area, years, classes, subtheme, legend):
    territory, level, parent = area
    response = read_api(territory["id"] + "-coverage", "statistics/area",
                        subthemeKey=subtheme, legendKey=legend, pixelValue=[c["id"] for c in classes],
                        territoryId=territory["id"], spatialMethod="union", year=years)
    observations = sorted(response["statistic"], key=lambda x: x["year"])
    if response["unit"] != "ha" or [i["year"] for i in observations] != [[y] for y in years]:
        raise ValueError(f"Missing area or year for {territory['name']}")
    values = {c["id"]: [] for c in classes}
    roots = {c["id"] for c in classes if c["parent"] is None}
    for item in observations:
        vals = {data["pixelValue"]: data["value"] for data in item["items"]}
        if vals.keys() != values.keys() or any(not math.isfinite(x) or x < 0 for x in vals.values()):
            raise ValueError(f"Invalid area class in {territory['name']} {item['year']}")
        if abs(sum(vals[n] for n in roots) - item["total"]) > .01:
            raise ValueError(f"Invalid territory class sum for {territory['name']}")
        for code, series in values.items():
            subcodes = [c["id"] for c in classes if c["parent"] == code]
            if subcodes and abs(sum(vals[i] for i in subcodes) - vals[code]) > .01:
                raise ValueError(f"Incomplete class {code} for {territory['name']}")
            series.append(round(vals[code], 2))
    print(f"{territory['geocode']} {territory['name']}", flush=True)
    return {"id": territory["geocode"], "level": level, "name": territory["name"],
            "parent": parent, "areaHa": round(response["territoryAreaHa"], 2), "series": values}


def main():
    subtheme = read_api("coverage-subtheme", f"themes/subthemes/{SUBTHEME}")["subtheme"]
    asset = subtheme["asset"]
    theme = read_api("coverage-theme", f"themes/{THEME}")["theme"]
    legend = read_api("coverage-legend", f"legends/{LEGEND}", aggregated="true")["legend"]
    city = read_api("city-boundary", f"territories/{CITY}")["territory"]
    years = asset["years"]
    assert theme["badges"] == ["col. 5"] and city["geocode"] == "5272"
    assert years == list(range(1990, 2026)) and asset["scale"] == 30
    classes = list(flatten(legend["items"]))
    districts = sorted(children(city, 126), key=lambda a: a["geocode"])
    assert len(districts) == 5
    areas = [(city, "kota", None)]
    for d in districts:
        areas.append((d, "kecamatan", city["geocode"]))
        for v in sorted(children(d, 127), key=lambda a: a["geocode"]):
            assert v["geocode"].startswith(d["geocode"])
            areas.append((v, "kelurahan", d["geocode"]))
    assert len({t["geocode"] for t, level, parent in areas}) == len(areas)
    def collect(a):
        return collect_area(a, years, classes, subtheme["key"], legend["key"])
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(collect, areas))
    source = {
        "name": "MapBiomas Indonesia Koleksi 5, Tutupan dan Penggunaan Lahan Tahunan Indonesia 1990–2025",
        "portal": "https://plataforma.mapbiomas.org/coverage/coverage_lclu?t%5BregionKey%5D=indonesia",
        "terms": "https://landy.mapbiomas.id/id/termsofuse", "license": "CC BY-SA",
        "api": API + "/statistics/area",
        "asset": asset["assetId"], "resolutionM": asset["scale"], "unit": "ha",
        "boundary": "Kementerian Dalam Negeri, batas administratif 2023 sebagaimana digunakan MapBiomas Indonesia",
        "retrieved": datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
        "method": "Luas kelas tahunan dihitung oleh platform untuk setiap poligon. Seluruh tahun memakai satu batas wilayah yang sama. Kelas induk menjumlahkan subkelas. Luas dihitung secara terpisah per wilayah, sehingga penjumlahan batas anak dapat berbeda dari batas induk."
    }
    output = ROOT / "data" / "city.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({"years": years, "classes": classes, "areas": results, "source": source},
                                 ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(len(results), "territories;", output.stat().st_size, "bytes", flush=True)


if __name__ == "__main__":
    main()
