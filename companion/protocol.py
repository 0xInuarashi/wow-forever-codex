"""CPB1: fixed binary frames; no game access, commands or executable payloads."""
import struct
import time
import zlib

HEADER = struct.Struct('>4sBBBB8sI')
SIZE, COLS, ROWS, CHUNK, MAX_PARTS = 64, 128, 4, 40, 32

def encode(text, session=b'12345678', message=1):
    data = text.encode('utf-8')
    if not 1 <= len(data) <= CHUNK * MAX_PARTS:
        raise ValueError('Prompt must contain 1..1280 UTF-8 bytes')
    total = (len(data) + CHUNK - 1) // CHUNK
    result = []
    for part in range(total):
        chunk = data[part*CHUNK:(part+1)*CHUNK]
        body = HEADER.pack(b'CPB1', 1, len(chunk), part, total, session, message)
        body += chunk.ljust(CHUNK, b'\0')
        result.append(body + struct.pack('>I', zlib.adler32(body)))
    return result

def parse(frame):
    if len(frame) != SIZE or zlib.adler32(frame[:60]) != int.from_bytes(frame[60:], 'big'):
        raise ValueError('Invalid length/checksum')
    magic, version, length, part, total, session, message = HEADER.unpack(frame[:20])
    if magic != b'CPB1' or version != 1 or not 1 <= total <= MAX_PARTS or not 0 <= part < total:
        raise ValueError('Invalid header')
    if not 1 <= length <= CHUNK or (part < total-1 and length != CHUNK) or message == 0:
        raise ValueError('Invalid payload')
    if any(frame[20+length:60]):
        raise ValueError('Nonzero padding')
    return session.hex() + ':' + str(message), part, total, frame[20:20+length]

def read_image_frame(image):
    """Sample a crop. Callers must validate their own packet type/checksum."""
    image = image.convert('RGB')
    w, h = image.size
    if w < COLS or h < ROWS:
        raise ValueError('Crop too small')
    bits = []
    for row in range(ROWS):
        for col in range(COLS):
            rgb = image.getpixel((int((col+.5)*w/COLS), int((row+.5)*h/ROWS)))
            if max(rgb)-min(rgb) > 45 or 80 < sum(rgb)/3 < 175:
                raise ValueError('Ambiguous/obscured pixel')
            bits.append(int(sum(rgb)/3 >= 175))
    return bytes(sum(bits[i+j] << (7-j) for j in range(8)) for i in range(0,512,8))

def decode_image(image):
    """Image must be an exact, axis-aligned crop of the 128 x 4 cell strip."""
    frame = read_image_frame(image)
    if frame[:4] in (b'CPBC', b'CPBN'):
        from .visual import parse_control
        parse_control(frame)
    else:
        parse(frame)
    return frame

def render(frame, cell=4):
    from PIL import Image, ImageDraw
    image = Image.new('RGB', (COLS*cell, ROWS*cell))
    draw = ImageDraw.Draw(image)
    for i in range(512):
        value = 255 if frame[i//8] & (1 << (7-i%8)) else 0
        x, y = (i%COLS)*cell, (i//COLS)*cell
        draw.rectangle((x,y,x+cell-1,y+cell-1), fill=(value,)*3)
    return image

class Assembler:
    def __init__(self):
        self.pending = {}

    def accept(self, frame):
        key, part, total, chunk = parse(frame)
        now = time.monotonic()
        self.pending = {k:v for k,v in self.pending.items() if now-v[0] < 180}
        if key not in self.pending:
            if len(self.pending) >= 64:
                self.pending.pop(next(iter(self.pending)))
            self.pending[key] = (now, total, {})
        _, expected, chunks = self.pending[key]
        if total != expected or (part in chunks and chunks[part] != chunk):
            del self.pending[key]
            raise ValueError('Conflicting fragments')
        chunks[part] = chunk
        if len(chunks) == total:
            del self.pending[key]
            return key, b''.join(chunks[i] for i in range(total)).decode('utf-8', errors='strict')
        return None
