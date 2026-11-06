"""Execute the Micro raw GPIO reader against synthetic register levels only."""
import json
import struct
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_LR, UC_ARM_REG_SP, UC_ARM_REG_PC
from firmware_image import ROOT, load_stock, sha256
from inspect_startup import machine, STOP

# Independently read from Micro 0x010200c4..0x010201d4, not physical labels.
INPUTS = ((0,0,5), (0,1,4), (0,6,16), (0,9,11), (0,10,15), (0,14,12),
          (1,0,13), (1,5,0), (1,10,8), (1,11,17), (1,12,6), (1,13,7), (1,2,31),
          (2,1,10), (2,4,14), (2,10,3), (2,0,9))


def verify():
    data = load_stock()[2][0]
    uc = machine(data)
    uc.mem_map(0xf8000, 0x1000)
    def check(levels, expected):
        uc.mem_write(0xf873c, struct.pack('<3H', *levels))
        uc.reg_write(UC_ARM_REG_SP, 0x2ff00)
        uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        uc.emu_start(0x010200c5, STOP, count=1000)
        assert uc.reg_read(UC_ARM_REG_PC) == STOP and uc.reg_read(UC_ARM_REG_SP) == 0x2ff00
        assert uc.reg_read(UC_ARM_REG_R0) == expected, (levels, expected, uc.reg_read(UC_ARM_REG_R0))
    for bits in range(1 << len(INPUTS)):
        levels, expected = [0xffff]*3, 0
        for index, (bank, pin, output) in enumerate(INPUTS):
            if bits & (1 << index):
                levels[bank] &= ~(1 << pin)
                expected |= 1 << output
        check(levels, expected)
    used = [0,0,0]
    for bank, pin, _ in INPUTS: used[bank] |= 1 << pin
    check(used, 0)  # Every unused input low must leave the returned mask zero.
    return dict(hardware_accessed=False, stock_plaintext_sha256=sha256(data),
                reader='0x010200c4', bank_reader='0x0101bff4', register_base='0x000f873c',
                active_low=True, combinations_checked=1 << len(INPUTS),
                unused_gpio_bits_ignored=True, instruction_stubs=[],
                mappings=[dict(bank=b, pin=p, mask_bit=m) for b,p,m in INPUTS],
                physical_button_labels_verified=False,
                limits=['Synthetic GPIO RAM only; no electrical or physical mapping proof',
                        'Raw sampling only; no debounce, input task or polling ownership established'])

if __name__ == '__main__':
    result = verify()
    (ROOT/'build/stock/input-emulation.json').write_text(json.dumps(result, indent=2)+'\n')
    print('Passed all 131072 Micro raw GPIO combinations and unused-bit check offline.')
