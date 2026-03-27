import Foundation

@MainActor
final class AccountViewModel: ObservableObject {
    @Published var profile: UserProfile?
    @Published var security: SecuritySettingsResponse?
    @Published var license: LicenseStatus?
    @Published var exportURL: URL?
    @Published var isLoading = false
    @Published var error: String?
    @Published var securityActionMessage: String?
    @Published var totpSetup: TotpSetupResponse?

    private let service: AccountService
    private let featureService: UserFeatureService

    init(service: AccountService, featureService: UserFeatureService) {
        self.service = service
        self.featureService = featureService
    }

    func load(token: String) async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        do {
            async let profile = service.fetchProfile(token: token)
            async let security = service.fetchSecuritySettings(token: token)
            async let license = service.fetchLicense(token: token)

            self.profile = try await profile
            self.security = try await security
            self.license = try await license
        } catch {
            self.error = error.localizedDescription
        }
    }

    func setupTotp(token: String) async {
        error = nil
        securityActionMessage = nil
        do {
            let payload = try await service.setupTotp(token: token)
            totpSetup = payload
            securityActionMessage = payload.message
            await load(token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func enableTotp(code: String, token: String) async {
        error = nil
        securityActionMessage = nil
        do {
            let response = try await service.enableTotp(code: code, token: token)
            securityActionMessage = response.message
            await load(token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func disableTotp(currentPassword: String, code: String, token: String) async {
        error = nil
        securityActionMessage = nil
        do {
            let response = try await service.disableTotp(currentPassword: currentPassword, code: code, token: token)
            securityActionMessage = response.message
            totpSetup = nil
            await load(token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func updateBiometric(enabled: Bool, preferred: Bool?, token: String) async {
        error = nil
        securityActionMessage = nil
        do {
            let response = try await service.updateBiometricPreference(enabled: enabled, preferred: preferred, token: token)
            securityActionMessage = response.message
            await load(token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func updateProfile(name: String, phone: String, city: String, token: String) async {
        do {
            profile = try await service.updateProfile(
                UserUpdateRequest(name: name, phone: phone, city: city, street: nil, streetNumber: nil, zip: nil),
                token: token
            )
        } catch {
            self.error = error.localizedDescription
        }
    }

    func changePassword(current: String, new: String, token: String) async {
        do {
            try await featureService.changePassword(ChangePasswordRequest(currentPassword: current, newPassword: new), token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func sendSupport(category: String, subject: String, message: String, phone: String?, token: String) async {
        do {
            try await featureService.sendSupport(
                SupportRequest(
                    category: category,
                    subject: subject,
                    message: message,
                    phone: phone,
                    includeDiagnostics: true,
                    pageUrl: nil,
                    userAgent: nil
                ),
                token: token
            )
        } catch {
            self.error = error.localizedDescription
        }
    }

    func downloadExport(token: String) async {
        do {
            exportURL = try await featureService.downloadExport(token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func deleteAccount(password: String, token: String) async {
        do {
            try await featureService.deleteAccount(
                DeleteAccountRequest(currentPassword: password, confirmationText: "SMAZAT UCET", exportDownloaded: true),
                token: token
            )
        } catch {
            self.error = error.localizedDescription
        }
    }
}
