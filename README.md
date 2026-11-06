# Glassly 8BitDo Micro

A separate 8BitDo Micro custom-firmware port for BLE button notifications and
Glassly controller support, following the Zero 2, Ananke and Gamebrick work.

**Status: the notification probe is flashed and all four BLE echoes pass with USB connected. Full readback and normal USB boot are verified. Button streaming is not implemented yet.** The Zero 2 firmware and flasher must not be used on a Micro.

See [findings](docs/findings.md) and the [plan](docs/plan.md). Downloaded firmware,
raw device captures and generated binaries stay local and ignored.

## Offline setup

```sh
python3 scripts/fetch_stock.py
python3 tools/inspect_stock.py
python3 scripts/check.py
```

Micro v1.05 is pinned by SHA256; every section is decrypted and rebuilt exactly.
The catalog MD5 discrepancy is recorded in `sources.lock.json`. On macOS,
`python3 tools/inspect_usb.py` saves descriptors without opening the device or
sending commands. Select **D** mode and reconnect USB to expose `2dc8:9020`.
See the [macOS flashing guide](docs/flashing.md) for the verified stock/name-only path.

See the [flashing guide](docs/flashing.md#notification-experiment) for the verified notification experiment and stock restoration.
