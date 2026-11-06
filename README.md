# Glassly 8BitDo Micro

A separate 8BitDo Micro custom-firmware port for BLE button notifications and
Glassly controller support, following the Zero 2, Ananke and Gamebrick work.

**Status: flashed with full readback. All 16 buttons, A+B, L2+R2 and BLE reconnect
are verified. Battery streaming stayed connected for 314 seconds, including
279 seconds idle without keepalive writes.** Use the Micro firmware and flasher
only on a Micro.

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
See the [macOS flashing guide](docs/flashing.md) for installation and stock restoration.

The [button-stream notes](docs/buttons-probe.md) describe its protocol and limits.
Glassly support is on the app’s `dev` branch; phone background/locked operation
has not yet been tested.
