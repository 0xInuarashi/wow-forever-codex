"""Read actual Codex JSON events as they arrive; never synthesize response text."""
import json
import queue
import subprocess
import threading
import time


def run_stream(args, prompt, on_update):
    command = [args.codex, 'exec', '--json', '--sandbox', args.sandbox,
               '--skip-git-repo-check', '--color', 'never', '-C', str(args.project), '-']
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                                   errors='replace', bufsize=1, shell=False,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except OSError as error:
        return 'failed', str(error)
    lines = queue.Queue(maxsize=64)
    stop = threading.Event()

    def offer(value):
        while not stop.is_set():
            try:
                lines.put(value, timeout=0.2)
                return
            except queue.Full:
                pass

    def read():
        try:
            while not stop.is_set():
                line = process.stdout.readline(262144)
                if not line:
                    break
                offer(line)
        finally:
            offer(None)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    started = time.monotonic()
    messages, failures, diagnostics = {}, [], ''
    completed, eof = False, False
    latest, last_emitted, last_emit_time = '', '', 0.0
    anonymous = 0
    try:
        try:
            process.stdin.write(prompt)
            process.stdin.close()
        except (OSError, BrokenPipeError):
            pass
        while True:
            if time.monotonic() - started >= args.timeout:
                process.kill()
                return 'failed', 'Agent timed out. Check its workspace before submitting again.'
            if eof and process.poll() is not None:
                break
            try:
                line = lines.get(timeout=0.1)
            except queue.Empty:
                continue
            if line is None:
                eof = True
                continue
            diagnostics = (diagnostics + line)[-4000:]
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            kind = event.get('type')
            if kind == 'turn.completed':
                completed = True
            elif kind in ('error', 'turn.failed'):
                failures.append(str(event.get('message') or event.get('error') or event))
            item = event.get('item')
            if kind in ('item.started', 'item.updated', 'item.completed') and isinstance(item, dict) and item.get('type') == 'agent_message':
                # CLI versions may publish only complete messages, or also updates.
                # Tool output/reasoning events are never presented as assistant replies.
                text = item.get('text')
                if isinstance(text, str) and text:
                    identity = item.get('id') or f'anonymous-{anonymous}'
                    messages[str(identity)] = text
                    if not item.get('id') and kind == 'item.completed':
                        anonymous += 1
                    latest = '\n'.join(messages.values())
                    now = time.monotonic()
                    if latest != last_emitted and (kind == 'item.completed' or now - last_emit_time >= 0.5):
                        on_update(latest)
                        last_emitted, last_emit_time = latest, now
        if process.returncode or failures or not completed:
            return 'failed', '\n'.join(failures + ([latest] if latest else [])) or diagnostics or 'No completion event'
        return 'done', latest or '(Agent completed without a text response)'
    finally:
        stop.set()
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        reader.join(timeout=0.3)
        if not reader.is_alive():
            process.stdout.close()
        if process.stdin and not process.stdin.closed:
            process.stdin.close()
