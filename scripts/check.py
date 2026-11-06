"""Run Micro-specific offline checks. No hardware access or flashing."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests'], cwd=ROOT, check=True)
subprocess.run([sys.executable, 'tools/inspect_stock.py'], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
if sys.platform == 'darwin':
    (ROOT / 'build').mkdir(exist_ok=True)
    for name in ('enter_update', 'read_micro', 'flash_micro'):
        subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-deprecated-declarations',
                        f'tools/{name}.c', '-framework', 'IOKit', '-framework', 'CoreFoundation',
                        '-o', str(ROOT / 'build' / name)], cwd=ROOT, check=True)
    subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-deprecated-declarations',
                    '-fsanitize=address,undefined', 'tests/test_flasher.c', '-framework', 'IOKit',
                    '-framework', 'CoreFoundation', '-o', str(ROOT / 'build/test_flasher')], cwd=ROOT, check=True)
    subprocess.run([str(ROOT / 'build/test_flasher')], cwd=ROOT, check=True)
    subprocess.run(['swiftc', '-warnings-as-errors', 'tools/probe_ble.swift', '-framework', 'CoreBluetooth', '-o', str(ROOT / 'build/probe_ble')], cwd=ROOT, check=True)
print('Micro source pins, container and static inspection passed; no hardware accessed.')
