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
