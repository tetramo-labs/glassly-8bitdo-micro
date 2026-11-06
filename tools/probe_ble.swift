import Foundation
import CoreBluetooth

// Bounded Micro BLE diagnostics. Echo writes 31/a5/00/ff; buttons writes A1/A0.
// Echo requires the separately flashed Micro notification probe; avoid vendor command 04.
let args = Array(CommandLine.arguments.dropFirst())
guard args.count == 3, ["scan", "inspect", "listen", "echo", "buttons"].contains(args[0]),
      let duration = Double(args[2]), duration.isFinite, (5...300).contains(duration),
      args[0] == "scan" ? args[1] == "-" : UUID(uuidString: args[1]) != nil else {
    fputs("Usage: probe_ble scan - SECONDS | inspect OBSERVED_UUID SECONDS | listen OBSERVED_UUID SECONDS | echo OBSERVED_UUID SECONDS | buttons OBSERVED_UUID SECONDS\n", stderr)
    exit(64)
}
final class Probe: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    var central: CBCentralManager!
    var target: CBPeripheral?
    var seen = Set<UUID>()
    var pending = 0
    var finished = false
    var subscribed = false
    var notifications = 0
    var characteristic: CBCharacteristic?
    let echoValues: [UInt8] = [0x31, 0xa5, 0x00, 0xff]
    var echoIndex = 0
    var acknowledged = false
    var echoed = false
    var streamStarted = false
    var stopping = false
    var previousSequence: UInt8?
    var previousMask: UInt32 = 0
    let identifier = UUID(uuidString: args[1])
    func emit(_ event: String, _ fields: [String: Any] = [:]) {
        var record = fields
        record["event"] = event
        record["time"] = ISO8601DateFormatter().string(from: Date())
        if let data = try? JSONSerialization.data(withJSONObject: record, options: [.sortedKeys]) {
            print(String(decoding: data, as: UTF8.self)); fflush(stdout)
        }
    }
    func finish(_ code: Int32, _ reason: String) {
        guard !finished else { return }
        finished = true
        central.stopScan()
        if let target { central.cancelPeripheralConnection(target) }
        emit("finished", ["code": code, "reason": reason]); exit(code)
    }
    func start(duration: Double) {
        central = CBCentralManager(delegate: self, queue: .main)
        DispatchQueue.main.asyncAfter(deadline: .now() + duration) { [weak self] in
            guard let self else { return }
            if args[0] == "buttons", self.streamStarted, let target = self.target, let characteristic = self.characteristic {
                self.stopping = true
                self.emit("stream_stop_requested")
                target.writeValue(Data([0xa0]), for: characteristic, type: .withResponse)
                DispatchQueue.main.asyncAfter(deadline: .now() + 5) { [weak self] in self?.finish(1, "Stop acknowledgement timeout") }
                return
            }
            self.finish(args[0] == "scan" || (args[0] == "listen" && self.subscribed) ? 0 : 1, "time limit")
        }
    }
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        emit("central_state", ["state": central.state.rawValue])
        if central.state == .poweredOn {
            central.scanForPeripherals(withServices: nil)
        } else if [.unauthorized, .unsupported, .poweredOff].contains(central.state) {
            finish(1, "Bluetooth unavailable")
        }
    }
    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral,
                        advertisementData ad: [String: Any], rssi: NSNumber) {
        let local = ad[CBAdvertisementDataLocalNameKey] as? String ?? ""
        let cached = peripheral.name ?? ""
        let services = (ad[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID] ?? []).map(\.uuidString)
        let candidate = [local, cached].contains {
            $0 == "80EL" || $0.lowercased().contains("micro") || $0.lowercased().contains("8bitdo")
        } || services.contains("FF10")
        guard args[0] == "scan" || candidate || peripheral.identifier == identifier else { return }
        if seen.insert(peripheral.identifier).inserted {
            emit("discovered", ["identifier": peripheral.identifier.uuidString, "local_name": local,
                 "cached_name": cached, "services": services, "rssi": rssi,
                 "manufacturer_data": (ad[CBAdvertisementDataManufacturerDataKey] as? Data ?? Data()).map { String(format: "%02x", $0) }.joined()])
        }
        guard args[0] != "scan", peripheral.identifier == identifier, target == nil else { return }
        target = peripheral; peripheral.delegate = self
        central.stopScan(); central.connect(peripheral)
    }
    func centralManager(_: CBCentralManager, didConnect peripheral: CBPeripheral) {
        emit("connected"); peripheral.discoverServices(nil)
    }
    func centralManager(_: CBCentralManager, didFailToConnect _: CBPeripheral, error: Error?) {
        finish(1, error?.localizedDescription ?? "connect failed")
    }
    func centralManager(_: CBCentralManager, didDisconnectPeripheral _: CBPeripheral, error: Error?) {
        finish(1, error?.localizedDescription ?? "disconnected")
    }
    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        guard error == nil, let services = peripheral.services else { finish(1, "service discovery failed"); return }
        pending = services.count
        if services.isEmpty { finish(args[0] == "inspect" ? 0 : 1, "no visible services"); return }
        for service in services { emit("service", ["uuid": service.uuid.uuidString]); peripheral.discoverCharacteristics(nil, for: service) }
    }
    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        guard error == nil else { finish(1, "characteristic discovery failed"); return }
        for characteristic in service.characteristics ?? [] {
            emit("characteristic", ["service": service.uuid.uuidString, "uuid": characteristic.uuid.uuidString,
                                    "properties": characteristic.properties.rawValue])
            pending += 1; peripheral.discoverDescriptors(for: characteristic)
        }
        complete()
    }
    func peripheral(_: CBPeripheral, didDiscoverDescriptorsFor characteristic: CBCharacteristic, error: Error?) {
        guard error == nil else { finish(1, "descriptor discovery failed"); return }
        emit("descriptors", ["characteristic": characteristic.uuid.uuidString,
                             "uuids": (characteristic.descriptors ?? []).map { $0.uuid.uuidString }])
        complete()
    }
    func peripheral(_: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic, error: Error?) {
        guard error == nil, characteristic.isNotifying else { finish(1, error?.localizedDescription ?? "subscription failed"); return }
        subscribed = true
        emit("subscribed", ["uuid": characteristic.uuid.uuidString])
        if args[0] == "echo" { sendEcho() }
        if args[0] == "buttons", let target {
            emit("stream_start_requested")
            target.writeValue(Data([0xa1]), for: characteristic, type: .withResponse)
        }
    }
    func sendEcho() {
        guard let target, let characteristic, echoIndex < echoValues.count else { finish(1, "Missing echo target"); return }
        acknowledged = false; echoed = false
        let value = echoValues[echoIndex]
        emit("write_requested", ["hex": String(format: "%02x", value)])
        target.writeValue(Data([value]), for: characteristic, type: .withResponse)
    }
    func advanceEcho() {
        guard acknowledged && echoed else { return }
        echoIndex += 1
        if echoIndex == echoValues.count { finish(0, "All four acknowledged echoes verified") }
        else { sendEcho() }
    }
    func peripheral(_: CBPeripheral, didWriteValueFor _: CBCharacteristic, error: Error?) {
        guard error == nil else { finish(1, error!.localizedDescription); return }
        if args[0] == "buttons" {
            if stopping { emit("stream_stop_acknowledged"); finish(previousSequence == nil ? 1 : 0, previousSequence == nil ? "No baseline received" : "Stream capture complete") }
            else { streamStarted = true; emit("stream_start_acknowledged") }
            return
        }
        acknowledged = true
        emit("write_acknowledged", ["index": echoIndex])
        advanceEcho()
    }
    func peripheral(_: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        guard error == nil else { finish(1, error!.localizedDescription); return }
        if args[0] == "echo" {
            guard echoIndex < echoValues.count, characteristic.value == Data([echoValues[echoIndex]]) else { finish(1, "Unexpected echo notification"); return }
            echoed = true
        }
        if args[0] == "buttons" {
            let bytes = Array(characteristic.value ?? Data())
            guard bytes.count == 8, bytes[0] == 0x47, bytes[1] == 5, bytes[3] & 0xfc == 0 else { finish(1, "Invalid Micro button packet"); return }
            let mask = UInt32(bytes[4]) | UInt32(bytes[5]) << 8 | UInt32(bytes[6]) << 16 | UInt32(bytes[7]) << 24
            guard mask & ~UInt32(0x8003fff9) == 0 else { finish(1, "Unknown raw button bits"); return }
            let baseline = bytes[3] & 2 != 0
            guard previousSequence != nil || (baseline && bytes[2] == 0) else { finish(1, "Missing initial baseline"); return }
            let gap = previousSequence.map { bytes[2] != $0 &+ 1 } ?? false
            let resync = baseline || bytes[3] & 1 != 0 || gap
            let pressed = resync ? 0 : mask & ~previousMask
            let released = resync ? 0 : previousMask & ~mask
            previousSequence = bytes[2]; previousMask = mask
            emit("button_state", ["sequence": bytes[2], "flags": bytes[3], "mask": String(format: "%08x", mask),
                 "pressed": String(format: "%08x", pressed), "released": String(format: "%08x", released),
                 "resync": resync, "sequence_gap": gap])
        }
        notifications += 1
        emit("notification", ["uuid": characteristic.uuid.uuidString, "sequence": notifications,
             "hex": (characteristic.value ?? Data()).map { String(format: "%02x", $0) }.joined()])
        if args[0] == "echo" { advanceEcho() }
    }
    func complete() {
        pending -= 1
        if pending == 0 {
            if ["listen", "echo", "buttons"].contains(args[0]), let target {
                let serviceID = CBUUID(string: "0000FF10-0000-1000-8000-00805F9B34FB")
                let valueID = CBUUID(string: "0000FF13-0000-1000-8000-00805F9B34FB")
                let matches = (target.services ?? []).filter { $0.uuid == serviceID }
                    .flatMap { $0.characteristics ?? [] }.filter { $0.uuid == valueID && $0.properties.contains(.notify) }
                guard matches.count == 1 else { finish(1, "Expected exactly one FF13 notify characteristic"); return }
                guard !["echo", "buttons"].contains(args[0]) || matches[0].properties.contains(.write) else { finish(1, "Echo requires writes with response"); return }
                characteristic = matches[0]
                target.setNotifyValue(true, for: matches[0])
            } else { finish(0, "GATT inventory complete") }
        }
    }
}
let probe = Probe()
probe.start(duration: duration)
RunLoop.main.run()
