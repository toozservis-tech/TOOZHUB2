import Foundation

struct Vehicle: Codable, Identifiable, Hashable {
    let id: Int
    let userEmail: String
    var nickname: String?
    var brand: String?
    var model: String?
    var year: Int?
    var engine: String?
    var vin: String?
    var plate: String?
    var notes: String?
    var photoPath: String?
    var stkValidUntil: Date?
    var currentMileageKm: Int?
    var lastStkMileageKm: Int?
    var mileageCheckedAt: Date?
    var tyresInfo: String?
    var insuranceProvider: String?
    var insuranceValidUntil: Date?
    var tenantId: Int?
    let createdAt: Date

    var displayName: String {
        let name = [brand, model].compactMap { $0 }.joined(separator: " ")
        if !name.isEmpty { return name }
        return nickname ?? "Vehicle #\(id)"
    }
}

struct VehicleCreateRequest: Encodable {
    var nickname: String
    var brand: String?
    var model: String?
    var year: Int?
    var engine: String?
    var vin: String?
    var plate: String?
    var notes: String?
    var stkValidUntil: String
    var currentMileageKm: Int?
    var lastStkMileageKm: Int?
    var tyresInfo: String?
    var insuranceProvider: String?
    var insuranceValidUntil: String?
}

struct TachometerChallengeResponse: Decodable {
    let challengeId: String
    let captchaImageBase64: String
    let captchaMimeType: String
    let expiresInSeconds: Int
}

struct TachometerLookupRequestBody: Encodable {
    let challengeId: String
    let vin: String
    let captchaCode: String
}

struct TachometerInspection: Decodable {
    let checkDate: Date?
    let mileageKm: Int
    let protocolNumber: String?
    let inspectionType: String?
}

struct TachometerLookupResponse: Decodable {
    let vin: String
    let latestMileageKm: Int
    let latestCheckDate: Date?
    let inspections: [TachometerInspection]
    let source: String
}
