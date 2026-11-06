# Micro port plan

- [x] Pin stock Micro firmware and inspect every package section.
- [x] Identify runtime/update USB interfaces and verify Micro boot type 17 and read/write protocol.
- [x] Back up and independently reread the application and metadata.
- [x] Reflash stock and a name-only patch; full readback, unchanged metadata and runtime USB verified.
- [x] Recover raw GPIO masks and stock notification sender offline; verify battery BLE subscription.
- [x] Flash the bounded notification echo experiment and verify delivery.
- [ ] Recover physical button labels, polling/debounce ownership, CCC lifecycle and idle policy.
- [ ] Bind memory/startup/execution placement and build the button stream.
- [ ] Flash and verify all buttons, chords, reconnect and battery idle behavior.
- [ ] Add native iOS/Android drivers and concise pairing UI to Glassly.
- [ ] Document flashing/restoring stock and publish source changes.

Phone background/locked delivery requires actual phone validation; macOS BLE
captures and offline emulation do not establish it.
