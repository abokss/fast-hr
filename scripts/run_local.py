"""Start database, migrate, then run both local app processes."""
from pathlib import Path
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request

root = Path(__file__).resolve().parents[1]
children = []


def cleanup(*_):
    for child in children:
        if child.poll() is None:
            child.terminate()
    for child in children:
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()


def main():
    if not (root / '.env').exists():
        shutil.copyfile(root / '.env.example', root / '.env')
        (root / '.env').chmod(0o600)
    for port in (8000, 8501):
        with socket.socket() as check:
            if check.connect_ex(('127.0.0.1', port)) == 0:
                raise RuntimeError(f'Port {port} is already occupied. Close the earlier FastHR process first.')
    subprocess.run(['docker', 'compose', 'up', '-d', '--wait', 'db'], cwd=root, check=True)
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=root / 'backend', check=True)
    children.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'], cwd=root / 'backend'))
    for _ in range(40):
        if children[0].poll() is not None:
            raise RuntimeError('Backend failed to start; see the message above.')
        try:
            with urllib.request.urlopen('http://127.0.0.1:8000/', timeout=1):
                break
        except OSError:
            time.sleep(0.25)
    else:
        raise RuntimeError('Backend did not become ready.')
    children.append(subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', 'frontend/streamlit_app.py',
        '--server.address', '127.0.0.1', '--server.port', '8501', '--server.headless', 'false',
        '--browser.gatherUsageStats', 'false'], cwd=root))
    print('\nFastHR: http://127.0.0.1:8501\nKeep this window open. Ctrl+C stops FastHR.\n', flush=True)
    while all(child.poll() is None for child in children):
        time.sleep(0.5)
    raise RuntimeError('One FastHR process stopped; see the message above.')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f'FastHR: {exc}', file=sys.stderr)
        sys.exit(1)
    finally:
        cleanup()
