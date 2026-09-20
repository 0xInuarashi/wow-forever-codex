"""Bounded first-use fonts carrying checked response bytes to native addon text."""
from io import BytesIO
import math
import os
from pathlib import Path
import struct
import tempfile
import time
import zlib

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from .visual import validate_addon
from .limits import FONT_BANK_SIZE

BANK_SIZE = FONT_BANK_SIZE
PACKET_SIZE = 512
HEADER = struct.Struct('>4sBBH8sIIIHH')
CHUNK = PACKET_SIZE - HEADER.size - 4
MAX_TEXT = 60000
STATES = {'waiting':0, 'queued':1, 'working':2, 'streaming':3, 'done':4, 'failed':5, 'interrupted':6}


def make_packet(control, snapshot):
    key = f'{control.session}:{control.request}'
    if snapshot.get('id') != key:
        snapshot = {'id':key, 'state':'waiting', 'reply':''}
    state = STATES.get(snapshot.get('state'), 0)
    text = snapshot.get('reply') or {
        0:'Waiting for the companion to receive your prompt.', 1:'Your prompt is queued.',
        2:'Codex is working.', 3:'Codex is writing.'}.get(state, 'Completed without response text.')
    encoded = str(text).encode('utf-8')
    if len(encoded) > MAX_TEXT:
        encoded = encoded[:MAX_TEXT-90].decode('utf-8',errors='ignore').encode('utf-8')
        encoded += b'\n\nPreview limit reached. The full reply is in the companion.'
    total = max(1, math.ceil(len(encoded)/CHUNK))
    part = control.page if control.page <= total else 1
    payload = encoded[(part-1)*CHUNK:part*CHUNK]
    revision = zlib.adler32(bytes([state])+encoded)
    header = HEADER.pack(b'CFN1',1,state,len(payload),bytes.fromhex(control.session),
                         control.request,control.slot,revision,part,total)
    body = header + payload.ljust(CHUNK,b'\0')
    return body + struct.pack('>I',zlib.adler32(body))


def make_font(data, slot):
    if len(data)!=PACKET_SIZE or not 1<=slot<=BANK_SIZE:
        raise ValueError('Invalid native font packet or slot')
    # Private-use characters index packet positions, not the decoded reply text.
    # Keep a conventional printable Latin repertoire as well as data glyphs.
    # Some game font loaders derive metrics/fallback eligibility from Latin glyphs.
    values = {**{c:16 for c in range(33,127)},33:0,34:255,126:16,
              **{0xE000+i:v for i,v in enumerate(data)}}
    order = ['.notdef','space']+[f'g{code}' for code in values]
    fb = FontBuilder(1024,isTTF=True); fb.setupGlyphOrder(order)
    fb.setupCharacterMap({32:'space',**{c:f'g{c}' for c in values}})
    glyphs={}; metrics={'.notdef':(512,0),'space':(256,0)}
    for name in order:
        pen=TTGlyphPen(None)
        if name!='space':
            pen.moveTo((0,0));pen.lineTo((64,0));pen.lineTo((64,512));pen.lineTo((0,512));pen.closePath()
        glyphs[name]=pen.glyph()
    metrics.update({f'g{c}':((16+v)*16,0) for c,v in values.items()})
    fb.setupGlyf(glyphs);fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=800,descent=-224)
    family=f'CodexReplyFont{slot}'
    fb.setupNameTable({'familyName':family,'styleName':'Regular','uniqueFontIdentifier':family,
                      'fullName':family,'psName':family,'version':'Version 1.0'})
    fb.setupOS2(sTypoAscender=800,sTypoDescender=-224,usWinAscent=800,usWinDescent=224)
    fb.setupPost();fb.setupMaxp()
    output=BytesIO();fb.save(output);return output.getvalue()


def font_path(directory, slot):
    if not 1<=slot<=BANK_SIZE: raise ValueError('Font bank exhausted')
    path=directory/f'fontreply{slot:04}.ttf'
    if path.resolve().parent!=directory.resolve(): raise ValueError('Unexpected font path')
    return path


def prepare_bank(directory, count=BANK_SIZE, progress=None):
    """Create missing valid placeholders, sharing at most 512 names per file.

    Never overwrite an existing slot. Writers MUST publish by atomic replacement,
    as NativeBridge does, rather than writing through a shared hard link.
    A failed/interrupted installation can be resumed by running this again.
    """
    directory=validate_addon(directory)
    if type(count) is not int or not 1<=count<=BANK_SIZE:
        raise ValueError('Invalid font bank size')
    started=time.monotonic();existing=set()
    with os.scandir(directory) as entries:
        for entry in entries:
            if entry.name.startswith('fontreply') and entry.name.endswith('.ttf'):
                if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                    raise ValueError('Font slot is not an ordinary file: '+entry.name)
                existing.add(entry.name)
    baseline=None;seed=None;links=0;created=0;groups=0
    try:
        for slot in range(1,count+1):
            path=directory/f'fontreply{slot:04}.ttf'
            if path.name in existing: continue
            if seed is None or links==512:
                if seed is not None: seed.unlink();seed=None
                if baseline is None: baseline=make_font(bytes(PACKET_SIZE),1)
                fd,name=tempfile.mkstemp(prefix='.fontseed-',suffix='.ttf',dir=directory)
                seed=Path(name)
                with os.fdopen(fd,'wb') as file: file.write(baseline)
                links=0;groups+=1
            try:
                os.link(seed,path)
            except FileExistsError:
                if path.is_symlink() or not path.is_file(): raise
                continue  # Another installer won; never replace its file.
            except OSError as exc:
                raise RuntimeError('Compact font installation requires hard-link support (NTFS on Windows). '
                                   'Existing slots are preserved; rerun to resume.') from exc
            links+=1;created+=1
            if progress and created%512==0: progress(created)
    finally:
        if seed is not None: seed.unlink(missing_ok=True)
    return {'slots':count,'created':created,'preserved':count-created,'shared_groups_created':groups,
            'new_font_payload_bytes':groups*len(baseline or b''),'filesystem_metadata_included':False,
            'seconds':round(time.monotonic()-started,3)}


class NativeBridge:
    def __init__(self,directory,clock=time.monotonic):
        self.directory=validate_addon(directory);self.clock=clock
        for slot in (1,BANK_SIZE):
            if not font_path(self.directory,slot).is_file(): raise ValueError('Install the native font bank first')
        self.session=None;self.slot=0;self.deadline=0;self.was_active=False;self.written=None
        self.pending_slot=0;self.pending_bytes=None

    def accept(self,control,snapshot):
        if control.kind!='font': raise ValueError('Expected native font control')
        if self.session!=control.session:
            self.session=control.session;self.slot=0;self.was_active=False;self.written=None
            self.pending_slot=0;self.pending_bytes=None
        if control.slot<self.slot: return False
        now=self.clock();deadline=now+control.remaining_ms/1000-.75
        if control.slot!=self.slot or (control.active and not self.was_active): self.deadline=deadline
        else: self.deadline=min(self.deadline,deadline)
        self.slot=control.slot;self.was_active=control.active
        if not control.active or control.remaining_ms<1000 or now>=self.deadline: return False
        path=font_path(self.directory,control.slot)
        if not path.is_file(): raise ValueError('Native font slot missing')
        # Freeze one complete packet per slot; writing it again is not a delivery ACK.
        if self.pending_slot!=control.slot:
            self.pending_slot=control.slot;self.pending_bytes=make_packet(control,snapshot)
        identity=(control.session,control.slot,self.pending_bytes)
        if identity==self.written: return False
        body=make_font(self.pending_bytes,control.slot)
        if self.clock()>=self.deadline: return False
        temporary=path.with_suffix('.next.ttf');temporary.write_bytes(body)
        if self.clock()>=self.deadline:
            temporary.unlink(missing_ok=True);return False
        temporary.replace(path);self.written=identity
        return True
