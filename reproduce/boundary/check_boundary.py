"""Recheck the working Rontu polygon against the named MapBiomas watershed.

Run: python check_boundary.py --output ./data
Requires requests, shapely>=2.1, pyproj. Only public read-only requests are sent.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path

import requests
import shapely
from pyproj import Transformer
from shapely.geometry import shape


BASE = "https://prd.plataforma.mapbiomas.org/api/v1/indonesia"
DAS = "4-179-2597"
ARCGIS = ("https://services-ap1.arcgis.com/zddIc5NlxDyZbzsT/ArcGIS/rest/services/"
          "Batas_DAS_KLHK_se_Indonesia/FeatureServer/0/query?objectIds=4779"
          "&outFields=FID,nama_das,luas_ha,kd_das,wil_kerja&outSR=4326&returnGeometry=true&f=geojson")
LAEA = "+proj=laea +lat_0=-8.5 +lon_0=118.8 +datum=WGS84 +units=m +no_defs"


def sha(content):
    return hashlib.sha256(content).hexdigest()


def fetch(session, path, **params):
    response = session.get(BASE + "/" + path, params=params, headers={"tenant-id": "mapbiomas"}, timeout=60)
    response.raise_for_status()
    return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent)
    output = parser.parse_args().output
    output.mkdir(parents=True, exist_ok=True)
    with requests.Session() as session:
        working = session.get(ARCGIS, timeout=60)
        working.raise_for_status()
        record = fetch(session, "territories/" + DAS)
        geometry = fetch(session, "territories/geometry", territoryId=DAS, simplify="false")
        area = fetch(session, "statistics/area", territoryId=DAS, subthemeKey="coverage-copia-p0wwe2_coverage-wdzhq4",
                     legendKey="coverage-kotjog", pixelValue=[1, 3], year=2025)
    ws = record.json()["territory"]
    cat = ws["category"]
    raw_shape = geometry.json()["geometry"]
    primary = working.json()["features"][0]
    attributes = primary["properties"]
    if (ws["name"], ws["categoryId"], attributes["kd_das"]) != ("RONTU", 179, "DAS420446"):
        raise ValueError("Source territory identifiers differ")
    project = Transformer.from_crs("EPSG:4326", LAEA, always_xy=True)
    a, b = [shapely.transform(shape(g), project.transform, interleaved=False) for g in (primary["geometry"], raw_shape)]
    if not all(g.is_valid and not g.is_empty and g.geom_type in ("Polygon", "MultiPolygon") for g in (a, b)):
        raise ValueError("Invalid geometry for comparison")
    overlap = a.intersection(b).area
    union = a.union(b).area
    feature = {"type": "Feature", "properties": {"name": ws["name"], "providerId": DAS,
               "provider": f"MapBiomas Indonesia, {cat['source']} {cat['year']}"}, "geometry": raw_shape}
    geo = json.dumps(feature, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    (output / "rontu-mapbiomas.geojson").write_bytes(geo)
    result = {
        "checked": datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
        "method": "Irisan dan gabungan kedua poligon asli dihitung dalam proyeksi Lambert Azimuthal Equal Area lokal. Persentase memakai luas hasil proyeksi ini; luas katalog dicatat terpisah.",
        "areaCRS": LAEA,
        "working": {
            "name": attributes["nama_das"].strip() or None, "id": attributes["kd_das"], "objectId": attributes["FID"],
            "layer": "Batas_DAS_KLHK_se_Indonesia", "url": working.url, "responseSha256": sha(working.content),
            "catalogHa": attributes["luas_ha"], "geometryHa": round(a.area / 10000, 4),
        },
        "reference": {
            "name": ws["name"], "id": ws["id"], "featureId": ws["featureId"], "category": cat["name"]["id-ID"],
            "source": cat["source"], "year": cat["year"], "dataset": cat["featureCollectionId"],
            "publicHeaders": {"tenant-id": "mapbiomas"}, "recordUrl": record.url, "geometryUrl": geometry.url,
            "geometryResponseSha256": sha(geometry.content), "geometryFile": "rontu-mapbiomas.geojson",
            "geometryFileSha256": sha(geo), "reportedHa": area.json()["territoryAreaHa"],
            "geometryHa": round(b.area / 10000, 4),
        },
        "intersectionHa": round(overlap / 10000, 4), "unionHa": round(union / 10000, 4),
        "intersectionShareOfWorking": round(overlap / a.area, 8),
        "intersectionShareOfReference": round(overlap / b.area, 8),
        "intersectionOverUnion": round(overlap / union, 8),
    }
    target = output / "rontu-boundary-check.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target, result["intersectionShareOfWorking"], result["intersectionOverUnion"])


if __name__ == "__main__":
    main()
