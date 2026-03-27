import SwiftUI

struct AccountView: View {
    @EnvironmentObject private var env: AppEnvironment
    @StateObject private var viewModel: AccountViewModel

    @State private var draftName = ""
    @State private var draftPhone = ""
    @State private var draftCity = ""

    @State private var currentPassword = ""
    @State private var newPassword = ""
    @State private var totpCode = ""
    @State private var totpDisableCode = ""
    @State private var totpDisablePassword = ""
    @State private var biometricPreferred = true
    @State private var supportSubject = ""
    @State private var supportMessage = ""
    @State private var customCategoryName = ""
    @State private var customCategoryIcon = "🧩"

    init() {
        let api = APIClient()
        _viewModel = StateObject(wrappedValue: AccountViewModel(service: AccountService(api: api), featureService: UserFeatureService(api: api)))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                    if viewModel.isLoading {
                        ProgressView()
                            .tint(.white)
                            .frame(maxWidth: .infinity)
                            .padding(.top, 60)
                    } else if let error = viewModel.error {
                        ErrorStateView(message: error) { Task { await reload() } }
                    } else {
                        profileHero
                        profileSection
                        licenseSection
                        recordConfigurationSection
                        securitySection
                        credentialsSection
                        supportSection
                        dataSection

                        Button("Odhlásit se") {
                            env.authManager.logout()
                        }
                        .buttonStyle(PrimaryActionButtonStyle())
                    }
                }
                .padding(Theme.Spacing.md)
                .padding(.bottom, Theme.Spacing.xxl + 24)
            }
            .hubPageBackground()
            .navigationTitle("Profil")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbarBackground(.hidden, for: .navigationBar)
            .task { await reload() }
        }
    }

    private var profileHero: some View {
        VStack(spacing: Theme.Spacing.sm) {
            Circle()
                .fill(
                    LinearGradient(
                        colors: [Theme.Colors.primary, Theme.Colors.accent],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: 84, height: 84)
                .overlay {
                    Text(profileInitials)
                        .font(.system(size: 28, weight: .bold, design: .default))
                        .foregroundStyle(Theme.Colors.textOnLight)
                }

            Text(draftName.isEmpty ? (viewModel.profile?.name ?? "Váš účet") : draftName)
                .font(Theme.Typography.sectionTitle)
                .foregroundStyle(.white)

            Text(viewModel.profile?.email ?? "")
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textSecondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, Theme.Spacing.sm)
    }

    private var profileSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Text("Účet")
                .font(Theme.Typography.cardTitle)
                .foregroundStyle(.white)

            TextField("Jméno", text: $draftName)
                .accountTextFieldStyle()
            TextField("Telefon", text: $draftPhone)
                .accountTextFieldStyle()
            TextField("Město", text: $draftCity)
                .accountTextFieldStyle()

            Button("Uložit profil") {
                guard let token = env.authManager.token else { return }
                Task {
                    await viewModel.updateProfile(name: draftName, phone: draftPhone, city: draftCity, token: token)
                    await env.authManager.refreshProfile()
                }
            }
            .buttonStyle(PrimaryActionButtonStyle())
        }
        .hubDarkCard()
    }

    private var licenseSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Text("Licence")
                .font(Theme.Typography.cardTitle)
                .foregroundStyle(.white)

            licenseLine(title: "Plán", value: viewModel.license?.plan.uppercased() ?? "-")
            licenseLine(title: "Stav", value: viewModel.license?.status ?? "-")
            licenseLine(
                title: "Vozidla",
                value: "\(viewModel.license?.vehiclesCurrent ?? 0) / \(viewModel.license?.isUnlimited == true ? "∞" : "\(viewModel.license?.vehiclesLimit ?? 0)")"
            )
        }
        .hubDarkCard()
    }

    private var securitySection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Text("Zabezpečení")
                .font(Theme.Typography.cardTitle)
                .foregroundStyle(.white)

            licenseLine(title: "2FA", value: viewModel.security?.twoFactorEnabled == true ? "Aktivní" : "Neaktivní")
            licenseLine(title: "Biometrie", value: viewModel.security?.biometricEnabled == true ? "Povolena" : "Zakázána")

            Toggle("Biometrie preferovaná", isOn: $biometricPreferred)
                .toggleStyle(.switch)
                .tint(Theme.Colors.primary)
                .foregroundStyle(.white)
                .onAppear {
                    biometricPreferred = viewModel.security?.biometricPreferred ?? true
                }

            HStack(spacing: Theme.Spacing.sm) {
                Button("Zapnout biometrii") {
                    guard let token = env.authManager.token else { return }
                    Task { await viewModel.updateBiometric(enabled: true, preferred: biometricPreferred, token: token) }
                }
                .buttonStyle(PrimaryActionButtonStyle())

                Button("Vypnout") {
                    guard let token = env.authManager.token else { return }
                    Task { await viewModel.updateBiometric(enabled: false, preferred: false, token: token) }
                }
                .buttonStyle(SecondaryActionButtonStyle())
            }

            Divider().overlay(Theme.Colors.hairline)

            Text("Dvoufázové ověření (TOTP)")
                .font(Theme.Typography.bodyStrong)
                .foregroundStyle(.white)

            Button("Vygenerovat 2FA klíč") {
                guard let token = env.authManager.token else { return }
                Task { await viewModel.setupTotp(token: token) }
            }
            .buttonStyle(PrimaryActionButtonStyle())

            if let setup = viewModel.totpSetup {
                Text("Secret: \(setup.secret)")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colors.textSecondary)
                    .textSelection(.enabled)

                Text("URI: \(setup.otpauthUri)")
                    .font(Theme.Typography.tiny)
                    .foregroundStyle(Theme.Colors.textSecondary)
                    .textSelection(.enabled)
            }

            SecureField("2FA kód pro aktivaci", text: $totpCode)
                .accountTextFieldStyle()

            Button("Aktivovat 2FA") {
                guard let token = env.authManager.token else { return }
                Task { await viewModel.enableTotp(code: totpCode, token: token) }
            }
            .buttonStyle(PrimaryActionButtonStyle())

            SecureField("Současné heslo (pro vypnutí 2FA)", text: $totpDisablePassword)
                .accountTextFieldStyle()

            SecureField("2FA kód pro vypnutí", text: $totpDisableCode)
                .accountTextFieldStyle()

            Button("Vypnout 2FA") {
                guard let token = env.authManager.token else { return }
                Task {
                    await viewModel.disableTotp(
                        currentPassword: totpDisablePassword,
                        code: totpDisableCode,
                        token: token
                    )
                }
            }
            .buttonStyle(SecondaryActionButtonStyle())

            if let message = viewModel.securityActionMessage {
                Text(message)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colors.textSecondary)
            }
        }
        .hubDarkCard()
    }

    private var recordConfigurationSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Text("Konfigurace záznamů")
                .font(Theme.Typography.cardTitle)
                .foregroundStyle(.white)

            Text("Vlastní kategorie a uložené šablony pro režim Nový záznam.")
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textSecondary)

            VStack(spacing: Theme.Spacing.sm) {
                HStack(spacing: Theme.Spacing.sm) {
                    TextField("Ikona", text: $customCategoryIcon)
                        .accountTextFieldStyle()
                        .frame(width: 84)

                    TextField("Nová kategorie", text: $customCategoryName)
                        .accountTextFieldStyle()
                }

                Button("Přidat kategorii") {
                    env.recordConfigurationStore.addCategory(
                        label: customCategoryName,
                        icon: customCategoryIcon.isEmpty ? "🧩" : customCategoryIcon
                    )
                    customCategoryName = ""
                    customCategoryIcon = "🧩"
                }
                .buttonStyle(SecondaryActionButtonStyle())
                .disabled(customCategoryName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }

            if !env.recordConfigurationStore.customCategories.isEmpty {
                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    Text("Moje kategorie")
                        .font(Theme.Typography.captionStrong)
                        .foregroundStyle(.white)

                    ForEach(env.recordConfigurationStore.customCategories) { category in
                        HStack(spacing: Theme.Spacing.sm) {
                            Text(category.icon)
                                .font(.system(size: 20))
                                .frame(width: 36, height: 36)
                                .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))

                            VStack(alignment: .leading, spacing: 2) {
                                Text(category.label)
                                    .font(Theme.Typography.bodyStrong)
                                    .foregroundStyle(.white)
                                Text(category.id)
                                    .font(Theme.Typography.tiny)
                                    .foregroundStyle(Theme.Colors.textSecondary)
                            }

                            Spacer()

                            Button(role: .destructive) {
                                env.recordConfigurationStore.deleteCategory(id: category.id)
                            } label: {
                                Image(systemName: "trash")
                            }
                            .buttonStyle(.plain)
                            .foregroundStyle(Theme.Colors.danger)
                        }
                        .padding(Theme.Spacing.sm)
                        .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
                    }
                }
            }

            if !env.recordConfigurationStore.customTemplates.isEmpty {
                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    Text("Moje šablony")
                        .font(Theme.Typography.captionStrong)
                        .foregroundStyle(.white)

                    ForEach(env.recordConfigurationStore.customTemplates) { template in
                        HStack(spacing: Theme.Spacing.sm) {
                            Text(template.icon)
                                .font(.system(size: 20))
                                .frame(width: 36, height: 36)
                                .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))

                            VStack(alignment: .leading, spacing: 2) {
                                Text(template.name)
                                    .font(Theme.Typography.bodyStrong)
                                    .foregroundStyle(.white)
                                Text(template.templateDescription ?? "Bez popisu")
                                    .font(Theme.Typography.tiny)
                                    .foregroundStyle(Theme.Colors.textSecondary)
                                    .lineLimit(2)
                            }

                            Spacer()

                            Button(role: .destructive) {
                                env.recordConfigurationStore.deleteTemplate(template)
                            } label: {
                                Image(systemName: "trash")
                            }
                            .buttonStyle(.plain)
                            .foregroundStyle(Theme.Colors.danger)
                        }
                        .padding(Theme.Spacing.sm)
                        .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
                    }
                }
            }
        }
        .hubDarkCard()
    }

    private var credentialsSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Text("Heslo")
                .font(Theme.Typography.cardTitle)
                .foregroundStyle(.white)

            SecureField("Současné heslo", text: $currentPassword)
                .accountTextFieldStyle()
            SecureField("Nové heslo", text: $newPassword)
                .accountTextFieldStyle()

            Button("Změnit heslo") {
                guard let token = env.authManager.token else { return }
                Task { await viewModel.changePassword(current: currentPassword, new: newPassword, token: token) }
            }
            .buttonStyle(PrimaryActionButtonStyle())
        }
        .hubDarkCard()
    }

    private var supportSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Text("Podpora")
                .font(Theme.Typography.cardTitle)
                .foregroundStyle(.white)

            TextField("Předmět", text: $supportSubject)
                .accountTextFieldStyle()

            TextField("Zpráva", text: $supportMessage, axis: .vertical)
                .lineLimit(3...6)
                .accountTextFieldStyle()

            Button("Odeslat na podporu") {
                guard let token = env.authManager.token else { return }
                Task {
                    await viewModel.sendSupport(
                        category: "obecne",
                        subject: supportSubject,
                        message: supportMessage,
                        phone: draftPhone,
                        token: token
                    )
                }
            }
            .buttonStyle(PrimaryActionButtonStyle())
        }
        .hubDarkCard()
    }

    private var dataSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Text("Data")
                .font(Theme.Typography.cardTitle)
                .foregroundStyle(.white)

            Button("Stáhnout export dat") {
                guard let token = env.authManager.token else { return }
                Task { await viewModel.downloadExport(token: token) }
            }
            .buttonStyle(PrimaryActionButtonStyle())

            if let exportURL = viewModel.exportURL {
                ShareLink(item: exportURL) {
                    Text("Sdílet export")
                        .font(Theme.Typography.captionStrong)
                        .foregroundStyle(.white)
                }
            }

            Button("Smazat účet") {
                guard let token = env.authManager.token else { return }
                Task {
                    await viewModel.deleteAccount(password: currentPassword, token: token)
                    env.authManager.logout()
                }
            }
            .buttonStyle(SecondaryActionButtonStyle())
        }
        .hubDarkCard()
    }

    private var profileInitials: String {
        let source = (draftName.isEmpty ? (viewModel.profile?.name ?? "TU") : draftName)
        let parts = source
            .split(separator: " ")
            .prefix(2)
            .map { String($0.prefix(1)).uppercased() }
            .joined()

        return parts.isEmpty ? "TU" : parts
    }

    private func licenseLine(title: String, value: String) -> some View {
        HStack {
            Text(title)
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textSecondary)
            Spacer()
            Text(value)
                .font(Theme.Typography.captionStrong)
                .foregroundStyle(.white)
        }
    }

    private func reload() async {
        guard let token = env.authManager.token else { return }
        await viewModel.load(token: token)
        draftName = viewModel.profile?.name ?? ""
        draftPhone = viewModel.profile?.phone ?? ""
        draftCity = viewModel.profile?.city ?? ""
    }
}

private struct AccountTextFieldModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .font(Theme.Typography.body)
            .foregroundStyle(.white)
            .padding(.horizontal, Theme.Spacing.sm)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous)
                    .fill(Theme.Colors.elevated)
            )
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous)
                    .stroke(Theme.Colors.hairline, lineWidth: 1)
            )
    }
}

private extension View {
    func accountTextFieldStyle() -> some View {
        modifier(AccountTextFieldModifier())
    }
}
