import SwiftUI

struct VehicleRemovalSheet: View {
    let vehicleId: Int
    let vehicleLabel: String
    let onRemove: (_ vehicleId: Int, _ reasonCode: String, _ followup: [String: String]) async throws -> VehicleRemovalConfirmResponse

    @Environment(\.dismiss) private var dismiss

    @State private var mode: RemovalMode = .sale
    @State private var followupText = ""
    @State private var buyerEmail = ""
    @State private var buyerPhone = ""
    @State private var busy = false
    @State private var localError: String?

    private enum RemovalMode: String, CaseIterable, Identifiable {
        case sale
        case ceased

        var id: String { rawValue }

        var title: String {
            switch self {
            case .sale:
                return "Prodáno (PDF s QR pro kupce)"
            case .ceased:
                return "Zánik / už ho nemám"
            }
        }

        var placeholder: String {
            switch self {
            case .sale:
                return "Kontakt kupce (e‑mail / telefon) nebo poznámka"
            case .ceased:
                return "Stručný popis (vrak, vývoz z evidence…)"
            }
        }

        var reasonCode: String {
            switch self {
            case .sale:
                return "sale"
            case .ceased:
                return "ceased"
            }
        }

    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text(vehicleLabel)
                        .font(Theme.Typography.body)
                        .foregroundStyle(Theme.Colors.textPrimary)
                } header: {
                    Text("Vozidlo")
                }

                Section {
                    Picker("Důvod odebrání", selection: $mode) {
                        ForEach(RemovalMode.allCases) { item in
                            Text(item.title).tag(item)
                        }
                    }
                    .pickerStyle(.inline)

                    if mode == .sale {
                        TextField("E-mail kupce", text: $buyerEmail)
                            .textContentType(.emailAddress)
                            .keyboardType(.emailAddress)
                            .autocapitalization(.none)
                        TextField("Telefon kupce", text: $buyerPhone)
                            .textContentType(.telephoneNumber)
                            .keyboardType(.phonePad)
                    } else {
                        TextField(mode.placeholder, text: $followupText, axis: .vertical)
                            .lineLimit(3 ... 6)
                    }
                } header: {
                    Text("Podrobnosti")
                } footer: {
                    Text("U prodeje vyplňte e-mail a telefon kupce; kupci odešleme digitální výpis a odkaz pro převod. U zániku stačí stručný popis.")
                        .font(Theme.Typography.caption)
                }

                if let localError {
                    Section {
                        Text(localError)
                            .foregroundStyle(.red)
                            .font(Theme.Typography.body)
                    }
                }
            }
            .navigationTitle("Odebrat z účtu")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Zrušit") {
                        dismiss()
                    }
                    .disabled(busy)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Odebrat") {
                        Task { await submit() }
                    }
                    .disabled(busy || !canSubmit)
                }
            }
        }
    }

    private var canSubmit: Bool {
        switch mode {
        case .sale:
            let em = buyerEmail.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            let ph = buyerPhone.trimmingCharacters(in: .whitespacesAndNewlines)
            let digits = ph.filter { $0.isNumber }
            return em.contains("@") && em.contains(".") && digits.count >= 9
        case .ceased:
            return !followupText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
    }

    private func submit() async {
        busy = true
        localError = nil
        defer { busy = false }
        let follow: [String: String]
        switch mode {
        case .sale:
            let em = buyerEmail.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            let ph = buyerPhone.trimmingCharacters(in: .whitespacesAndNewlines)
            follow = ["buyer_email": em, "buyer_phone": ph]
        case .ceased:
            let trimmed = followupText.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else { return }
            follow = ["note": trimmed]
        }
        do {
            _ = try await onRemove(vehicleId, mode.reasonCode, follow)
            dismiss()
        } catch {
            localError = UserFacingErrorMapper.message(
                for: error,
                context: .account,
                fallback: "Vozidlo se nepodařilo odebrat z profilu."
            )
        }
    }
}
