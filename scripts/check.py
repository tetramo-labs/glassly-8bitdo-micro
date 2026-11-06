"""Run Micro-specific offline checks. No hardware access or flashing."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests'], cwd=ROOT, check=True)
subprocess.run([sys.executable, 'tools/inspect_stock.py'], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
print('Micro source pins, container and static inspection passed; no hardware accessed.')
