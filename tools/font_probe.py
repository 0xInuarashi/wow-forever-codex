"""Bounded, non-executable font-metric experiment. Not a production transport.

The font contains ordinary TrueType outlines and advance widths, no bytecode.
Only eight explicitly named probe fonts can be written by this tool.
"""
import argparse
from io import BytesIO
from pathlib import Path
import struct
import time
import zlib
import secrets
import json
from datetime import datetime, timezone

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen


def packet(text, sequence=0):
    payload = text.encode('utf-8')
    if len(payload) > 51:
        raise ValueError('Probe payload limit is 51 UTF-8 bytes')
    body = (b'CFP1' + struct.pack('>IB', sequence, len(payload)) + payload).ljust(60, b'\0')
    return body + struct.pack('>I', zlib.adler32(body))


def font_bytes(data, slot):
    if len(data) != 64 or not 1 <= slot <= 8:
        raise ValueError('Expected one 64-byte packet and probe slot 1..8')
    values = {33: 0, 34: 255, 126: 16}
    values.update({35 + i: value for i, value in enumerate(data)})
    order = ['.notdef', 'space'] + [f'g{code}' for code in values]
    fb = FontBuilder(1024, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({32: 'space', **{code: f'g{code}' for code in values}})
    glyphs = {}
    metrics = {'.notdef': (512, 0), 'space': (256, 0)}
    for name in order:
        pen = TTGlyphPen(None)
        if name != 'space':
            pen.moveTo((0, 0)); pen.lineTo((64, 0)); pen.lineTo((64, 512)); pen.lineTo((0, 512)); pen.closePath()
        glyphs[name] = pen.glyph()
    metrics.update({f'g{code}': ((16 + value) * 16, 0) for code, value in values.items()})
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=800, descent=-224)
    family = f'CodexFontProbe{slot}'
    fb.setupNameTable({'familyName': family, 'styleName': 'Regular', 'uniqueFontIdentifier': family,
                       'fullName': family, 'psName': family, 'version': 'Version 1.0'})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-224, usWinAscent=800, usWinDescent=224)
    fb.setupPost(); fb.setupMaxp()
    output = BytesIO(); fb.save(output)
    return output.getvalue()


def write_font(directory, slot, data, prepare=False):
    directory = Path(directory).resolve()
    if directory.name != 'CodexPixelBridge' or not (directory / 'CodexPixelBridge.toc').is_file():
        raise ValueError('Expected the CodexPixelBridge addon folder')
    destination = directory / f'fontprobe{slot:02}.ttf'
    if destination.resolve().parent != directory or not 1 <= slot <= 8:
        raise ValueError('Unexpected font probe path')
    if not prepare and not destination.is_file():
        raise ValueError('Prepare the probe fonts before loading the UI')
    if prepare and destination.exists():
        return
    body = font_bytes(data, slot)
    temporary = destination.with_suffix('.next.ttf')
    temporary.write_bytes(body); temporary.replace(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--duration', type=int, default=150)
    args = parser.parse_args()
    if args.prepare:
        for slot in range(1, 9):
            write_font(args.directory, slot, packet(f'Installed baseline {slot}'), prepare=True)
        return
    if not 1 <= args.duration <= 180:
        parser.error('Duration must be between 1 and 180 seconds')
    deadline = time.monotonic() + args.duration
    sequence = 0
    nonce = secrets.token_hex(3)
    while time.monotonic() < deadline:
        sequence += 1
        text = f'Live {nonce} / {sequence:04}'
        for slot in (6, 7, 8):
            write_font(args.directory, slot, packet(text, sequence))
        print(json.dumps({'utc': datetime.now(timezone.utc).isoformat(), 'sequence': sequence, 'text': text}), flush=True)
        time.sleep(2)


if __name__ == '__main__':
    main()
