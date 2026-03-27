import Foundation

@MainActor
final class VehiclesViewModel: ObservableObject {
    @Published var isLoading = false
    @Published var error: String?
    @Published var vehicles: [Vehicle] = []

    private let service: VehicleService
    private let featureService: UserFeatureService

    init(service: VehicleService, featureService: UserFeatureService) {
        self.service = service
        self.featureService = featureService
    }

    func load(token: String) async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        do {
            vehicles = try await service.fetchVehicles(token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func createVehicle(_ request: VehicleCreateRequest, token: String) async {
        do {
            _ = try await featureService.createVehicle(request, token: token)
            await load(token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func updateVehicle(id: Int, request: VehicleCreateRequest, token: String) async {
        do {
            _ = try await featureService.updateVehicle(id: id, request, token: token)
            await load(token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func deleteVehicle(id: Int, token: String) async {
        do {
            try await featureService.deleteVehicle(id: id, token: token)
            await load(token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }
}
