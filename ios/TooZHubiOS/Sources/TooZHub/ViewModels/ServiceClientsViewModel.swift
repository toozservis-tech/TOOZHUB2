import Foundation

@MainActor
final class ServiceClientsViewModel: ObservableObject {
    @Published var customers: [ServiceWorkspaceCustomer] = []
    @Published var selectedCustomerVehicles: [ServiceWorkspaceVehicle] = []
    @Published var selectedCustomerId: Int?
    @Published var isLoading = false
    @Published var error: String?

    private let service: ServiceWorkspaceService

    init(service: ServiceWorkspaceService) {
        self.service = service
    }

    func load(token: String) async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        do {
            customers = try await service.fetchCustomers(token: token)
            if selectedCustomerId == nil {
                selectedCustomerId = customers.first?.customerId
            }
            if let selectedCustomerId {
                selectedCustomerVehicles = try await service.fetchCustomerVehicles(customerId: selectedCustomerId, token: token)
            } else {
                selectedCustomerVehicles = []
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func selectCustomer(_ customerId: Int, token: String) async {
        selectedCustomerId = customerId
        do {
            selectedCustomerVehicles = try await service.fetchCustomerVehicles(customerId: customerId, token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }
}
