# Micro button-stream experiment

Status: flashed with full readback and unchanged metadata. Runtime USB boot, A1
acknowledgement and the first BLE baseline `4705000200000000` are observed.
Offline qualification passed (131,072 masks, 2,048 buffer/IRQ cases and 12,000
independent-model polls). All 16 physical buttons and A+B / L2+R2 combinations are verified. Reconnect produced a fresh baseline. On battery in K mode, the stream stayed
connected 314 seconds, including 279 seconds idle after A release without
keepalive writes; A0 was acknowledged before intentional disconnect.

The image preserves the Micro's existing FF10/FF13 registration and radio-owned
CCC handling. Subscribe, wait for subscription completion, then write **A1** with
response to start/reset the stream. Write **A0** and await its response before
unsubscribing. Connect and disconnected polling reset the session. Explicit host
intent is required; this is not automatic tracking of the internal CCC callback.

Each notification is eight bytes:

| Bytes | Meaning |
| --- | --- |
| 0–1 | `47 05`: Micro experimental stream |
| 2 | Sequence modulo 256, advanced after command-09 success |
| 3 | Bit 0: overflow; bit 1: initial baseline |
| 4–7 | Full raw Micro mask, little endian; allowed bits `0x8003fff9` |

Physical mappings from the ordered tap test are in `firmware/protocol.json`.
Bit 31 is retained but unassigned; its physical role is not established. Baseline, overflow and sequence gaps replace held state without
synthesizing input edges. Regular consecutive packets produce pressed/released
masks from the difference.

## Micro-specific bindings

- Startup registers timer `0x219e4` with callback `0x0101c290` through
  `0x010209d0`; its normal rearm byte is 10. The hook at `0x0101c2a4` precedes the
  stock report task's congestion gates. Actual wall-clock cadence is unmeasured.
- Raw GPIO reader `0x010200c4` is executed directly. Two consecutive identical
  whole-mask samples qualify a change; changes between samples are not recoverable.
- Sixteen 32-bit snapshots are queued. Overflow discards queued history, retains
  the newest state and sets the overflow flag. In-flight state is separate.
- The sender uses the registered handle at `0x20648`, command 09, and actual IPC
  routines. Awake/capacity checks, stale-ACK clearing and synchronous copying are
  protected by saved/restored PRIMASK. Capacity must exceed the 13-byte packet.
- Stock completion dispatch sets bit 6 at `0x20010` only for zero-status command
  09. This is radio acceptance, not proof of host receipt. Missing/nonzero ACKs
  stall transmission while sampling continues; A1 can reset the session.
- While connected and explicitly enabled, each poll clears idle and cancels the
  stock watchdog. Stop/disconnect restores the stock policy. Idle suppression on
  battery passed the bounded 314-second capture; longer-term behavior is unmeasured.

## State and placement

One count instruction at `0x0102459e` reduces the first 600-byte pool from three
blocks to two. The excluded third block is `[0x225dc,0x22834)`; stream state uses
88 bytes. Startup already zeroes that BSS. Other pool lists remain unchanged.

| State offset | Storage |
| --- | --- |
| 0, 4 | Candidate/stable 32-bit masks |
| 8–11 | Head, count, sequence, flags |
| 12–15 | Enabled, pending, initialized, padding |
| 16–79 | Sixteen queued masks |
| 80–87 | In-flight sequence, flags, full mask, padding |

The 352-byte code/literal block fits within the 432-byte stock-cleared tail at
`0x0102ae50`, whose execution was demonstrated by the notification echo probe.
Package extent, startup records and SP are unchanged. A raw four-byte-window scan
finds one apparent pointer into the reserved pool at offset `0x105d5`: it crosses
GATT record fields (bytes `00 28 02 00`, yielding `0x22800`), rather than an ARM
pointer literal. The only pool-base pointer is the initializer literal at
`0xc600`. This does not exclude computed ROM/DMA accesses. Reducing OEM pool
capacity requires live coexistence testing.

The stock report task and connection power/indicator helper are isolated in the
stream model; startup, pool initialization, GPIO, event dequeue, stream code,
timer cancellation and IPC execute actual instructions. Radio completion bits
are synthetic in the queue model and separately checked through the stock
completion switch. No whole-firmware stack bound is claimed.

## Reproduce offline checks

```sh
python3 tools/build_buttons_probe.py
.venv/bin/python tools/inspect_micro_bindings.py
.venv/bin/python tools/inspect_buttons_probe.py
python3 scripts/check.py
```

Generated images, raw USB backups and BLE captures remain local under `build/`.

The isolated maximum observed stack use is 900 bytes. Sanitized checks are in
`evidence/buttons-probe-emulation.json` and `evidence/micro-bindings.json`.

## Observed physical mapping

| Button | Raw mask |
| --- | --- |
| A | `0x00002000` |
| B | `0x00001000` |
| X | `0x00000010` |
| Y | `0x00000020` |
| Up | `0x00000200` |
| Down | `0x00000100` |
| Left | `0x00000080` |
| Right | `0x00000040` |
| L | `0x00000400` |
| R | `0x00000800` |
| L2 | `0x00004000` |
| R2 | `0x00008000` |
| Minus | `0x00000008` |
| Plus | `0x00000001` |
| Star | `0x00010000` |
| Home | `0x00020000` |

All 16 ordered press/release pairs arrived consecutively with no gaps or overflow.
A+B produced `0x3000`, and L2+R2 produced `0xc000`; staggered transitions and
additional taps during the chord test are retained in the local capture.
