"""Independently check every published in-boundary pixel against its original tile."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
import rasterio
from rasterio.windows import Window


def validate(output, cache):
    m = json.loads((output / "manifest.json").read_text())
    s = json.loads((output / m["summary"]).read_text())
    mask = np.asarray(Image.open(output / m["mask"])) > 0
    grids = {}
    for entry in m["years"]:
        year = entry["year"]
        png = np.asarray(Image.open(output / entry["file"]))
        with rasterio.open(cache / f"50L_{year}.tif") as ds:
            assert ds.crs.to_string() == m["crs"] and ds.res == (10.0, 10.0)
            col, row = ~ds.transform * (m["transform"][2], m["transform"][5])
            assert abs(col - round(col)) < 1e-6 and abs(row - round(row)) < 1e-6
            raw = ds.read(1, window=Window(round(col), round(row), m["width"], m["height"]))
        np.testing.assert_array_equal(raw[mask], png[mask])
        assert not png[~mask].any()
        grids[year] = png
    for key, summary in s.items():
        left, right = (grids[int(year)] for year in key.split("-"))
        valid = mask & np.isin(left, m["validClasses"]) & np.isin(right, m["validClasses"])
        assert valid.sum() == summary["validPixels"]
        assert (valid & (left == 2) & (right != 2)).sum() == summary["lossPixels"]
        assert (valid & (right == 2) & (left != 2)).sum() == summary["gainPixels"]
        transition_total = sum(count for _, _, count in summary["transitions"])
        assert transition_total == summary["validPixels"]
    print(f"Verified {len(grids)} complete annual grids against source pixels and {len(s)} summaries.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    validate(args.output, args.cache)
