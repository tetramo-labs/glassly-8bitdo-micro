# Micro port plan

- [x] Pin stock Micro firmware and inspect every package section.
- [ ] Identify update USB interface and verify its protocol. Runtime D-mode identity and updater boot-type selection are established.
- [ ] Back up the installed application and device data using a verified read path.
- [ ] Reflash stock, then a minimal observable patch with full readback.
- [ ] Recover Micro input masks, notification/CCC lifecycle and idle policy.
- [ ] Bind memory/startup/execution placement and build the button stream.
- [ ] Flash and verify all buttons, chords, reconnect and battery idle behavior.
- [ ] Add native iOS/Android drivers and concise pairing UI to Glassly.
- [ ] Document flashing/restoring stock and publish source changes.

Phone background/locked delivery requires actual phone validation; macOS BLE
captures and offline emulation do not establish it.
