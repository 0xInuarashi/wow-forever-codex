"""Standalone storage experiment, not the production bank installer.

Prepare many valid font filenames using small groups of NTFS hard links.
Publish with atomic replacement, never by writing through a shared link.
"""
import argparse
import json
import os
from pathlib import Path
import time

from companion.native import make_font


def prepare(directory, count=10000, group_size=512):
    directory=Path(directory).resolve()
    if not 1<=count<=100000 or not 1<=group_size<=512:
        raise ValueError('Experiment supports 1..100000 names, groups of 1..512')
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('Use a new empty experiment directory; existing assets are never modified')
    directory.mkdir(parents=True,exist_ok=True)
    started=time.monotonic();baseline=make_font(bytes(512),1);seeds=[]
    for index in range(count):
        if index%group_size==0:
            seed=directory/f'seed{index//group_size:04}.ttf'
            with seed.open('xb') as file:file.write(baseline)
            seeds.append(seed)
        os.link(seed,directory/f'reserve{index+1:08}.ttf')
    report={'filenames':count,'seed_files':len(seeds),'group_size':group_size,
            'seconds':time.monotonic()-started,'baseline_bytes':len(baseline),
            'unique_font_payload_bytes':len(seeds)*len(baseline),
            'separate_copies_payload_bytes':count*len(baseline),
            'filesystem_metadata_included':False,
            'maximum_observed_links':max(p.stat().st_nlink for p in seeds)}
    (directory/'preparation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('--count',type=int,default=10000)
    args=parser.parse_args();print(json.dumps(prepare(args.directory,args.count)),flush=True)


if __name__=='__main__':main()
