import SwiftUI
import PhotosUI
import UIKit

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
    @State private var selectedServiceReservation: Reservation?
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
            .sheet(item: $selectedServiceReservation, onDismiss: {
                Task { await reload(force: true) }
            }) { reservation in
                ServiceReservationWorkspaceSheet(reservation: reservation)
            }
            .task { await reload() }
            .refreshable { await reload(force: true) }
        }
    }

    private func reservationCard(_ reservation: Reservation) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            if isServiceRole {
                Button {
                    selectedServiceReservation = reservation
                } label: {
                    Label("Otevřít zakázku", systemImage: "wrench.and.screwdriver")
                        .font(Theme.Typography.captionStrong)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .foregroundStyle(Theme.Colors.primary)
                }
                .buttonStyle(.plain)
                .accessibilityHint("Příjem, změna termínu, práce a předání vozidla")
            }

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


// One-hand service reception: the reservation is a lead, not owner consent.
// All history reads and writes are still authorized on the server per vehicle.
struct ServiceReservationWorkspaceSheet: View {
    let reservation: Reservation
    @EnvironmentObject private var env: AppEnvironment
    @Environment(\.dismiss) private var dismiss
    @State private var snapshot: WorkshopReservationSnapshot?
    @State private var job: WorkshopJobSnapshot?
    @State private var isLoading = true
    @State private var isSaving = false
    @State private var errorMessage: String?
    @State private var infoMessage: String?
    @State private var appointmentTime = Date().addingTimeInterval(86_400)
    @State private var editAppointment = false
    @State private var mileage = ""
    @State private var note = ""
    @State private var price = ""
    @State private var photoCaption = "Příjem vozidla"
    @State private var selectedImage: PhotosPickerItem?
    @State private var showCamera = false
    @State private var showHandoverConfirmation = false

    private let api = APIClient()
    private var quickTasks: [String] {
        let subject = "\(reservation.serviceType ?? "") \(reservation.note ?? "")".lowercased()
        var selected: [String] = []
        if subject.contains("brzd") { selected += ["Kontrola brzd", "Výměna destiček", "Kotouče"] }
        if subject.contains("olej") || subject.contains("filtr") { selected += ["Výměna oleje", "Olejový filtr", "Vzduchový filtr"] }
        if subject.contains("pneu") || subject.contains("kola") { selected += ["Demontáž kol", "Přezutí", "Vyvážení"] }
        if subject.contains("klima") { selected += ["Kontrola těsnosti", "Plnění klimatizace"] }
        if subject.contains("diagnost") || subject.contains("závad") { selected += ["Načtení závad", "Kontrola elektroinstalace"] }
        selected += ["Vizuální kontrola", "Diagnostika", "Zkušební jízda", "Kontrola hotové práce"]
        var seen = Set<String>()
        return selected.filter { seen.insert($0).inserted }
    }

    private var canWriteJob: Bool {
        snapshot?.accessApproved == true && job != nil
    }

    private var parsedMileage: Int? {
        let clean = mileage.replacingOccurrences(of: " ", with: "")
            .replacingOccurrences(of: ".", with: "")
        return clean.isEmpty ? nil : Int(clean)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Příjem vozidla") {
                    LabeledContent("Zákazník", value: snapshot?.customerName ?? reservation.customerName ?? "Zákazník rezervace")
                    LabeledContent("Vozidlo", value: snapshot?.vehicleName ?? reservation.vehicleName ?? "Vozidlo")
                    if let plate = snapshot?.vehiclePlate ?? reservation.vehiclePlate {
                        LabeledContent("SPZ", value: plate)
                    }
                    LabeledContent("Požadavek", value: reservation.serviceType ?? "Servis")
                    if let text = reservation.note, !text.isEmpty {
                        Text(text)
                            .font(Theme.Typography.body)
                    }
                    LabeledContent("Stav rezervace", value: snapshot?.reservationStatus ?? reservation.status)
                    LabeledContent("Termín", value: (snapshot?.scheduledAt ?? reservation.startDatetime).formatted(date: .numeric, time: .shortened))
                }

                if isLoading {
                    Section { ProgressView("Načítám zakázku") }
                } else {
                    if let errorMessage {
                        Section {
                            Text(errorMessage).foregroundStyle(.red)
                            Button("Načíst znovu") { Task { await reload() } }
                        }
                    }
                    if let infoMessage {
                        Section {
                            Text(infoMessage)
                                .foregroundStyle(Theme.Colors.textPrimary)
                        }
                    }

                    if let context = snapshot, context.ownerStillValid {
                        Section("Termín a potvrzení") {
                            if context.reservationStatus.uppercased() == "PENDING" {
                                Button("Potvrdit rezervaci") {
                                    Task { await updateReservation(status: "CONFIRMED") }
                                }
                                .disabled(isSaving)
                            }
                            if context.reservationStatus.uppercased() != "CANCELLED" &&
                               context.reservationStatus.uppercased() != "COMPLETED" &&
                               (job == nil || job?.status == "received") {
                                Toggle("Upravit termín", isOn: $editAppointment)
                                if editAppointment {
                                    DatePicker(
                                        "Nový termín",
                                        selection: $appointmentTime,
                                        in: Date().addingTimeInterval(60)...,
                                        displayedComponents: [.date, .hourAndMinute]
                                    )
                                    Button("Uložit nový termín") {
                                        Task { await updateReservation(date: appointmentTime) }
                                    }
                                    .disabled(isSaving)
                                }
                            }
                        }

                        if context.reservationStatus.uppercased() == "CONFIRMED" {
                            if !context.accessApproved {
                                Section("Souhlas majitele") {
                                    Label("Rezervace neuděluje přístup k historii vozidla.", systemImage: "lock.shield")
                                        .font(Theme.Typography.caption)
                                    if context.accessRequested {
                                        Text("Žádost o přístup čeká na schválení majitelem.")
                                    } else {
                                        Button("Vyžádat přístup jedním klepnutím") {
                                            Task { await requestAccess() }
                                        }
                                        .disabled(isSaving)
                                    }
                                    Button("Zkontrolovat schválení") { Task { await reload() } }
                                }
                            } else if job == nil {
                                Section("Příjem zakázky") {
                                    Button {
                                        Task { await startJob() }
                                    } label: {
                                        Label("Přijmout vozidlo", systemImage: "car.side.rear.open")
                                    }
                                    .disabled(isSaving)
                                    Text("Příjem naváže na rezervaci. Nevytvoří duplicitní vozidlo.")
                                        .font(Theme.Typography.caption)
                                }
                            }
                        }

                        if let job {
                            Section("Průběh zakázky") {
                                LabeledContent("Stav", value: job.statusLabel)
                                if let km = job.mileage {
                                    LabeledContent("Při příjmu", value: "\(km.formatted()) km")
                                }

                                if job.status == "received" {
                                    Button("Zahájit práci") {
                                        Task { await updateJob(status: "in_progress", message: "Práce na vozidle zahájena.") }
                                    }
                                    .disabled(isSaving)
                                }

                                if job.status == "received" || job.status == "in_progress" {
                                    TextField("Stav tachometru (km)", text: $mileage)
                                        .keyboardType(.numberPad)
                                    TextField("Krátká poznámka / práce", text: $note, axis: .vertical)
                                        .lineLimit(1...3)

                                    ScrollView(.horizontal, showsIndicators: false) {
                                        HStack(spacing: 6) {
                                            ForEach(quickTasks, id: \.self) { task in
                                                Button(task) { note = task }
                                                    .buttonStyle(.bordered)
                                                    .controlSize(.small)
                                            }
                                        }
                                    }

                                    Button("Zapsat úkon") {
                                        Task { await updateJob(status: nil, message: note) }
                                    }
                                    .disabled(isSaving || note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

                                    HStack {
                                        if UIImagePickerController.isSourceTypeAvailable(.camera) {
                                            Button("Vyfotit") { showCamera = true }
                                        }
                                        PhotosPicker(selection: $selectedImage, matching: .images) {
                                            Label("Přidat foto", systemImage: "camera")
                                        }
                                    }
                                    TextField("Popisek fotografie", text: $photoCaption)
                                    TextField("Cena celkem Kč (volitelně)", text: $price)
                                        .keyboardType(.decimalPad)

                                    Button("Dokončit opravu") {
                                        Task {
                                            await updateJob(
                                                status: "completed",
                                                message: note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                                    ? "Oprava dokončena, vozidlo připraveno k předání."
                                                    : note
                                            )
                                        }
                                    }
                                    .disabled(isSaving || (job.status != "in_progress"))
                                }

                                if job.status == "completed" {
                                    Label("Vozidlo připraveno k předání", systemImage: "checkmark.seal")
                                    Button("Předat zákazníkovi") { showHandoverConfirmation = true }
                                        .disabled(isSaving)
                                } else if job.status == "handed_over" {
                                    Label("Vozidlo předáno zákazníkovi", systemImage: "checkmark.circle.fill")
                                }

                                if !job.photos.isEmpty {
                                    Text("Fotodokumentace: \(job.photos.count) snímků")
                                        .font(Theme.Typography.captionStrong)
                                    ForEach(job.photos) { photo in
                                        Label(photo.caption ?? "Foto vozidla", systemImage: "photo")
                                            .font(Theme.Typography.caption)
                                    }
                                }
                            }

                            if !job.events.isEmpty {
                                Section("Historie úkonů") {
                                    ForEach(job.events) { event in
                                        HStack(alignment: .top) {
                                            Text(event.message)
                                                .font(Theme.Typography.caption)
                                            Spacer(minLength: 8)
                                            Text(event.createdAt.formatted(date: .numeric, time: .shortened))
                                                .font(Theme.Typography.tiny)
                                                .foregroundStyle(Theme.Colors.textSecondary)
                                        }
                                    }
                                }
                            }
                        }
                    } else if let context = snapshot, !context.ownerStillValid {
                        Section {
                            Label("Vlastnictví vozidla se změnilo. Zakázku nelze zahájit.", systemImage: "exclamationmark.shield")
                        }
                    }
                }
            }
            .scrollDismissesKeyboard(.interactively)
            .navigationTitle("Servisní zakázka")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Zavřít") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { Task { await reload() } } label: { Image(systemName: "arrow.clockwise") }
                        .disabled(isSaving)
                }
            }
            .confirmationDialog(
                "Opravdu předat dokončené vozidlo?",
                isPresented: $showHandoverConfirmation,
                titleVisibility: .visible
            ) {
                Button("Potvrdit předání") { Task { await handover() } }
                Button("Zrušit", role: .cancel) {}
            }
            .sheet(isPresented: $showCamera) {
                WorkshopCameraCapture { photoData in
                    Task { await uploadPhoto(data: photoData) }
                }
            }
            .onChange(of: selectedImage) { _, picked in
                guard let picked else { return }
                Task {
                    if let data = try? await picked.loadTransferable(type: Data.self) {
                        await uploadPhoto(data: data)
                    }
                    selectedImage = nil
                }
            }
            .task { await reload() }
        }
    }

    private func reload() async {
        guard let token = env.authManager.token else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            let context: WorkshopReservationSnapshot = try await api.request(
                .get("/api/v1/reservations/\(reservation.id)/workspace"),
                token: token
            )
            snapshot = context
            if let jobInfo = context.job {
                job = try await api.request(
                    .get("/api/v1/service-jobs/\(jobInfo.id)"), token: token
                )
                mileage = job?.mileage.map(String.init) ?? mileage
            } else {
                job = nil
            }
            errorMessage = nil
        } catch {
            errorMessage = friendlyError(error, "Nepodařilo se načíst pracovní kartu.")
        }
    }

    private func perform<T: Decodable>(_ endpoint: APIEndpoint, failure: String) async -> T? {
        guard !isSaving, let token = env.authManager.token else { return nil }
        isSaving = true
        defer { isSaving = false }
        do {
            let answer: T = try await api.request(endpoint, token: token)
            infoMessage = nil
            errorMessage = nil
            await reload()
            return answer
        } catch {
            errorMessage = friendlyError(error, failure)
            return nil
        }
    }

    private func updateReservation(status: String? = nil, date: Date? = nil) async {
        struct Change: Encodable {
            let status: String?
            let startDatetime: Date?
        }
        guard let body = try? api.encodeBody(Change(status: status, startDatetime: date)) else { return }
        let response: Reservation? = await perform(
            .put("/api/v1/reservations/\(reservation.id)", body: body),
            failure: "Termín nebo potvrzení se nepodařilo uložit."
        )
        if response != nil {
            editAppointment = false
            infoMessage = "Rezervace byla aktualizována."
        }
    }

    private func requestAccess() async {
        struct Answer: Decodable { let message: String }
        let answer: Answer? = await perform(
            .post("/api/v1/reservations/\(reservation.id)/request-access"),
            failure: "Žádost o přístup nebylo možné odeslat."
        )
        if let answer { infoMessage = answer.message }
    }

    private func startJob() async {
        let answer: WorkshopJobSnapshot? = await perform(
            .post("/api/v1/reservations/\(reservation.id)/start-job"),
            failure: "Příjem se nepodařilo založit. Ověřte stav schválení."
        )
        if answer != nil { infoMessage = "Vozidlo přijato. Můžete začít pracovat." }
    }

    private func updateJob(status: String?, message: String) async {
        guard let job else { return }
        struct Change: Encodable {
            let clientId: UUID
            let expectedVersion: Int
            let status: String?
            let message: String
            let mileage: Int?
            let price: Double?
        }
        let cost = price.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: ",", with: ".")
        let amount = cost.isEmpty ? nil : Double(cost)
        if status == "completed" && !cost.isEmpty && amount == nil {
            errorMessage = "Cena musí být platné číslo."
            return
        }
        if !mileage.isEmpty && parsedMileage == nil {
            errorMessage = "Stav tachometru musí být platné číslo."
            return
        }
        let payload = Change(
            clientId: UUID(),
            expectedVersion: job.version,
            status: status,
            message: message,
            mileage: parsedMileage,
            price: status == "completed" ? amount : nil
        )
        guard let body = try? api.encodeBody(payload) else { return }
        let answer: WorkshopJobSnapshot? = await perform(
            .post("/api/v1/service-jobs/\(job.id)/updates", body: body),
            failure: "Úkon se nepodařilo uložit. Načtěte aktuální stav zakázky."
        )
        if answer != nil {
            note = ""
            infoMessage = status == "completed" ? "Oprava dokončena, záznam uložen do historie." : "Úkon zapsán."
        }
    }

    private func uploadPhoto(data: Data) async {
        guard let job else {
            errorMessage = "Nejdříve přijměte zakázku."
            return
        }
        struct ImageBody: Encodable {
            let clientId: UUID
            let caption: String
            let contentBase64: String
        }
        guard let photo = UIImage(data: data) else {
            errorMessage = "Nepodařilo se načíst fotografii."
            return
        }
        let longest = max(photo.size.width, photo.size.height)
        let scale = min(1.0, 2048.0 / max(longest, 1.0))
        let image = UIGraphicsImageRenderer(
            size: CGSize(width: photo.size.width * scale, height: photo.size.height * scale)
        ).image { _ in
            photo.draw(in: CGRect(origin: .zero,
                                  size: CGSize(width: photo.size.width * scale,
                                               height: photo.size.height * scale)))
        }
        guard let jpeg = image.jpegData(compressionQuality: 0.78),
              !jpeg.isEmpty, jpeg.count <= 10_000_000 else {
            errorMessage = "Fotografie je příliš velká."
            return
        }
        let payload = ImageBody(
            clientId: UUID(),
            caption: photoCaption,
            contentBase64: jpeg.base64EncodedString()
        )
        guard let body = try? api.encodeBody(payload) else { return }
        struct ImageResult: Decodable { let photo: WorkshopJobPhoto; let job: WorkshopJobSnapshot }
        let answer: ImageResult? = await perform(
            .post("/api/v1/service-jobs/\(job.id)/photos", body: body),
            failure: "Fotografii se nepodařilo uložit."
        )
        if answer != nil { infoMessage = "Fotografie uložena do zakázky." }
    }

    private func handover() async {
        guard let job, let body = try? api.encodeBody(
            WorkshopHandoverRequest(clientId: UUID(), expectedVersion: job.version)
        ) else { return }
        let answer: WorkshopJobSnapshot? = await perform(
            .post("/api/v1/service-jobs/\(job.id)/handover", body: body),
            failure: "Předání se nepodařilo zaznamenat."
        )
        if answer != nil { infoMessage = "Vozidlo předáno a zapsáno do historie." }
    }

    private func friendlyError(_ error: Error, _ fallback: String) -> String {
        UserFacingErrorMapper.message(for: error, context: .account, fallback: fallback)
    }
}

private struct WorkshopHandoverRequest: Encodable {
    let clientId: UUID
    let expectedVersion: Int
}

private struct WorkshopReservationSnapshot: Decodable {
    let reservationId: Int
    let vehicleId: Int
    let customerId: Int
    let vehicleName: String?
    let vehiclePlate: String?
    let customerName: String?
    let customerEmail: String?
    let workType: String?
    let workNote: String?
    let reservationStatus: String
    let scheduledAt: Date
    let ownerStillValid: Bool
    let accessApproved: Bool
    let accessRequested: Bool
    let job: WorkshopJobSummary?
}

private struct WorkshopJobSummary: Decodable {
    let id: Int
    let status: String
    let version: Int
    let title: String
    let mileage: Int?
}

private struct WorkshopJobSnapshot: Decodable {
    let id: Int
    let vehicleId: Int
    let serviceId: Int
    let status: String
    let title: String
    let description: String?
    let mileage: Int?
    let version: Int
    let finalRecordId: Int?
    let events: [WorkshopJobEvent]
    let photos: [WorkshopJobPhoto]

    var statusLabel: String {
        switch status {
        case "received": return "Přijato"
        case "in_progress": return "Pracuje se"
        case "completed": return "Hotovo"
        case "handed_over": return "Předáno"
        case "cancelled": return "Zrušeno"
        default: return status
        }
    }
}

private struct WorkshopJobEvent: Decodable, Identifiable {
    let id: Int
    let status: String
    let message: String
    let createdAt: Date
}

private struct WorkshopJobPhoto: Decodable, Identifiable {
    let id: Int
    let caption: String?
    let mimeType: String
    let fileSize: Int
}

private struct WorkshopCameraCapture: UIViewControllerRepresentable {
    let onPhoto: (Data) -> Void
    @Environment(\.dismiss) private var dismiss

    func makeCoordinator() -> Coordinator { Coordinator(parent: self) }

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    final class Coordinator: NSObject, UINavigationControllerDelegate, UIImagePickerControllerDelegate {
        let parent: WorkshopCameraCapture
        init(parent: WorkshopCameraCapture) { self.parent = parent }
        func imagePickerController(
            _ picker: UIImagePickerController,
            didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]
        ) {
            if let image = info[.originalImage] as? UIImage,
               let bytes = image.jpegData(compressionQuality: 0.75) {
                parent.onPhoto(bytes)
            }
            parent.dismiss()
        }
        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            parent.dismiss()
        }
    }
}
