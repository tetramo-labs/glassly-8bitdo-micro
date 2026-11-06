"""Prepare or flash a pinned Micro stock or experimental image on macOS.

Default is offline preparation. --apply explicitly performs device writes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from firmware_image import load_stock, sha256
from build_name_probe import build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', choices=['stock', 'name-probe'])
    parser.add_argument('--location', type=lambda s: int(s, 0), help='Observed macOS USB location ID')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.image == 'stock':
        package, _, payloads = load_stock()
        payload = payloads[0]
    else:
        package, payload, _ = build()
    plan = dict(image=args.image, package_sha256=sha256(package), plaintext_sha256=sha256(payload),
                product='Micro / boot product 0x9020', address='0x01018000',
                length=len(payload), version_record='0x01017040',
                steps=['verify device', 'back up application and metadata', 'erase',
                       'write encrypted section', 'verify full plaintext readback',
                       'commit version 105', 'verify version', 'reset'],
                apply=args.apply, location=args.location)
    print(json.dumps(plan, indent=2), flush=True)
    if not args.apply:
        return
    if sys.platform != 'darwin' or args.location is None or not 0 < args.location <= 0xffffffff:
        parser.error('--apply requires macOS and an explicit valid --location')
    # Refuse competing vendor updater ownership before starting any transaction.
    processes = subprocess.run(['pgrep', '-f', '/Contents/MacOS/8BitDo Firmware Updater'], capture_output=True)
    if processes.returncode != 1:
        raise SystemExit('Close the vendor updater first (or resolve process-list access); no flash started')
    native = ROOT / 'build/flash_micro'
    subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-deprecated-declarations',
                    str(ROOT/'tools/flash_micro.c'), '-framework', 'IOKit', '-framework', 'CoreFoundation',
                    '-o', str(native)], check=True)
    output = ROOT/'build/hardware'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ-script-flash')
    output.mkdir(parents=True)
    (output/'input.dat').write_bytes(package)
    (output/'input-plaintext.bin').write_bytes(payload)
    sources = ['scripts/flash.py', 'tools/flash_micro.c', 'tools/build_name_probe.py',
               'tools/firmware_image.py', 'third_party/8cryptdo/cryptdo8.py', 'sources.lock.json']
    plan['source_sha256'] = {p: sha256((ROOT/p).read_bytes()) for p in sources}
    for source in sources:
        archive = output / 'sources' / source
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes((ROOT/source).read_bytes())
    (output/'plan.json').write_text(json.dumps(plan, indent=2)+'\n')
    print(f'Local backup and transaction log: {output}', flush=True)
    with (output/'transport.log').open('x') as log:
        result = subprocess.run([str(native), '--apply', hex(args.location), str(output/'input.dat'),
                                 str(output/'input-plaintext.bin'), str(output)], stdout=log)
    report = dict(exit_code=result.returncode, files={p.name: dict(size=p.stat().st_size,
                  sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in output.iterdir() if p.is_file()})
    (output/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'Exit code {result.returncode}; evidence: {output}', flush=True)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
