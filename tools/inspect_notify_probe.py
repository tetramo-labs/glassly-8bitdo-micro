"""Exercise actual Micro patched startup/dispatch/IPC in synthetic memory only."""
import json
import struct
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PRIMASK, UC_ARM_REG_R0, UC_ARM_REG_R1
from firmware_image import ROOT, load_stock, sha256
from startup import reconstruct
from inspect_startup import machine, STOP
from build_notify_probe import build, HOOK, TAIL


def verify():
    _, data, manifest = build()
    stock = load_stock()[2][0]
    uc = machine(data)
    regions = reconstruct(data)[1]
    # Independently verify the stock sender prefixes the registered handle and uses command 09.
    sender = machine(stock)
    for address, content in reconstruct(stock)[1].items(): sender.mem_write(address, content)
    sender.mem_map(0xe000e000, 0x1000)
    for handle in (0x0123, 0x2345, 0xfffe):
        sender.mem_write(0x20648, struct.pack('<H',handle))
        sender.mem_write(0x25000, b'\x31')
        sender.reg_write(UC_ARM_REG_R0,0x25000); sender.reg_write(UC_ARM_REG_R1,1)
        sender.reg_write(UC_ARM_REG_SP,0x2ff00); sender.reg_write(UC_ARM_REG_LR,STOP|1)
        sender.emu_start(0x0101a6cd,0x01020a14,count=10000)
        assert sender.reg_read(UC_ARM_REG_PC)==0x01020a14
        descriptor=bytes(sender.mem_read(sender.reg_read(UC_ARM_REG_R0),8))
        length,pointer=struct.unpack_from('<HI',descriptor,2)
        assert descriptor[1]==9 and length==3
        assert bytes(sender.mem_read(pointer,length))==struct.pack('<HB',handle,0x31)
    reads = []
    def read(emu, access, address, size, value, context):
        if address < 0x0102b000 and address+size > 0x01018000+TAIL: reads.append(address)
    rh = uc.hook_add(UC_HOOK_MEM_READ, read)
    uc.emu_start(0x01018201, 0x010261b0, count=500000)
    assert uc.reg_read(UC_ARM_REG_PC) == 0x010261b0
    assert not reads, 'Startup reads injected tail as data'
    for address, content in regions.items(): assert bytes(uc.mem_read(address,len(content))) == content
    uc.hook_del(rh)
    uc.mem_map(0xe000e000, 0x1000)
    uc.mem_map(0xf8000, 0x1000)
    uc.mem_map(0xc0000, 0x10000)
    low_sp = [0x2ff00]
    def observe(emu, address, size, context): low_sp[0] = min(low_sp[0], emu.reg_read(UC_ARM_REG_SP))
    uc.hook_add(UC_HOOK_CODE, observe)
    count = 0
    def event(payload, expected_echo, read_cursor=0, write_cursor=0, irq=0, sleep=0, handle=0x2345):
        nonlocal count
        packet = bytes((2,8,len(payload))) + payload
        uc.mem_write(0x25000, packet)
        uc.mem_write(0x20f94, struct.pack('<5I', 0x25000,256,len(packet),0,len(packet)))
        uc.mem_write(0x20020, struct.pack('<I',1))
        uc.mem_write(0x20648,struct.pack('<H',handle))
        uc.mem_write(0x20190,struct.pack('<I',0x12345678))
        uc.mem_write(0x21edc, bytes(24))  # Stock watchdog inactive; timer-list mutation is not modeled here.
        uc.mem_write(0x20034, struct.pack('<I',0x24000))
        uc.mem_write(0x24000, struct.pack('<4H',0x6000,0x601f,0x6000+read_cursor,0x6000+write_cursor))
        uc.mem_write(0xc6000, b'\xcc'*32)
        uc.mem_write(0x20038,bytes([sleep]))
        uc.reg_write(UC_ARM_REG_PRIMASK,irq)
        uc.reg_write(UC_ARM_REG_SP,0x2ff00)
        uc.reg_write(UC_ARM_REG_LR,STOP|1)
        uc.emu_start(0x0101986d,STOP,count=100000)
        assert uc.reg_read(UC_ARM_REG_PC)==STOP and uc.reg_read(UC_ARM_REG_SP)==0x2ff00
        assert uc.reg_read(UC_ARM_REG_PRIMASK)==irq
        assert bytes(uc.mem_read(0x20f9c,4))==bytes(4), 'Input event not consumed'
        expected = bytearray(b'\xcc'*32)
        if expected_echo:
            for i, value in enumerate(bytes((1,9,3))+payload): expected[(write_cursor+i)%32]=value
        assert bytes(uc.mem_read(0xc6000,32))==bytes(expected)
        cursor=int.from_bytes(uc.mem_read(0x24006,2),'little')
        assert cursor==0x6000+(write_cursor+(6 if expected_echo else 0))%32
        matched = len(payload)>0 and int.from_bytes((payload+bytes(2))[:2],'little')==handle
        assert int.from_bytes(uc.mem_read(0x20190,4),'little')==(0 if matched else 0x12345678)
        count+=1
    for read_cursor in range(32):
        for write_cursor in range(32):
            capacity=(read_cursor-write_cursor)%32 or 32
            for irq in (0,1): event(b'\x45\x23\x31',capacity>6,read_cursor,write_cursor,irq)
    for handle in (0x0123,0x2345,0xfffe):
        for value in (0x31,0xa5,0,0xff): event(struct.pack('<HB',handle,value),True,handle=handle)
    for payload in (b'',b'\x45',b'\x45\x23',b'\x45\x23\x31\x32',b'\x46\x23\x31'):
        event(payload,False)
    for sleep in (1,2,255): event(b'\x45\x23\x31',False,sleep=sleep)
    return dict(hardware_accessed=False, image=manifest, event_cases=count,
                startup_ram_matches=True, startup_reads_tail=False, instruction_stubs=[],
                full_dispatch_and_ipc_executed=True, stock_sender_command09_and_handle_prefix_verified=True, dynamic_handle_cases=3,
                irq_states_checked=[0,1], ring_cursor_pairs=1024,
                lowest_observed_sp=hex(low_sp[0]), isolated_stack_bytes=0x2ff00-low_sp[0],
                gpio_or_button_stream_included=False,
                limits=['Radio and CCC not emulated', 'Watchdog inactive in event cases',
                        'No whole-firmware stack bound', 'No on-air notification result'])

if __name__ == '__main__':
    result=verify()
    (ROOT/'build/notify-probe/emulation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f"Passed {result['event_cases']} Micro notification dispatch cases offline.")
