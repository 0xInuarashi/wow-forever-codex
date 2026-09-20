"""Desktop shortcut entry point; choose the work folder on first launch."""
import json
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
from companion.launching import find_codex

BASE = Path(__file__).resolve().parent
STATE = BASE / 'state'

def launch():
    root = tk.Tk()
    root.withdraw()
    settings = STATE / 'launcher.json'
    try:
        config = json.loads(settings.read_text(encoding='utf-8')) if settings.exists() else {}
        codex = find_codex(config.get('codex', ''))
        if not codex:
            raise RuntimeError('Codex could not be found in this computer\'s Codex installation.')
        project = config.get('project', '')
        if not project or not Path(project).is_dir():
            project = filedialog.askdirectory(parent=root, title='Choose your work project for Codex')
            if not project:
                return
        STATE.mkdir(parents=True, exist_ok=True)
        config.update(project=project, codex=codex)
        settings.write_text(json.dumps(config, indent=2), encoding='utf-8')
    finally:
        root.destroy()
    from companion.app import main
    launch_options = [arg for arg in sys.argv[1:] if arg in ('--start-capture', '--minimized')]
    if config.get('start_capture') and '--start-capture' not in launch_options:
        launch_options.append('--start-capture')
    sys.argv = [__file__, '--backend', 'codex', '--project', project, '--codex', codex, '--state', str(STATE)] + launch_options
    main()

if __name__ == '__main__':
    try:
        launch()
    except Exception as exc:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror('Forever Bridge could not start', str(exc), parent=root)
        root.destroy()
