# 65,535-slot font bank — 0.4.7

The native return channel now supports 65,535 first-use font filenames, from
`fontreply0001.ttf` to `fontreply65535.ttf`. This is the unsigned 16-bit maximum;
the unsigned 8-bit maximum is 255. The transport already carries slot numbers in
32-bit fields. Slot 65,536 is an inactive exhaustion marker, never a font file.
The separate legacy image bank remains at 4,096 slots.

## Compact installation

The installer creates ordinary, valid fonts with a zero-filled packet, grouped
into at most 512 hard-linked filenames per underlying file. When the companion
publishes a reply it writes a separate temporary file and atomically replaces
only the chosen slot. Other names retain the blank baseline. Do not edit shared
font files in place: writing through a hard link would change its siblings.

When upgrading the original 1,024-slot installation, its files are preserved byte for byte. The 64,511 new
names need 126 shared baseline files, about 2.76 MB of new font payload, plus
filesystem metadata. A completely fresh bank needs 128 underlying baselines,
about 2.81 MB of font payload, plus metadata. As replies consume slots, each
replaced font becomes independent and storage grows. This is not a fixed-size
cache or automatic recycling scheme. The older separately stored fonts remain
allocated; the installer does not consolidate or reset them.

Use the installer from the project root after installing `requirements.txt`:

```powershell
python -m tools.install_addon 'C:\path\to\World of Warcraft\_classic_beta_\Interface\AddOns\CodexPixelBridge'
```

It copies code, preserves existing font/image assets and creates only missing
production slots. It can resume after an interrupted run. Hard-link support is
required (NTFS on Windows); it reports an error instead of falling back to about
1.4 GB of duplicate fonts. All links are made inside the destination directory.
Each group's temporary seed name is removed after creation.

The ZIP omits generated production fonts, since ZIP extraction does not preserve
hard links. Existing local working folders may have prepared banks, but copying those
files with a normal copy tool can also expand their storage. Use the installer
for additional installations. Never copy blank fonts over a live reply bank.

## Loading the update

After installation, manually `/reload` once to load the updated Lua and make the
new filenames available to the UI. If that client session does not discover the
new names, fully restart WoW. The title becomes `Codex | Live text 0.4.7`.
No per-message reload is added. The saved next-slot counter is not reset.

## Reuse after a full restart

On 2026-09-21, two previously loaded diagnostic font filenames delivered new
bytes after a full restart of Forever 1.60.1.69913. One replacement was written
before restart; the other was written after the new client started, before its
first use of that filename. The same-session control still returned cached data.

This establishes reuse of those diagnostic paths across client processes.
Automatic recycling and counter reset are not implemented: restarting today
continues from the saved position. The live test used 64-byte probe packets and
did not reset the 65,535-slot production bank. [Full experiment](font-recycling.md).

## Startup scope

The running addon requests one slot at a time; Lua does not create 65,535 frames
or load every font into memory at startup. The game still has to discover the
directory entries. Startup cost and live discovery at this scale are unverified
until the updated installation is loaded in WoW.

## Verification and remaining limits

86 local tests pass, including real generated fonts measured by FreeType and
the production Lua receiver. New cases cross slot 9,999 to 10,000, deliver a
reply through slot 65,535, stop at 65,536, preserve image limits, detach a written
hard link, preserve existing slots, and resume an interrupted installation.
The local upgrade verified every filename and SHA-256 preservation of all 1,024 existing slots. Private installation records and screenshots are retained locally and excluded from Git.

The earlier live matrix decoded externally updated shared valid placeholders
twice. That demonstrates the storage mechanism on this client build, but does
not establish startup performance or successful use of all 65,535 names. The
larger bank is finite in the current implementation. Loaded fonts returned
cached data within the running client; diagnostic reuse after full restart is
now verified. Automatic full-bank recycling and dynamic discovery of newly
created filenames remain unproven. Reply packet
size, polling cadence, per-frame measurement bounds and the 20-minute watch are
unchanged. No synthetic game input, process memory access or injection is used.
