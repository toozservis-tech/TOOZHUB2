import Foundation

@MainActor
final class ReservationsViewModel: ObservableObject {
    @Published var reservations: [Reservation] = []
    @Published var services: [ServiceContact] = []
    @Published var vehicleOptions: [ReservationVehicleOption] = []
    @Published var isLoading = false
    @Published var error: String?

    private let service: ReservationService
    private let featureService: UserFeatureService

    init(service: ReservationService, featureService: UserFeatureService) {
        self.service = service
        self.featureService = featureService
    }

    func load(token: String, role: String) async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        do {
            let normalizedRole = role.lowercased()
            async let reservations: [Reservation] = (normalizedRole == "service")
                ? service.fetchServiceReservations(token: token)
                : service.fetchReservations(token: token)
            async let discovery = service.fetchServiceDiscovery(token: token)
            async let linkedContacts = service.fetchMyServiceContacts(token: token)
            async let vehicles = service.fetchReservationVehicleOptions(token: token)
            self.reservations = try await reservations
            self.vehicleOptions = try await vehicles

            let discoveryServices = try await discovery
            let linked = try await linkedContacts
            var mergedServices = Dictionary(uniqueKeysWithValues: discoveryServices.map { ($0.id, $0) })
            for item in linked {
                mergedServices[item.id] = mergedServices[item.id] ?? item
            }
            self.services = mergedServices.values.sorted { lhs, rhs in
                lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func createReservation(
        vehicleId: Int,
        serviceId: Int,
        type: String,
        note: String,
        start: Date,
        token: String,
        role: String
    ) async {
        do {
            _ = try await service.createReservation(
                ReservationCreateRequest(
                    serviceId: serviceId,
                    vehicleId: vehicleId,
                    serviceType: type,
                    note: note.isEmpty ? nil : note,
                    startDatetime: start,
                    endDatetime: nil,
                    createdVia: "ios_app"
                ),
                token: token
            )
            await load(token: token, role: role)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func cancelReservation(reservationId: Int, token: String, role: String) async {
        do {
            _ = try await featureService.updateReservationStatus(reservationId: reservationId, status: "CANCELLED", token: token)
            await load(token: token, role: role)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func deleteReservation(reservationId: Int, token: String, role: String) async {
        do {
            try await featureService.deleteReservation(reservationId: reservationId, token: token)
            await load(token: token, role: role)
        } catch {
            self.error = error.localizedDescription
        }
    }
}
