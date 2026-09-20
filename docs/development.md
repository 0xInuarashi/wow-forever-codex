# Development

`addon/CodexPixelBridge/` contains the native Lua UI, optical protocol, font
receiver, item-link behavior and opt-in diagnostics. `companion/` contains screen
decoding, the durable inbox, the agent adapter and native font writer. `tools/`
contains asset generation and bounded experiments; `tests/` exercises Python,
Lua 5.1 and real font measurements.

Install `requirements-dev.txt`, then run:

```powershell
python -m unittest discover -s tests -v
```

Windows is the target. Tkinter tests need an interactive desktop; some font/UI
behavior is platform-specific. GitHub Actions is configured for Windows and
Python 3.12. No live Codex credentials or game installation are needed for the
automated suite. The separate desktop capture smoke tool opens its own test
window and does not generate input.

## Resource generation

A clean checkout intentionally has no TTF/TGA bank. Run `tools.install_addon` as
shown in the README to create it in an addon installation. Production slots and
fixed diagnostic fonts/images are regenerated from code. Existing assets are
preserved. Larger matrix/discovery experiments require their explicit prepare
step; their default Lua configurations have no armed token.

Production writes must use temporary-file creation followed by atomic
replacement. Never write in place through a shared hard link, reset consumed
slots, or reuse a filename already loaded in the current game process. Changing
the bank capacity requires matching Python/Lua limits and active/exhausted
control tests. Font `unitsPerEm=1024` is a metric scale, unrelated to bank size.

## Repository and releases

Git excludes runtime state, generated resources, private investigation notes,
screenshots, logs, caches and credentials. Keep setup paths generic in published
documentation. Preserve the exclusions when changing packaging.

After committing, create a source archive from tracked files:

```powershell
git archive --format=zip --prefix=forever-bridge/ --output=forever-bridge-source.zip HEAD
```

The archive requires the installer just like a clone. ZIP and ordinary directory
copies do not preserve compact hard-link storage. Do not distribute a live
installation's fonts: those may encode actual replies.

## Client evidence

The implementation was exercised against Forever 1.60.1.69913. API investigation
used the matching exported UI source at commit
[`70ef1b2`](https://github.com/Gethe/wow-ui-source/tree/70ef1b2fd78061a73f886c4a1e79dc5b5cff6d5e).
Relevant declarations include SimpleFontString, SimpleFont, Font, UIFileAsset
and the shared UI XML schema. This exported source is a public mirror of the
client UI, not a description of internal native cache behavior.

Keep live observations separate from modeled test results. New UI code requires
a manual reload; no tooling should synthesize game input to perform it.
