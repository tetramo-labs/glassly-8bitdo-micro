"""Pinned Micro container handling. No hardware access."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_crypto():
    lock = json.loads((ROOT / 'sources.lock.json').read_text())
    path = ROOT / 'third_party/8cryptdo/cryptdo8.py'
    if sha256(path.read_bytes()) != lock['cryptdo8']['sha256']:
        raise ValueError('8cryptdo source hash mismatch')
    spec = importlib.util.spec_from_file_location('cryptdo8', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unpack(raw, ciphers):
    crypto = load_crypto()
    sections = crypto.parse_sections(raw)
    if not sections or len(sections) != len(ciphers):
        raise ValueError('Unexpected section count')
    if sections[-1]['offset'] + crypto.HEADER_SIZE + sections[-1]['payload_len'] != len(raw):
        raise ValueError('Unparsed or truncated container bytes')
    payloads = []
    for section, name in zip(sections, ciphers):
        payload = crypto.decrypt_section(raw, section, crypto.CIPHERS[name])
        rebuilt = crypto.build_section(payload, crypto.CIPHERS[name], section['id'],
                                       section['addr'], section['payload_len'], section['pid'])
        start = section['offset']
        if rebuilt != raw[start:start + len(rebuilt)]:
            raise ValueError('Container roundtrip mismatch')
        payloads.append(payload)
    return sections, payloads


def load_stock():
    source = json.loads((ROOT / 'sources.lock.json').read_text())['stock']
    raw = (ROOT / source['path']).read_bytes()
    if len(raw) != source['size'] or sha256(raw) != source['sha256']:
        raise ValueError('Stock size/SHA256 mismatch')
    sections, payloads = unpack(raw, [s['cipher'] for s in source['sections']])
    for actual, payload, expected in zip(sections, payloads, source['sections']):
        if any(actual[k] != expected[k] for k in actual) or sha256(payload) != expected['sha256']:
            raise ValueError('Stock section mismatch')
    return raw, sections, payloads
