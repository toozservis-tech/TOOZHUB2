import Foundation

final class ServiceWorkspaceService {
    private let api: APIClient

    init(api: APIClient) {
        self.api = api
    }

    func fetchCustomers(token: String) async throws -> [ServiceWorkspaceCustomer] {
        try await api.request(.get("/api/v1/services/workspace/customers"), token: token)
    }

    func fetchCustomerVehicles(customerId: Int, token: String) async throws -> [ServiceWorkspaceVehicle] {
        try await api.request(.get("/api/v1/services/workspace/customers/\(customerId)/vehicles"), token: token)
    }

    func createCustomerVehicle(customerId: Int, request: ServiceWorkspaceVehicleCreateRequest, token: String) async throws {
        let body = try api.encodeBody(request)
        try await api.requestNoContent(.post("/api/v1/services/workspace/customers/\(customerId)/vehicles", body: body), token: token)
    }

    func fetchReminders(token: String) async throws -> [ServiceWorkspaceReminder] {
        try await api.request(
            .get(
                "/api/v1/services/workspace/reminders",
                queryItems: [
                    URLQueryItem(name: "include_completed", value: "true"),
                    URLQueryItem(name: "limit", value: "200")
                ]
            ),
            token: token
        )
    }

    func createReminder(_ request: ServiceWorkspaceReminderCreateRequest, token: String) async throws -> ServiceWorkspaceReminder {
        let body = try api.encodeBody(request)
        return try await api.request(.post("/api/v1/services/workspace/reminders", body: body), token: token)
    }

    func updateReminder(reminderId: Int, request: ServiceWorkspaceReminderUpdateRequest, token: String) async throws -> ServiceWorkspaceReminder {
        let body = try api.encodeBody(request)
        return try await api.request(.put("/api/v1/services/workspace/reminders/\(reminderId)", body: body), token: token)
    }

    func deleteReminder(reminderId: Int, token: String) async throws {
        try await api.requestNoContent(.delete("/api/v1/services/workspace/reminders/\(reminderId)"), token: token)
    }
}
