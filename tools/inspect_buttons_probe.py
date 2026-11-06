"""Execute button probe plus stock GPIO, event dequeue, startup, pools and IPC.

Offline synthetic MMIO. Only OEM report generation and connect power/indicator
side effects are stubbed; the probe, GPIO reader, FIFO, timers and IPC are real.
ACK bitmap changes model radio completion; no radio or interrupts are emulated.
"""
import itertools
import json
import random
import struct
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_HOOK_MEM_READ
from unicorn.arm_const import *
from build_buttons_probe import build, STATE, STATE_BYTES, HOOKS
from build_buttons_probe import TAIL
from inspect_startup import machine as base_machine, BASE, STOP
from inspect_input import INPUTS
from firmware_image import ROOT, load_stock, sha256


from startup import reconstruct


POOLS = ((0x206e8,0x2212c,3,600),(0x206ec,0x22834,4,20),(0x206f0,0x22884,4,64),
         (0x206f4,0x22984,3,60),(0x206f8,0x22a38,1,16),(0x206fc,0x22a48,3,40),
         (0x20700,0x22ac0,5,28),(0x20704,0x22b4c,3,12))

def call(uc,address,arg=0):
    uc.reg_write(UC_ARM_REG_SP,0x2ff00);uc.reg_write(UC_ARM_REG_LR,STOP|1);uc.reg_write(UC_ARM_REG_R0,arg)
    uc.emu_start(address|1,STOP,count=100000)
    assert uc.reg_read(UC_ARM_REG_PC)==STOP and uc.reg_read(UC_ARM_REG_SP)==0x2ff00, hex(uc.reg_read(UC_ARM_REG_PC))
    return uc.reg_read(UC_ARM_REG_R0)

def gpio(uc,bits):
    levels,expected=[0xffff]*3,0
    for index,(bank,pin,mask_bit) in enumerate(INPUTS):
        if bits & (1<<index): levels[bank]&=~(1<<pin);expected|=1<<mask_bit
    uc.mem_write(0xf873c,struct.pack('<3H',*levels))
    return expected

def machine(payload):
    uc=base_machine(payload)
    uc.mem_map(0xc0000,0x10000);uc.mem_map(0xe000e000,0x1000)
    for address,data in reconstruct(payload)[1].items():uc.mem_write(address,data)
    call(uc,0x1024a28,0x102a3b8)
    call(uc,0x1024908)
    scale=struct.unpack_from('<I',payload,0xddd0)[0]
    uc.mem_write(scale,b'\x0a')
    uc.mem_write(0x20034,struct.pack('<I',0x24000));uc.mem_write(0x20648,struct.pack('<H',0x2345))
    return uc


def verify():
    package, payload, report = build()
    stock = load_stock()[2][0]
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    def target(offset):
        ins = next(md.disasm(payload[offset:offset+4], BASE+offset))
        assert ins.mnemonic == 'bl'
        return int(ins.op_str[1:], 16)
    poll = target(0x42a4)
    # All raw word windows, including unaligned ones, not only literal alignment.
    owners = [i for i in range(len(stock)-3) if 0x225dc <= struct.unpack_from('<I',stock,i)[0] < 0x22834]
    assert owners == [0x105d5], owners  # Cross-field GATT bytes decode as 0x22800; not a pointer literal.
    bases = [i for i in range(len(stock)-3) if stock[i:i+4] == struct.pack('<I',0x2212c)]
    assert bases == [0xc600]
    for offset in range(0,0xed2a,2):
        ins = next(md.disasm(stock[offset:offset+4],BASE+offset),None)
        if ins and ins.mnemonic.startswith('b') and ins.op_str.startswith('#0x'):
            assert not BASE+TAIL <= int(ins.op_str[1:],16) < BASE+len(stock)
    uc = machine(payload)
    reads = []
    hook = uc.hook_add(UC_HOOK_MEM_READ, lambda u,a,p,s,v,d: reads.append(p),
                       begin=BASE+TAIL, end=BASE+len(payload)-1)
    uc.mem_write(STATE, b'\xa5'*600)
    uc.emu_start(BASE+0x201,BASE+0xe1b0,count=500000)
    assert uc.reg_read(UC_ARM_REG_PC) == BASE+0xe1b0
    assert not reads
    for address,data in reconstruct(stock)[1].items():
        assert bytes(uc.mem_read(address,len(data))) == data
    uc.hook_del(hook)
    # Actual initializer must leave the entire reserved block untouched.
    uc.mem_write(STATE,b'\xa5'*600)
    call(uc,0x1024598)
    assert bytes(uc.mem_read(STATE,600)) == b'\xa5'*600
    for head,start,count,stride in POOLS:
        if head == 0x206e8: count = 2
        cursor = int.from_bytes(uc.mem_read(head,4),'little')
        for expected in reversed([start+i*stride for i in range(count)]):
            assert cursor == expected
            cursor = int.from_bytes(uc.mem_read(cursor,4),'little')
        assert cursor == 0
    # Zero startup state, then initialize normal synthetic test environment.
    uc = machine(payload)
    uc.mem_map(0xf8000,0x10000)
    input_calls, min_sp = [], [0x2ff00]
    radio_writes, state_writes = [], set()
    def code(emu,address,size,_):
        min_sp[0] = min(min_sp[0],emu.reg_read(UC_ARM_REG_SP))
        if address == 0x101ce94:
            input_calls.append(emu.reg_read(UC_ARM_REG_R0))
            emu.reg_write(UC_ARM_REG_R0,0x55)
            emu.reg_write(UC_ARM_REG_PC,emu.reg_read(UC_ARM_REG_LR))
        elif address == 0x101cca4:
            emu.reg_write(UC_ARM_REG_PC,emu.reg_read(UC_ARM_REG_LR))
    def write(emu,access,address,size,value,_):
        if 0xc0000 <= address < 0xd0000:
            assert 0xc6000 <= address < 0xc6020
            assert emu.reg_read(UC_ARM_REG_PRIMASK) == 1
            radio_writes.append(address)
        if STATE <= address < STATE+600:
            assert address+size <= STATE+STATE_BYTES
            state_writes.update(range(address,address+size))
    uc.hook_add(UC_HOOK_CODE,code)
    uc.hook_add(UC_HOOK_MEM_WRITE,write)
    def event(opcode,value=b''):
        packet = bytes([2,opcode,len(value)])+value
        uc.mem_write(0x25000,packet)
        uc.mem_write(0x20f94,struct.pack('<5I',0x25000,512,len(packet),0,len(packet)))
        uc.mem_write(0x20020,struct.pack('<I',1))
        call(uc,0x101986c)
        assert int.from_bytes(uc.mem_read(0x20f9c,4),'little') == 0
    def start():
        uc.mem_write(0x20682,b'\x02')
        event(8,b'\x45\x23\xa1')
        assert uc.mem_read(STATE+12,1) == b'\x01'
    def sample(bits,read=0,cursor=0,sleep=0,mask=0,ack=False):
        expected = gpio(uc,bits)
        uc.mem_write(0x24000,struct.pack('<4H',0x6000,0x601f,0x6000+read,0x6000+cursor))
        uc.mem_write(0xc6000,b'\xa5'*32)
        uc.mem_write(0x20038,bytes([sleep]))
        uc.mem_write(0x20010,struct.pack('<I',0x80000001|(64 if ack else 0)))
        uc.reg_write(UC_ARM_REG_PRIMASK,mask)
        saved = (UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7)
        for i,r in enumerate(saved): uc.reg_write(r,0x554400+i)
        radio_writes.clear()
        assert call(uc,poll,0x12345678) == 0x55
        assert input_calls[-1] == 0x12345678
        assert uc.reg_read(UC_ARM_REG_PRIMASK) == mask
        for i,r in enumerate(saved): assert uc.reg_read(r) == 0x554400+i
        end = int.from_bytes(uc.mem_read(0x24006,2),'little')-0x6000
        sent = (end-cursor)%32
        assert sent in (0,13)
        data = bytes(uc.mem_read(0xc6000,32))
        assert bool(radio_writes) == bool(sent)
        packet = bytes(data[(cursor+i)%32] for i in range(sent))
        unchanged = set(range(32))-{(cursor+i)%32 for i in range(sent)}
        assert all(data[i] == 0xa5 for i in unchanged)
        assert int.from_bytes(uc.mem_read(0x20010,4),'little') & ~64 == 0x80000001
        return expected,packet
    # Real full dispatcher validates handle + exact control lengths.
    start()
    for value in (b'',b'\x45',b'\x45\x23',b'\x46\x23\xa0',b'\x45\x23\x31',b'\x45\x23\xa0\x00'):
        event(8,value)
        assert uc.mem_read(STATE+12,1) == b'\x01'
    event(8,b'\x45\x23\xa0')
    assert sample(131071)[1] == b''
    for bits in range(131072):
        start()
        expected,packet = sample(bits)
        if bits: assert not packet
        expected,packet2 = sample(bits)
        actual = packet or packet2
        assert actual == b'\x01\x09\x0a\x45\x23\x47\x05\x00\x02'+struct.pack('<I',expected)
    cases = 0
    for read,cursor,mask in itertools.product(range(32),range(32),(0,1)):
        start()
        _,packet = sample(0,read,cursor,mask=mask,ack=True)
        assert bool(packet) == (((read-cursor)%32 or 32)>13)
        cases += 1
    for sleep in (1,2,255):
        start()
        assert not sample(0,sleep=sleep)[1]
        assert uc.mem_read(STATE+9,1) == b'\x01'
        assert sample(0)[1]
    # Independent Python state machine under random bounce, congestion, ACKs,
    # sleeping radio, overflow and both incoming interrupt masks.
    rng = random.Random(0x8b17)
    start()
    candidate=stable=seq=head=flags_pending=0
    initialized=pending=False
    queue=[];flags=2;overflows=sent_total=0
    for i in range(12000):
        bits = rng.randrange(131072) if i%3==0 else bits
        read,cursor = rng.randrange(32),rng.randrange(32)
        sleep = 1 if rng.randrange(10)==0 else 0
        ack = rng.randrange(8)==0
        mask = rng.randrange(2)
        raw,packet = sample(bits,read,cursor,sleep,mask,ack)
        if raw == candidate and (not initialized or raw != stable):
            stable=raw;initialized=True
            if len(queue)==16:
                queue=[];head=0;flags|=1;overflows+=1
            queue.append(raw)
        candidate=raw
        if pending and ack: pending=False;seq=(seq+1)%256
        wanted=b''
        if queue and not pending and not sleep and ((read-cursor)%32 or 32)>13:
            raw_sent=queue.pop(0)
            wanted=b'\x01\x09\x0a\x45\x23\x47\x05'+bytes([seq,flags])+struct.pack('<I',raw_sent)
            head=(head+1)%16;flags=0;pending=True;sent_total+=1
        assert packet == wanted,(i,packet.hex(),wanted.hex())
        state=bytes(uc.mem_read(STATE,STATE_BYTES))
        assert struct.unpack_from('<II',state) == (candidate,stable)
        assert list(state[8:15]) == [head,len(queue),seq,flags,1,int(pending),int(initialized)]
        stored=[struct.unpack_from('<I',state,16+4*((head+j)%16))[0] for j in range(len(queue))]
        assert stored == queue
        if wanted: assert state[80:88] == wanted[7:13]+bytes(2)
    assert overflows>0 and sent_total>256
    # Reconnect resets even without an intervening poll in disconnected state.
    event(2)
    assert bytes(uc.mem_read(STATE,16)) == bytes(16)
    assert not sample(1)[1]
    start();sample(0)
    uc.mem_write(0x20682,b'\x03')
    assert not sample(131071)[1]
    assert bytes(uc.mem_read(STATE,16)) == bytes(16)
    idle_cases=[]
    for connected,enabled in itertools.product((False,True),(False,True)):
        start()
        if not enabled: event(8,b'\x45\x23\xa0')
        call(uc,0x102443c)
        uc.mem_write(0x20682,bytes([2 if connected else 3]))
        uc.mem_write(0x20190,struct.pack('<I',123))
        sample(0)
        count=int.from_bytes(uc.mem_read(0x20190,4),'little')
        assert count==(0 if connected and enabled else 123)
        assert bool(uc.mem_read(0x21ef0,1)[0]) != (connected and enabled)
        idle_cases.append(dict(connected=connected,enabled=enabled))
    return dict(kind='Offline button streaming execution and independent queue model',hardware_accessed=False,
                package_sha256=sha256(package),plaintext_sha256=sha256(payload),
                source_sha256=sha256((ROOT/'firmware/buttons_probe.s').read_bytes()),
                gpio_combinations=131072,ipc_capacity_irq_cases=cases,random_model_polls=12000,
                model_overflows=overflows,model_packets=sent_total,
                startup_matches_stock=True,startup_reads_tail=False,pool_block_reserved=True,
                oem_pool_counts=[2,4,4,3,1,3,5,3],reserved_block_pointer_candidates=owners,
                sole_pool_base_pointer_offset=hex(bases[0]),state_written_extent=[hex(min(state_writes)),hex(max(state_writes)+1)],
                poll_entry=hex(poll),idle_cases=idle_cases,
                maximum_observed_stack_bytes=0x2ff00-min_sp[0],
                stubs={'0x0101ce94':'OEM report task returns 0x55; argument and saved registers checked',
                       '0x0101cca4':'OEM connection power/indicator helper only'},
                limits=['No radio, interrupt execution, actual sampling cadence or physical button labels',
                        'ACK bits are synthetic; no new proof of radio FIFO errors or CCC ordering',
                        'No complete stack/ROM/DMA ownership claim; static word scan cannot exclude computed accesses',
                        'Reduced OEM allocation capacity needs live coexistence testing'])


if __name__=='__main__':
    result=verify()
    (ROOT/'build/buttons-probe/emulation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
