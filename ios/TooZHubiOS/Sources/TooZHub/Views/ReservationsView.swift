import SwiftUI

struct ReservationsView: View {
    private enum ReservationFilter: String, CaseIterable, Identifiable {
        case all = "Vše"
        case pending = "Čeká"
        case confirmed = "Potvrzené"
        case completed = "Hotové"
        case cancelled = "Zrušené"

        var id: String { rawValue }
    }

    @EnvironmentObject private var env: AppEnvironment
    @EnvironmentObject private var viewModel: ReservationsViewModel
    @State private var showNewReservation = false
    @State private var selectedFilter: ReservationFilter = .all
    @State private var bookingRequests: [ServiceBookingRequestItem] = []
    @State private var selectedBookingRequest: ServiceBookingRequestItem?
    @State private var bookingError: String?
    private let bookingAPI = APIClient()

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                    HStack(alignment: .center) {
                        Text(isServiceRole ? "Příchozí rezervace klientů a servisní kalendář" : "Naplánované termíny a servisní schůzky")
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.textSecondary)
                        Spacer()
                        PillBadge(title: "\(filteredReservations.count) termínů", style: .success)
                    }

                    if !bookingRequests.isEmpty {
                        bookingRequestsSection
                    }
                    if let bookingError {
                        Text(bookingError)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.textSecondary)
                    }

                    if viewModel.isLoading {
                        ProgressView()
                            .tint(.white)
                            .frame(maxWidth: .infinity)
                            .padding(.top, 60)
                    } else if let error = viewModel.error {
                        ErrorStateView(message: error) { Task { await reload() } }
                    } else if viewModel.reservations.isEmpty {
                        EmptyStateView(
                            icon: "calendar.badge.plus",
                            title: "Zatím žádné rezervace",
                            subtitle: "Vytvořte si první servisní termín a mějte přehled o návštěvách.",
                            actionTitle: "Vytvořit rezervaci"
                        ) {
                            showNewReservation = true
                        }
                    } else {
                        reservationSummary
                        reservationFilterBar

                        LazyVStack(spacing: Theme.Spacing.md) {
                            ForEach(filteredReservations) { reservation in
                                reservationCard(reservation)
                            }
                        }
                    }
                }
                .padding(Theme.Spacing.md)
                .padding(.bottom, Theme.Spacing.xxl + 20)
            }
            .hubPageBackground()
            .navigationTitle("Rezervace")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showNewReservation = true
                    } label: {
                        Image(systemName: "plus")
                            .font(.headline.bold())
                            .foregroundStyle(Theme.Colors.textOnLight)
                            .frame(width: 34, height: 34)
                            .background(Theme.Colors.primary, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    }
                }
            }
            .sheet(isPresented: $showNewReservation) {
                NewReservationSheet(
                    vehicles: viewModel.vehicleOptions,
                    services: serviceOptionsForCurrentUserRole,
                    role: env.authManager.user?.role ?? "user",
                    currentUserId: env.authManager.user?.id
                ) { vehicleId, serviceId, type, note, start in
                    guard let token = env.authManager.token else { return }
                    Task {
                        await viewModel.createReservation(
                            vehicleId: vehicleId,
                            serviceId: serviceId,
                            type: type,
                            note: note,
                            start: start,
                            token: token,
                            role: env.authManager.user?.role ?? "user"
                        )
                    }
                }
            }
            .sheet(item: $selectedBookingRequest) { booking in
                ServiceBookingDecisionSheet(
                    booking: booking,
                    isServiceRole: isServiceRole
                ) { action, message, date in
                    await decideBooking(booking, action: action, message: message, proposedDate: date)
                }
            }
            .task { await reload() }
            .refreshable { await reload(force: true) }
        }
    }

    private func reservationCard(_ reservation: Reservation) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(reservation.serviceType ?? "Servisní rezervace")
                        .font(Theme.Typography.headline)
                        .foregroundStyle(Theme.Colors.textOnLight)

                    Text(reservation.serviceName ?? reservation.serviceEmail ?? "Bez názvu servisu")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textOnLightSecondary)
                }

                Spacer()

                PillBadge(
                    title: statusTitle(reservation.status),
                    style: statusStyle(reservation.status)
                )
            }

            HStack(spacing: Theme.Spacing.sm) {
                VehicleInfoPillLight(icon: "calendar", label: "Termín", value: reservation.startDatetime.formatted(date: .abbreviated, time: .omitted))
                VehicleInfoPillLight(icon: "clock", label: "Čas", value: reservation.startDatetime.formatted(date: .omitted, time: .shortened))
            }

            if isServiceRole {
                HStack(spacing: Theme.Spacing.sm) {
                    if let customerName = reservation.customerName ?? reservation.customerEmail {
                        VehicleInfoPillLight(icon: "person", label: "Klient", value: customerName)
                    }
                    if let vehicleName = reservation.vehicleName ?? reservation.vehiclePlate {
                        VehicleInfoPillLight(icon: "car.fill", label: "Vozidlo", value: vehicleName)
                    }
                }
            }

            if let note = reservation.note, !note.isEmpty {
                Text(note)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colors.textOnLightSecondary)
            }

            HStack(spacing: Theme.Spacing.sm) {
                if shouldShowConfirmAction(for: reservation) {
                    Button("Potvrdit") {
                        guard let token = env.authManager.token else { return }
                        Task {
                            await viewModel.confirmReservation(
                                reservationId: reservation.id,
                                token: token,
                                role: env.authManager.user?.role ?? "user"
                            )
                        }
                    }
                    .buttonStyle(InlineChipButtonStyle(isSelected: true))
                }

                if shouldShowCompleteAction(for: reservation) {
                    Button("Dokončit") {
                        guard let token = env.authManager.token else { return }
                        Task {
                            await viewModel.completeReservation(
                                reservationId: reservation.id,
                                token: token,
                                role: env.authManager.user?.role ?? "user"
                            )
                        }
                    }
                    .buttonStyle(InlineChipButtonStyle(isSelected: false))
                }

                if shouldShowCancelAction(for: reservation) {
                    Button("Zrušit") {
                        guard let token = env.authManager.token else { return }
                        Task {
                            await viewModel.cancelReservation(
                                reservationId: reservation.id,
                                token: token,
                                role: env.authManager.user?.role ?? "user"
                            )
                        }
                    }
                    .buttonStyle(InlineChipButtonStyle(isSelected: false))
                }

                if shouldShowDeleteAction(for: reservation) {
                    Button("Smazat") {
                        guard let token = env.authManager.token else { return }
                        Task {
                            await viewModel.deleteReservation(
                                reservationId: reservation.id,
                                token: token,
                                role: env.authManager.user?.role ?? "user"
                            )
                        }
                    }
                    .buttonStyle(InlineChipButtonStyle(isSelected: false))
                }
            }
        }
        .hubLightCard()
    }

    private func statusTitle(_ status: String) -> String {
        switch status.uppercased() {
        case "PENDING":
            return "Čeká"
        case "CONFIRMED":
            return "Potvrzeno"
        case "CANCELLED":
            return "Zrušeno"
        case "COMPLETED":
            return "Hotovo"
        default:
            return status
        }
    }

    private func statusStyle(_ status: String) -> PillBadge.Style {
        switch status.uppercased() {
        case "CONFIRMED", "COMPLETED":
            return .success
        case "CANCELLED":
            return .danger
        case "PENDING":
            return .warning
        default:
            return .neutral
        }
    }

    private var reservationSummary: some View {
        HStack(spacing: Theme.Spacing.sm) {
            reservationSummaryCard(title: "Čeká", value: count(for: .pending))
            reservationSummaryCard(title: "Potvrzené", value: count(for: .confirmed))
            reservationSummaryCard(title: "Hotové", value: count(for: .completed))
        }
    }

    private var reservationFilterBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: Theme.Spacing.sm) {
                ForEach(ReservationFilter.allCases) { filter in
                    Button(filter.rawValue) {
                        selectedFilter = filter
                    }
                    .buttonStyle(InlineChipButtonStyle(isSelected: selectedFilter == filter))
                }
            }
        }
    }

    private var filteredReservations: [Reservation] {
        let source = viewModel.reservations.sorted { $0.startDatetime < $1.startDatetime }
        switch selectedFilter {
        case .all:
            return source
        case .pending:
            return source.filter { normalizedStatus($0.status) == "PENDING" }
        case .confirmed:
            return source.filter { normalizedStatus($0.status) == "CONFIRMED" }
        case .completed:
            return source.filter { normalizedStatus($0.status) == "COMPLETED" }
        case .cancelled:
            return source.filter { normalizedStatus($0.status) == "CANCELLED" }
        }
    }

    private var isServiceRole: Bool {
        (env.authManager.user?.role ?? "").lowercased() == "service"
    }

    private func normalizedStatus(_ status: String) -> String {
        status.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
    }

    private func count(for filter: ReservationFilter) -> Int {
        switch filter {
        case .all:
            return viewModel.reservations.count
        case .pending:
            return viewModel.reservations.filter { normalizedStatus($0.status) == "PENDING" }.count
        case .confirmed:
            return viewModel.reservations.filter { normalizedStatus($0.status) == "CONFIRMED" }.count
        case .completed:
            return viewModel.reservations.filter { normalizedStatus($0.status) == "COMPLETED" }.count
        case .cancelled:
            return viewModel.reservations.filter { normalizedStatus($0.status) == "CANCELLED" }.count
        }
    }

    private func shouldShowConfirmAction(for reservation: Reservation) -> Bool {
        isServiceRole && normalizedStatus(reservation.status) == "PENDING"
    }

    private func shouldShowCompleteAction(for reservation: Reservation) -> Bool {
        isServiceRole && normalizedStatus(reservation.status) == "CONFIRMED"
    }

    private func shouldShowCancelAction(for reservation: Reservation) -> Bool {
        let status = normalizedStatus(reservation.status)
        if isServiceRole {
            return status == "PENDING" || status == "CONFIRMED"
        }
        return status != "CANCELLED" && status != "COMPLETED"
    }

    private func shouldShowDeleteAction(for reservation: Reservation) -> Bool {
        let status = normalizedStatus(reservation.status)
        return isServiceRole || status == "CANCELLED" || status == "COMPLETED"
    }

    private func reservationSummaryCard(title: String, value: Int) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(Theme.Typography.tiny)
                .foregroundStyle(Theme.Colors.textSecondary)
            Text("\(value)")
                .font(Theme.Typography.headline)
                .foregroundStyle(.white)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(
            RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                .fill(Theme.Colors.surface)
        )
    }

    private var bookingRequestsSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Text(isServiceRole ? "Nové žádosti klientů o servis" : "Moje žádosti do servisu")
                .font(Theme.Typography.sectionTitle)
                .foregroundStyle(Theme.Colors.textPrimary)
            ForEach(bookingRequests) { booking in
                Button {
                    selectedBookingRequest = booking
                } label: {
                    HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                        Image(systemName: "wrench.and.screwdriver")
                            .foregroundStyle(Theme.Colors.primary)
                            .frame(width: 26)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(booking.vehicleName)
                                .font(Theme.Typography.bodyStrong)
                                .foregroundStyle(Theme.Colors.textOnLight)
                            Text(booking.serviceType)
                                .font(Theme.Typography.caption)
                                .foregroundStyle(Theme.Colors.textOnLightSecondary)
                            Text(isServiceRole ? (booking.customerName ?? "Zákazník") : booking.serviceName)
                                .font(Theme.Typography.tiny)
                                .foregroundStyle(Theme.Colors.textOnLightSecondary)
                        }
                        Spacer(minLength: 4)
                        PillBadge(title: booking.statusLabel, style: booking.statusStyle)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.plain)
                .hubLightCard()
            }
        }
    }

    private func loadBookings(token: String) async {
        do {
            let response: ServiceBookingList = try await bookingAPI.request(
                .get("/api/v1/service-booking-requests"),
                token: token
            )
            bookingRequests = response.items
            bookingError = nil
        } catch {
            bookingError = UserFacingErrorMapper.message(
                for: error, context: .account,
                fallback: "Žádosti do servisu se teď nepodařilo načíst."
            )
        }
    }

    private func decideBooking(
        _ booking: ServiceBookingRequestItem,
        action: String,
        message: String,
        proposedDate: Date?
    ) async -> String? {
        guard let token = env.authManager.token else { return "Relace vypršela. Přihlaste se znovu." }
        do {
            let payload = ServiceBookingDecisionPayload(
                clientId: UUID(),
                expectedVersion: booking.version,
                action: action,
                message: message,
                proposedDatetime: proposedDate
            )
            let body = try bookingAPI.encodeBody(payload)
            let _: ServiceBookingRequestItem = try await bookingAPI.request(
                .post("/api/v1/service-booking-requests/\(booking.id)/decision", body: body),
                token: token
            )
            await loadBookings(token: token)
            await viewModel.loadIfNeeded(
                token: token,
                role: env.authManager.user?.role ?? "user",
                force: true
            )
            return nil
        } catch {
            return UserFacingErrorMapper.message(
                for: error, context: .account,
                fallback: "Odpověď se nepodařilo uložit. Obnovte seznam a zkuste to znovu."
            )
        }
    }

    private func reload(force: Bool = false) async {
        guard let token = env.authManager.token else { return }
        await viewModel.loadIfNeeded(
            token: token,
            role: env.authManager.user?.role ?? "user",
            force: force
        )
        await loadBookings(token: token)
    }

    private var serviceOptionsForCurrentUserRole: [ServiceContact] {
        let role = (env.authManager.user?.role ?? "").lowercased()
        guard role == "service", let currentUserId = env.authManager.user?.id else {
            return viewModel.services
        }
        if let currentService = viewModel.services.first(where: { $0.id == currentUserId }) {
            return [currentService]
        }
        return viewModel.services
    }
}

private struct VehicleInfoPillLight: View {
    let icon: String
    let label: String
    let value: String

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
                .foregroundStyle(Theme.Colors.accent)
            VStack(alignment: .leading, spacing: 0) {
                Text(label)
                    .font(Theme.Typography.tiny)
                    .foregroundStyle(Theme.Colors.textOnLightSecondary)
                Text(value)
                    .font(Theme.Typography.captionStrong)
                    .foregroundStyle(Theme.Colors.textOnLight)
            }
        }
        .padding(.horizontal, Theme.Spacing.sm)
        .padding(.vertical, Theme.Spacing.xs)
        .background(Theme.Colors.lightMuted, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
    }
}


private struct ServiceBookingList: Decodable {
    let items: [ServiceBookingRequestItem]
}

private struct ServiceBookingRequestItem: Decodable, Identifiable, Hashable {
    let id: Int
    let vehicleId: Int
    let vehicleName: String
    let vehiclePlate: String?
    let serviceId: Int
    let serviceName: String
    let customerName: String?
    let serviceType: String
    let description: String
    let status: String
    let version: Int
    let preferredDatetime: Date?
    let proposedDatetime: Date?
    let serviceReply: String?

    var statusLabel: String {
        switch status.lowercased() {
        case "pending": return "Čeká"
        case "proposed": return "Návrh termínu"
        case "confirmed": return "Potvrzeno"
        case "rejected": return "Odmítnuto"
        case "cancelled": return "Zrušeno"
        default: return status
        }
    }

    var statusStyle: PillBadge.Style {
        switch status.lowercased() {
        case "confirmed": return .success
        case "pending", "proposed": return .warning
        case "rejected", "cancelled": return .danger
        default: return .neutral
        }
    }
}

private struct ServiceBookingDecisionPayload: Encodable {
    let clientId: UUID
    let expectedVersion: Int
    let action: String
    let message: String
    let proposedDatetime: Date?
}

private struct ServiceBookingDecisionSheet: View {
    let booking: ServiceBookingRequestItem
    let isServiceRole: Bool
    let onSubmit: (String, String, Date?) async -> String?

    @Environment(\.dismiss) private var dismiss
    @State private var reply = ""
    @State private var proposedDate = Date().addingTimeInterval(86_400)
    @State private var isSubmitting = false
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Vozidlo a požadavek") {
                    LabeledContent("Vozidlo", value: booking.vehicleName)
                    LabeledContent("Práce", value: booking.serviceType)
                    Text(booking.description)
                    LabeledContent("Stav", value: booking.statusLabel)
                    if let date = booking.preferredDatetime {
                        LabeledContent("Požadovaný termín", value: date.formatted(date: .abbreviated, time: .shortened))
                    }
                    if let date = booking.proposedDatetime {
                        LabeledContent("Návrh servisu", value: date.formatted(date: .abbreviated, time: .shortened))
                    }
                    if let serviceReply = booking.serviceReply, !serviceReply.isEmpty {
                        Text(serviceReply)
                    }
                }

                if booking.status == "pending" || booking.status == "proposed" {
                    Section("Odpověď") {
                        if isServiceRole {
                            DatePicker(
                                "Nový termín",
                                selection: $proposedDate,
                                in: Date().addingTimeInterval(60)...,
                                displayedComponents: [.date, .hourAndMinute]
                            )
                        }
                        TextField("Zpráva nebo důvod odmítnutí", text: $reply, axis: .vertical)
                            .lineLimit(2...5)
                    }

                    Section {
                        if isServiceRole {
                            if booking.status == "pending", let when = booking.preferredDatetime, when > Date() {
                                Button("Potvrdit požadovaný termín") { perform("accept") }
                                    .disabled(isSubmitting)
                            }
                            Button("Navrhnout jiný termín") { perform("propose", date: proposedDate) }
                                .disabled(isSubmitting || proposedDate <= Date())
                            Button("Odmítnout", role: .destructive) { perform("reject") }
                                .disabled(isSubmitting || reply.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        } else {
                            if booking.status == "proposed", let when = booking.proposedDatetime, when > Date() {
                                Button("Přijmout navržený termín") { perform("accept_proposal") }
                                    .disabled(isSubmitting)
                            }
                            Button("Zrušit žádost", role: .destructive) { perform("cancel") }
                                .disabled(isSubmitting)
                        }
                    }
                }

                if let errorMessage {
                    Section {
                        Text(errorMessage)
                            .foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("Servisní žádost")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Zavřít") { dismiss() }
                        .disabled(isSubmitting)
                }
            }
            .scrollDismissesKeyboard(.interactively)
        }
    }

    private func perform(_ action: String, date: Date? = nil) {
        guard !isSubmitting else { return }
        isSubmitting = true
        errorMessage = nil
        Task {
            let result = await onSubmit(
                action,
                reply.trimmingCharacters(in: .whitespacesAndNewlines),
                date
            )
            isSubmitting = false
            if let result {
                errorMessage = result
            } else {
                dismiss()
            }
        }
    }
}
