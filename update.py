"""Discover new or revised annual observations, then verify the staged publication."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from fetch_landcover import inventory

def read(name):
    return json.loads((Path("data") / name).read_text(encoding="utf-8"))

def verify():
    manifest = read("manifest.json")
    pair_rows = read(manifest["summary"])
    years = [item["year"] for item in manifest["years"]]
    for item in manifest["years"]:
        data = (Path("data") / item["file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError(f"Checksum mismatch for {item['year']}")
    for i, first in enumerate(years):
        for second in years[i:]:
            row = pair_rows[f"{first}-{second}"]
            if (row["treeAfterPixels"]-row["treeBeforePixels"] != row["gainPixels"]-row["lossPixels"]
                or row["netPixels"] != row["gainPixels"]-row["lossPixels"]
                or sum(t[2] for t in row["transitions"]) != row["validPixels"]
                or not 0 < row["validPixels"] <= row["insidePixels"]):
                raise ValueError(f"Invalid comparison: {first}, {second}")

if __name__ == "__main__":
    existing = {item["year"] for item in read("manifest.json")["years"]}
    if not existing.issubset({entry[0] for entry in inventory()}):
        raise RuntimeError("An existing source year is missing. Keep last good publication.")
    subprocess.run([sys.executable,"fetch_landcover.py","--boundary","boundary.geojson",
                    "--output","data","--cache","cache"],check=True)
    verify()
