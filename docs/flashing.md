# Micro flashing on macOS

The current custom image is a **name-only experiment**, not a Glassly button
stream. It was flashed on one Micro with full readback and normal USB boot.
Experimental firmware can brick the device. Keep all local backups.

## Prepare

Install Python 3 and Xcode Command Line Tools. In this repository:

```sh
python3 scripts/fetch_stock.py
python3 tools/inspect_stock.py
python3 scripts/check.py
python3 tools/build_name_probe.py
python3 scripts/flash.py name-probe
```

The final command prints an offline plan. Stock Micro v1.05 is pinned by size
and SHA256. The catalog-MD5 discrepancy is recorded in `sources.lock.json`;
a SHA256 failure is not expected and must not be bypassed.

## Enter update mode

Close the vendor updater. Set the Micro to **D** mode and connect a USB data
cable. Run `python3 tools/inspect_usb.py`: expect `8BitDo Micro gamepad` (or the
custom name), VID/PID `2dc8:9020`. Copy its `location` value into the commands
below in place of `USB_LOCATION`; do not reuse someone else's port value.

```sh
build/enter_update --apply USB_LOCATION
python3 tools/inspect_usb.py
```

This uses the vendor's runtime update-entry reports, not a flash operation.
Expect `8BitDo Boot`, `2dc8:3208`, at the same port. The flashing tool separately
checks the exact boot descriptor and product query `9020` before writing.

## Flash, verify and restore

```sh
python3 scripts/flash.py name-probe --location USB_LOCATION --apply
python3 tools/inspect_usb.py
```

The tool saves application/metadata backups, writes the pinned package, compares
all **77,824 plaintext bytes**, commits/verifies version 105, then reboots.
Keep USB connected until completion. Exit code zero and runtime USB name
**Glassly Micro test01** confirm the tested result. The name probe changes twenty
bytes; it adds no GATT stream.

Transactions, input/source snapshots and `before-application.bin` /
`before-metadata.bin` are kept under ignored `build/hardware/`. Preserve them.
The original development unit had a nonzero 432-byte application tail; stock
reflash replaced it with zeros. Its purpose is unknown and its backup is retained.

Only exact known stock/name/development-unit factory hashes and version 105 are
accepted. An unknown baseline is saved, then rejected before erase. For another
unit, keep that backup and use the official updater to install stock Micro v1.05
before retrying. If it still differs, inspect the evidence; do not relax the pins.
A partially written image is not automatically retried or forcibly recovered.

To remove the name patch, re-enter update mode and flash stock with the same
verification path:

```sh
python3 scripts/flash.py stock --location USB_LOCATION --apply
```

This reinstalls pinned v1.05, not arbitrary historical device data. Full button
streaming and phone background operation remain work in progress.
