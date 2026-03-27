import Foundation

@MainActor
final class ServiceRemindersViewModel: ObservableObject {
    @Published var reminders: [ServiceWorkspaceReminder] = []
    @Published var customers: [ServiceWorkspaceCustomer] = []
    @Published var selectedCustomerVehicles: [ServiceWorkspaceVehicle] = []
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
            async let remindersReq = service.fetchReminders(token: token)
            async let customersReq = service.fetchCustomers(token: token)
            reminders = try await remindersReq
            customers = try await customersReq
        } catch {
            self.error = error.localizedDescription
        }
    }

    func loadVehiclesForCustomer(customerId: Int, token: String) async {
        do {
            selectedCustomerVehicles = try await service.fetchCustomerVehicles(customerId: customerId, token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func createReminder(_ request: ServiceWorkspaceReminderCreateRequest, token: String) async {
        do {
            _ = try await service.createReminder(request, token: token)
            await load(token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func updateReminder(reminderId: Int, request: ServiceWorkspaceReminderUpdateRequest, token: String) async {
        do {
            _ = try await service.updateReminder(reminderId: reminderId, request: request, token: token)
            await load(token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func deleteReminder(reminderId: Int, token: String) async {
        do {
            try await service.deleteReminder(reminderId: reminderId, token: token)
            await load(token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }
}
