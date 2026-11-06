# Micro findings

## 2026-11-05

The user has a Micro connected over USB. The macOS registry contains a
`Pro Controller` interface with VID/PID `057e:2009`, revision `0200`, consistent
with a Switch-compatible interface. This does not independently prove model,
chipset or installed firmware. The raw registry is saved locally under
`build/hardware/initial-usb.plist`. No device commands have been sent.

The official [support page](https://support.8bitdo.com/) lists Micro v1.05,
including Switch 2 support and an idle-power fix. Its separate Odyssey package
link returned HTTP 403 to the initial downloader. The public updater catalog
is being checked for the ordinary v1.05 package.

The [Micro FAQ](https://support.8bitdo.com/faq/micro.html) describes Switch,
Dinput and keyboard modes. No GATT contract or physical raw button mask is
established yet.

## Pinned stock and updater selection

Vendor catalog type 60 / entry 1987 is Micro v1.05, 77,852 bytes. It contains one
77,824-byte Yichip-cipher section at `0x01018000`, version 105, product `0x9020`.
Decryption yields Micro names, SDK paths and HCI diagnostic strings; re-encryption
reproduces the entire package exactly. Package and plaintext hashes are pinned in
`sources.lock.json`. The catalog MD5 differs from the downloaded package, just as
in the Zero 2 investigation; the discrepancy is preserved rather than ignored.
This is reproducibility evidence, not vendor authentication.

The pinned official macOS updater 2.5.2 (build 5), binary SHA256
`966eabd911b6027951a06989d90c34bb38729ca53b22e7bf4db9ac6e935a5d2a`, maps Micro
`0x9020` to **boot type 17**, whereas Zero 2 `0x9018` selects type 20. ARM64 anchors:
`0x100007ca4` tests 9020, `0x100007cb4` sets 17, `0x100007d9c` calls
`setBootType:`. The latter selector is confirmed by the existing REA metadata
capture for this exact binary in the Zero 2 investigation. This does not yet
establish Micro flash/read semantics.

The updater's `S8BitdoDevice.plist` names Micro at VID/PID `2dc8:9020`, catalog
60. Its English `MacOSTisp` says to select D mode. After the user did that,
USB enumerated **8BitDo Micro gamepad**, `2dc8:9020`, revision `0200`, with a
136-byte HID report descriptor (SHA256
`2c5b161fb5dafa36f3337fcc8ced3b6f806d14cf4563817b6a1696b86988c264`). USB revision
is not treated as installed firmware version. No device commands or flash had been performed at that stage. Native UI automation was unavailable (pipe startup failure), so
analysis continues through the updater binary and USB descriptors.

## Verified update entry, backups and first flashes

Executing the pinned updater's `SHIDDinput boot:` routine at `0x10001be68`
offline with Micro identity produces two 64-byte output reports beginning
`06 00 50 01 00 00` and `81 05 00 51 00 00`. The rest is zero in the controlled
emulation; the vendor legacy path leaves trailing stack bytes uninitialized.
Our tool initializes the entire reports. Sending this sequence to the exact
runtime VID/PID/location/136-byte descriptor changed enumeration to `8BitDo Boot`,
`2dc8:3208`, with the observed 33-byte boot HID descriptor. Command 8 returned
product `9020`, with valid response CRC.

Two independent command-5 reads produced identical 77,824-byte application
backups and 4,096-byte metadata backups. Version record is 105. The installed
application matches pinned v1.05 through offset `0x12e4f`; its last 432 bytes are
nonzero and differ from stock zeros. Their purpose is unknown. Both original
captures remain local and were preserved before any erase.

`scripts/flash.py stock --apply` then completed using the Micro boot-type-17
path audited in `evidence/macos-updater-protocol.json`. All 77,824 plaintext bytes
match the stock image, all 4,096 metadata bytes are unchanged, and USB rebooted
as `8BitDo Micro gamepad`. Stock flashing overwrote the original tail with the
package's zeros; this does not establish the tail's purpose.

The name-only image changes the same-length string at offset `0x12a44` from
`8BitDo Micro gamepad` to `Glassly Micro test01`. It changes no instructions,
addresses, startup data, RAM allocation or GATT behavior. Its full readback
matches, exactly twenty plaintext bytes differ from stock, metadata is unchanged,
and runtime USB reports **Glassly Micro test01** with the original 136-byte HID
descriptor. This establishes the first minimal custom flash, not button streaming.

Flashing evidence is in `evidence/flashing.json`. The native flasher admits only
pinned stock/name image pairs and three exact installed hashes: stock, name probe
or the independently backed-up development unit's factory image. Unknown baselines
are backed up and rejected before erase. There is no forced recovery mode.

## First BLE candidate inventory

While the Micro still enumerated over USB in D mode, a 40-second scan discovered
one new `80EL` candidate (different CoreBluetooth UUID from the earlier Zero 2).
A bounded connection exposed FF10, FF13 with write+notify properties (`0x18`),
and CCC descriptor 2902. No subscription or characteristic write was made.
Sanitized events are in `evidence/ble-inventory.json`. Because `80EL` is shared,
physical power/mode correlation is still required before attributing that radio
to this Micro. The user has been asked to unplug and pair in K mode.

Static investigation found a radio configuration script at section offset
`0xed2a` (7,596 bytes / 70 records under the previously recovered format), with
an 18-entry attribute-table candidate at `0x105b4` targeting radio `0xc4975`.
This is structural comparison evidence; Micro loader execution remains to audit.

The Micro scatter records at offsets `0x12a8c` and `0x12a9c` describe initialized
RAM at `0x20000` (size `0x794`, compressed source `0x0102aaac`, initializer
`0x010183ca`) and BSS at `0x20794` (size `0x244c`, source marker `0x0102ae50`,
initializer `0x01023d22`). The complete decompressor at offsets `0x3ca..0x41f`
is byte-identical to the audited Zero 2 helper. These are Micro-derived table
entries, not proof of free RAM, custom code placement or interrupt ownership.
