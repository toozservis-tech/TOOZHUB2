import Foundation

struct DashboardPayload {
    let vehicles: [Vehicle]
    let reminders: [Reminder]
    let analytics: AnalyticsSummary
    let monthlyCosts: MonthlyCosts
    let notifications: [SystemNotification]
}

final class DashboardService {
    private let api: APIClient

    init(api: APIClient) {
        self.api = api
    }

    func loadDashboard(token: String) async throws -> DashboardPayload {
        async let vehicles: [Vehicle] = api.request(.get("/api/v1/vehicles"), token: token)
        async let reminders: [Reminder] = api.request(.get("/api/v1/reminders"), token: token)
        async let summary: AnalyticsSummary = api.request(.get("/api/v1/analytics/summary"), token: token)
        async let monthly: MonthlyCosts = api.request(.get("/api/v1/analytics/monthly-costs", queryItems: [URLQueryItem(name: "months", value: "6")]), token: token)
        async let notificationsPayload: SystemNotificationsResponse = api.request(
            .get("/api/v1/system-notifications", queryItems: [URLQueryItem(name: "limit", value: "20")]),
            token: token
        )
        let notifications = try await notificationsPayload.items
        return try await DashboardPayload(
            vehicles: vehicles,
            reminders: reminders,
            analytics: summary,
            monthlyCosts: monthly,
            notifications: notifications
        )
    }
}
