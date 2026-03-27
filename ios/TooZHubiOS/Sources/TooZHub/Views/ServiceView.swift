import SwiftUI

struct ServiceView: View {
    enum Mode: String, CaseIterable, Identifiable {
        case reminders = "Připomínky"
        case services = "Servisy"

        var id: String { rawValue }

        var icon: String {
            switch self {
            case .reminders:
                return "bell.badge"
            case .services:
                return "wrench.and.screwdriver"
            }
        }
    }

    @EnvironmentObject private var env: AppEnvironment
    @StateObject private var viewModel: ServiceViewModel
    @State private var mode: Mode = .reminders
    @State private var vehicles: [Vehicle] = []
    @State private var showAddReminder = false
    @State private var selectedVehicleIdForGrant: Int = 0
    @State private var selectedServiceDetail: ServiceContact?

    init() {
        let api = APIClient()
        _viewModel = StateObject(wrappedValue: ServiceViewModel(api: api, featureService: UserFeatureService(api: api)))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                    HStack(alignment: .center) {
                        Text("Připomínky, přístupy a servisní kontakty")
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.textSecondary)
                        Spacer()
                        PillBadge(title: mode.rawValue, style: .success)
                    }

                    modeSwitch

                    if viewModel.isLoading {
                        ProgressView()
                            .tint(.white)
                            .frame(maxWidth: .infinity)
                            .padding(.top, 40)
                    } else if let error = viewModel.error {
                        ErrorStateView(message: error) { Task { await reload() } }
                    } else {
                        if mode == .reminders {
                            remindersContent
                        } else {
                            servicesContent
                        }
                    }
                }
                .padding(Theme.Spacing.md)
                .padding(.bottom, Theme.Spacing.xxl + 20)
            }
            .hubPageBackground()
            .navigationTitle("Servis")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbar {
                if mode == .reminders {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button {
                            showAddReminder = true
                        } label: {
                            Image(systemName: "plus")
                                .font(.headline.bold())
                                .foregroundStyle(Theme.Colors.textOnLight)
                                .frame(width: 34, height: 34)
                                .background(Theme.Colors.primary, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                        }
                    }
                }
            }
            .sheet(isPresented: $showAddReminder) {
                AddReminderSheet(vehicles: vehicles) { request in
                    guard let token = env.authManager.token else { return }
                    Task { await viewModel.createReminder(request, token: token) }
                }
            }
            .navigationDestination(item: $selectedServiceDetail) { service in
                ServiceContactDetailView(service: service)
            }
            .task { await reload() }
            .refreshable { await reload() }
        }
    }

    private var modeSwitch: some View {
        HStack(spacing: Theme.Spacing.sm) {
            ForEach(Mode.allCases) { option in
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        mode = option
                    }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: option.icon)
                        Text(option.rawValue)
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(InlineChipButtonStyle(isSelected: mode == option))
            }
        }
    }

    private var remindersContent: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            reminderSettingsCard

            if viewModel.reminders.isEmpty {
                EmptyStateView(
                    icon: "bell.slash",
                    title: "Bez připomínek",
                    subtitle: "Nemáte žádné aktivní připomínky.",
                    actionTitle: "Přidat připomínku"
                ) {
                    showAddReminder = true
                }
            } else {
                ForEach(viewModel.reminders, id: \.self) { reminder in
                    VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                        TimelineRow(
                            title: reminder.text,
                            subtitle: reminder.vehicleName ?? "Obecná položka",
                            date: reminder.dueDate,
                            color: reminder.isCompleted == true ? Theme.Colors.primary : Theme.Colors.warning
                        )

                        HStack(spacing: Theme.Spacing.sm) {
                            Button(reminder.isCompleted == true ? "Označit aktivní" : "Dokončit") {
                                guard let token = env.authManager.token, let id = reminder.id else { return }
                                Task {
                                    await viewModel.updateReminder(
                                        id: id,
                                        ReminderUpdateRequest(
                                            type: nil,
                                            vehicleId: reminder.vehicleId,
                                            text: reminder.text,
                                            dueDate: reminder.dueDate.map { date in
                                                let formatter = DateFormatter()
                                                formatter.locale = Locale(identifier: "en_US_POSIX")
                                                formatter.timeZone = TimeZone(secondsFromGMT: 0)
                                                formatter.dateFormat = "yyyy-MM-dd"
                                                return formatter.string(from: date)
                                            },
                                            notifyAt: reminder.notifyAt,
                                            notificationMethod: reminder.notificationMethod,
                                            isCompleted: !(reminder.isCompleted ?? false)
                                        ),
                                        token: token
                                    )
                                }
                            }
                            .buttonStyle(InlineChipButtonStyle(isSelected: reminder.isCompleted == true))

                            if let id = reminder.id {
                                Button("Smazat") {
                                    guard let token = env.authManager.token else { return }
                                    Task { await viewModel.deleteReminder(id: id, token: token) }
                                }
                                .buttonStyle(InlineChipButtonStyle(isSelected: false))
                            }
                        }
                    }
                    .hubDarkCard()
                }
            }
        }
    }

    private var reminderSettingsCard: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Text("Nastavení připomínek")
                .font(Theme.Typography.headline)
                .foregroundStyle(.white)

            Text("Kanál: \(viewModel.reminderSettings?.notification.notificationMethod ?? "app")")
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textSecondary)

            HStack(spacing: Theme.Spacing.sm) {
                Button("App") { updateNotification(method: "app") }
                    .buttonStyle(InlineChipButtonStyle(isSelected: viewModel.reminderSettings?.notification.notificationMethod == "app"))
                Button("Email") { updateNotification(method: "email") }
                    .buttonStyle(InlineChipButtonStyle(isSelected: viewModel.reminderSettings?.notification.notificationMethod == "email"))
                Button("Both") { updateNotification(method: "both") }
                    .buttonStyle(InlineChipButtonStyle(isSelected: viewModel.reminderSettings?.notification.notificationMethod == "both"))
            }

            Text("Předstih: \(viewModel.reminderSettings?.notification.notifyDaysBefore ?? 7) dní")
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textSecondary)
        }
        .hubDarkCard()
    }

    private var servicesContent: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            if viewModel.servicesDiscovery.isEmpty {
                EmptyStateView(icon: "building.2", title: "Žádné servisy", subtitle: "Katalog servisů je zatím prázdný.")
            } else {
                SectionHeader(title: "Katalog servisů", subtitle: "Vyberte servis a připojte vozidlo")

                ForEach(viewModel.servicesDiscovery) { service in
                    VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                        Button {
                            selectedServiceDetail = service
                        } label: {
                            HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(service.name)
                                        .font(Theme.Typography.headline)
                                        .foregroundStyle(Theme.Colors.textOnLight)
                                        .multilineTextAlignment(.leading)

                                    Text(service.discoverySubtitle)
                                        .font(Theme.Typography.caption)
                                        .foregroundStyle(Theme.Colors.textOnLightSecondary)
                                        .multilineTextAlignment(.leading)
                                }

                                Spacer(minLength: Theme.Spacing.sm)

                                Image(systemName: "chevron.right")
                                    .font(.caption.weight(.bold))
                                    .foregroundStyle(Theme.Colors.textOnLightSecondary)
                                    .padding(.top, 4)
                            }
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)

                        if let distance = service.distanceKm {
                            Text("Vzdálenost: \(distance, specifier: "%.1f") km")
                                .font(Theme.Typography.caption)
                                .foregroundStyle(Theme.Colors.textOnLightSecondary)
                        }

                        if !vehicles.isEmpty {
                            Picker("Vozidlo", selection: $selectedVehicleIdForGrant) {
                                ForEach(vehicles) { v in
                                    Text(v.displayName).tag(v.id)
                                }
                            }
                            .pickerStyle(.menu)

                            Button("Povolit přístup k vozidlu") {
                                guard let token = env.authManager.token else { return }
                                Task {
                                    await viewModel.grantVehicleAccess(
                                        vehicleId: selectedVehicleIdForGrant,
                                        serviceId: service.id,
                                        token: token
                                    )
                                }
                            }
                            .buttonStyle(PrimaryActionButtonStyle())
                        }
                    }
                    .hubLightCard()
                }
            }

            if !viewModel.myContacts.isEmpty {
                SectionHeader(title: "Moje servisní kontakty")

                ForEach(viewModel.myContacts) { service in
                    VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                        Button {
                            selectedServiceDetail = service
                        } label: {
                            HStack(spacing: Theme.Spacing.sm) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(service.name)
                                        .font(Theme.Typography.bodyStrong)
                                        .foregroundStyle(Theme.Colors.textOnLight)
                                    Text(service.discoverySubtitle)
                                        .font(Theme.Typography.caption)
                                        .foregroundStyle(Theme.Colors.textOnLightSecondary)
                                        .multilineTextAlignment(.leading)
                                }

                                Spacer()

                                Image(systemName: "chevron.right")
                                    .font(.caption.weight(.bold))
                                    .foregroundStyle(Theme.Colors.textOnLightSecondary)
                            }
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)

                        Button("Odpojit") {
                            guard let token = env.authManager.token else { return }
                            Task { await viewModel.disconnectService(serviceId: service.id, token: token) }
                        }
                        .buttonStyle(InlineChipButtonStyle(isSelected: false))
                    }
                    .hubLightCard()
                }
            }

            if !viewModel.accessGrants.isEmpty {
                SectionHeader(title: "Povolené přístupy")

                ForEach(viewModel.accessGrants) { grant in
                    HStack(spacing: Theme.Spacing.sm) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(grant.serviceName)
                                .font(Theme.Typography.bodyStrong)
                                .foregroundStyle(Theme.Colors.textOnLight)
                            Text("Vozidlo #\(grant.vehicleId)")
                                .font(Theme.Typography.caption)
                                .foregroundStyle(Theme.Colors.textOnLightSecondary)
                        }

                        Spacer()

                        Button("Odebrat") {
                            guard let token = env.authManager.token else { return }
                            Task {
                                await viewModel.revokeVehicleAccess(
                                    serviceId: grant.serviceId,
                                    vehicleId: grant.vehicleId,
                                    token: token
                                )
                            }
                        }
                        .buttonStyle(InlineChipButtonStyle(isSelected: false))
                    }
                    .hubLightCard()
                }
            }
        }
    }

    private func updateNotification(method: String) {
        guard let token = env.authManager.token else { return }
        Task {
            await viewModel.updateReminderSettings(
                notificationMethod: method,
                daysBefore: viewModel.reminderSettings?.notification.notifyDaysBefore ?? 7,
                token: token
            )
        }
    }

    private func reload() async {
        guard let token = env.authManager.token else { return }
        await viewModel.load(token: token)

        do {
            vehicles = try await env.vehicleService.fetchVehicles(token: token)
            selectedVehicleIdForGrant = vehicles.first?.id ?? 0
        } catch {
            viewModel.error = error.localizedDescription
        }
    }
}

struct AddReminderSheet: View {
    let vehicles: [Vehicle]
    let onSubmit: (ReminderCreateRequest) -> Void
    @Environment(\.dismiss) private var dismiss

    @State private var text = ""
    @State private var type = "VLASTNI"
    @State private var dueDate = Date().addingTimeInterval(7 * 24 * 3600)
    @State private var vehicleId: Int = 0

    var body: some View {
        NavigationStack {
            Form {
                TextField("Text připomínky", text: $text)
                TextField("Typ", text: $type)
                DatePicker("Termín", selection: $dueDate, displayedComponents: .date)
                Picker("Vozidlo", selection: $vehicleId) {
                    Text("Obecná").tag(0)
                    ForEach(vehicles) { vehicle in
                        Text(vehicle.displayName).tag(vehicle.id)
                    }
                }
            }
            .navigationTitle("Nová připomínka")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Zrušit") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Uložit") {
                        let formatter = DateFormatter()
                        formatter.locale = Locale(identifier: "en_US_POSIX")
                        formatter.timeZone = TimeZone(secondsFromGMT: 0)
                        formatter.dateFormat = "yyyy-MM-dd"
                        onSubmit(
                            ReminderCreateRequest(
                                vehicleId: vehicleId == 0 ? nil : vehicleId,
                                type: type,
                                text: text,
                                dueDate: formatter.string(from: dueDate),
                                notifyAt: nil,
                                notificationMethod: nil,
                                repeatCount: 0,
                                repeatIntervalDays: 0
                            )
                        )
                        dismiss()
                    }
                    .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).count < 3)
                }
            }
            .onAppear {
                vehicleId = vehicles.first?.id ?? 0
            }
        }
    }
}

private struct ServiceContactDetailView: View {
    let service: ServiceContact
    @Environment(\.openURL) private var openURL

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                heroCard

                if quickActionsAvailable {
                    VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                        SectionHeader(title: "Rychlé akce", subtitle: "Kontaktujte servis nebo otevřete lokaci")

                        VStack(spacing: Theme.Spacing.sm) {
                            if let phoneURL {
                                quickActionButton("Zavolat", icon: "phone.fill", tint: Theme.Colors.primary) {
                                    openURL(phoneURL)
                                }
                            }
                            if let mailURL {
                                quickActionButton("Napsat email", icon: "envelope.fill", tint: Theme.Colors.accent) {
                                    openURL(mailURL)
                                }
                            }
                            if let mapsURL {
                                quickActionButton("Otevřít v Mapách", icon: "map.fill", tint: Theme.Colors.primaryDark) {
                                    openURL(mapsURL)
                                }
                            }
                        }
                    }
                }

                VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                    SectionHeader(title: "Kontaktní údaje", subtitle: "Detail servisního partnera")

                    detailRow(title: "Název", value: service.name)
                    detailRow(title: "Email", value: service.email.trimmedNonEmpty ?? "Neuvedeno")
                    detailRow(title: "Telefon", value: service.phone.nonEmptyFallback("Neuvedeno"))
                    detailRow(title: "Město", value: service.city.nonEmptyFallback("Neuvedeno"))
                    detailRow(title: "Adresa", value: service.fullAddress.nonEmptyFallback("Neuvedeno"))
                    detailRow(title: "IČO", value: service.ico.nonEmptyFallback("Neuvedeno"))
                    if let distance = service.distanceKm {
                        detailRow(title: "Vzdálenost", value: String(format: "%.1f km", distance))
                    }
                    detailRow(title: "Sdílená vozidla", value: "\(service.sharedVehiclesCount)")
                    detailRow(title: "Propojeno", value: service.isLinked ? "Ano" : "Ne")
                }
                .hubDarkCard()
            }
            .padding(Theme.Spacing.md)
            .padding(.bottom, Theme.Spacing.xxl + 20)
        }
        .hubPageBackground()
        .navigationTitle("Detail servisu")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .toolbarBackground(.hidden, for: .navigationBar)
    }

    private var heroCard: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.md) {
            HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(service.name)
                        .font(Theme.Typography.cardTitle)
                        .foregroundStyle(.white)
                    Text(service.discoverySubtitle)
                        .font(Theme.Typography.body)
                        .foregroundStyle(Theme.Colors.textSecondary)
                }
                Spacer(minLength: Theme.Spacing.sm)
                if service.isLinked {
                    PillBadge(title: "Propojeno", style: .success)
                }
            }

            HStack(spacing: Theme.Spacing.sm) {
                contactStat(title: "Město", value: service.city.nonEmptyFallback("—"), icon: "building.2.fill")
                contactStat(title: "Kontakt", value: service.phone.nonEmptyFallback(service.email.trimmedNonEmpty ?? "—"), icon: "phone.fill")
            }
        }
        .hubDarkCard()
    }

    private var quickActionsAvailable: Bool {
        phoneURL != nil || mailURL != nil || mapsURL != nil
    }

    private var phoneURL: URL? {
        guard let phone = service.phone?.digitsAndPhoneSymbolsOnly, !phone.isEmpty else { return nil }
        return URL(string: "tel://\(phone)")
    }

    private var mailURL: URL? {
        guard let email = service.email.trimmedNonEmpty?.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) else { return nil }
        return URL(string: "mailto:\(email)")
    }

    private var mapsURL: URL? {
        guard let rawAddress = service.fullAddress,
              let address = rawAddress.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
              !address.isEmpty else { return nil }
        return URL(string: "http://maps.apple.com/?q=\(address)")
    }

    private func contactStat(title: String, value: String, icon: String) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            Image(systemName: icon)
                .font(.headline.weight(.semibold))
                .foregroundStyle(Theme.Colors.primary)
            Text(title)
                .font(Theme.Typography.tiny)
                .foregroundStyle(Theme.Colors.textSecondary)
            Text(value)
                .font(Theme.Typography.bodyStrong)
                .foregroundStyle(.white)
                .lineLimit(2)
                .minimumScaleFactor(0.8)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Color.white.opacity(0.07))
        )
    }

    private func quickActionButton(_ title: String, icon: String, tint: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: Theme.Spacing.sm) {
                Image(systemName: icon)
                    .font(.headline.weight(.semibold))
                Text(title)
                    .font(Theme.Typography.bodyStrong)
                Spacer()
                Image(systemName: "arrow.up.right")
                    .font(.caption.weight(.bold))
            }
            .foregroundStyle(.white)
            .padding()
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(tint.opacity(0.82))
            )
        }
        .buttonStyle(.plain)
    }

    private func detailRow(title: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title.uppercased())
                .font(Theme.Typography.tiny)
                .foregroundStyle(Theme.Colors.textSecondary)
            Text(value)
                .font(Theme.Typography.body)
                .foregroundStyle(.white)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Color.white.opacity(0.05))
        )
    }
}

private extension ServiceContact {
    var discoverySubtitle: String {
        let location = city?.trimmingCharacters(in: .whitespacesAndNewlines)
        let emailText = email.trimmingCharacters(in: .whitespacesAndNewlines)
        switch (location?.isEmpty == false ? location : nil, emailText.isEmpty ? nil : emailText) {
        case let (.some(city), .some(email)):
            return "\(city) • \(email)"
        case let (.some(city), nil):
            return city
        case let (nil, .some(email)):
            return email
        default:
            return "Kontakt není doplněn"
        }
    }

    var fullAddress: String? {
        let streetParts = [street?.trimmedNonEmpty, streetNumber?.trimmedNonEmpty].compactMap { $0 }
        let cityParts = [zip?.trimmedNonEmpty, city?.trimmedNonEmpty].compactMap { $0 }
        let parts = [
            streetParts.isEmpty ? nil : streetParts.joined(separator: " "),
            cityParts.isEmpty ? nil : cityParts.joined(separator: " ")
        ].compactMap { $0 }
        return parts.isEmpty ? nil : parts.joined(separator: ", ")
    }
}

private extension Optional where Wrapped == String {
    func nonEmptyFallback(_ fallback: String) -> String {
        self?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false ? self!.trimmingCharacters(in: .whitespacesAndNewlines) : fallback
    }
}

private extension String {
    var trimmedNonEmpty: String? {
        let trimmed = trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    var digitsAndPhoneSymbolsOnly: String {
        filter { $0.isNumber || $0 == "+" }
    }
}
