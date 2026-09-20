"""Install/update addon code and create missing compact font slots before UI load."""
import argparse
import json
from pathlib import Path
import shutil

from companion.native import prepare_bank
from companion.visual import prepare_bank as prepare_images
from tools.font_probe import packet, write_font
from tools.probe_session import ASSETS, asset_image


def prepare_diagnostics(destination):
    """Reproduce fixed probe baselines without shipping captured font/image data."""
    for slot in range(1,9):
        write_font(destination,slot,packet(f'Installed baseline {slot}'),prepare=True)
    picture=None
    for name in ASSETS:
        path=destination/name
        if path.exists(): continue
        if picture is None: picture=asset_image(0)
        with path.open('xb') as file: picture.save(file,format='TGA')


def install(destination, progress=None):
    destination=Path(destination).resolve()
    if destination.name!='CodexPixelBridge':
        raise ValueError('Destination must be the CodexPixelBridge addon folder')
    source=Path(__file__).resolve().parents[1]/'addon'/'CodexPixelBridge'
    destination.mkdir(parents=True,exist_ok=True)
    if destination!=source.resolve():
        for path in source.iterdir():
            if not path.is_file() or path.suffix.lower() not in ('.lua','.xml','.toc'): continue
            target=destination/path.name
            shutil.copy2(path,target)
    prepare_diagnostics(destination)
    prepare_images(destination)
    return prepare_bank(destination,progress=progress)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path,help='Full path ending in Interface/AddOns/CodexPixelBridge')
    args=parser.parse_args()
    report=install(args.directory,lambda n:print(f'Created {n:,} missing font slots...',flush=True) if n%8192==0 else None)
    print(json.dumps(report,indent=2))
    print('Installed. Reload the WoW UI once to load this update; restart WoW if new assets are not discovered.')


if __name__=='__main__':main()
