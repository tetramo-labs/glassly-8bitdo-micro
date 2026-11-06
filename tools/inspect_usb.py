"""Save macOS USB descriptors. No device opens or commands."""
from datetime import datetime, timezone
import hashlib
import json
import plistlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def walk(node):
    if isinstance(node, dict):
        yield node
        for child in node.get('IORegistryEntryChildren', []):
            yield from walk(child)


def main():
    raw = subprocess.check_output(['/usr/sbin/ioreg', '-r', '-c', 'IOUSBHostDevice', '-l', '-w', '0', '-a'], timeout=20)
    selected = [n for root in plistlib.loads(raw) for n in walk(root)
                if n.get('IOObjectClass') == 'IOUSBHostDevice' and
                (n.get('idVendor') == 0x2dc8 or (n.get('idVendor'), n.get('idProduct')) == (0x057e, 0x2009))]
    path = ROOT / 'build/hardware' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    path.mkdir(parents=True)
    (path / 'target-registry.plist').write_bytes(plistlib.dumps(selected))
    summary = dict(device_commands_sent=False, devices=[])
    for node in selected:
        reports = {c['ReportDescriptor'] for c in walk(node) if isinstance(c.get('ReportDescriptor'), bytes)}
        summary['devices'].append(dict(name=node.get('USB Product Name'), vid=hex(node['idVendor']),
            pid=hex(node['idProduct']), bcdDevice=node.get('bcdDevice'),
            location=hex(node['locationID']),
            hid_reports=[dict(size=len(d), sha256=hashlib.sha256(d).hexdigest()) for d in sorted(reports)]))
    (path / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    print('Local capture:', path)


if __name__ == '__main__':
    main()
