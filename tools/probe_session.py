"""Bounded visual asset experiment. No game input, process access, or Lua writes."""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import threading
import time

from PIL import Image, ImageDraw, ImageFont

ASSETS = ['probe.tga', 'probe_release.tga'] + [f'probe_slot{i:02}.tga' for i in range(1, 9)]


def validate_target(directory):
    target = Path(directory).resolve()
    if target.name != 'CodexPixelBridge' or not (target / 'CodexPixelBridge.toc').is_file():
        raise ValueError('Expected the CodexPixelBridge addon folder')
    return target


def asset_image(counter):
    image = Image.new('RGB', (64, 64), (0, 100, 30) if counter % 2 else (125, 20, 0))
    draw = ImageDraw.Draw(image)
    draw.text((4, 5), 'PROBE', fill='white', font=ImageFont.load_default(size=12))
    draw.text((3, 26), f'{counter:04}', fill='white', font=ImageFont.load_default(size=22))
    return image


def write_assets(target, image):
    target = validate_target(target)
    for name in ASSETS:
        destination = target / name
        temporary = destination.with_suffix('.next.tga')
        image.save(temporary, format='TGA')
        temporary.replace(destination)


def make_server(image_supplier, report, port=18761):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != '/probe.png':
                self.send_error(404)
                return
            body = BytesIO()
            image_supplier().save(body, format='PNG')
            data = body.getvalue()
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)
            report({'event': 'http_request', 'path': self.path})

        def log_message(self, *_):
            pass

    # A single generated image on loopback. Never serve a folder or arbitrary file.
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--prepare', action='store_true', help='Create numbered assets, then exit')
    action.add_argument('--create-late', action='store_true', help='After probe 3 is running, create its new 0909 asset once, then exit')
    parser.add_argument('--duration', type=int, default=240)
    parser.add_argument('--serve-image', action='store_true', help='Optional standalone loopback image server; the addon URL test was removed after a protected-UI rejection')
    parser.add_argument('--log', type=Path)
    args = parser.parse_args()
    try:
        target = validate_target(args.directory)
    except ValueError as error:
        parser.error(str(error))
    if not 1 <= args.duration <= 900:
        parser.error('duration must be between 1 and 900 seconds')
    if args.create_late:
        destination = target / 'probe_late_v3.tga'
        if destination.exists():
            parser.error('The late asset must be absent during UI load; refusing to replace it')
        temporary = target / 'probe_late_v3.next.tga'
        asset_image(909).save(temporary, format='TGA')
        temporary.replace(destination)
        print(json.dumps({'time': datetime.now(timezone.utc).isoformat(), 'event': 'late_asset_created', 'counter': 909}))
        return
    if args.prepare:
        write_assets(target, asset_image(0))
        print('Prepared ten diagnostic images; no executable addon files were changed.')
        return
    if any(not (target / name).is_file() for name in ASSETS):
        parser.error('Run --prepare before loading the updated addon')
    originals = {name: (target / name).read_bytes() for name in ASSETS}
    current = [asset_image(0)]
    log = args.log.open('a', encoding='utf-8') if args.log else None

    def report(data):
        line = json.dumps({'time': datetime.now(timezone.utc).isoformat(), **data})
        print(line, flush=True)
        if log:
            log.write(line + '\n')
            log.flush()

    server = make_server(lambda: current[0], report) if args.serve_image else None
    thread = None
    if server:
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True)
        thread.start()
    report({'event': 'started', 'duration': args.duration, 'image_server': bool(server)})
    started = time.monotonic()
    counter = 0
    try:
        while time.monotonic() - started < args.duration:
            counter += 1
            current[0] = asset_image(counter)
            write_assets(target, current[0])
            report({'event': 'asset_write', 'counter': counter})
            time.sleep(min(2, max(0, args.duration - (time.monotonic() - started))))
    finally:
        if server:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        for name, contents in originals.items():
            temporary = (target / name).with_suffix('.restore.tga')
            temporary.write_bytes(contents)
            temporary.replace(target / name)
        report({'event': 'finished', 'originals_restored': True})
        if log:
            log.close()


if __name__ == '__main__':
    main()
