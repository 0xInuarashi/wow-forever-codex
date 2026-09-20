"""Generate only a fixed non-executable probe.tga, never Lua or SavedVariables."""
import argparse
from pathlib import Path
from PIL import Image

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path,help='CodexPixelBridge addon folder')
    p.add_argument('--color',choices=['red','green'],default='red')
    a=p.parse_args()
    target=a.directory.resolve()
    if target.name!='CodexPixelBridge' or not (target/'CodexPixelBridge.toc').is_file():
        p.error('Expected the CodexPixelBridge addon folder')
    # Replace atomically so the renderer cannot observe a partially written asset.
    temp=target/'probe.next.tga'
    Image.new('RGB',(64,64),a.color).save(temp,format='TGA')
    temp.replace(target/'probe.tga')
    print('Wrote',target/'probe.tga')

if __name__=='__main__': main()
