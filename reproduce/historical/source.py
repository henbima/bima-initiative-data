"""Extract the two original GLC_FCS30D Bima GeoTIFFs using byte ranges and ZIP CRC."""
import io
import re
import shutil
import zipfile
import zlib
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent
RECORD = "https://zenodo.org/api/records/15063683"
ARCHIVE = "GLC_FCS30D_19852022maps_E110-E115.zip"

class Ranges(io.RawIOBase):
    def __init__(self, url, length):
        self.url, self.length, self.pos = url, length, 0
        self.window = b""
        self.offset = -1
        self.session = requests.Session()
        self.session.mount("https://",HTTPAdapter(max_retries=Retry(total=4,backoff_factor=1, status_forcelist=[429,500,502,503,504],allowed_methods=["GET"])))

    def tell(self): return self.pos
    def seekable(self): return True
    def seek(self, offset, whence=0):
        self.pos = [offset,self.pos+offset,self.length+offset][whence]
        return self.pos

    def read(self, size=-1):
        if size<0: size=self.length-self.pos
        remaining=min(size,self.length-self.pos)
        if remaining<=0: return b""
        pieces=[]
        while remaining:
            if not self.offset<=self.pos<self.offset+len(self.window):
                start=self.pos
                end=min(self.length-1,start+max(1_048_576,remaining)-1,start+16*1024*1024-1)
                self.offset=start
                response=self.session.get(self.url,params={"range":f"{start}-{end}"},headers={"Range":f"bytes={start}-{end}","Accept-Encoding":"identity"},timeout=(30,150),stream=True)
                with response:
                    expected=f"bytes {start}-{end}/{self.length}"
                    if response.status_code!=206 or response.headers.get("Content-Range","")!=expected:
                        raise ValueError(f"Invalid HTTP range {response.status_code}, {response.headers.get('Content-Range')!r}, wanted {expected}")
                    self.window=response.content
                    if len(self.window)!=end-start+1:
                        raise ValueError("Incomplete range")
            i=self.pos-self.offset
            part=self.window[i:i+remaining]
            pieces.append(part)
            self.pos+=len(part)
            remaining-=len(part)
        return b"".join(pieces)

def main():
    meta=requests.get(RECORD,timeout=40).json()
    obj=next(entry for entry in meta["files"] if entry["key"]==ARCHIVE)
    source=Ranges(obj["links"]["self"],obj["size"])
    dest=ROOT/"originals"; dest.mkdir(exist_ok=True)
    with zipfile.ZipFile(source) as z:
        names=z.infolist()
        print([entry.filename for entry in names if "S5" in entry.filename or "S05" in entry.filename],flush=True)
        results=[entry for entry in names if re.search(r"E115S0?5_(5years|Annual)_V1\.1\.tif$",entry.filename,re.I)]
        if len(results)!=2:
            raise ValueError(str([e.filename for e in names]))
        for entry in results:
            print(entry.filename,entry.file_size,entry.compress_size,flush=True)
            path=dest/Path(entry.filename.replace("\\","/")).name
            if path.exists() and path.stat().st_size==entry.file_size:
                with path.open("rb") as prior:
                    crc=0
                    for block in iter(lambda: prior.read(2*1024*1024),b""):
                        crc=zlib.crc32(block,crc)
                if crc==entry.CRC:
                    continue
            temp=path.with_suffix(".partial")
            with z.open(entry) as incoming, temp.open("wb") as outgoing:
                shutil.copyfileobj(incoming,outgoing,length=2*1024*1024)
            temp.replace(path)
            print("verified ZIP CRC",path.name,flush=True)

if __name__=="__main__": main()
