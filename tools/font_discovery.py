"""One-run experiment: discover genuinely new font paths after UI load.

Prepare before reloading the addon; watch before opening /codex latefontprobe.
Only three explicitly named non-executable font assets can be written.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import secrets
import struct
import time
from types import SimpleNamespace
import zlib

from fontTools.ttLib import TTFont
from companion.native import make_font, make_packet
from companion.protocol import read_image_frame
from companion.visual import validate_addon

NAMES = ('control', 'late1', 'late2')
HEADER = struct.Struct('>4sBBBB8sI')


def utc():
    return datetime.now(timezone.utc).isoformat()


def asset_path(directory, token, case):
    if not re.fullmatch('[0-9a-f]{8}', token) or case not in range(1, 4):
        raise ValueError('Invalid discovery token/case')
    directory = validate_addon(Path(directory))
    path = directory / f'fontdiscover_{token}_{NAMES[case-1]}.ttf'
    if path.resolve().parent != directory.resolve():
        raise ValueError('Unexpected discovery asset path')
    return path


def font_content(token, case, text):
    session = token.encode('ascii').hex()
    control = SimpleNamespace(session=session, request=1, slot=case, page=1)
    data = make_packet(control, {'id': session+':1', 'state': 'done', 'reply': text})
    font = TTFont(BytesIO(make_font(data, case)))
    # Keep production font structure but avoid internal family-name collisions.
    family = f'CodexDiscovery{token}{case}'
    for item in font['name'].names:
        if item.nameID in (1, 3, 4, 6):
            item.string = family.encode(item.getEncoding())
    output = BytesIO(); font.save(output)
    return output.getvalue()


def prepare(directory, manifest_path):
    directory = validate_addon(Path(directory))
    token = secrets.token_hex(4)
    paths = [asset_path(directory, token, case) for case in range(1, 4)]
    if any(path.exists() for path in paths) or Path(manifest_path).exists():
        raise ValueError('Use a fresh manifest and fresh filenames for every experiment')
    content = font_content(token, 1, 'PREPARED BASELINE')
    with paths[0].open('xb') as file:
        file.write(content)
    manifest = {'token': token, 'addon': str(directory.resolve()), 'prepared_utc': utc(),
                'baseline_sha256': hashlib.sha256(content).hexdigest(),
                'late_files_absent_at_preparation': not paths[1].exists() and not paths[2].exists(),
                'paths': [str(path) for path in paths]}
    Path(manifest_path).write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (directory/'LateFontProbeConfig.lua').write_text(
        '-- One-run diagnostic filename token, not a production bank setting.\n'
        f"local _,NS=...\nNS.FontDiscoveryToken='{token}'\n", encoding='utf-8')
    return manifest


def parse_report(frame):
    if len(frame) != 64 or zlib.adler32(frame[:60]) != int.from_bytes(frame[60:], 'big'):
        raise ValueError('Invalid discovery report checksum')
    magic, version, phase, case, status, token, elapsed = HEADER.unpack(frame[:20])
    if magic != b'CPFD' or version != 1 or phase not in (1, 2, 3) or case not in range(4) or status not in (0, 1, 2) or elapsed > 140:
        raise ValueError('Invalid discovery report fields')
    if phase != (3 if elapsed >= 120 else 2 if elapsed >= 70 else 1):
        raise ValueError('Invalid discovery phase timing')
    token = token.decode('ascii')
    if not re.fullmatch('[0-9a-f]{8}', token):
        raise ValueError('Invalid discovery token')
    text = frame[20:60].rstrip(b'\0').decode('ascii')
    if '\0' in text or (not status and text) or (case == 0 and status):
        raise ValueError('Invalid discovery report payload')
    return {'token': token, 'phase': phase, 'case': case, 'status': status, 'elapsed': elapsed, 'text': text}


class Experiment:
    def __init__(self, manifest, record, clock=time.monotonic):
        self.manifest = manifest; self.record = Path(record); self.clock = clock
        self.directory = validate_addon(Path(manifest['addon']))
        self.token = manifest['token']
        self.paths = [asset_path(self.directory, self.token, case) for case in range(1, 4)]
        if self.record.exists():
            raise ValueError('A record already exists; never repeat an old experiment')
        if hashlib.sha256(self.paths[0].read_bytes()).hexdigest() != manifest['baseline_sha256'] or any(p.exists() for p in self.paths[1:]):
            raise ValueError('Baseline changed or late files already exist; prepare fresh paths')
        self.nonce = secrets.token_hex(8)
        self.markers = {i: f'{NAMES[i-1].upper()} {self.nonce}' for i in range(1, 4)}
        self.first_seen = None; self.last_elapsed = -1; self.second_written = False
        self.done = False; self.results = {}
        self.data = {'manifest': manifest, 'armed_utc': utc(), 'nonce': self.nonce,
                     'expected': self.markers, 'events': [], 'results': {}, 'status': 'armed'}
        self.save()

    def save(self):
        temporary = self.record.with_suffix('.next.json')
        temporary.write_text(json.dumps(self.data, indent=2), encoding='utf-8')
        temporary.replace(self.record)

    def event(self, event, **fields):
        self.data['events'].append({'utc': utc(), 'event': event, **fields})
        self.save()

    def write(self, case, elapsed):
        path = self.paths[case-1]
        content = font_content(self.token, case, self.markers[case])
        if case == 1:
            if hashlib.sha256(path.read_bytes()).hexdigest() != self.manifest['baseline_sha256']:
                raise ValueError('Control baseline was changed by another writer')
            temporary = path.with_suffix('.next.ttf')
            with temporary.open('xb') as file: file.write(content)
            temporary.replace(path)
        else:
            # Exclusive creation: a prior/stale existing path invalidates the test.
            # The earliest reader is at least ten seconds after our write window.
            with path.open('xb') as file: file.write(content)
        self.event('font_written', case=case, path=str(path), game_elapsed=elapsed,
                   sha256=hashlib.sha256(content).hexdigest(), bytes=len(content))

    def accept(self, report):
        if self.done or report['token'] != self.token:
            return
        elapsed = report['elapsed']; now = self.clock()
        if elapsed < self.last_elapsed:
            raise ValueError('Probe clock restarted; cached filenames cannot be reused')
        self.last_elapsed = elapsed
        if self.first_seen is None:
            if report['phase'] != 1 or elapsed > 15:
                raise ValueError('Missed the initial creation window; prepare a fresh test')
            if any(p.exists() for p in self.paths[1:]):
                raise ValueError('Late paths already exist before the running probe signal')
            self.first_seen = (now, elapsed)
            self.data['status'] = 'running'
            self.event('running_probe_seen', game_elapsed=elapsed, late_files_absent=True)
            self.write(1, elapsed); self.write(2, elapsed)
        # A frozen screenshot cannot extend the late-write window indefinitely.
        estimated = self.first_seen[1] + now - self.first_seen[0]
        if not self.second_written and report['phase'] == 2:
            if elapsed > 85 or estimated > 88:
                raise ValueError('Missed the second creation window; result is inconclusive')
            self.event('second_creation_signal', game_elapsed=elapsed, late2_absent=not self.paths[2].exists())
            self.write(3, elapsed); self.second_written = True
        case = report['case']
        if case and report['status'] and case not in self.results:
            if elapsed < (30, 50, 100)[case-1]:
                raise ValueError('Result arrived before its scheduled first load')
            self.results[case] = {'status': report['status'], 'text': report['text'],
                                  'matches_nonce': report['text'] == self.markers[case], 'game_elapsed': elapsed}
            self.data['results'][str(case)] = self.results[case]
            self.event('decoded_result', case=case, **self.results[case])
        if report['phase'] == 3 and len(self.results) == 3:
            valid = self.second_written and self.results[1]['status'] == 1 and self.results[1]['matches_nonce']
            if not valid:
                verdict = 'inconclusive: the preinstalled control did not return the fresh marker'
            elif all(self.results[i]['status'] == 1 and self.results[i]['matches_nonce'] for i in (2, 3)):
                verdict = 'supported in this run: both post-UI-load font paths returned exact fresh bytes'
            elif all(self.results[i]['status'] == 2 for i in (2, 3)):
                verdict = 'not demonstrated: control passed but both new font paths failed'
            else:
                verdict = 'mixed results: inspect individual paths; no general conclusion'
            self.done = True; self.data['status'] = 'complete'; self.data['verdict'] = verdict
            self.event('completed', verdict=verdict)


def watch(args):
    from PIL import ImageGrab
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    experiment = Experiment(manifest, args.record)
    x, y, w, h = json.loads(args.capture.read_text(encoding='utf-8'))['region']
    if not (w >= 128 and h >= 4 and x >= 0 and y >= 0):
        raise ValueError('Invalid screen calibration')
    deadline = time.monotonic() + args.timeout
    print(json.dumps({'status': 'armed', 'token': manifest['token'], 'record': str(args.record)}), flush=True)
    try:
        while time.monotonic() < deadline and not experiment.done:
            crop = ImageGrab.grab(bbox=(x,y,x+w,y+h), all_screens=True)
            try:
                report = parse_report(read_image_frame(crop))
            except (ValueError, UnicodeError):
                report = None
            if report:
                experiment.accept(report)
            time.sleep(.15)
        if not experiment.done:
            experiment.data['status'] = 'inconclusive'
            experiment.event('timeout', reason='No complete live result before the observation deadline')
    except Exception as error:
        experiment.data['status'] = 'inconclusive'
        experiment.event('error', reason=str(error))
        raise
    print(json.dumps({'status': experiment.data['status'], 'verdict': experiment.data.get('verdict')}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    preparation = sub.add_parser('prepare')
    preparation.add_argument('addon', type=Path); preparation.add_argument('manifest', type=Path)
    observer = sub.add_parser('watch')
    observer.add_argument('manifest', type=Path); observer.add_argument('record', type=Path)
    observer.add_argument('--capture', type=Path, default=Path('state/capture.json'))
    observer.add_argument('--timeout', type=int, default=1200)
    args = parser.parse_args()
    if args.command == 'prepare':
        print(json.dumps(prepare(args.addon, args.manifest)), flush=True)
    else:
        if not 150 <= args.timeout <= 10800:
            parser.error('Observation timeout must be 150..10800 seconds')
        watch(args)


if __name__ == '__main__':
    main()
