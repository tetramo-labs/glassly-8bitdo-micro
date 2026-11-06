import Foundation
import CoreBluetooth

// Bounded Micro discovery/inventory only. No characteristic writes or subscriptions.
let args = Array(CommandLine.arguments.dropFirst())
guard args.count == 3, ["scan", "inspect"].contains(args[0]),
      let duration = Double(args[2]), duration.isFinite, (5...120).contains(duration),
      args[0] == "scan" ? args[1] == "-" : UUID(uuidString: args[1]) != nil else {
    fputs("Usage: probe_ble scan - SECONDS | inspect OBSERVED_UUID SECONDS\n", stderr)
    exit(64)
}
final class Probe: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    var central: CBCentralManager!
    var target: CBPeripheral?
    var seen = Set<UUID>()
    var pending = 0
    var finished = false
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
            self?.finish(args[0] == "scan" ? 0 : 1, "time limit")
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
        guard candidate || peripheral.identifier == identifier else { return }
        if seen.insert(peripheral.identifier).inserted {
            emit("discovered", ["identifier": peripheral.identifier.uuidString, "local_name": local,
                 "cached_name": cached, "services": services, "rssi": rssi,
                 "manufacturer_data": (ad[CBAdvertisementDataManufacturerDataKey] as? Data ?? Data()).map { String(format: "%02x", $0) }.joined()])
        }
        guard args[0] == "inspect", peripheral.identifier == identifier, target == nil else { return }
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
        if services.isEmpty { finish(0, "no visible services"); return }
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
    func complete() {
        pending -= 1
        if pending == 0 { finish(0, "GATT inventory complete") }
    }
}
let probe = Probe()
probe.start(duration: duration)
RunLoop.main.run()
