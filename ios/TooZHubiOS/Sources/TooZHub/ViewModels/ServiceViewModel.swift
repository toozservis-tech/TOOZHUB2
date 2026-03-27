import Foundation

@MainActor
final class ServiceViewModel: ObservableObject {
    @Published var reminders: [Reminder] = []
    @Published var servicesDiscovery: [ServiceContact] = []
    @Published var myContacts: [ServiceContact] = []
    @Published var accessGrants: [VehicleAccessGrant] = []
    @Published var reminderSettings: ReminderSettings?
    @Published var isLoading = false
    @Published var error: String?

    private let api: APIClient
    private let featureService: UserFeatureService

    init(api: APIClient, featureService: UserFeatureService) {
        self.api = api
        self.featureService = featureService
    }

    func load(token: String) async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        async let remindersReq: [Reminder] = api.request(.get("/api/v1/reminders"), token: token)
        async let discoveryReq = featureService.fetchServiceDiscovery(token: token)
        async let contactsReq = featureService.fetchMyServiceContacts(token: token)
        async let grantsReq = featureService.fetchVehicleAccessGrants(token: token)
        async let settingsReq = featureService.fetchReminderSettings(token: token)

        var loadErrors: [String] = []

        do {
            self.reminders = try await remindersReq
        } catch {
            self.reminders = []
            loadErrors.append(error.localizedDescription)
        }

        do {
            self.servicesDiscovery = try await discoveryReq.services
        } catch {
            self.servicesDiscovery = []
            loadErrors.append(error.localizedDescription)
        }

        do {
            self.myContacts = try await contactsReq.services
        } catch {
            self.myContacts = []
            loadErrors.append(error.localizedDescription)
        }

        do {
            self.accessGrants = try await grantsReq.grants
        } catch {
            self.accessGrants = []
            loadErrors.append(error.localizedDescription)
        }

        do {
            self.reminderSettings = try await settingsReq
        } catch {
            self.reminderSettings = nil
            loadErrors.append(error.localizedDescription)
        }

        let hasAnyData =
            !reminders.isEmpty ||
            !servicesDiscovery.isEmpty ||
            !myContacts.isEmpty ||
            !accessGrants.isEmpty

        if !hasAnyData, let first = loadErrors.first {
            self.error = first
        } else {
            self.error = nil
        }
    }

    func createReminder(_ request: ReminderCreateRequest, token: String) async {
        do {
            _ = try await featureService.createReminder(request, token: token)
            await load(token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func updateReminder(id: Int, _ request: ReminderUpdateRequest, token: String) async {
        do {
            _ = try await featureService.updateReminder(id: id, request, token: token)
            await load(token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func deleteReminder(id: Int, token: String) async {
        do {
            try await featureService.deleteReminder(id: id, token: token)
            await load(token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func updateReminderSettings(notificationMethod: String, daysBefore: Int, token: String) async {
        do {
            _ = try await featureService.updateReminderSettings(
                ReminderSettingsUpdateRequest(
                    enabled: reminderSettings?.enabled ?? true,
                    notification: ReminderNotificationSettingsUpdateRequest(
                        notificationMethod: notificationMethod,
                        notifyDaysBefore: daysBefore
                    )
                ),
                token: token
            )
            await load(token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func grantVehicleAccess(vehicleId: Int, serviceId: Int, token: String) async {
        do {
            try await featureService.grantVehicleAccess(
                VehicleAccessGrantRequest(vehicleId: vehicleId, serviceId: serviceId, note: nil, conflictStrategy: "keep"),
                token: token
            )
            await load(token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func revokeVehicleAccess(serviceId: Int, vehicleId: Int, token: String) async {
        do {
            try await featureService.revokeVehicleAccess(serviceId: serviceId, vehicleId: vehicleId, token: token)
            await load(token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func disconnectService(serviceId: Int, token: String) async {
        do {
            try await featureService.disconnectService(serviceId: serviceId, token: token)
            await load(token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }
}
