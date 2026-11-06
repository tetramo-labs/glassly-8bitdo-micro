"""Build the Micro's experimental 32-bit queued button stream."""
import json
import subprocess
from firmware_image import ROOT, load_stock, load_crypto, unpack, sha256
from build_name_probe import build as build_name
from startup import reconstruct
from elf_text import text_section

TAIL, STATE, STATE_BYTES = 0x12e50, 0x225dc, 88
HOOKS = {0x1930: bytes.fromhex('0af0aaf9'), 0x1b06: bytes.fromhex('03f0cdf8'),
         0x42a4: bytes.fromhex('00f0f6fd'), 0xc59e: bytes.fromhex('0322')}


def build():
    raw, sections, _ = load_stock()
    _, baseline, _ = build_name()
    if any(baseline[TAIL:]): raise ValueError('Expected stock-cleared tail')
    out = ROOT/'build/buttons-probe'; out.mkdir(parents=True, exist_ok=True)
    subprocess.run(['clang','--target=arm-none-eabi','-mcpu=cortex-m0','-mthumb','-c',str(ROOT/'firmware/buttons_probe.s'),'-o',str(out/'buttons_probe.o')],check=True)
    code = text_section((out/'buttons_probe.o').read_bytes())
    if not TAIL<len(code)<=len(baseline): raise ValueError('Code exceeds audited image extent')
    patched=bytearray(baseline)
    for offset, expected in HOOKS.items():
        if baseline[offset:offset+len(expected)]!=expected: raise ValueError(f'Hook changed: {offset:#x}')
        patched[offset:offset+len(expected)]=code[offset:offset+len(expected)]
    patched[TAIL:len(code)]=code[TAIL:];patched=bytes(patched)
    if reconstruct(patched)!=reconstruct(baseline): raise ValueError('Startup RAM changed')
    crypto=load_crypto();section=sections[0]
    package=crypto.build_section(patched,crypto.CIPHERS['yichip'],section['id'],section['addr'],section['payload_len'],section['pid'])
    if unpack(package,['yichip'])!=(sections,[patched]): raise ValueError('Package roundtrip differs')
    report=dict(kind='Experimental Micro 32-bit queued button stream',hardware_accessed=False,
                package_sha256=sha256(package),plaintext_sha256=sha256(patched),
                hooks={hex(o):dict(before=v.hex(),after=patched[o:o+len(v)].hex()) for o,v in HOOKS.items()},
                tail_offset=hex(TAIL),tail_bytes=len(code)-TAIL,state_address=hex(STATE),state_bytes=STATE_BYTES,
                pool_blocks_before=3,pool_blocks_after=2,reserved_pool_bytes=600,
                protocol_tag='4705',packet_bytes=8,queue_snapshots=16,raw_mask_bits='0x8003fff9',
                startup_ram_unchanged=True,assembly_sha256=sha256((ROOT/'firmware/buttons_probe.s').read_bytes()),
                limits=['Offline build; no hardware button mapping established',
                        'Subscribe then A1; A0 before unsubscribe; connect resets state',
                        'Active sessions clear idle and watchdog; stop/disconnect preserves stock idle policy',
                        'Two consecutive whole-mask samples qualify; no wall-clock debounce claim',
                        'ACK is radio acceptance, not host receipt; missing/nonzero ACK stalls sending',
                        'One OEM pool block removed; no whole-firmware stack or ROM/DMA proof'])
    return package,patched,report

if __name__=='__main__':
    package,payload,report=build();out=ROOT/'build/buttons-probe'
    (out/'Micro-v1.05-buttons-probe.dat').write_bytes(package)
    (out/'yichip.bin').write_bytes(payload)
    (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
