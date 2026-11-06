"""Execute Micro startup and visibility construction offline, with explicit boundaries."""
import itertools
import json
import struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3
from firmware_image import ROOT, load_stock, sha256
from startup import reconstruct

BASE = 0x01018000
STOP = BASE + 0x100


def machine(data):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    uc.mem_map(BASE, 0x13000)
    uc.mem_write(BASE, data)
    uc.mem_map(0x20000, 0x10000)
    return uc


def verify():
    data = load_stock()[2][0]
    records, regions, consumed = reconstruct(data)
    uc = machine(data)
    uc.mem_write(0x20000, b'\xa5' * 0x10000)
    app = struct.unpack_from('<I', data, 0x20c)[0] & ~1
    assert app == 0x010261b0
    written = set()
    low_sp = [0x30000]
    def writes(_, access, address, size, value, context):
        written.update(range(address, address + size))
    def instructions(emu, address, size, context):
        sp = emu.reg_read(UC_ARM_REG_SP)
        if sp: low_sp[0] = min(low_sp[0], sp)
    wh = uc.hook_add(UC_HOOK_MEM_WRITE, writes)
    ch = uc.hook_add(UC_HOOK_CODE, instructions)
    uc.emu_start(BASE + 0x201, app, count=500000)
    assert uc.reg_read(UC_ARM_REG_PC) == app, 'Startup did not reach application boundary'
    for address, expected in regions.items():
        assert bytes(uc.mem_read(address, len(expected))) == expected
    declared = set(range(0x20000, 0x22be0))
    stack_top = struct.unpack_from('<I', data, 0x210)[0]
    assert stack_top == 0x2ff00
    assert written <= declared | set(range(low_sp[0], stack_top))
    uc.hook_del(wh); uc.hook_del(ch)

    pools = []
    def pool_arguments(emu, address, size, context):
        if address == 0x01024640:
            pools.append(tuple(emu.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)))
    ph = uc.hook_add(UC_HOOK_CODE, pool_arguments)
    uc.reg_write(UC_ARM_REG_SP, 0x2ff00)
    uc.reg_write(UC_ARM_REG_LR, STOP | 1)
    uc.emu_start(0x01024599, STOP, count=10000)
    assert uc.reg_read(UC_ARM_REG_PC) == STOP and uc.reg_read(UC_ARM_REG_SP) == 0x2ff00
    uc.hook_del(ph)
    assert len(pools) == 8
    for head, start, count, stride in pools:
        cursor = int.from_bytes(uc.mem_read(head, 4), 'little')
        for index in reversed(range(count)):
            assert cursor == start + index * stride
            cursor = int.from_bytes(uc.mem_read(cursor, 4), 'little')
        assert cursor == 0

    # Stop at IPC submission, before hardware, waits, or acknowledgement handling.
    visibility = []
    for arguments in itertools.product((0, 1), repeat=3):
        emu = machine(data)
        for address, content in regions.items(): emu.mem_write(address, content)
        emu.mem_map(0xe000e000, 0x1000)  # Synthetic NVIC page.
        emu.reg_write(UC_ARM_REG_SP, 0x2ff00)
        emu.reg_write(UC_ARM_REG_LR, STOP | 1)
        for register, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2), arguments):
            emu.reg_write(register, value)
        emu.emu_start(0x0101a389, 0x01020a14, count=10000)
        assert emu.reg_read(UC_ARM_REG_PC) == 0x01020a14
        descriptor = bytes(emu.mem_read(emu.reg_read(UC_ARM_REG_R0), 8))
        length, pointer = struct.unpack_from('<HI', descriptor, 2)
        assert descriptor[1] == 2 and length == 1
        payload = bytes(emu.mem_read(pointer, length))
        assert payload == bytes([arguments[0] | 6])
        visibility.append(dict(arguments=arguments, opcode=2, payload_hex=payload.hex()))
    return dict(hardware_accessed=False, stock_plaintext_sha256=sha256(data),
                startup=dict(records=records, compressed_bytes_consumed=consumed,
                             ram_sha256=sha256(b''.join(regions.values())), application_boundary=hex(app),
                             stack_top=hex(stack_top), lowest_observed_startup_sp=hex(low_sp[0]),
                             actual_thumb_matches_reconstruction=True, writes_within_regions_and_stack=True),
                pools=[dict(head=hex(h), start=hex(s), count=c, stride=n, end=hex(s+c*n)) for h,s,c,n in pools],
                pool_free_lists_verified=True, visibility_cases=visibility,
                visibility_entry='0x0101a388', ipc_submission_entry='0x01020a14',
                instruction_stubs=[], synthetic_register_pages=['0xe000e000'],
                limits=['No radio execution or on-air result', 'No whole-firmware stack or free-RAM proof',
                        'Visibility wrapper always requests bits 1 and 2; caller coverage is not established'])


if __name__ == '__main__':
    result = verify()
    out = ROOT / 'build/stock/startup-emulation.json'
    out.write_text(json.dumps(result, indent=2)+'\n')
    print('Micro startup, eight pool free lists and eight visibility cases passed offline.')
