"""Micro v1.05 startup reconstruction; shared decoder, Micro-specific records.

Decoder follows the same byte-identical Thumb helper as the Zero 2 port.
Memory ownership and execution placement are not implied by these records.
"""
import struct

BASE = 0x01018000


def unpack_data(source, output_size):
    """Decode literal/zero/backreference runs; return bytes and input consumed."""
    if output_size < 0 or output_size > 0x10000:
        raise ValueError('Invalid initialized-data size')
    pos, out = 0, bytearray()

    def take():
        nonlocal pos
        if pos >= len(source):
            raise ValueError('Truncated initialized-data stream')
        value = source[pos]
        pos += 1
        return value

    def emit(value):
        if len(out) >= output_size:
            raise ValueError('Initialized-data run exceeds destination')
        out.append(value)

    while len(out) < output_size:
        code = take()
        literal = (code & 7) or take()
        length = (code >> 4) or take()
        if literal == 0:
            raise ValueError('Zero literal count would underflow stock loop')
        for _ in range(literal - 1):
            emit(take())
        if code & 8:
            distance = take()
            if distance == 0 or distance > len(out):
                raise ValueError('Backreference outside initialized output')
            for _ in range(length + 2):
                emit(out[-distance])
        else:
            for _ in range(length):
                emit(0)
    return bytes(out), pos


def reconstruct(data):
    """Decode only the independently identified Micro v1.05 scatter layout."""
    if len(data) != 0x13000:
        raise ValueError('Unsupported Micro image extent')
    expected = [(0x0102aaac, 0x20000, 0x794, 0x010183ca),
                (0x0102ae50, 0x20794, 0x244c, 0x01023d22)]
    values = [struct.unpack_from('<4I', data, off) for off in (0x12a8c, 0x12a9c)]
    if values != expected or struct.unpack_from('<2I', data, 0x380) != (BASE+0x12a8c, BASE+0x12aac):
        raise ValueError('Unsupported Micro scatter records')
    if data[0xbd22:0xbd30].hex() != '002001e001c1121f002afbd17047':
        raise ValueError('Unsupported Micro zero initializer')
    initialized, consumed = unpack_data(data[0x12aac:0x12e50], 0x794)
    if any(data[0x12aac+consumed:0x12e50]):
        raise ValueError('Unexpected compressed-stream trailing bytes')
    records = [dict(zip(('source', 'destination', 'size', 'initializer'), v)) for v in values]
    return records, {0x20000: initialized, 0x20794: bytes(0x244c)}, consumed
