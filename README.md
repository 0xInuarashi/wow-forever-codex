# Forever Bridge

Version **0.4.7** — a native WoW: Forever chat panel connected to a local Codex process.

Prompts leave the game through an on-screen pixel strip. Replies return as checked bytes encoded in ordinary addon font metrics, then appear as normal scrollable text. Once installed and loaded, ordinary messages need no `/reload`.

This is an experimental, finite transport built around documented addon APIs. It uses no DLL injection, game-process memory access, anti-cheat bypass, generated keyboard/mouse input or executable reply payloads. Using documented APIs does not imply Blizzard endorsement.

## Features

- Native chat/status frame with `/codex`, hide/show, minimap toggle and completion badge.
- Shift-click or drag items into a focused draft. Item references in responses can become native links with tooltips.
- Checked UTF-8 replies, multipart assembly, stale-packet rejection and automatic retry after missed writes.
- A **65,535-slot** font bank with compact shared placeholders and isolated writes.
- A Windows companion with capture controls, persistent inbox, reply notifications and a local Codex adapter. The default agent sandbox is read-only.

## Requirements

- Windows with NTFS for compact font installation.
- WoW: Forever; development and live experiments used **1.60.1.69913 / TOC 16001**. Other builds are unverified.
- Python 3.12+ with tkinter.
- An authenticated native Codex CLI for the real backend. The mock backend needs no agent login.
- Windowed or borderless WoW with the pixel strip visible and unobscured.

## Install

From this repository's folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m tools.install_addon 'C:\path\to\World of Warcraft\_classic_beta_\Interface\AddOns\CodexPixelBridge'
```

Use your actual game path. The installer copies addon code, generates the font/image resources and preserves existing resource files. **Do not just copy the addon source folder:** generated assets are intentionally excluded from Git and source archives. Fonts can contain response data and ordinary copies also lose their compact shared storage.

Enable the addon and load WoW. If updating while playing, manually `/reload` once to load new Lua and asset names. Fully restart WoW if new assets remain undiscovered. The title should say **Codex | Live text 0.4.7**. Never reset or replace a used font bank while the game is running.

## Run the companion

```powershell
.\.venv\Scripts\python.exe -m companion.app --backend codex --project 'C:\path\to\work-project' --codex 'C:\path\to\codex.exe' --addon 'C:\path\to\World of Warcraft\_classic_beta_\Interface\AddOns\CodexPixelBridge'
```

Use an existing work directory, separate from the game installation. In the companion, set the capture crop to the strip's exact desktop coordinates: left, top, width, height. The nominal strip is 512 by 16 at (8, 8), but display scaling changes those values. Start capture, open `/codex` and send a short message. Capture calibration is saved locally.

To test without calling an agent, replace `--backend codex` with `--backend mock` and omit `--codex`. The adapter normally runs `codex exec --json --sandbox read-only`; `--sandbox workspace-write` is an explicit opt-in to project edits. No bypass mode is provided.

`Launch Companion.pyw` is an optional Windows launcher that remembers your work folder and discovers the CLI. For an initial installation, the command above also supplies the addon path explicitly.

## In-game controls

| Action | Control |
| --- | --- |
| Show/hide the panel | `/codex`, `/cpb`, minimap C button, or addon keybinding |
| Explicit visibility | `/codex show`, `/codex hide` |
| Send a prompt | Enter or Send in the message box |
| Link an item | Focus the message box and Shift-click an item, or drag it into the box |
| Pause/resume receiving | `/codex pause`, `/codex resume`, or panel buttons |
| Clear repeating prompts | `/codex clear` (already received agent jobs continue) |
| Read a response item link | Hover/click; Shift-click inserts it into a draft without sending |

The strip changes while transmitting prompts or receive timing. Duplicate prompt packets do not create duplicate jobs. A fully received final response raises the completion badge and leaves the strip steady. A new prompt resumes transfer.

## Limits and verification

The font bank is finite and does not automatically recycle. Each font carries a 512-byte packet with up to 476 response bytes. A fresh slot is requested roughly every five seconds while watching, plus assignment/decoding time. Replies are displayed as complete checked revisions; token-by-token streaming is not guaranteed.

The preview limit is 60,000 UTF-8 bytes. The companion retains the full response. Each receive watch stops after 20 minutes, three consecutive real loading/corruption failures, or a completed response. Lost saved counters can require reading past cached old slots. Keep the strip visible while receiving.

The native channel has delivered real responses and completion notifications in the tested client. Shared placeholders delivered fresh bytes in two live experiments. Full-bank startup performance and live use of slot 65,535 remain unverified. Native item-link mouse behavior and the split-stack fix still need broader live verification.

**86 local tests pass**, including production Lua 5.1, real font measurements, consecutive multipart replies, the last slot and a clean-source installer. CI repeats the suite on Windows; adding its configuration is not a claim that hosted CI has already passed. [Testing](docs/testing.md).

## Local data

`state/` contains the inbox, preferences, capture calibration and bounded transport logs. Normal operation captures only the selected strip and does not save screenshots. Prompt and reply text persists in the local inbox and can also be encoded in installed fonts. Keep the inbox to prevent replay of repeated request IDs. Do not commit runtime data or generated assets.

[Architecture](docs/architecture.md) · [Font bank](docs/font-bank.md) · [Development](docs/development.md) · [Testing](docs/testing.md)
