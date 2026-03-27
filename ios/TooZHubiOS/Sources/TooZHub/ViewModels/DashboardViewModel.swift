import Foundation

@MainActor
final class DashboardViewModel: ObservableObject {
    @Published var isLoading = false
    @Published var error: String?
    @Published var vehicles: [Vehicle] = []
    @Published var reminders: [Reminder] = []
    @Published var analytics: AnalyticsSummary?
    @Published var monthlyCosts: [MonthlyCostEntry] = []
    @Published var notifications: [SystemNotification] = []

    private let service: DashboardService

    init(service: DashboardService) {
        self.service = service
    }

    func load(token: String) async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        do {
            let payload = try await service.loadDashboard(token: token)
            vehicles = payload.vehicles
            reminders = payload.reminders
            analytics = payload.analytics
            monthlyCosts = payload.monthlyCosts.entries
            notifications = payload.notifications
        } catch {
            self.error = error.localizedDescription
        }
    }
}
