# Working instructions

Read docs/findings.md and docs/plan.md before continuing. The user requested the
same custom-firmware/BLE/Glassly workflow as Zero 2, in this separate repository.
Experimental flashing is in scope; start with stock or a minimal change and
preserve local device backups before writing. Distinguish offline analysis from
observed hardware results. Do not transfer Zero 2, Ananke or Gamebrick addresses,
physical masks, memory ownership, updater selection or BLE handles without
Micro-specific evidence.

Keep OEM packages, ROM/device dumps, updater binaries and downloaded research
repositories ignored under research/ or build/. Publish source, hashes and
sanitized findings only. Pin sources and retain all firmware package sections.
Run python3 scripts/check.py after code changes; never describe an unbound
component or a model-only test as flashable firmware or observed device behavior.
