# Verification

The local Windows suite contains **86 tests**, using Python 3.12, Pillow/FreeType,
fontTools and Lupa's Lua 5.1 runtime. The initial GitHub Windows CI run also passed all 86 tests on commit `5eda9a7`.
[Hosted result](https://github.com/0xInuarashi/wow-forever-codex/actions/runs/35528904070).
Local/hosted tests remain distinct from the live-client observations below.

Coverage includes:

- Optical packet checksums, assembly, duplicate suppression and control routing.
- Agent event handling and inbox persistence without a live agent login.
- Real generated fonts decoded through measured glyph widths and production Lua.
- Consecutive replies, multipart UTF-8, cached old slots, blank writes, corruption,
  transient write errors and automatic idle after completion.
- Item insertion/normalization and returned links, metadata availability,
  draft routing and rejection of untrusted markup.
- Four-to-five-digit filename transitions, actual slot 65,535 delivery and the
  inactive 65,536 exhaustion marker. Legacy image limits remain unchanged.
- Compact hard-link isolation, existing-file preservation and resumable setup.
- A clean-source installation that recreates fixed diagnostic assets and
  preserves previously written font/image data on a second run.

## Live observations

In Forever **1.60.1.69913**, the native receiver delivered actual agent responses,
including a subsequent conversation reply and multipart item-related responses.
Completion raised a badge and left the strip inactive. These observations were
made on the earlier smaller bank using the same font-packet transport.

Two independent live matrix runs decoded fresh data from pre-existing empty
files and shared valid font placeholders after external publication. Newly
created paths remained unknown mid-session. Reusing loaded paths through new
font objects/families or outline changes returned cached bytes. Both fresh and
reused larger-size controls failed, so that comparison was inconclusive.

The 65,535-name upgrade was checked on disk, including preservation of all 1,024
existing font files and independently decoding representative new baseline
fonts through slot 65,535. Full-bank startup performance and live delivery at
the highest slot remain unverified. UI stubs do not establish real item-link
mouse behavior or whether the duplicate stack-split menu is fully resolved.

## Manual check after installation

1. Load the addon or manually `/reload` after updating its code.
2. Confirm the panel title says `Codex | Live text 0.4.7`.
3. Run the companion with the installed addon path and correct strip crop.
4. Send two short prompts in sequence. Confirm both final replies arrive, each
   completion raises a badge, and the strip becomes steady.
5. Focus the message box, Shift-click a stacked bag item, and check that the link
   inserts without an unwanted split dialog. Check ordinary splitting when the
   Codex box is unfocused.
6. Ask for an item reference, then check native hover/click and Shift-click draft
   insertion. No click should automatically send a message.

If new asset names are not discovered after reload, restart the client. Preserve
the inbox and existing fonts while investigating a failed transfer. All game
input in manual checks must come from the user.
