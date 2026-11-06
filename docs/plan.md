# Micro port plan

- [x] Pin stock Micro firmware and inspect every package section.
- [x] Identify runtime/update USB interfaces and verify Micro boot type 17 and read/write protocol.
- [x] Back up and independently reread the application and metadata.
- [x] Reflash stock and a name-only patch; full readback, unchanged metadata and runtime USB verified.
- [x] Recover raw GPIO masks and stock notification sender offline; verify battery BLE subscription.
- [x] Flash the bounded notification echo experiment and verify delivery.
- [x] Recover physical labels and polling/debounce; bind explicit A1/A0 subscription intent and idle policy.
- [x] Bind memory/startup/execution placement and build the button stream.
- [x] Flash and verify all buttons, chords, reconnect and bounded battery idle behavior.
- [x] Add native iOS/Android drivers, tests and concise pairing UI to Glassly.
- [x] Document flashing/restoring stock and publish source changes.

Phone background/locked delivery requires actual phone validation; macOS BLE
captures and offline emulation do not establish it.
