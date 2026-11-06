import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from firmware_image import load_stock, unpack, load_crypto


class StockTests(unittest.TestCase):
    def test_micro_identity_and_extent(self):
        raw, sections, payloads = load_stock()
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]['pid'], 0x9020)
        self.assertEqual(sections[0]['id'], 105)
        self.assertEqual(sections[0]['addr'], 0x01018000)
        self.assertEqual(len(payloads[0]), 77824)
        self.assertIn(b'8BitDo Micro gamepad\0', payloads[0])

    def test_rejects_truncated_and_trailing_bytes(self):
        raw, _, _ = load_stock()
        for value in (raw[:-1], raw + b'\0', b''):
            with self.assertRaises(ValueError):
                unpack(value, ['yichip'])

    def test_rejects_unknown_header_bytes(self):
        raw, _, _ = load_stock()
        value = bytearray(raw)
        value[16] = 1
        with self.assertRaises(ValueError):
            unpack(bytes(value), ['yichip'])

    def test_cipher_detection_agrees_with_pin(self):
        raw, sections, _ = load_stock()
        self.assertEqual(load_crypto().detect_cipher(raw, sections[0]).NAME, 'yichip')


class NameProbeTests(unittest.TestCase):
    def test_only_complete_model_name_changes(self):
        from build_name_probe import build, OFFSET, BEFORE, AFTER
        raw, sections, payloads = load_stock()
        package, payload, report = build()
        self.assertEqual(package[:28], raw[:28])
        self.assertEqual(payload[:OFFSET], payloads[0][:OFFSET])
        self.assertEqual(payload[OFFSET:OFFSET + len(AFTER)], AFTER)
        self.assertEqual(payload[OFFSET + len(BEFORE):], payloads[0][OFFSET + len(BEFORE):])
        self.assertFalse(report['hardware_accessed'])
        self.assertEqual(unpack(package, ['yichip']), (sections, [payload]))


class StartupTests(unittest.TestCase):
    def test_micro_layout_and_name_patch_ram(self):
        from startup import reconstruct
        from build_name_probe import build
        stock = load_stock()[2][0]
        records, regions, consumed = reconstruct(stock)
        self.assertEqual(consumed, 929)
        self.assertEqual([(r['destination'], r['size']) for r in records], [(0x20000, 0x794), (0x20794, 0x244c)])
        self.assertEqual(reconstruct(build()[1]), (records, regions, consumed))

    def test_rejects_other_scatter_layout(self):
        from startup import reconstruct
        stock = load_stock()[2][0]
        for offset in (0x380, 0x12a8c, 0x12a9c, 0xbd22):
            changed = bytearray(stock)
            changed[offset] ^= 1
            with self.assertRaises(ValueError): reconstruct(changed)

    def test_invalid_compressed_stream(self):
        from startup import unpack_data
        for source, count in [(b'', 1), (b'\x10\x00', 1), (b'\x19\x01', 3), (b'\x21', 1)]:
            with self.assertRaises(ValueError): unpack_data(source, count)


class NotifyProbeTests(unittest.TestCase):
    def test_only_audited_hook_tail_and_name_change(self):
        from build_name_probe import build as name
        from build_notify_probe import build, HOOK, TAIL
        from firmware_image import sha256
        _, base, _ = name()
        package, patched, report = build()
        self.assertEqual(patched[:HOOK], base[:HOOK])
        self.assertEqual(patched[HOOK+4:TAIL], base[HOOK+4:TAIL])
        self.assertEqual(patched[TAIL+report['tail_bytes']:], base[TAIL+report['tail_bytes']:])
        native = (Path(__file__).resolve().parents[1]/'tools/flash_micro.c').read_text()
        self.assertIn(sha256(package), native)
        self.assertIn(sha256(patched), native)
        self.assertEqual(report['persistent_ram_bytes'], 0)
        self.assertEqual(report['tail_bytes'], 76)
