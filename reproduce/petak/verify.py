"""Independently verify ranked cell metrics by cropping each selected square."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image


def read(p):
    return json.loads(p.read_text(encoding="utf-8"))


def verify(root, detail):
    cfg=read(root/"manifest.json")
    info=read(detail/"index.json")
    native={y["year"]:np.asarray(Image.open(root/y["file"])) for y in cfg["years"]}
    allowed=cfg["validClasses"]
    forest=cfg.get("forestClasses") or [cfg["treeClass"]]
    mask=np.asarray(Image.open(root/cfg["mask"]))>0
    step,_,west,_,_,north=cfg["transform"]
    xs=west+(np.arange(cfg["width"])+.5)*step
    ys=north-(np.arange(cfg["height"])+.5)*step
    visited=0
    for year, filename in info["files"].items():
        first=native[int(year)]
        for end, pair in read(detail/filename).items():
            second=native[int(end)]
            for rank, row in enumerate(pair["topLoss"]):
                box=info["cells"][row["cell"]]
                x=np.flatnonzero((xs>=box["west"]) & (xs<box["east"]))
                y=np.flatnonzero((ys>=box["south"]) & (ys<box["north"]))
                sl=(slice(y[0],y[-1]+1),slice(x[0],x[-1]+1))
                a,b=first[sl],second[sl]
                good=mask[sl] & np.isin(a,allowed) & np.isin(b,allowed)
                tr_a,tr_b=np.isin(a,forest),np.isin(b,forest)
                lost=good & tr_a & ~tr_b
                assert row["loss"] == lost.sum()
                assert row["gain"] == (good & tr_b & ~tr_a).sum()
                assert row["valid"] == good.sum()
                assert row["inside"] == mask[sl].sum()
                classes,counts=np.unique(b[lost],return_counts=True)
                assert dict(row["dest"])==dict(zip(classes,counts))
                i,j=int((north-row["y"])/step),int((row["x"]-west)/step)
                assert first[i,j] in forest and second[i,j] not in forest and second[i,j] in allowed
                if rank: assert row["loss"]<=pair["topLoss"][rank-1]["loss"]
                visited+=1
    print(f"{root}: {visited} cell comparisons independently reconciled.")

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data",type=Path)
    parser.add_argument("detail",type=Path)
    args=parser.parse_args()
    verify(args.data,args.detail)

