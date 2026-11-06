"""Audit pinned macOS updater packets using REA method anchors and Unicorn.

Runs only isolated ARM64 code with Objective-C, file and USB calls stubbed.
Never executes the app or sends device commands. REA metadata is retained locally.
"""
import hashlib
import json
import struct
from firmware_image import ROOT

APP = ROOT / 'research/updater/updater-universal'
PIN = '966eabd911b6027951a06989d90c34bb38729ca53b22e7bf4db9ac6e935a5d2a'


def image():
    data = APP.read_bytes()
    if hashlib.sha256(data).hexdigest() != PIN:
        raise ValueError('Unexpected macOS updater')
    magic, count = struct.unpack_from('>II', data)
    if magic != 0xcafebabe:
        raise ValueError('Expected universal Mach-O')
    for i in range(count):
        cpu, _, off, size, _ = struct.unpack_from('>5I', data, 8+20*i)
        if cpu == 0x100000c:
            return data[off:off+size]
    raise ValueError('Missing ARM64 slice')


def verify():
    from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
    from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X5, UC_ARM64_REG_X6, UC_ARM64_REG_X7, UC_ARM64_REG_LR, UC_ARM64_REG_SP, UC_ARM64_REG_PC
    regs = (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X5, UC_ARM64_REG_X6, UC_ARM64_REG_X7)
    data = image()
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0x100000000, 0x100000)
    off = 32
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        cmd, size = struct.unpack_from('<II', data, off)
        if cmd == 0x19:
            va, _, fileoff, filesize = struct.unpack_from('<4Q', data, off+24)
            if filesize:
                uc.mem_write(va, data[fileoff:fileoff+filesize])
        off += size
    uc.mem_map(0x200000000, 0x20000)
    stop, stack, payload = 0x100000000, 0x200010000, 0x200001000
    uc.mem_write(0x100038020, struct.pack('<Q', 0x200000100))
    captures, packets = [], []
    def hook(emu, addr, size, user):
        args = [emu.reg_read(r) for r in regs]
        value = args[0]
        if addr == 0x100024c00: value = 17  # Micro PID dispatcher at 0x100007cb4
        elif addr == 0x100024c20: value = 0x9020
        elif addr == 0x100025180: value = 0x1234  # device getter
        elif addr == 0x100023ca0:
            emu.mem_write(args[0], bytes(emu.mem_read(args[1], args[2])))
        elif addr == 0x100022c38:
            packets.append(bytes(emu.mem_read(args[1], 64)))
        elif addr == 0x100024360:
            captures.append(args[2:7])
        else: return
        emu.reg_write(regs[0], value)
        emu.reg_write(UC_ARM64_REG_PC, emu.reg_read(UC_ARM64_REG_LR))
    uc.hook_add(UC_HOOK_CODE, hook)
    def call(address, args):
        for reg, value in zip(regs, args): uc.reg_write(reg, value)
        uc.reg_write(UC_ARM64_REG_SP, stack)
        uc.reg_write(UC_ARM64_REG_LR, stop)
        uc.emu_start(address, stop, count=10000)
        if uc.reg_read(UC_ARM64_REG_PC) != stop or uc.reg_read(UC_ARM64_REG_SP) != stack:
            raise AssertionError('Native routine did not return cleanly')
    def crc(data):
        value = 65535
        for byte in data:
            value ^= byte
            for _ in range(8): value = (value >> 1) ^ (0xa001 if value & 1 else 0)
        return value
    cases = []
    for cmd, length, address, total, has_data in (
            (8, 2, 0, 2, False), (5, 32, 0x1018000, 32, False),
            (4, 0, 0x1018000, 0x13000, False), (4, 0, 0x1017040, 32, False),
            (3, 46, 0x1018000, 0x13000, True), (3, 30, 0x102afe2, 0x13000, True),
            (2, 4, 0x1017040, 4, True), (7, 0, 0, 0, False)):
        blob = struct.pack('<I', 105) if cmd == 2 else bytes(range(length))
        uc.mem_write(payload, blob or b'\0')
        call(0x100006d74, (0x1234, 0, payload if has_data else 0, length, address, total, cmd, 0))
        # The native constructor CRC includes zero padding for read requests.
        body = blob if has_data else bytes(length)
        expected = struct.pack('<BHHHHII', 5, cmd, 0, length, crc(body), total, address)
        expected += body + bytes(64-17-length)
        if packets[-1] != expected:
            raise AssertionError(f'Constructor differs for command {cmd}: {packets[-1].hex()} != {expected.hex()}')
        cases.append(dict(command=cmd, length=length, address=address, total=total, packet=packets[-1].hex()))
    uc.mem_write(0x1000442f0, struct.pack('<III', 105, 0x13000, 0x1018000))
    for address in (0x100008224, 0x10000870c, 0x1000093dc, 0x100009688):
        call(address, (0x1234, 0))
    expected_args = [[0,0,0x1018000,0x13000,4], [0,0,0x1017040,32,4],
                     [0x1000442f0,4,0x1017040,4,2], [0,0,0,0,7]]
    if captures != expected_args:
        raise AssertionError(f'Native erase/version/reset arguments differ: {captures}')
    return dict(updater_sha256=PIN, packet_cases=cases, erase_version_reset_arguments=captures,
                rea_evidence='ev_321378fbae9caf40aa718dd27cb1788391f22ca1da7fb93f7014dd92087b93b0',
                stubs=['bootType=17', 'bootType_PID=0x9020', 'device getter', 'memcpy', 'USB packet capture', 'BootReadFlash call capture'],
                hardware_accessed=False,
                limits=['Isolated native routines only; no bootloader execution', 'REA supplied method metadata; assembly and emulation supply protocol evidence'])


if __name__ == '__main__':
    report = verify()
    (ROOT / 'build/macos-updater-protocol.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Verified 8 native packet cases and 4 erase/version/reset argument cases; no hardware access.')
