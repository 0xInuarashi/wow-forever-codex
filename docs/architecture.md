# Communication architecture

```mermaid
flowchart LR
    UI[WoW addon chat] --> Strip[Pixel strip]
    Strip --> Capture[Companion screen capture]
    Capture --> Inbox[Checked packets and durable inbox]
    Inbox --> Agent[Local Codex process]
    Agent --> Font[Atomic replacement of unused font asset]
    Font --> Metrics[Documented font width measurements]
    Metrics --> Reply[Checked UTF-8 response in native frame]
```

## Outbound pixels

The addon draws a 128 by 4 grid of binary cells: 512 bits, or 64 bytes per frame.
At the nominal four-pixel cell size, the strip is 512 by 16 screen pixels. Actual
desktop capture dimensions depend on UI/display scaling. Prompt frames use CPB1,
an eight-byte session identifier, a 32-bit request sequence, part counts and
Adler-32. Forty payload bytes fit each prompt frame; 32 parts allow up to 1,280
UTF-8 bytes. The companion assembles validated packets and uses its SQLite inbox
to deduplicate requests before launching an agent.

The strip alternates prompts and receive-control packets while active. CPBN v2
control frames carry the next font slot, milliseconds remaining in its write
window, requested response fragment, active flag, request ID and previous slot.
Control and diagnostic frames cannot be interpreted as prompts. Idle frames are
steady and historical prompts stop repeating after completion or pause.

## Inbound font metrics

Font filenames must exist before the game discovers addon resources. Before the
first load of an unused slot, the companion creates a valid TrueType font whose
private-use glyph advance widths encode a 512-byte response packet. Publication
uses an atomic file replacement. Loaded paths are treated as consumed because
the tested client continued returning cached data after files were rewritten.

The addon calls ordinary SetFont, SetText and GetStringWidth APIs. Two calibration
glyphs define byte values zero and 255; a common trailing glyph stabilizes width
measurement. U+E000 onward selects each packet byte. Font units-per-em is 1,024,
the nominal measurement size is 64, and each value maps to `(16 + byte) * 16`
advance units. Fonts contain ordinary outlines and metrics, no TrueType programs.
The reader retries asynchronous assignment and measures at most 32 data glyphs
per frame.

The packet header is `>4sBBH8sIIIHH`, followed by up to 476 bytes of UTF-8 data,
zero padding and a four-byte Adler-32 checksum:

| Field | Meaning |
| --- | --- |
| Magic/version | CFN1 / 1 |
| State | waiting, queued, working, streaming, done, failed or interrupted |
| Length | Bytes in this fragment |
| Session/request/slot | Must match the current request and expected file |
| Revision | Checksum of state and complete preview text |
| Part/total | One-based fragment and total, up to 127 |

The receiver rejects stale/corrupt packets and assembles a single complete
revision before displaying text. Partial UTF-8 sequences may span packets.
Response text is never evaluated as Lua or game commands. Raw markup is escaped;
explicit `[label](item:ID[:fields])` references are validated and rendered using
game-provided item metadata.

## Timing, storage and boundaries

The initial write window is six seconds; subsequent windows normally use five.
The companion freezes one packet per slot and will not extend a deadline based
on repeated screenshots. Blank installation packets preserve partial assembly
and retry a fresh slot with bounded backoff. Three real loading/corruption errors
pause reception. A complete final reply pauses immediately and raises a badge.

The 65,535-slot bank uses hard-linked blank baselines; publication detaches one
filename. Both slot fields are 32-bit, so the inactive sentinel 65,536 needs no
wire-format change. The addon saves its next slot before requesting a font. Beta
settings restoration has sometimes lost that counter, so checksum-valid old
packets are skipped through normal font reads. [Storage details](font-bank.md).

Checksums detect corruption, not malicious local forgery. The bridge assumes the
local desktop and addon directory are trusted. It does not access game memory,
inject code, generate input, use restricted URL APIs or bypass client checks.
Newly created filenames were not discovered mid-session in the tested build;
automatic cache recycling and arbitrary runtime file access are not provided.
