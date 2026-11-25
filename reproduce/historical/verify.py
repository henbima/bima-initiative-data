"""Cross-check output PNGs against native GeoTIFF pixels and all comparisons."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.transform import xy
from rasterio.warp import transform

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path(__file__).parent/'data')
    parser.add_argument('--source',type=Path,default=Path(__file__).parent/'originals')
    args=parser.parse_args()
    data=args.output
    manifest=json.loads((data/'manifest.json').read_text(encoding='utf-8'))
    summary=json.loads((data/'summary.json').read_text(encoding='utf-8'))
    mask=np.array(Image.open(data/manifest['mask']))>0
    r,c=np.nonzero(mask)
    random=np.random.default_rng(20261125).choice(len(r),256,replace=False)
    rows,cols=r[random],c[random]
    tr=rasterio.Affine(*manifest['transform'])
    xx,yy=xy(tr,rows,cols)
    lons,lats=transform(manifest['crs'],'EPSG:4326',xx,yy)
    samples=list(zip(lons,lats))
    years={}
    for member,items in itertools.groupby(manifest['years'],key=lambda y:y['member']):
        items=list(items)
        with rasterio.open(args.source/member) as native:
            source=np.array(list(native.sample(samples,indexes=[i['band'] for i in items])))
        for i,item in enumerate(items):
            file=data/item['file']
            assert hashlib.sha256(file.read_bytes()).hexdigest()==item['sha256']
            arr=np.array(Image.open(file))
            np.testing.assert_array_equal(arr[rows,cols],source[:,i])
            assert np.all(arr[~mask]==0)
            years[item['year']]=arr[mask]
    tree={y:np.isin(arr,manifest['forestClasses']) for y,arr in years.items()}
    valid={y:np.isin(arr,manifest['validClasses']) for y,arr in years.items()}
    for (a,b) in itertools.combinations_with_replacement(years.keys(),2):
        common=valid[a]&valid[b]
        before,after=tree[a]&common,tree[b]&common
        expected=summary[f'{a}-{b}']
        actual=dict(insidePixels=int(mask.sum()),validPixels=int(common.sum()),treeBeforePixels=int(before.sum()),
                    treeAfterPixels=int(after.sum()),lossPixels=int((before&~after).sum()),
                    gainPixels=int((~before&after).sum()),netPixels=int(after.sum())-int(before.sum()))
        assert all(expected[key]==value for key,value in actual.items()), f'{a}-{b}'
        assert sum(x[2] for x in expected['transitions'])==int(common.sum())
    print(f"{len(samples)} native sample locations × {len(years)} dates agree. All {len(summary)} pairwise valid areas, forest areas, net, gain and loss match.")
if __name__=='__main__':
    main()
