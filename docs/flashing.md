# Flash the Micro on macOS

Use this repository only with an **8BitDo Micro**. The experimental image has
passed full flash readback, all 16 physical buttons, A+B, L2+R2 and BLE reconnect
on one controller. Battery streaming passed a 314-second run with 279 seconds
idle and no keepalive writes. Experimental firmware can brick the device; retain backups.

## Build

Install Python 3 and Xcode Command Line Tools, then run:

```sh
git clone https://github.com/tetramo-labs/glassly-8bitdo-micro.git
cd glassly-8bitdo-micro
python3 scripts/fetch_stock.py
python3 tools/inspect_stock.py
python3 scripts/check.py
python3 scripts/flash.py buttons-probe
```

The last command builds the image and prints an **offline plan**. It does not
access the controller. Micro v1.05 and each generated image are pinned by size
and SHA256. The vendor catalog MD5 mismatch is recorded in `sources.lock.json`;
SHA256 provides reproducibility, not vendor authentication. Do not bypass a pin
failure. OEM images and generated files remain local under `research/` and `build/`.

## Connect and flash

Close the vendor updater. Set the Micro to **D**, connect a USB data cable, and
inspect the device:

```sh
python3 tools/inspect_usb.py
```

Expect `8BitDo Micro gamepad` or `Glassly Micro test01`, VID/PID `2dc8:9020`.
Replace `USB_LOCATION` below with the reported `location` value for your unit.

```sh
build/enter_update --apply USB_LOCATION
python3 tools/inspect_usb.py
python3 scripts/flash.py buttons-probe --location USB_LOCATION --apply
python3 tools/inspect_usb.py
```

After update entry, expect `8BitDo Boot`, `2dc8:3208`, at the same location. The
flasher independently checks the boot descriptor and product `9020`, saves the
application and metadata, writes the image, verifies **all 77,824 plaintext
bytes**, commits/verifies version 105 and reboots. Keep USB connected until it
finishes. Check exit code zero and normal runtime USB `Glassly Micro test01`.

Transactions and source snapshots are saved under `build/hardware/`, including
`before-application.bin` and `before-metadata.bin`. Preserve these files. The
original development unit had a nonzero 432-byte tail that stock flashing
replaced with zeros; its purpose is unknown and its original backup is retained.

Only exact known stock, experimental and backed-up factory hashes are accepted.
An unknown baseline is saved and rejected **before erase**. On another unit,
retain that backup, install stock Micro v1.05 with the official updater, and
retry. If it still differs, inspect the evidence without relaxing the pins. A
partially written image is not automatically retried or forcibly recovered.

## Pair with Glassly

Unplug USB and switch to **K**. Turn the Micro on and hold its pairing button
until the LED blinks rapidly. In a Glassly build containing Micro support, choose
**8BitDo Micro** in controller pairing. Pair inside Glassly.

The advertisement `80EL` is shared with other hardware. The driver validates the
Micro `47 05` baseline before reporting readiness. All sixteen buttons use the
[documented mapping](buttons-probe.md); phone background/locked operation still
requires physical phone validation.

## Restore stock

Select D, connect USB, inspect the location and re-enter update mode as above:

```sh
build/enter_update --apply USB_LOCATION
python3 tools/inspect_usb.py
python3 scripts/flash.py stock --location USB_LOCATION --apply
python3 tools/inspect_usb.py
```

This reinstalls pinned Micro v1.05 with full readback. It does not restore
arbitrary historical device data.

## Optional diagnostics

With the flashed controller advertising, discover its local identifier:

```sh
build/probe_ble scan - 30
build/probe_ble buttons OBSERVED_UUID 300
```

Identify the Micro by its wake/power correlation; `80EL` alone is insufficient.
The receiver subscribes, writes A1 and records eight-byte states, sequence gaps
and overflow. On normal timeout it writes A0 and requires acknowledgement before
disconnecting. It sends no keepalives. Do not run it while pairing with Glassly.

`name-probe` and `notify-probe` remain available as development milestones, using
the same `scripts/flash.py IMAGE` / `--apply` flow. The former changes only the
name; the latter echoes one byte and does not stream buttons. `probe_ble echo`
is only for `notify-probe`.

For the extended offline emulation checks:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-analysis.txt
.venv/bin/python tools/inspect_micro_bindings.py
.venv/bin/python tools/inspect_buttons_probe.py
```
