"""Build the historical Bima GLC_FCS30D series in an aligned 30 m UTM grid."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.features import bounds, geometry_mask
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds, transform_geom
from rasterio.windows import Window

ROOT = Path(__file__).resolve().parent
DATASET = "https://doi.org/10.5281/zenodo.15063683"
GUIDE = "https://zenodo.org/records/15063683/files/GLC_FCS30D%20UserGuides.pdf"
PAPER = "https://doi.org/10.5194/essd-16-1353-2024"
ARCHIVE = "https://zenodo.org/records/15063683/files/GLC_FCS30D_19852022maps_E110-E115.zip"
CLASSES = {
    10:"Pertanian tadah hujan",11:"Pertanian tanaman herba",12:"Pertanian tanaman pohon atau perdu",
    20:"Pertanian beririgasi",51:"Hutan daun lebar selalu hijau terbuka",
    52:"Hutan daun lebar selalu hijau rapat",61:"Hutan daun lebar gugur terbuka",
    62:"Hutan daun lebar gugur rapat",71:"Hutan daun jarum selalu hijau terbuka",
    72:"Hutan daun jarum selalu hijau rapat",81:"Hutan daun jarum gugur terbuka",
    82:"Hutan daun jarum gugur rapat",91:"Hutan campuran terbuka",92:"Hutan campuran rapat",
    120:"Semak belukar",121:"Semak selalu hijau",122:"Semak gugur",130:"Padang rumput",
    140:"Lumut kerak dan lumut",150:"Vegetasi jarang",152:"Semak jarang",153:"Vegetasi herba jarang",
    181:"Rawa berpohon",182:"Rawa berumput",183:"Dataran tergenang",184:"Lahan salin",
    185:"Mangrove",186:"Rawa asin",187:"Dataran pasang surut",190:"Permukaan kedap air",
    200:"Lahan terbuka",201:"Lahan terbuka padat",202:"Lahan terbuka lepas",210:"Badan air",220:"Es atau salju permanen"}
FOREST = (51,52,61,62,71,72,81,82,91,92)
NOMINAL = [1985,1990,1995]
CRS = "EPSG:32750"

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save_json(path, obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")

def metrics(before, after, inside):
    valid=inside & np.isin(before,list(CLASSES)) & np.isin(after,list(CLASSES))
    pair_counts=np.bincount(before[valid].astype(np.uint16)*256+after[valid],minlength=256*256).reshape(256,256)
    if not valid.any():
        raise ValueError("Empty common valid footprint")
    a=int(pair_counts[list(FOREST),:].sum())
    b=int(pair_counts[:,list(FOREST)].sum())
    stay=int(pair_counts[np.ix_(FOREST,FOREST)].sum())
    rows,cols=np.nonzero(pair_counts)
    transitions=[[int(x),int(y),int(pair_counts[x,y])] for x,y in zip(rows,cols)]
    loss=a-stay
    gain=b-stay
    assert gain-loss==b-a and sum(row[2] for row in transitions)==valid.sum()
    return dict(validPixels=int(valid.sum()),insidePixels=int(inside.sum()),treeBeforePixels=a,treeAfterPixels=b,
                gainPixels=gain,lossPixels=loss,netPixels=b-a,transitions=transitions)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boundary',type=Path,default=ROOT.parent/'bima-boundary/klhk-das420446.geojson')
    parser.add_argument('--source',type=Path,default=ROOT/'originals')
    parser.add_argument('--output',type=Path,default=ROOT/'data')
    args=parser.parse_args()
    out=args.output
    out.mkdir(parents=True,exist_ok=True)
    doc=json.loads(args.boundary.read_text(encoding='utf-8-sig'))
    geo=[f['geometry'] for f in doc['features']] if doc['type']=='FeatureCollection' else [doc['geometry']]
    geom=[transform_geom('EPSG:4326',CRS,g) for g in geo]
    bbox=[bounds(g) for g in geom]
    w=math.floor(min(b[0] for b in bbox)/30)*30
    s=math.floor(min(b[1] for b in bbox)/30)*30
    e=math.ceil(max(b[2] for b in bbox)/30)*30
    n=math.ceil(max(b[3] for b in bbox)/30)*30
    width=(e-w)//30
    height=(n-s)//30
    grid=from_origin(w,n,30,30)
    mask=geometry_mask(geom,out_shape=(height,width),transform=grid,invert=True,all_touched=False)
    Image.fromarray(mask.astype('uint8')*255).save(out/'mask.png',optimize=True)
    row,col=np.indices((height,width))
    xs,ys=w+30*(col+.5),n-30*(row+.5)
    back=Transformer.from_crs(CRS,4326,always_xy=True)
    lons,lats=back.transform(xs,ys)
    corners=[list(back.transform(x,y)) for x,y in [(w,n),(e,n),(e,s),(w,s)]]
    manifest=dict(title='Arsip Landsat GLC_FCS30D',source=DATASET,archive=ARCHIVE,
        attribution='Liangyun Liu, Xiao Zhang, dan Zhehua Li (2025), GLC_FCS30D v2, AIRCAS.',
        license='https://creativecommons.org/licenses/by/4.0/',guide=GUIDE,paper=PAPER,
        sourceTile='E115S5',width=width,height=height,crs=CRS,transform=list(grid)[:6],
        bounds4326=list(transform_bounds(CRS,4326,w,s,e,n)),corners4326=corners,
        resolutionM=30,pixelHa=0.09,mask='mask.png',summary='summary.json',
        validClasses=list(CLASSES),classNames=CLASSES,forestClasses=list(FOREST),invalidClasses=[0,250,255],
        boundarySha256=sha(args.boundary),years=[],methodVersion='nearest-utm30-pixel-center-v1',
        definition='Hutan mencakup kelas hutan terbuka dan rapat pada kode 51–92. Mangrove, rawa dan kebun berkayu memiliki kelas tersendiri.',
        temporalNote='1985, 1990, dan 1995 adalah tahun tengah jendela pengamatan lima tahunan (±2 tahun). Seri tahunan tersedia dari 2000 sampai 2022.')
    arrays={}
    for pattern,years in [('GLC*5years*.tif',NOMINAL),('GLC*Annual*.tif',list(range(2000,2023)))]:
        choices=list(args.source.glob(pattern))
        if len(choices)!=1:raise ValueError(f'Expected one source for {pattern}, got {choices}')
        path=choices[0]
        with rasterio.open(path) as ds:
            if ds.count!=len(years) or ds.crs.to_epsg()!=4326:
                raise ValueError(f'Source metadata mismatch: {path}')
            c,r=(~ds.transform)*(lons,lats)
            c,r=np.floor(c).astype('int32'),np.floor(r).astype('int32')
            x0,x1,y0,y1=c.min(),c.max(),r.min(),r.max()
            if x0<0 or y0<0 or x1>=ds.width or y1>=ds.height:raise ValueError('Tile coverage incomplete')
            window=Window(int(x0),int(y0),int(x1-x0+1),int(y1-y0+1))
            source_sha=sha(path)
            for band,year in enumerate(years,1):
                src=ds.read(band,window=window)
                arr=src[r-y0,c-x0].astype('uint8')
                arr[~mask]=0
                seen=set(np.unique(arr).tolist())
                if seen-set(CLASSES)-{0,250,255}:raise ValueError(f'Unexpected classes {seen}: {year}')
                if not np.isin(arr,list(CLASSES)).any():raise ValueError(f'No coverage in year {year}')
                dest=out/f'{year}.png';Image.fromarray(arr).save(dest,optimize=True)
                assert np.array_equal(arr,np.asarray(Image.open(dest)))
                arrays[year]=arr
                manifest['years'].append(dict(year=year,file=dest.name,sha256=sha(dest),bytes=dest.stat().st_size,
                    band=band,member=path.name,source=DATASET,sourceTileSha256=source_sha,
                    windowYears=[year-2,year+2] if year<2000 else [year,year]))
                print(f'Extracted {year}, {len(seen)-1} classes',flush=True)
    pairs={f'{a}-{b}':metrics(arrays[a], arrays[b], mask) for a in arrays for b in arrays if a<=b}
    save_json(out/'summary.json',pairs)
    save_json(out/'manifest.json',manifest)
    print('Area ha',mask.sum()*.09,'1985 to 2022', {key:val for key,val in pairs['1985-2022'].items() if key!='transitions'},flush=True)

if __name__=='__main__':main()
