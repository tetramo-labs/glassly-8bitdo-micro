"""Offline execution of the pinned vendor Micro update-mode command builder.

Only property getters and IOHIDDeviceSetReport are stubbed. No device access.
"""
import struct,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def image():
 data=(ROOT/'research/updater/updater-universal').read_bytes()
 assert hashlib.sha256(data).hexdigest()=='966eabd911b6027951a06989d90c34bb38729ca53b22e7bf4db9ac6e935a5d2a'
 assert struct.unpack_from('>I',data)[0]==0xcafebabe
 for i in range(struct.unpack_from('>I',data,4)[0]):
  cpu,_,off,size,_=struct.unpack_from('>5I',data,8+20*i)
  if cpu==0x100000c:return data[off:off+size]
 raise ValueError('No ARM64 slice')
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm64_const import *
data=image();u=Uc(UC_ARCH_ARM64,UC_MODE_ARM);u.mem_map(0x100000000,0x100000);off=32
for _ in range(struct.unpack_from('<I',data,16)[0]):
 cmd,size=struct.unpack_from('<II',data,off)
 if cmd==0x19:
  va,_,fo,fs=struct.unpack_from('<4Q',data,off+24)
  if fs:u.mem_write(va,data[fo:fo+fs])
 off+=size
u.mem_map(0x200000000,0x20000);u.mem_write(0x100038020,struct.pack('<Q',0x200000100))
packets=[]
trace=[]
def hook(u,a,s,d):
 trace.append(hex(a)); del trace[:-20]
 if a in (0x100022ab4,0x100022b68):
  u.reg_write(UC_ARM64_REG_X0,0x2dc8 if a==0x100022ab4 else 0x9020)
 elif a==0x100022ae4:
  key=u.reg_read(UC_ARM64_REG_X1)
  assert key in (0x10003ac98,0x10003acb8),hex(key)
  u.mem_write(u.reg_read(UC_ARM64_REG_X2),struct.pack('<I',0x2dc8 if key==0x10003ac98 else 0x9020))
  u.reg_write(UC_ARM64_REG_X0,1)
 elif a==0x100023bc8:
  ptr=u.reg_read(UC_ARM64_REG_X3);n=u.reg_read(UC_ARM64_REG_X4)
  packets.append(dict(type=u.reg_read(UC_ARM64_REG_X1),report_id=u.reg_read(UC_ARM64_REG_X2),bytes=bytes(u.mem_read(ptr,n)).hex()))
  u.reg_write(UC_ARM64_REG_X0,0)
 else:return
 u.reg_write(UC_ARM64_REG_PC,u.reg_read(UC_ARM64_REG_LR))
u.hook_add(UC_HOOK_CODE,hook)
u.reg_write(UC_ARM64_REG_X2,0x1234);u.reg_write(UC_ARM64_REG_SP,0x200010000);u.reg_write(UC_ARM64_REG_LR,0x100000000)
try: u.emu_start(0x10001be68,0x100000000,count=10000)
except Exception: print(trace); raise
assert u.reg_read(UC_ARM64_REG_PC)==0x100000000
expected=['060050010000'+'00'*58,'810500510000'+'00'*58]
assert [p['bytes'] for p in packets]==expected
assert all(p['type']==1 and p['report_id']==0 for p in packets)
report=dict(updater_sha256='966eabd911b6027951a06989d90c34bb38729ca53b22e7bf4db9ac6e935a5d2a',
 entry='0x10001be68',device_vid='0x2dc8',device_pid='0x9020',packets=packets,
 hardware_accessed=False,stubs=['USB identity property getters','IOHIDDeviceSetReport capture'],
 limitations=['Stack/globals initially zero; vendor legacy packet has trailing uninitialized stack bytes',
 'Host routine execution only; device command handling not emulated'])
(ROOT/'build/update-mode-emulation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
