import Foundation

@MainActor
final class VehicleDetailViewModel: ObservableObject {
    @Published var isLoading = false
    @Published var error: String?
    @Published var vehicle: Vehicle?
    @Published var records: [ServiceRecord] = []

    private let service: VehicleService
    private let featureService: UserFeatureService

    init(service: VehicleService, featureService: UserFeatureService) {
        self.service = service
        self.featureService = featureService
    }

    func load(vehicleId: Int, token: String) async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        do {
            async let detail = service.fetchVehicleDetail(id: vehicleId, token: token)
            async let records = service.fetchServiceRecords(vehicleId: vehicleId, token: token)
            self.vehicle = try await detail
            self.records = try await records
        } catch {
            self.error = error.localizedDescription
        }
    }

    func addRecord(vehicleId: Int, request: ServiceRecordCreateRequest, token: String) async {
        do {
            _ = try await featureService.createServiceRecord(vehicleId: vehicleId, request, token: token)
            await load(vehicleId: vehicleId, token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func updateRecord(vehicleId: Int, recordId: Int, request: ServiceRecordUpdateRequest, token: String) async {
        do {
            _ = try await featureService.updateServiceRecord(vehicleId: vehicleId, recordId: recordId, request, token: token)
            await load(vehicleId: vehicleId, token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func deleteRecord(vehicleId: Int, recordId: Int, token: String) async {
        do {
            try await featureService.deleteServiceRecord(vehicleId: vehicleId, recordId: recordId, token: token)
            await load(vehicleId: vehicleId, token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }
}
