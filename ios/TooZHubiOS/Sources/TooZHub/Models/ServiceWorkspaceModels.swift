import Foundation

struct ServiceWorkspaceCustomer: Codable, Identifiable, Hashable {
    var id: Int { customerId }
    let customerId: Int
    let email: String
    let name: String?
    let phone: String?
    let vehiclesCount: Int
    let sharedVehiclesCount: Int
    let lastServiceDate: String?
    let note: String?
    let createdAt: String?
}

struct ServiceWorkspaceVehicle: Codable, Identifiable, Hashable {
    let id: Int
    let nickname: String?
    let brand: String?
    let model: String?
    let year: Int?
    let plate: String?
    let vin: String?
    let stkValidUntil: String?
    let currentMileageKm: Int?
    let lastStkMileageKm: Int?
    let mileageCheckedAt: String?
    let createdAt: String?
    let isShared: Bool

    var displayName: String {
        let composed = [brand, model].compactMap { $0 }.joined(separator: " ")
        if !composed.isEmpty { return composed }
        return nickname ?? "Vehicle #\(id)"
    }
}

struct ServiceWorkspaceReminder: Codable, Identifiable, Hashable {
    let id: Int
    let customerId: Int
    let customerName: String?
    let vehicleId: Int?
    let vehicleName: String?
    let text: String
    let type: String
    let dueDate: String?
    let isCompleted: Bool
}

struct ServiceWorkspaceVehicleCreateRequest: Encodable {
    let nickname: String
    let brand: String?
    let model: String?
    let year: Int?
    let plate: String?
    let vin: String?
    let stkValidUntil: String
    let currentMileageKm: Int?
    let lastStkMileageKm: Int?
}

struct ServiceWorkspaceReminderCreateRequest: Encodable {
    let customerId: Int
    let vehicleId: Int?
    let type: String
    let text: String
    let dueDate: String?
    let notifyAt: String?
    let notificationMethod: String?
}

struct ServiceWorkspaceReminderUpdateRequest: Encodable {
    let type: String?
    let text: String?
    let dueDate: String?
    let notifyAt: String?
    let notificationMethod: String?
    let isCompleted: Bool?
}
