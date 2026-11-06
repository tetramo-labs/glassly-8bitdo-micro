"""Micro-specific timer registration and command-09 completion checks, offline."""
import json
import struct
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_SP
from firmware_image import ROOT, load_stock, sha256
from inspect_buttons_probe import machine, call


def verify():
    stock=load_stock()[2][0]
    uc=machine(stock)
    # Initialize the actual stock input timer through its own registration routine.
    call(uc,0x10209d0)
    timer=bytes(uc.mem_read(0x219e4,24))
    assert struct.unpack_from('<I',timer,8)[0]==0x101c291
    assert timer[20]==1
    assert int.from_bytes(uc.mem_read(0x2063c,4),'little')==0x219e4
    period=uc.mem_read(0x205f4,1)[0]
    assert period==10
    # Scope starts after the stock ISR has assembled a completion payload.
    # Execute the real opcode jump table and status branch; no instruction stubs.
    cases=[]
    for status in (0,1,2,255):
        uc.mem_write(0x20029,struct.pack('<I',0x25000))
        uc.mem_write(0x25000,bytes([9,status]))
        uc.mem_write(0x20010,struct.pack('<I',0x80000001))
        uc.reg_write(UC_ARM_REG_SP,0x2ff00)
        uc.emu_start(0x10190cb,0x101970a,count=10000)
        assert uc.reg_read(UC_ARM_REG_PC)==0x101970a
        assert uc.reg_read(UC_ARM_REG_SP)==0x2ff00
        bitmap=int.from_bytes(uc.mem_read(0x20010,4),'little')
        assert bitmap==0x80000001|(64 if status==0 else 0)
        cases.append(dict(status=status,ack_bit6=bool(bitmap&64)))
    return dict(hardware_accessed=False,stock_plaintext_sha256=sha256(stock),
                input_timer='0x219e4',callback='0x0101c290',registration='0x010209d0',
                report_task_call='0x0101c2a4',report_task='0x0101ce94',
                nominal_rearm_byte=period,timer_active_and_linked=True,
                completion_entry_boundary='0x010190ca',completion_exit_boundary='0x0101970a',
                command09_status_cases=cases,ack_bitmap='0x20010',instruction_stubs=[],
                limits=['Timer wall-clock cadence not measured','Completion payload is synthetic; ISR/radio not emulated',
                        'ACK means radio acceptance, not host receipt'])

if __name__=='__main__':
    result=verify()
    (ROOT/'build/stock/micro-bindings.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
