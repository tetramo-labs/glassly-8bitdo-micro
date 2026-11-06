"""Build a same-length Micro model-name experiment. No code or GATT changes."""
import json
from firmware_image import ROOT, load_crypto, load_stock, sha256, unpack

OFFSET = 0x12a44
BEFORE = b'8BitDo Micro gamepad\0'
AFTER = b'Glassly Micro test01\0'


def build():
    raw, sections, payloads = load_stock()
    assert len(BEFORE) == len(AFTER)
    assert payloads[0][OFFSET:OFFSET + len(BEFORE)] == BEFORE
    assert payloads[0].count(BEFORE) == 1
    patched = payloads[0][:OFFSET] + AFTER + payloads[0][OFFSET + len(BEFORE):]
    c = load_crypto(); s = sections[0]
    package = c.build_section(patched, c.CIPHERS['yichip'], s['id'], s['addr'], s['payload_len'], s['pid'])
    headers, decoded = unpack(package, ['yichip'])
    assert headers == sections and decoded == [patched]
    assert package[:28] == raw[:28]
    report = dict(kind='Experimental name-only package; no custom button stream',
                  package_sha256=sha256(package), plaintext_sha256=sha256(patched),
                  offset=hex(OFFSET), before=BEFORE.decode().rstrip('\0'), after=AFTER.decode().rstrip('\0'),
                  changed_bytes=[i for i, (a, b) in enumerate(zip(payloads[0], patched)) if a != b],
                  firmware_code_unchanged=True, header_unchanged=True, hardware_accessed=False,
                  limits=['Runtime visibility of this model string requires a hardware check',
                          'No custom GATT, new RAM or execution placement'])
    return package, patched, report


if __name__ == '__main__':
    package, payload, report = build()
    out = ROOT / 'build/name-probe'; out.mkdir(parents=True, exist_ok=True)
    (out / 'Micro-v1.05-name-probe.dat').write_bytes(package)
    (out / 'yichip.bin').write_bytes(payload)
    (out / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
