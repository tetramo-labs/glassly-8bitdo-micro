"""Extract relocation-free ARM text from a locally assembled ELF object."""
import struct

def text_section(elf):
    if elf[:7] != b'\x7fELF\x01\x01\x01' or struct.unpack_from('<H', elf, 18)[0] != 40:
        raise ValueError('Expected ELF32 little-endian ARM object')
    offset = struct.unpack_from('<I', elf, 32)[0]
    size, count, names = struct.unpack_from('<3H', elf, 46)
    if size != 40:
        raise ValueError('Unexpected ELF section size')
    sections = [struct.unpack_from('<10I', elf, offset+i*size) for i in range(count)]
    ns = sections[names]
    strings = elf[ns[4]:ns[4]+ns[5]]
    found = []
    for section in sections:
        name = strings[section[0]:].split(b'\0', 1)[0]
        if section[1] in (4, 9) and section[5]:
            raise ValueError('Unresolved assembler relocation')
        if name == b'.text':
            found.append(elf[section[4]:section[4]+section[5]])
    if len(found) != 1:
        raise ValueError('Expected one text section')
    return found[0]

