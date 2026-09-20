"""Finite, first-use addon image slots. No native game access or input generation."""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import struct
import time
import zlib

from PIL import Image, ImageDraw, ImageFont
from .limits import FONT_BANK_SIZE

BANK_SIZE = 4096
BLOCK_SIZE = 32
SLOT_SECONDS = 5
MAX_FULL_IMAGES = 256
CONTROL = struct.Struct('>IIHHII')
HEADER = struct.Struct('>4sBBBB8sI')


@dataclass(frozen=True)
class Control:
    session: str
    slot: int
    remaining_ms: int
    page: int
    active: bool
    request: int
    loaded: int
    kind: str = 'image'


def parse_control(frame):
    if len(frame) != 64 or zlib.adler32(frame[:60]) != int.from_bytes(frame[60:], 'big'):
        raise ValueError('Invalid control checksum')
    magic, version, length, part, total, session, message = HEADER.unpack(frame[:20])
    if magic not in (b'CPBC', b'CPBN') or (version, length, part, total, message) != (2 if magic==b'CPBN' else 1, CONTROL.size, 0, 1, 0):
        raise ValueError('Invalid control header')
    if any(frame[20 + CONTROL.size:60]):
        raise ValueError('Invalid control padding')
    slot, remaining, page, flags, request, loaded = CONTROL.unpack(frame[20:40])
    capacity = FONT_BANK_SIZE if magic == b'CPBN' else BANK_SIZE
    if not 1 <= slot <= capacity + 1 or not 0 <= loaded < slot or loaded != slot - 1:
        raise ValueError('Invalid return slot')
    if not 1 <= page <= 128 or flags not in (0, 1) or not 0 <= remaining <= 6500:
        raise ValueError('Invalid preview control')
    if flags and (slot > capacity or request == 0):
        raise ValueError('Invalid active preview')
    return Control(session.hex(), slot, remaining, page, bool(flags), request, loaded, 'font' if magic==b'CPBN' else 'image')


def encode_control(session=b'12345678', slot=1, remaining_ms=5000, page=1, active=True, request=1, kind='image'):
    body = HEADER.pack(b'CPBN' if kind=='font' else b'CPBC', 2 if kind=='font' else 1, CONTROL.size, 0, 1, session, 0)
    body += CONTROL.pack(slot, remaining_ms, page, int(active), request, slot - 1)
    body = body.ljust(60, b'\0')
    frame = body + struct.pack('>I', zlib.adler32(body))
    parse_control(frame)
    return frame


def validate_addon(directory):
    directory = Path(directory).resolve()
    if directory.name != 'CodexPixelBridge' or not (directory / 'CodexPixelBridge.toc').is_file():
        raise ValueError('Select the installed CodexPixelBridge addon folder')
    return directory


def slot_path(directory, slot):
    if not 1 <= slot <= BANK_SIZE:
        raise ValueError('Image bank exhausted')
    path = directory / f'reply{slot:04}.tga'
    if path.resolve().parent != directory.resolve():
        raise ValueError('Unexpected image path')
    return path


def placeholder(checkpoint=False):
    return Image.new('RGBA', (2, 2), (17, 21, 28, 255 if checkpoint else 0))


def prepare_bank(directory):
    """Installation only, before UI load; never overwrite a live bank."""
    directory = validate_addon(directory)
    from io import BytesIO
    blobs = {}
    for checkpoint in (False, True):
        buffer = BytesIO()
        placeholder(checkpoint).save(buffer, format='TGA')
        blobs[checkpoint] = buffer.getvalue()
    created = 0
    for slot in range(1, BANK_SIZE + 1):
        path = slot_path(directory, slot)
        if not path.exists():
            path.write_bytes(blobs[(slot - 1) % BLOCK_SIZE == 0])
            created += 1
    return created


def font(size, bold=False):
    name = 'segoeuib.ttf' if bold else 'segoeui.ttf'
    try:
        return ImageFont.truetype(str(Path('C:/Windows/Fonts') / name), size)
    except OSError:
        return ImageFont.load_default(size=size)


def wrap_text(text, face, width):
    lines = []
    for paragraph in str(text).replace('\r', '').replace('\t', '    ').split('\n'):
        if not paragraph:
            lines.append('')
            continue
        line = ''
        for word in paragraph.split(' '):
            candidate = (line + ' ' + word) if line else word
            if face.getlength(candidate) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
            line = ''
            for char in word:
                if line and face.getlength(line + char) > width:
                    lines.append(line)
                    line = ''
                line += char
        lines.append(line)
    return lines


def render_reply(snapshot, page):
    state = snapshot.get('state', 'waiting')
    reply = snapshot.get('reply', '')
    labels = {'queued': 'Queued', 'working': 'Working', 'streaming': 'Writing',
              'done': 'Reply ready', 'failed': 'Could not finish', 'interrupted': 'Interrupted'}
    color = {'done': '#5fdb9b', 'failed': '#ff937a', 'interrupted': '#ff937a'}.get(state, '#8dbdff')
    image = Image.new('RGB', (512, 512), '#11151c')
    draw = ImageDraw.Draw(image)
    body, title, small = font(16), font(20, True), font(12)
    # The same corner is cropped by the native minimap status badge.
    draw.rectangle((0, 0, 31, 31), fill=color)
    draw.text((12, 1), '!' if state in ('done', 'failed') else '~', font=font(22, True), fill='#11151c')
    draw.text((44, 6), 'Codex  /  ' + labels.get(state, 'Waiting for companion'), font=title, fill=color)
    prompt = snapshot.get('prompt', '')
    prompt_lines = wrap_text(prompt, small, 476)
    draw.text((18, 42), 'You: ' + (prompt_lines[0][:95] if prompt_lines else ''), font=small, fill='#aab6c5')
    draw.line((18, 67, 494, 67), fill='#313b49')
    if not reply:
        reply = {'working': 'Codex is working. Its reply will appear here automatically.',
                 'queued': 'Your prompt is queued.',
                 'waiting': 'Waiting for the companion to receive your prompt.'}.get(state, 'Waiting for reply text.')
    text = reply[:60000]
    if len(reply) > len(text):
        text += '\n\nPreview limit reached. The full reply is in the companion.'
    lines = wrap_text(text, body, 476)
    per_page = 19
    pages = max(1, math.ceil(len(lines) / per_page))
    # Lua cannot know the rendered page count. An extra Next must never
    # replace a valid reply with an empty/end screen, including while writing.
    page = max(1, min(page, pages))
    visible = lines[(page - 1) * per_page:page * per_page]
    for i, line in enumerate(visible):
        draw.text((18, 82 + i * 20), line, font=body, fill='#ecf0f6')
    draw.line((18, 472, 494, 472), fill='#313b49')
    draw.text((18, 484), f'Page {page} / {pages}   |   Previous / Next below', font=small, fill='#aab6c5')
    return image


def limit_image():
    image = Image.new('RGB', (128, 128), '#191713')
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 7, 7), fill='#f3c773')
    draw.multiline_text((8, 13), 'Preview limit\nRead replies in\nthe companion.\n\nReload the UI\nwhen ready.', font=font(13), spacing=3, fill='#f3c773')
    return image


class VisualBridge:
    def __init__(self, directory, clock=time.monotonic, budget_path=None):
        self.directory = validate_addon(directory)
        if not slot_path(self.directory, 1).is_file() or not slot_path(self.directory, BANK_SIZE).is_file():
            raise ValueError('Install the reply image bank before loading the addon')
        self.clock = clock
        self.session = None
        self.slot = 0
        self.last_seen = 0
        self.displayed = None
        self.pending = None
        self.written = None
        self.writes = 0
        self.slot_deadline = 0
        self.was_active = False
        self.cached_signature = None
        self.cached_image = None
        self.budget_path = Path(budget_path) if budget_path else None
        self.full_slots = set()
        if self.budget_path:
            if self.budget_path.exists():
                saved = json.loads(self.budget_path.read_text(encoding='utf-8'))
                session = saved.get('session') if isinstance(saved, dict) else None
                slots = saved.get('full_slots') if isinstance(saved, dict) else None
                if not isinstance(session, str) or len(session) != 16 or any(c not in '0123456789abcdef' for c in session):
                    raise ValueError('Invalid preview budget session')
                if not isinstance(slots, list) or any(type(i) is not int or not 1 <= i <= BANK_SIZE for i in slots):
                    raise ValueError('Invalid preview budget slots')
                self.session, self.full_slots = session, set(slots)
            else:
                # Conservative first adoption of an already-running bank.
                self.full_slots = {i for i in range(1, BANK_SIZE + 1)
                                   if slot_path(self.directory, i).is_file() and slot_path(self.directory, i).stat().st_size > 65536}

    def save_budget(self):
        if self.budget_path:
            self.budget_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.budget_path.with_suffix('.next.json')
            temporary.write_text(json.dumps({'session':self.session, 'full_slots':sorted(self.full_slots)}), encoding='utf-8')
            temporary.replace(self.budget_path)

    def accept(self, control, snapshot):
        now = self.clock()
        if control.session != self.session:
            if self.session is not None:
                self.full_slots = set()
            self.session = control.session
            self.slot = 0
            self.was_active = False
            self.displayed = self.pending = self.written = None
        if control.slot < self.slot:
            return False
        candidate_deadline = now + control.remaining_ms / 1000 - 0.75
        if control.slot != self.slot or (control.active and not self.was_active):
            self.slot_deadline = candidate_deadline
        else:
            # A frozen/repeated screenshot must never extend an old slot's deadline.
            self.slot_deadline = min(self.slot_deadline, candidate_deadline)
        self.was_active = control.active
        if self.pending and control.loaded >= self.pending[0]:
            if self.pending[1]:
                self.displayed = self.pending[2]
            self.pending = None
        recovered = now - self.last_seen > 12
        self.last_seen = now
        if recovered:
            self.displayed = None
        self.slot = control.slot
        if not control.active or control.remaining_ms < 1000 or now >= self.slot_deadline:
            return False
        key = f'{control.session}:{control.request}'
        if snapshot.get('id') != key:
            snapshot = {'id': key, 'state': 'waiting', 'reply': '', 'prompt': ''}
        signature = hashlib.sha256(repr((snapshot, control.page)).encode('utf-8')).hexdigest()
        limited = len(self.full_slots) >= MAX_FULL_IMAGES and control.slot not in self.full_slots
        if limited:
            signature = 'preview-resource-limit'
        full = (control.slot - 1) % BLOCK_SIZE == 0 or signature != self.displayed
        identity = (control.slot, full, signature)
        if identity == self.written:
            return False
        destination = slot_path(self.directory, control.slot)
        if not destination.is_file():
            raise ValueError('Reply asset missing; files must exist before UI load')
        if full and limited:
            image = limit_image()
        elif full:
            if signature != self.cached_signature:
                self.cached_image = render_reply(snapshot, control.page)
                self.cached_signature = signature
            image = self.cached_image
        else:
            image = placeholder()
        if self.clock() >= self.slot_deadline:
            return False
        if full and not limited and control.slot not in self.full_slots:
            self.full_slots.add(control.slot)
            # Reserve before committing the asset; interrupted writes remain counted.
            self.save_budget()
        temporary = destination.with_suffix('.next.tga')
        image.save(temporary, format='TGA')
        if self.clock() >= self.slot_deadline:
            temporary.unlink(missing_ok=True)
            return False
        temporary.replace(destination)
        self.written = identity
        self.pending = (control.slot, full, signature)
        self.writes += 1
        return True
