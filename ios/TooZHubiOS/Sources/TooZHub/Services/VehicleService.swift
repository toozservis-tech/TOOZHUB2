import Foundation

final class VehicleService {
    private let api: APIClient

    init(api: APIClient) {
        self.api = api
    }

    func fetchVehicles(token: String) async throws -> [Vehicle] {
        try await api.request(.get("/api/v1/vehicles"), token: token)
    }

    func fetchVehicleDetail(id: Int, token: String) async throws -> Vehicle {
        try await api.request(.get("/api/v1/vehicles/\(id)"), token: token)
    }

    func fetchServiceRecords(vehicleId: Int, token: String) async throws -> [ServiceRecord] {
        try await api.request(.get("/api/v1/vehicles/\(vehicleId)/records"), token: token)
    }

    func lookupVIN(_ vin: String, token: String) async throws -> VinLookupResponse {
        let clean = vin.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        let escaped = clean.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? clean
        return try await api.request(.get("/api/v1/vin/\(escaped)"), token: token)
    }

    func decodeVINDetailed(_ vin: String, token: String) async throws -> DecoderResponse {
        let clean = vin.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        let body = try api.encodeBody(["vin": clean])
        return try await api.request(.post("/api/vehicles/decode-vin", body: body), token: token)
    }

    func decodePlate(_ plate: String, token: String) async throws -> DecoderResponse {
        let body = try api.encodeBody(["plate": plate])
        return try await api.request(.post("/api/vehicles/decode-plate", body: body), token: token)
    }

    func createTachometerChallenge(token: String) async throws -> TachometerChallengeResponse {
        try await api.request(.post("/api/v1/vehicles/tachometer/challenge"), token: token)
    }

    func lookupTachometer(
        challengeId: String,
        vin: String,
        captchaCode: String,
        token: String
    ) async throws -> TachometerLookupResponse {
        let body = try api.encodeBody(
            TachometerLookupRequestBody(
                challengeId: challengeId,
                vin: vin,
                captchaCode: captchaCode
            )
        )
        return try await api.request(.post("/api/v1/vehicles/tachometer/lookup", body: body), token: token)
    }
}
