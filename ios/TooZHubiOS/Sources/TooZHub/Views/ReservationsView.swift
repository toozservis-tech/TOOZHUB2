import SwiftUI

struct ReservationsView: View {
    @EnvironmentObject private var env: AppEnvironment
    @StateObject private var viewModel: ReservationsViewModel
    @State private var showNewReservation = false

    init() {
        let api = APIClient()
        _viewModel = StateObject(wrappedValue: ReservationsViewModel(service: ReservationService(api: api), featureService: UserFeatureService(api: api)))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                    HStack(alignment: .center) {
                        Text("Naplánované termíny a servisní schůzky")
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.textSecondary)
                        Spacer()
                        PillBadge(title: "\(viewModel.reservations.count) termínů", style: .success)
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
                        ForEach(viewModel.reservations) { reservation in
                            reservationCard(reservation)
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
            .task { await reload() }
            .refreshable { await reload() }
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

            if let note = reservation.note, !note.isEmpty {
                Text(note)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colors.textOnLightSecondary)
            }

            HStack(spacing: Theme.Spacing.sm) {
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

    private func reload() async {
        guard let token = env.authManager.token else { return }
        await viewModel.load(token: token, role: env.authManager.user?.role ?? "user")
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
