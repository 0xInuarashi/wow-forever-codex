"""Resolve the CLI even when Explorer has a different PATH from Codex."""
import os
from pathlib import Path
import shutil


def find_codex(remembered=''):
    if remembered and Path(remembered).is_file():
        return str(Path(remembered).resolve())
    on_path = shutil.which('codex.exe') or shutil.which('codex')
    if on_path and Path(on_path).suffix.lower() == '.exe':
        return str(Path(on_path).resolve())
    local_data = os.environ.get('LOCALAPPDATA')
    if local_data:
        root = Path(local_data) / 'OpenAI' / 'Codex' / 'bin'
        candidates = [p for p in root.glob('*/codex.exe') if p.is_file()]
        if candidates:
            return str(max(candidates, key=lambda p: p.stat().st_mtime).resolve())
    return ''
