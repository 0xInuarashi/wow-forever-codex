# Agent guide: install and run WoW Forever Codex

This is the repository-level entry point for agents. Use it when the user asks
to install, run, update or troubleshoot the addon and companion. A request to
edit documentation alone does not authorize reinstalling or restarting anything.

Canonical repository: <https://github.com/0xInuarashi/wow-forever-codex>.
The product name and addon folder remain **Forever Bridge** and
**CodexPixelBridge**. Do not rename the addon folder to match the repository.

## What you are installing

- `addon/CodexPixelBridge/`: native WoW Lua UI and optical/font protocols.
- `companion/`: local Python GUI, screen capture, durable inbox and Codex adapter.
- `tools/install_addon.py`: the installer. It copies code and creates missing
  font/image assets without resetting existing resources.
- `Launch Companion.pyw`: optional desktop launcher; uses the repository's
  `state/launcher.json` and native Codex discovery.

The current production bank has **65,535 first-use fonts**. A clean Git checkout
contains no generated TTF/TGA files. Copying the addon source folder alone is
not a complete installation. The installer also creates 4,096 legacy image
placeholders and the fixed diagnostic resources; normal replies use fonts.

## Boundaries and existing installations

1. Use documented addon APIs, ordinary file operations and screen capture only.
   Never inject code into WoW, read game-process memory, bypass client checks,
   synthesize game input or use protected URL calls. The user types game commands.
2. Preserve all existing font/image assets, SavedVariables, inbox data, settings
   and capture calibration. Never reset a bank or its next-slot counter as a
   routine repair. Never write in place through a shared font hard link.
3. Keep one companion per inbox/addon. Reuse the running instance when possible.
   Before restarting your own companion, check that its queue is idle and close
   it normally. Startup marks unfinished inbox jobs interrupted; do not start a
   second process against that database. Do not terminate or restart WoW.
4. Keep the Codex sandbox `read-only` unless the user has authorized project
   edits. Send prompts as data through the existing adapter; do not interpolate
   prompt text into shell commands.
5. Complete authorized setup and local checks before asking for the final manual
   game step. Ask only for unresolved choices or required sign-in/game input.
   Explain the specific missing detail or reason for a reload.
6. Keep machine-specific paths, screenshots, credentials and runtime data out of
   commits. Observe `.gitignore`; generated fonts can contain actual reply bytes.

## 1. Resolve the installation paths

Discover or infer these from the existing installation before asking the user:

| Variable | Meaning |
| --- | --- |
| `bridgeRoot` | Stable local checkout containing `companion/`, `tools/` and the launcher |
| `bridgeClient` | Actual Forever client directory containing the game executable and `Interface/` |
| `bridgeAddon` | `bridgeClient/Interface/AddOns/CodexPixelBridge` |
| `bridgeProject` | Existing work directory Codex should operate in; separate from the game installation |
| `bridgeState` | Existing companion state directory; normally `bridgeRoot/state` |
| `bridgeCodex` | Verified native `codex.exe` path |

For upgrades, read the current companion's configuration and launch location
first. A source copy and the running companion may be in different folders.
Changing folders must not silently create a new inbox or orphan the desktop
shortcut. Do not print private inbox contents while discovering paths.

Windows, Python **3.12+ with tkinter**, and a filesystem supporting hard links
(normally NTFS) are required. The tested client was Forever **1.60.1.69913 / TOC
16001**, commonly under `_classic_beta_`. Check the actual installation instead
of assuming a drive letter, retail client, or another Classic folder. If WoW is
running, its executable path is useful discovery metadata; avoid printing its
full command line, which may contain login arguments. If several installations
are plausible and no saved path resolves the choice, ask which one to target.

All examples below run in PowerShell. Replace example paths with discovered
absolute paths. Do not overwrite a valid saved value with an example.

```powershell
$bridgeRoot = (Get-Location).Path  # Run from this checkout's root.
$bridgeClient = 'C:\path\to\World of Warcraft\_classic_beta_'
$bridgeAddon = Join-Path $bridgeClient 'Interface\AddOns\CodexPixelBridge'
$bridgeProject = 'C:\path\to\work-project'
$bridgeState = Join-Path $bridgeRoot 'state'
```

## 2. Prepare the Python runtime and locate Codex

Reuse a working project virtual environment. Otherwise, select an installed
Python 3.12+ and create one; substitute that interpreter for `python` below.
Do not overwrite an existing environment just because `python` on PATH differs.

```powershell
Set-Location -LiteralPath $bridgeRoot
python --version
# Run only if this checkout does not already have a usable .venv:
python -m venv .venv
$bridgePython = Join-Path $bridgeRoot '.venv\Scripts\python.exe'
& $bridgePython -m pip install -r requirements.txt
& $bridgePython -c "import sys, tkinter, PIL, fontTools; assert sys.version_info >= (3, 12); print('Python dependencies ready')"
```

Prefer a valid remembered `codex` path in `launcher.json`. If none exists, use the
same discovery helper as the launcher instead of making the user browse for an
executable or hardcoding a versioned Codex desktop path:

```powershell
$bridgeCodex = (& $bridgePython -c "from companion.launching import find_codex; print(find_codex())").Trim()
if (-not $bridgeCodex -or -not (Test-Path -LiteralPath $bridgeCodex -PathType Leaf)) {
    throw 'Native Codex CLI not found. Resolve its installation before continuing with the real backend.'
}
& $bridgeCodex --version
```

The real backend needs Codex authentication. Use the installed CLI's help/status
commands to check it; request user sign-in only if it is missing. Do not ask the
user to paste tokens into chat. GitHub authentication is separate from Codex
authentication. For a transport-only test, use the mock backend without Codex.

## 3. Install the addon and generate its assets

Validate that `bridgeClient` is the intended game client before writing into it.
Use the installer even when the game is currently open: it preserves existing
resource files, and changed Lua takes effect only when the user reloads.

```powershell
& $bridgePython -m tools.install_addon $bridgeAddon
if ($LASTEXITCODE -ne 0) { throw 'Addon installation did not complete.' }
```

The installer creates only missing bank slots and can resume after interruption.
Hard-link groups keep a fresh bank near 2.81 MB of font payload plus filesystem
metadata; used slots become independent files. If hard links are unavailable,
report that constraint rather than copying roughly 1.4 GB of fonts or creating
empty files by hand. Do not copy clean fonts from another installation over this
one, and do not modify fonts already consumed by a running client.

Verify the installed TOC/Lua files against the source and check every expected
font filename. This read-only check also constructs the production bridge:

```powershell
@'
from pathlib import Path
import sys
from companion.native import BANK_SIZE, NativeBridge
addon = Path(sys.argv[1]).resolve()
source = Path('addon/CodexPixelBridge')
for file in source.iterdir():
    if file.suffix.lower() in ('.lua', '.xml', '.toc'):
        assert (addon / file.name).read_bytes() == file.read_bytes(), file.name
expected = {f'fontreply{i:04}.ttf' for i in range(1, BANK_SIZE + 1)}
present = {file.name for file in addon.iterdir() if file.is_file()}
missing = expected - present
assert not missing, f'{len(missing)} font slots are missing'
NativeBridge(addon)
print(f'Installed code matches; all {BANK_SIZE:,} font slots are present')
'@ | & $bridgePython - $bridgeAddon
```

This verifies disk installation, not live asset discovery or in-game delivery.

## 4. Configure the companion without losing state

The reliable first launch passes **both** the work project and installed addon
path explicitly. Also use the intended state directory:

```powershell
& $bridgePython -m companion.app --backend codex --project $bridgeProject --codex $bridgeCodex --addon $bridgeAddon --state $bridgeState
```

Do not run that command if the existing companion is already using this inbox.
For mock operation, use `--backend mock` and omit `--codex`; keep the addon,
project and state arguments. Prefer a separate temporary state directory for
mock tests so their messages do not enter the real inbox.

**Launcher pitfall:** passing `--addon` to `companion.app` does not by itself
persist that path for `Launch Companion.pyw`. Before relying on the desktop
launcher, merge `project`, `codex` and `addon` into the launcher's own
`bridgeRoot/state/launcher.json`. Preserve all other keys and keep
`state/capture.json` unchanged. Do not rewrite preferences while a running
companion may be saving them; use its existing valid configuration or close it
normally when idle first.

If the active inbox lives elsewhere, keep using the explicit `--state` command
until its ownership/location is deliberately resolved. The following merge is
for the normal launcher-owned state directory only:

```powershell
@'
import json, sys
from pathlib import Path
state, project, codex, addon = map(Path, sys.argv[1:])
assert project.is_dir() and codex.is_file()
assert (addon / 'CodexPixelBridge.toc').is_file()
state.mkdir(parents=True, exist_ok=True)
path = state / 'launcher.json'
config = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
assert isinstance(config, dict), 'Existing launcher settings need inspection'
config.update(project=str(project.resolve()), codex=str(codex.resolve()), addon=str(addon.resolve()))
temporary = path.with_suffix('.next.json')
temporary.write_text(json.dumps(config, indent=2), encoding='utf-8')
temporary.replace(path)
print('Launcher paths saved; other preferences preserved')
'@ | & $bridgePython - $bridgeState $bridgeProject $bridgeCodex $bridgeAddon
```

After configuring, run the launcher with the same Python environment. Do not
launch it alongside a companion started by the explicit command:

```powershell
& $bridgePython '.\Launch Companion.pyw'
```

If the user wants a desktop shortcut, target this environment's `pythonw.exe`,
pass the quoted absolute `Launch Companion.pyw` path, and set the working
directory to `bridgeRoot`. Do not rely on an arbitrary system `.pyw` association.
For background launches with `Start-Process`, use `-WindowStyle Hidden`.
`--start-capture` and `--minimized` are launcher options only after calibration
and saved paths are known to be correct. Do not automatically change notification
or sandbox preferences during installation.

## 5. Calibrate and verify with the user

1. Reuse valid saved `state/capture.json` coordinates. Otherwise identify the
   exact strip crop in desktop pixels: left, top, width, height. The nominal
   strip is **512 × 16 at (8, 8)**; UI/display scaling can change it. Never replace
   a working crop with those nominal values just to match an example.
2. Keep WoW windowed/borderless and the strip unobscured. Start capture in the
   companion once the crop is correct. The normal loop captures only that strip
   and does not save screenshots.
3. When safe, have the user enable the addon and load the game. For changed Lua
   or newly installed resources, ask for one manual `/reload`; ask for a full
   client restart only if new resources remain undiscovered. No per-message
   reload is part of normal operation. Read the version from the installed TOC
   when telling the user what title to expect; the current title is 0.4.7.
4. Have the user open `/codex` and send a short prompt, then a second prompt after
   the first reply. Verify that each reaches the companion, the complete reply
   appears in the native frame, and the strip becomes steady after completion.
   A desktop notification alone does not verify the inbound game channel.
5. Report the actual install path, launcher/runtime location, work folder, backend,
   saved calibration and checks completed. Distinguish “installed on disk,”
   “companion running” and “round trip verified.” If user input is pending, say
   exactly what remains; do not claim the game has loaded an unverified update.

## Troubleshooting

| Symptom | Check or next step |
| --- | --- |
| Addon absent in game | Correct client/AddOns directory, TOC compatibility, addon enabled, user load/reload |
| Companion asks for an executable again | Verify the remembered native Codex path; rerun `find_codex` if an app update moved it |
| Prompts arrive but replies do not | Correct `--addon`/saved addon path, all font slots present, native publisher enabled, capture still visible |
| Works with the command but not the shortcut | Same Python, launcher location and state directory; persist the `addon` setting |
| Strip is unreadable | Crop, scaling, window mode or another window covering the strip |
| Strip changes after Codex finishes | Reply fragments may still be transferring; inspect receiver state instead of resubmitting |
| Blank slots or write retries | Keep capture visible; inspect bounded `state/transport.jsonl` metadata and receiver status; preserve partial replies |
| Old cached replies after reload | Allow the existing stale-packet recovery; do not reset counters or overwrite cached fonts |
| Channel exhausted | Finite bank reached; full replies remain in the companion. Automatic recycling is not implemented |

Normal source archives omit generated resources and local evidence. Do not
interpret their absence as missing source files. Opt-in probes need their own
explicit preparation and manual activation; do not arm them during ordinary
installation or claim they prove unsupported runtime cache recycling.

## Development and verification

For implementation changes, use the existing tests appropriate to the change:

```powershell
& $bridgePython -m pip install -r requirements-dev.txt
& $bridgePython -m unittest discover -s tests -v
```

The suite covers Python, production Lua 5.1, real font measurements and companion
UI behavior. Windows/tkinter GUI checks require a usable desktop session. Tests
need neither a live agent login nor a running game. Documentation-only changes
need link/command/example checks, not a live reinstall. Preserve the split between
local tests and live-client evidence; full-bank startup scaling remains unverified.

Further reading: [setup and channel walkthrough](README.md),
[architecture](docs/architecture.md), [font bank](docs/font-bank.md),
[test coverage](docs/testing.md), [development](docs/development.md).
