"""Controlled font API/storage/reuse comparisons. No game input or memory access."""
import argparse
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import secrets
import time
import zlib

from fontTools.ttLib import TTFont
from companion.native import make_font
from companion.protocol import read_image_frame
from companion.visual import validate_addon
from tools.font_discovery import HEADER, utc
from tools.font_probe import packet

SPECS=[
    (1,1,'direct',64,''),(2,1,'object',64,''),(3,1,'family',64,''),
    (4,1,'direct',64,''),(5,1,'object',64,''),(6,1,'family',64,''),
    (7,1,'direct',64,''),(8,1,'direct',64,''),
    *[(i,1,'direct',64,'') for i in range(9,14)],
    (9,2,'direct',64,''),(10,2,'direct',128,''),(11,2,'object',64,''),
    (12,2,'family',64,''),(13,2,'direct',64,'OUTLINE'),(4,2,'direct',64,''),(14,2,'direct',64,''),
    (15,2,'direct',128,''),(16,2,'direct',64,'OUTLINE')]
LATE=(4,5,6)


def asset_path(directory,token,asset):
    if not re.fullmatch('[0-9a-f]{8}',token) or not 0<=asset<=16:
        raise ValueError('Invalid matrix filename')
    directory=validate_addon(Path(directory))
    result=directory/f'fontmatrix_{token}_{asset:02}.ttf'
    if result.resolve().parent!=directory.resolve(): raise ValueError('Unexpected asset parent')
    return result


def font_content(token,asset,text):
    data=packet(text)
    font=TTFont(BytesIO(make_font(data.ljust(512,b'\0'),1)))
    # Keep the production font's full repertoire, plus 64 ASCII data positions
    # so a roman FontFamily comparison does not depend on private-use fallback.
    cmap=font.getBestCmap()
    for i,value in enumerate(data):font['hmtx'][cmap[35+i]]=((16+value)*16,0)
    family=f'CodexMatrix{token}{asset}'
    for item in font['name'].names:
        if item.nameID in (1,3,4,6):item.string=family.encode(item.getEncoding())
    out=BytesIO();font.save(out);return out.getvalue()


def prepare(directory,manifest_path):
    directory=validate_addon(Path(directory));token=secrets.token_hex(4)
    paths={i:asset_path(directory,token,i) for i in range(17)}
    manifest_path=Path(manifest_path)
    if manifest_path.exists() or any(p.exists() for p in paths.values()):
        raise ValueError('Use a fresh experiment and manifest')
    for asset,path in paths.items():
        if asset in LATE or asset==8:continue
        content=b'' if asset==7 else font_content(token,8 if asset==0 else asset,'PREPARED')
        with path.open('xb') as file:file.write(content)
    os.link(paths[0],paths[8])
    prepared={str(i):{'exists':p.exists(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None,
                       'bytes':p.stat().st_size if p.exists() else None} for i,p in paths.items()}
    manifest={'token':token,'addon':str(directory.resolve()),'prepared_utc':utc(),'prepared':prepared,
              'shared_seed_verified':os.path.samefile(paths[0],paths[8])}
    manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (directory/'FontMatrixConfig.lua').write_text(f"local _,NS=...\nNS.FontMatrixToken='{token}'\n",encoding='utf-8')
    return manifest


def parse_report(frame):
    if len(frame)!=64 or zlib.adler32(frame[:60])!=int.from_bytes(frame[60:],'big'):
        raise ValueError('Invalid matrix checksum')
    magic,version,phase,case,status,token,elapsed=HEADER.unpack(frame[:20])
    if magic!=b'CPFM' or version!=2 or not 0<=case<=22 or status not in range(4) or elapsed>165:
        raise ValueError('Invalid matrix header')
    if phase!=(3 if elapsed>=140 else 2 if elapsed>=75 else 1) or (status==3 and not 1<=case<=16):
        raise ValueError('Invalid matrix phase/metadata')
    token=token.decode('ascii');text=frame[20:60].rstrip(b'\0').decode('ascii')
    if not re.fullmatch('[0-9a-f]{8}',token) or '\0' in text or (status==0 and text) or (case==0 and status):
        raise ValueError('Invalid matrix payload')
    return dict(token=token,phase=phase,case=case,status=status,elapsed=elapsed,text=text)


class Matrix:
    def __init__(self,manifest,record,clock=time.monotonic):
        self.manifest=manifest;self.token=manifest['token'];self.directory=Path(manifest['addon'])
        self.record=Path(record);self.clock=clock;self.nonce=secrets.token_hex(8)
        self.paths={i:asset_path(self.directory,self.token,i) for i in range(17)}
        if self.record.exists():raise ValueError('A matrix record already exists')
        for asset,path in self.paths.items():
            entry=manifest['prepared'][str(asset)]
            if path.exists()!=entry['exists'] or (path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']):
                raise ValueError('Prepared assets changed; use fresh preparation')
        if not os.path.samefile(self.paths[0],self.paths[8]):raise ValueError('Shared placeholder was changed')
        self.first=None;self.last_elapsed=-1;self.written=set();self.done=False;self.started_second=False
        self.data={'manifest':manifest,'armed_utc':utc(),'nonce':self.nonce,'status':'armed',
                   'events':[],'results':{},'metadata':{},'summary':{}}
        self.save()

    def save(self):
        temp=self.record.with_suffix('.next.json');temp.write_text(json.dumps(self.data,indent=2),encoding='utf-8');temp.replace(self.record)

    def event(self,name,**fields):
        self.data['events'].append(dict(utc=utc(),event=name,**fields));self.save()

    def marker(self,asset,phase):return f'{"A" if phase==1 else "B"}{asset:02} {self.nonce}'

    def write(self,asset,phase,elapsed):
        if (asset,phase) in self.written:return
        path=self.paths[asset];body=font_content(self.token,asset,self.marker(asset,phase))
        if asset in LATE:
            with path.open('xb') as file:file.write(body)
        else:
            expected=self.manifest['prepared'][str(asset)]['sha256']
            if phase==2 and asset<14:
                expected=next(e['sha256'] for e in self.data['events'] if e['event']=='font_written' and e['asset']==asset and e['phase']==1)
            if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('Another writer changed an experiment asset')
            temp=path.with_suffix('.next.ttf')
            with temp.open('xb') as file:file.write(body)
            temp.replace(path)
        self.written.add((asset,phase))
        self.event('font_written',asset=asset,phase=phase,game_elapsed=elapsed,sha256=hashlib.sha256(body).hexdigest(),bytes=len(body))
        if asset==8:
            seed=self.paths[0]
            unchanged=hashlib.sha256(seed.read_bytes()).hexdigest()==self.manifest['prepared']['0']['sha256']
            independent=not os.path.samefile(seed,path)
            if not unchanged or not independent:raise ValueError('Shared seed isolation failed')
            self.event('shared_seed_isolated',seed_unchanged=True,published_path_independent=True)

    def accept(self,r):
        if self.done or r['token']!=self.token:return
        elapsed=r['elapsed'];now=self.clock()
        if elapsed<self.last_elapsed:raise ValueError('Probe restarted; old filenames cannot be reused')
        self.last_elapsed=elapsed
        if self.first is None:
            if elapsed>12:raise ValueError('Missed initial write window')
            if any(self.paths[i].exists() for i in LATE):raise ValueError('Late paths already exist')
            self.first=(now,elapsed);self.data['status']='running'
            self.event('running_probe_seen',game_elapsed=elapsed,late_paths_absent=True)
            for asset in range(1,14):self.write(asset,1,elapsed)
        if r['phase']==2 and not self.started_second:
            if elapsed>87 or self.first[1]+now-self.first[0]>90:raise ValueError('Missed second write window')
            self.started_second=True;self.event('second_write_signal',game_elapsed=elapsed)
            for asset in range(9,17):self.write(asset,2,elapsed)
        case=r['case']
        if r['status']==3:
            if r['text'] and str(case) not in self.data['metadata']:
                self.data['metadata'][str(case)]={'text':r['text'],'game_elapsed':elapsed};self.save()
        elif case and r['status'] and str(case) not in self.data['results']:
            asset,phase,method,height,flags=SPECS[case-1]
            if elapsed<(30 if phase==1 else 105):raise ValueError('Result before its load window')
            expected_phase=1 if case==19 else phase
            value=dict(asset=asset,phase=phase,method=method,height=height,flags=flags,
                       status=r['status'],text=r['text'],game_elapsed=elapsed,
                       matches_expected=r['text']==self.marker(asset,expected_phase),
                       matches_old=r['text']==self.marker(asset,1) if phase==2 and case!=19 else False)
            self.data['results'][str(case)]=value;self.event('result',case=case,**value)
        if r['phase']==3 and len(self.data['results'])==22:
            get=lambda n:self.data['results'][str(n)]
            passed=lambda n:get(n)['status']==1 and get(n)['matches_expected']
            self.data['summary']={
                'direct_control_passed':passed(1),'object_control_passed':passed(2),'family_control_passed':passed(3),
                'second_phase_control_passed':passed(20),
                'large_size_control_passed':passed(21),'outline_control_passed':passed(22),
                'new_path_candidates':[SPECS[i-1][2] for i in (4,5,6) if passed(i) and passed(i-3)],
                'new_path_long_retry_passed':passed(19) and passed(1) and passed(20),
                'empty_placeholder_passed':passed(7),'shared_placeholder_passed':passed(8),
                'reuse_candidates':[{'case':i,'method':SPECS[i-1][2],'height':SPECS[i-1][3],'flags':SPECS[i-1][4]}
                                    for i in range(14,19) if passed(i) and passed(i-5) and passed(20)
                                    and (i!=15 or passed(21)) and (i!=18 or passed(22)) and (i!=17 or passed(3))],
                'interpretation':'Candidate results require their matching controls; no unlimited production channel is enabled.'}
            self.done=True;self.data['status']='complete';self.event('complete',summary=self.data['summary'])


def watch(args):
    from PIL import ImageGrab
    matrix=Matrix(json.loads(args.manifest.read_text(encoding='utf-8')),args.record)
    x,y,w,h=json.loads(args.capture.read_text(encoding='utf-8'))['region']
    if not (x>=0 and y>=0 and w>=128 and h>=4):raise ValueError('Invalid capture calibration')
    deadline=time.monotonic()+args.timeout
    print(json.dumps(dict(status='armed',token=matrix.token)),flush=True)
    try:
        while not matrix.done and time.monotonic()<deadline:
            crop=ImageGrab.grab(bbox=(x,y,x+w,y+h),all_screens=True)
            try:r=parse_report(read_image_frame(crop))
            except (ValueError,UnicodeError):r=None
            if r:matrix.accept(r)
            time.sleep(.15)
        if not matrix.done:
            matrix.data['status']='inconclusive';matrix.event('timeout')
    except Exception as error:
        matrix.data['status']='inconclusive';matrix.event('error',reason=str(error));raise
    print(json.dumps(dict(status=matrix.data['status'],summary=matrix.data['summary'])),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('addon',type=Path);prep.add_argument('manifest',type=Path)
    observer=sub.add_parser('watch');observer.add_argument('manifest',type=Path);observer.add_argument('record',type=Path)
    observer.add_argument('--capture',type=Path,default=Path('state/capture.json'));observer.add_argument('--timeout',type=int,default=1200)
    args=p.parse_args()
    if args.command=='prepare':print(json.dumps(prepare(args.addon,args.manifest)),flush=True)
    else:
        if not 180<=args.timeout<=10800:p.error('Timeout must be 180..10800 seconds')
        watch(args)


if __name__=='__main__':main()
