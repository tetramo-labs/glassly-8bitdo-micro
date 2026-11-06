"""Build a Micro-specific one-byte FF13 echo experiment; no button stream."""
import json
import subprocess
from firmware_image import ROOT, load_stock, load_crypto, unpack, sha256
from build_name_probe import build as build_name
from startup import reconstruct
from elf_text import text_section

HOOK, TAIL = 0x1930, 0x12e50


def build():
    raw, sections, _ = load_stock()
    _, baseline, _ = build_name()
    if baseline[HOOK:HOOK+4].hex() != '0af0aaf9':
        raise ValueError('Micro clear-idle call differs from audited hook')
    if baseline[TAIL:] != bytes(len(baseline)-TAIL):
        raise ValueError('Expected previously stock-cleared tail')
    out = ROOT/'build/notify-probe'
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(['clang', '--target=arm-none-eabi', '-mcpu=cortex-m0', '-mthumb', '-c',
                    str(ROOT/'firmware/notify_probe.s'), '-o', str(out/'notify_probe.o')], check=True)
    code = text_section((out/'notify_probe.o').read_bytes())
    if not TAIL < len(code) <= len(baseline): raise ValueError('Code exceeds tail')
    patched = bytearray(baseline)
    patched[HOOK:HOOK+4] = code[HOOK:HOOK+4]
    patched[TAIL:len(code)] = code[TAIL:]
    patched = bytes(patched)
    if reconstruct(patched) != reconstruct(baseline): raise ValueError('Startup RAM changed')
    crypto = load_crypto(); section = sections[0]
    package = crypto.build_section(patched, crypto.CIPHERS['yichip'], section['id'], section['addr'], section['payload_len'], section['pid'])
    if unpack(package, ['yichip']) != (sections, [patched]): raise ValueError('Package roundtrip differs')
    report = dict(kind='Experimental one-byte FF13 echo; no button stream or idle-policy change',
                  hardware_accessed=False, package_sha256=sha256(package), plaintext_sha256=sha256(patched),
                  baseline_sha256=sha256(baseline), hook=hex(HOOK), before=baseline[HOOK:HOOK+4].hex(), after=patched[HOOK:HOOK+4].hex(),
                  tail_offset=hex(TAIL), tail_bytes=len(code)-TAIL, persistent_ram_bytes=0, local_stack_bytes=48,
                  startup_ram_unchanged=True, assembly_sha256=sha256((ROOT/'firmware/notify_probe.s').read_bytes()),
                  limits=['Requires live notification verification', 'Stock radio owns registration and CCC handling',
                          'No queue or retry; drops on sleeping radio or insufficient capacity',
                          'Existing vendor write semantics remain; diagnostic writes must avoid configuration command 04',
                          'Whole-firmware stack and computed references to tail are not proven'])
    return package, patched, report

if __name__ == '__main__':
    package, payload, report = build()
    out = ROOT/'build/notify-probe'
    (out/'Micro-v1.05-notify-probe.dat').write_bytes(package)
    (out/'yichip.bin').write_bytes(payload)
    (out/'manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
