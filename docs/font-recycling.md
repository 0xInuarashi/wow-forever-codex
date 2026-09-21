# Font reuse after a full client restart

**Verified on 2026-09-21 in WoW: Forever 1.60.1.69913 / TOC 16001:** two
previously loaded diagnostic font filenames could deliver new bytes after a
full client restart. One delivered a replacement prepared before restart; the
other delivered data written after the new client had started, before its first
use of that filename.

This supports implementing recycling across game processes. **Automatic
recycling is not implemented.** The current addon preserves its next-slot
counter across normal restarts and continues consuming the finite bank.

## Live observations

The installed addon was version 0.4.7, using the existing
[FontProbe.lua](../addon/CodexPixelBridge/FontProbe.lua) and
[font writer](../tools/font_probe.py). No addon code was changed for the test.
The probe decodes 64-byte CFP1 packets through documented font assignment and
width measurements and validates their Adler-32 checksum.

The table uses A and B for two distinct WoW processes, verified by process ID
and creation time. The old process had exited before the new one was observed.
All listed readings were observed directly on screen.

| Step | Client | File | Data on disk | Decoded in WoW |
| --- | --- | --- | --- | --- |
| Initial read | A | `fontprobe05.ttf` | `Before restart 1b9c3e` | `Before restart 1b9c3e` |
| Replace file and rerun the probe | A | Same file | `Recycled font 1b9c3e` | `Before restart 1b9c3e` |
| Fully close/reopen WoW and run the probe | B | Same file | `Recycled font 1b9c3e` | `Recycled font 1b9c3e` |
| Replace a second previously used file after B starts, before its first read | B | `fontprobe06.ttf` | `After startup 1b9c3e` | `After startup 1b9c3e` |

The second file had already been decoded in client A as `Live 8dd43f / 0074`.
Its new payload was written after client B started and was visible at probe tick
44, following the scheduled tick-40 read. This checks live publication into a
reused filename, beyond just loading a file changed before startup.

Each file kept its exact path and font family name (`CodexFontProbe5` or
`CodexFontProbe6`). Writes used temporary files and atomic replacement. Disk
payloads were independently decoded through FreeType, and the first file's new
hash remained unchanged across the restart. Neither a new filename nor a font
family rename was needed.

Only these two diagnostic assets were modified. Both originals were backed up
and restored byte-for-byte after the test. Production reply fonts, the saved
counter, inbox, companion preferences and calibration were untouched. Game
commands and the full restart were performed by the user; observation used
screen capture and process metadata, with no game memory access or generated
input. Private raw records and screenshots are not included in source releases.

## What this establishes, and what remains open

The same-session comparison returned old data after a fresh probe invocation;
the successful read after process replacement therefore supports **font reuse
across full client restarts** on this build. The second asset also accepted
publication after startup, provided the new client had not yet loaded it.

The test does not establish:

- Recycling within one running client, through `/reload`, logout, character
  changes or a companion restart.
- An automatic reset of all 65,535 production slots, or reliable unattended
  coordination of the slot counter and writer.
- Live reuse of the 512-byte production packet format at full-bank scale, or
  consistent behavior on other client builds.
- Discovery of filenames created mid-session or a documented cache-flush API.

A separate local experiment reused the same production filename and family
across three fresh Python/Pillow/FreeType reader processes. All three decoded
the exact new 512-byte packet. That checks the file format and local writer; it
does not substitute for a live WoW cache test. These standalone experiments did
not add tests to the existing 86-test suite.

## Why restarting does not reset today's bank

[Native.lua](../addon/CodexPixelBridge/Native.lua) restores
`CodexPixelBridgeState.nextFontSlotV2` at addon load and advances the saved value
before requesting a font. It does not distinguish a full process restart from
an addon reload for resetting that value. The
[companion writer](../companion/native.py) resets its temporary bookkeeping on
a new control-session identifier, but follows the slot requested by the addon.
A new control session alone does not prove that WoW's process has restarted.

Consequently, closing and reopening WoW currently resumes the saved position.
The observed ability to reuse filenames does not replenish the bank by itself.
If the bank is exhausted, full replies remain in the companion.

## Repeating the experiment

Use the existing opt-in probe, separate from the chat bank. Record the client
build and preserve the original diagnostic files before publishing test data.
The `packet` and `write_font` functions in
[tools/font_probe.py](../tools/font_probe.py) generate bounded diagnostic data
and publish it atomically; do not write through shared hard links in place.

1. Publish a distinct baseline to diagnostic slot 5. Have the user run
   `/codex fontprobe` and observe valid readings for both slots 5 and 6. Slot 5
   starts at tick 1; slot 6 starts at tick 40, with loading retries if needed.
2. After confirming slot 5 has been read, publish a different value to its exact
   same filename and family. Rerun the probe in the same process. Record its new
   reading, rather than interpreting an old, still-visible result as a reread.
3. Have the user fully close and reopen WoW. Verify process replacement using
   executable identity and creation time; a missing strip or closed window alone
   is not proof that the client process exited.
4. Run the probe in the new client and observe slot 5. Successful decoding of
   the replacement value establishes reuse of that diagnostic filename.
5. Before the new client's first slot-6 read, publish a third value to the
   previously used slot-6 filename. Record whether that exact value decodes. If
   the write window is missed, mark this follow-up inconclusive instead of
   treating cached data as a new delivery.
6. Restore both diagnostic originals atomically and verify their hashes. Keep
   the production bank and saved counter unchanged throughout the experiment.

## Requirements for a future automatic recycler

A recycler needs reliable evidence of a full client exit and a coordinated new
generation for the reader, writer and slot position. It must preserve the bank
when process identity is unknown, another client is using it, or the companion
has merely reconnected. Editing SavedVariables while WoW is running cannot
reliably replace the game's runtime copy.

The reset must handle interrupted preparation, quick client restarts, stale
packets and late worker results without admitting data from the previous
generation. It must retain atomic publication so shared baselines remain
isolated. Reusing filenames does not automatically restore compact hard-link
storage. These are implementation requirements, not features provided by the
current prototype.

See [bank storage and limits](font-bank.md), [test coverage](testing.md) and
[client API evidence](development.md#client-evidence). The cache behavior above
is an empirical result, not a general-purpose file-access guarantee in the
documented addon API.
