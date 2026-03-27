import SwiftUI

struct ServiceClientsView: View {
    @EnvironmentObject private var env: AppEnvironment
    @StateObject private var viewModel: ServiceClientsViewModel

    init() {
        _viewModel = StateObject(wrappedValue: ServiceClientsViewModel(service: ServiceWorkspaceService(api: APIClient())))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                    SectionHeader(
                        title: "Klienti",
                        subtitle: "Správa zákazníků a sdílených vozidel",
                        trailing: AnyView(PillBadge(title: "\(viewModel.customers.count)", style: .success))
                    )

                    if viewModel.isLoading {
                        ProgressView()
                            .tint(.white)
                            .frame(maxWidth: .infinity)
                            .padding(.top, 60)
                    } else if let error = viewModel.error {
                        ErrorStateView(message: error) { Task { await reload() } }
                    } else if viewModel.customers.isEmpty {
                        EmptyStateView(
                            icon: "person.3",
                            title: "Zatím žádní klienti",
                            subtitle: "Jakmile získáte přístup k vozidlům klientů, objeví se zde jejich přehled."
                        )
                    } else {
                        ForEach(viewModel.customers) { customer in
                            VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                                Text(customer.name ?? customer.email)
                                    .font(Theme.Typography.headline)
                                    .foregroundStyle(.white)

                                Text("Email: \(customer.email)")
                                    .font(Theme.Typography.caption)
                                    .foregroundStyle(Theme.Colors.textSecondary)

                                Text("Vozidla: \(customer.vehiclesCount) • Sdílená: \(customer.sharedVehiclesCount)")
                                    .font(Theme.Typography.caption)
                                    .foregroundStyle(Theme.Colors.textSecondary)

                                HStack {
                                    Button("Načíst vozidla klienta") {
                                        guard let token = env.authManager.token else { return }
                                        Task { await viewModel.selectCustomer(customer.customerId, token: token) }
                                    }
                                    .buttonStyle(InlineChipButtonStyle(isSelected: viewModel.selectedCustomerId == customer.customerId))

                                    Spacer()

                                    if viewModel.selectedCustomerId == customer.customerId {
                                        PillBadge(title: "Vybráno", style: .success)
                                    }
                                }
                            }
                            .hubDarkCard()
                        }

                        if !viewModel.selectedCustomerVehicles.isEmpty {
                            VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                                Text("Vozidla klienta")
                                    .font(Theme.Typography.cardTitle)
                                    .foregroundStyle(.white)

                                ForEach(viewModel.selectedCustomerVehicles) { vehicle in
                                    Text("• \(vehicle.displayName) (\(vehicle.plate ?? "bez SPZ"))")
                                        .font(Theme.Typography.caption)
                                        .foregroundStyle(Theme.Colors.textSecondary)
                                }
                            }
                            .hubDarkCard()
                        }
                    }
                }
                .padding(Theme.Spacing.md)
                .padding(.bottom, Theme.Spacing.xxl + 18)
            }
            .hubPageBackground()
            .navigationTitle("Klienti")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbarBackground(.hidden, for: .navigationBar)
            .task { await reload() }
            .refreshable { await reload() }
        }
    }

    private func reload() async {
        guard let token = env.authManager.token else { return }
        await viewModel.load(token: token)
    }
}
