"""Inspect every pinned Micro package section, preserving local plaintext."""
import json
import re
import struct
from firmware_image import ROOT, load_stock, sha256


def inspect():
    raw, sections, payloads = load_stock()
    output = ROOT / 'build/stock'
    output.mkdir(parents=True, exist_ok=True)
    reports = []
    for i, (section, payload) in enumerate(zip(sections, payloads)):
        (output / f'section{i}.bin').write_bytes(payload)
        strings = [{'offset': hex(m.start()), 'text': m.group().decode('ascii')}
                   for m in re.finditer(rb'[\x20-\x7e]{6,}', payload)
                   if any(s in m.group().lower() for s in (b'8bitdo', b'ble_', b'hci_', b'yc_'))]
        descriptors = []
        for offset in range(len(payload) - 17):
            if payload[offset:offset + 2] == bytes([18, 1]) and payload[offset + 7] in (8, 16, 32, 64):
                usb, vid, pid, revision = (struct.unpack_from('<H', payload, offset + n)[0] for n in (2, 8, 10, 12))
                if usb in (0x110, 0x200, 0x210):
                    descriptors.append(dict(offset=hex(offset), vid=hex(vid), pid=hex(pid), bcdDevice=hex(revision)))
        reports.append(dict(**section, sha256=sha256(payload), strings=strings,
                            candidate_usb_descriptors=descriptors))
    report = dict(package_sha256=sha256(raw), package_roundtrip_exact=True, sections=reports,
                  hardware_accessed=False,
                  limits=['String and descriptor matches are static candidates, not runtime observations',
                          'No Micro GATT lifecycle, physical key map, code placement or flash protocol established'])
    (output / 'inspection.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    print(json.dumps(inspect(), indent=2))
