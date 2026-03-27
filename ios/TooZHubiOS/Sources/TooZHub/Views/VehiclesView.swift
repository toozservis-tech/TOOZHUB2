import SwiftUI
import UIKit

struct VehiclesView: View {
    @EnvironmentObject private var env: AppEnvironment
    @StateObject private var viewModel: VehiclesViewModel

    @State private var showAddVehicle = false
    @State private var editVehicle: Vehicle?

    init() {
        let api = APIClient()
        _viewModel = StateObject(wrappedValue: VehiclesViewModel(service: VehicleService(api: api), featureService: UserFeatureService(api: api)))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                    HStack(alignment: .center) {
                        Text("Správa garáže a detailů vozidel")
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.textSecondary)
                        Spacer()
                        PillBadge(title: "\(viewModel.vehicles.count) záznamů", style: .success)
                    }

                    if viewModel.isLoading {
                        ProgressView()
                            .tint(.white)
                            .frame(maxWidth: .infinity)
                            .padding(.top, 60)
                    } else if let error = viewModel.error {
                        ErrorStateView(message: error) { Task { await reload() } }
                    } else if viewModel.vehicles.isEmpty {
                        EmptyStateView(
                            icon: "car.rear",
                            title: "Zatím nemáte žádné vozidlo",
                            subtitle: "Přidejte první auto a sledujte servisní historii i náklady.",
                            actionTitle: "Přidat vozidlo"
                        ) {
                            showAddVehicle = true
                        }
                    } else {
                        VStack(spacing: Theme.Spacing.md) {
                            ForEach(viewModel.vehicles) { vehicle in
                                VStack(spacing: Theme.Spacing.sm) {
                                    NavigationLink {
                                        VehicleDetailView(vehicleId: vehicle.id)
                                    } label: {
                                        VehicleCard(vehicle: vehicle)
                                    }
                                    .buttonStyle(.plain)

                                    HStack(spacing: Theme.Spacing.sm) {
                                        Button("Upravit") {
                                            editVehicle = vehicle
                                        }
                                        .buttonStyle(InlineChipButtonStyle(isSelected: true))

                                        Button("Smazat") {
                                            guard let token = env.authManager.token else { return }
                                            Task { await viewModel.deleteVehicle(id: vehicle.id, token: token) }
                                        }
                                        .buttonStyle(InlineChipButtonStyle(isSelected: false))
                                    }
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                }
                            }
                        }
                    }
                }
                .padding(Theme.Spacing.md)
                .padding(.bottom, Theme.Spacing.xxl + 24)
            }
            .hubPageBackground()
            .navigationTitle("Vozidla")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showAddVehicle = true
                    } label: {
                        Image(systemName: "plus")
                            .font(.headline.bold())
                            .foregroundStyle(Theme.Colors.textOnLight)
                            .frame(width: 34, height: 34)
                            .background(Theme.Colors.primary, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    }
                }
            }
            .sheet(isPresented: $showAddVehicle) {
                AddOrEditVehicleSheet(vehicle: nil, existingVehicles: viewModel.vehicles) { request in
                    guard let token = env.authManager.token else { return }
                    Task { await viewModel.createVehicle(request, token: token) }
                }
            }
            .sheet(item: $editVehicle) { vehicle in
                AddOrEditVehicleSheet(vehicle: vehicle, existingVehicles: viewModel.vehicles) { request in
                    guard let token = env.authManager.token else { return }
                    Task { await viewModel.updateVehicle(id: vehicle.id, request: request, token: token) }
                }
            }
            .refreshable { await reload() }
            .task { await reload() }
        }
    }

    private func reload() async {
        guard let token = env.authManager.token else { return }
        await viewModel.load(token: token)
    }
}

private struct TachometerCaptchaSheet: View {
    let challenge: TachometerChallengeResponse
    let isSubmitting: Bool
    let onSubmit: (String) -> Void
    let onCancel: () -> Void

    @State private var captchaCode = ""

    private var captchaImage: UIImage? {
        guard let data = Data(base64Encoded: challenge.captchaImageBase64) else { return nil }
        return UIImage(data: data)
    }

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: Theme.Spacing.md) {
                Text("Opište kód z obrázku pro ověření na Kontrole tachometru.")
                    .font(Theme.Typography.body)
                    .foregroundStyle(Theme.Colors.textSecondary)

                if let captchaImage {
                    Image(uiImage: captchaImage)
                        .resizable()
                        .interpolation(.none)
                        .scaledToFit()
                        .frame(maxWidth: .infinity)
                        .frame(height: 92)
                        .padding(Theme.Spacing.sm)
                        .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
                } else {
                    Text("Captcha obrázek se nepodařilo načíst.")
                        .font(Theme.Typography.body)
                        .foregroundStyle(.red)
                }

                TextField("Kód z obrázku", text: $captchaCode)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled(true)
                    .font(Theme.Typography.body)
                    .padding(.horizontal, Theme.Spacing.md)
                    .padding(.vertical, Theme.Spacing.sm)
                    .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))

                if isSubmitting {
                    HStack(spacing: Theme.Spacing.sm) {
                        ProgressView()
                        Text("Ověřuji…")
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.textSecondary)
                    }
                }

                Spacer(minLength: 0)
            }
            .padding(Theme.Spacing.md)
            .navigationTitle("Ověření captchy")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Zavřít") { onCancel() }
                        .disabled(isSubmitting)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Načíst km") {
                        onSubmit(captchaCode)
                    }
                    .disabled(
                        isSubmitting ||
                        captchaCode.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    )
                }
            }
        }
        .presentationDetents([.medium])
    }
}

struct AddOrEditVehicleSheet: View {
    let vehicle: Vehicle?
    let existingVehicles: [Vehicle]
    let onSubmit: (VehicleCreateRequest) -> Void

    @EnvironmentObject private var env: AppEnvironment
    @Environment(\.dismiss) private var dismiss
    @State private var nickname = ""
    @State private var brand = ""
    @State private var model = ""
    @State private var year = ""
    @State private var engine = ""
    @State private var vin = ""
    @State private var plate = ""
    @State private var notes = ""
    @State private var currentMileageKm = ""
    @State private var lastStkMileageKm = ""
    @State private var stkDate = Date().addingTimeInterval(365 * 24 * 3600)
    @State private var vinLookupMessage: String?
    @State private var vinLookupError: String?
    @State private var isLookingUpVIN = false
    @State private var isLookingUpTachometer = false
    @State private var tachometerChallenge: TachometerChallengeResponse?
    @State private var showTachometerCaptchaSheet = false
    @State private var hasManualNicknameOverride = false
    @State private var isSyncingNickname = false

    private let vehicleService = VehicleService(api: APIClient())
    private var parsedCurrentMileageKm: Int? { parseMileageInput(currentMileageKm) }
    private var parsedLastStkMileageKm: Int? { parseMileageInput(lastStkMileageKm) }
    private var normalizedCurrentVIN: String { normalizeVin(vin) }
    private var duplicateVINError: String? {
        guard !normalizedCurrentVIN.isEmpty else { return nil }

        let colliding = existingVehicles.first { candidate in
            guard candidate.id != vehicle?.id else { return false }
            let normalizedCandidateVIN = normalizeVin(candidate.vin ?? "")
            return !normalizedCandidateVIN.isEmpty && normalizedCandidateVIN == normalizedCurrentVIN
        }
        guard colliding != nil else { return nil }
        return "Vozidlo s tímto VIN už existuje."
    }

    private var mileageValidationError: String? {
        guard
            let current = parsedCurrentMileageKm,
            let lastStk = parsedLastStkMileageKm,
            current < lastStk
        else { return nil }
        return "Aktuální stav km musí být alespoň \(formatMileage(lastStk)) km (poslední údaj ze STK/emisí)."
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Základní údaje") {
                    HStack {
                        TextField("VIN", text: $vin)
                            .textInputAutocapitalization(.characters)
                            .autocorrectionDisabled(true)
                        Button("Načíst z VIN") {
                            Task { await decodeVIN() }
                        }
                        .disabled(isLookingUpVIN || vin.trimmingCharacters(in: .whitespacesAndNewlines).count != 17)
                    }
                    TextField("Název", text: $nickname)
                    TextField("Značka", text: $brand)
                    TextField("Model", text: $model)
                    TextField("Rok výroby", text: $year)
                        .keyboardType(.numberPad)
                    TextField("Motor", text: $engine)
                    HStack {
                        TextField("SPZ", text: $plate)
                            .textInputAutocapitalization(.characters)
                            .autocorrectionDisabled(true)
                        Button("Načíst ze SPZ") {
                            Task { await decodePlate() }
                        }
                        .disabled(isLookingUpVIN || plate.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                    DatePicker("STK", selection: $stkDate, displayedComponents: .date)
                    TextField("Aktuální stav km", text: $currentMileageKm)
                        .keyboardType(.numberPad)
                    TextField("Poslední km ze STK/emisí", text: $lastStkMileageKm)
                        .keyboardType(.numberPad)
                    Button {
                        Task { await startTachometerLookup() }
                    } label: {
                        HStack {
                            if isLookingUpTachometer {
                                ProgressView()
                            }
                            Text("Načíst poslední km z Kontroly tachometru")
                        }
                    }
                    .disabled(
                        isLookingUpVIN ||
                        isLookingUpTachometer ||
                        normalizeVin(vin).count != 17
                    )
                    TextField("Poznámky", text: $notes, axis: .vertical)
                        .lineLimit(2...4)
                }
                if let mileageValidationError {
                    Section {
                        Text(mileageValidationError)
                            .foregroundStyle(.red)
                    }
                }
                if let duplicateVINError {
                    Section {
                        Text(duplicateVINError)
                            .foregroundStyle(.red)
                    }
                }
                if let message = vinLookupMessage {
                    Section {
                        Text(message)
                            .foregroundStyle(Theme.Colors.accent)
                    }
                }
                if let error = vinLookupError {
                    Section {
                        Text(error)
                            .foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle(vehicle == nil ? "Přidat vozidlo" : "Upravit vozidlo")
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
                            VehicleCreateRequest(
                                nickname: nickname,
                                brand: brand.isEmpty ? nil : brand,
                                model: model.isEmpty ? nil : model,
                                year: Int(year),
                                engine: engine.isEmpty ? nil : engine,
                                vin: normalizedCurrentVIN.isEmpty ? nil : normalizedCurrentVIN,
                                plate: plate.isEmpty ? nil : plate,
                                notes: notes.isEmpty ? nil : notes,
                                stkValidUntil: formatter.string(from: stkDate),
                                currentMileageKm: parsedCurrentMileageKm,
                                lastStkMileageKm: parsedLastStkMileageKm,
                                tyresInfo: vehicle?.tyresInfo,
                                insuranceProvider: vehicle?.insuranceProvider,
                                insuranceValidUntil: nil
                            )
                        )
                        dismiss()
                    }
                    .disabled(
                        nickname.trimmingCharacters(in: .whitespacesAndNewlines).count < 2 ||
                        mileageValidationError != nil ||
                        duplicateVINError != nil
                    )
                }
            }
            .sheet(isPresented: $showTachometerCaptchaSheet) {
                if let challenge = tachometerChallenge {
                    TachometerCaptchaSheet(
                        challenge: challenge,
                        isSubmitting: isLookingUpTachometer,
                        onSubmit: { code in
                            Task { await submitTachometerLookup(captchaCode: code) }
                        },
                        onCancel: {
                            showTachometerCaptchaSheet = false
                            tachometerChallenge = nil
                        }
                    )
                }
            }
            .onAppear {
                nickname = vehicle?.nickname ?? ""
                brand = vehicle?.brand ?? ""
                model = vehicle?.model ?? ""
                year = vehicle?.year.map(String.init) ?? ""
                engine = vehicle?.engine ?? ""
                vin = vehicle?.vin ?? ""
                plate = vehicle?.plate ?? ""
                notes = vehicle?.notes ?? ""
                currentMileageKm = vehicle?.currentMileageKm.map(String.init) ?? ""
                lastStkMileageKm = vehicle?.lastStkMileageKm.map(String.init) ?? ""
                stkDate = vehicle?.stkValidUntil ?? Date().addingTimeInterval(365 * 24 * 3600)
                hasManualNicknameOverride = vehicle != nil
                if vehicle == nil {
                    syncNicknameIfNeeded()
                }
            }
            .onChange(of: brand) { _, _ in
                syncNicknameIfNeeded()
            }
            .onChange(of: model) { _, _ in
                syncNicknameIfNeeded()
            }
            .onChange(of: nickname) { _, newValue in
                guard !isSyncingNickname else { return }
                let trimmed = newValue.trimmingCharacters(in: .whitespacesAndNewlines)
                if trimmed.isEmpty {
                    hasManualNicknameOverride = false
                    syncNicknameIfNeeded()
                    return
                }
                let suggested = suggestedNickname()
                if suggested.isEmpty {
                    hasManualNicknameOverride = true
                    return
                }
                hasManualNicknameOverride = trimmed.caseInsensitiveCompare(suggested) != .orderedSame
            }
        }
    }

    private func decodeVIN() async {
        guard let token = env.authManager.token else { return }
        let vinValue = normalizeVin(vin)
        guard vinValue.count == 17 else {
            vinLookupError = "VIN musí mít přesně 17 znaků."
            return
        }

        isLookingUpVIN = true
        vinLookupMessage = nil
        vinLookupError = nil
        defer { isLookingUpVIN = false }

        do {
            let decoded = try await vehicleService.decodeVINDetailed(vinValue, token: token)
            if decoded.success, let data = decoded.data {
                vin = data.vin ?? vinValue
                if let make = data.make, !make.isEmpty { brand = make }
                if let modelValue = data.model, !modelValue.isEmpty { model = modelValue }
                if let yearValue = data.productionYear ?? data.modelYear { year = String(yearValue) }

                if let displacement = data.engineDisplacementCc, let power = data.enginePowerKw {
                    engine = "\(displacement) cm3 / \(power) kW"
                } else if let code = data.engineCode, !code.isEmpty {
                    engine = code
                }

                if let stk = data.stkValidUntil ?? data.techInspectionValidTo, let parsed = parseDate(stk) {
                    stkDate = parsed
                    vinLookupMessage = "VIN dekódováno a platnost STK aktualizována."
                } else {
                    vinLookupMessage = "VIN dekódováno, ale platnost STK se nepodařilo určit."
                }
                return
            }

            // Fallback na původní endpoint pro případ, že detailní dekodér nevrátí data.
            let response = try await vehicleService.lookupVIN(vinValue, token: token)
            vin = response.vin
            if let make = response.make, !make.isEmpty { brand = make }
            if let modelValue = response.model, !modelValue.isEmpty { model = modelValue }
            if let yearValue = response.year { year = String(yearValue) }
            if let engineValue = response.engine, !engineValue.isEmpty { engine = engineValue }

            if let detail = response.detail, !detail.isEmpty {
                vinLookupMessage = detail
            } else {
                vinLookupMessage = "VIN dekódováno ze zdroje: \(response.source)."
            }
        } catch {
            vinLookupError = error.localizedDescription
        }
    }

    private func decodePlate() async {
        guard let token = env.authManager.token else { return }
        let plateValue = plate.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard !plateValue.isEmpty else { return }

        isLookingUpVIN = true
        vinLookupMessage = nil
        vinLookupError = nil
        defer { isLookingUpVIN = false }

        do {
            let decoded = try await vehicleService.decodePlate(plateValue, token: token)
            guard decoded.success, let data = decoded.data else {
                vinLookupError = decoded.errors.first ?? "Dekódování SPZ se nezdařilo."
                return
            }
            plate = data.plate ?? plateValue
            if let vinValue = data.vin, !vinValue.isEmpty { vin = vinValue }
            if let make = data.make, !make.isEmpty { brand = make }
            if let modelValue = data.model, !modelValue.isEmpty { model = modelValue }
            if let yearValue = data.productionYear ?? data.modelYear { year = String(yearValue) }
            if let displacement = data.engineDisplacementCc, let power = data.enginePowerKw {
                engine = "\(displacement) cm3 / \(power) kW"
            } else if let code = data.engineCode, !code.isEmpty {
                engine = code
            }
            if let stk = data.stkValidUntil ?? data.techInspectionValidTo, let parsed = parseDate(stk) {
                stkDate = parsed
            }
            vinLookupMessage = "Data vozidla načtena podle SPZ."
        } catch {
            vinLookupError = error.localizedDescription
        }
    }

    private func startTachometerLookup() async {
        guard let token = env.authManager.token else { return }
        let vinValue = normalizeVin(vin)
        guard vinValue.count == 17 else {
            vinLookupError = "Pro kontrolu tachometru zadejte validní VIN (17 znaků)."
            return
        }

        isLookingUpTachometer = true
        vinLookupMessage = nil
        vinLookupError = nil
        defer { isLookingUpTachometer = false }

        do {
            tachometerChallenge = try await vehicleService.createTachometerChallenge(token: token)
            showTachometerCaptchaSheet = true
        } catch {
            vinLookupError = error.localizedDescription
        }
    }

    private func submitTachometerLookup(captchaCode: String) async {
        guard let token = env.authManager.token else { return }
        guard let challenge = tachometerChallenge else {
            vinLookupError = "Captcha challenge vypršel. Zkuste načíst nový obrázek."
            return
        }

        let vinValue = normalizeVin(vin)
        let code = captchaCode.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !code.isEmpty else {
            vinLookupError = "Zadejte captcha kód z obrázku."
            return
        }

        isLookingUpTachometer = true
        vinLookupMessage = nil
        vinLookupError = nil
        defer { isLookingUpTachometer = false }

        do {
            let response = try await vehicleService.lookupTachometer(
                challengeId: challenge.challengeId,
                vin: vinValue,
                captchaCode: code,
                token: token
            )

            let formatted = formatMileage(response.latestMileageKm)
            lastStkMileageKm = String(response.latestMileageKm)
            vinLookupMessage = "Načten poslední stav km ze STK/emisí: \(formatted) km."
            showTachometerCaptchaSheet = false
            tachometerChallenge = nil
        } catch {
            vinLookupError = error.localizedDescription
            showTachometerCaptchaSheet = false
            tachometerChallenge = nil
        }
    }

    private func parseDate(_ value: String) -> Date? {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }

        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = iso.date(from: trimmed) { return d }
        iso.formatOptions = [.withInternetDateTime]
        if let d = iso.date(from: trimmed) { return d }

        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        for format in [
            "yyyy-MM-dd",
            "dd.MM.yyyy",
            "dd/MM/yyyy",
            "yyyy-MM-dd'T'HH:mm:ss",
            "yyyy-MM-dd'T'HH:mm:ss.SSS",
            "yyyy-MM-dd'T'HH:mm:ssZ",
            "yyyy-MM-dd'T'HH:mm:ss.SSSZ"
        ] {
            formatter.dateFormat = format
            if let d = formatter.date(from: trimmed) { return d }
        }
        return nil
    }

    private func parseMileageInput(_ raw: String) -> Int? {
        let normalized = raw
            .replacingOccurrences(of: " ", with: "")
            .replacingOccurrences(of: ".", with: "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalized.isEmpty else { return nil }
        return Int(normalized)
    }

    private func formatMileage(_ value: Int) -> String {
        let formatter = NumberFormatter()
        formatter.locale = Locale(identifier: "cs_CZ")
        formatter.numberStyle = .decimal
        formatter.groupingSeparator = " "
        return formatter.string(from: NSNumber(value: value)) ?? String(value)
    }

    private func normalizeVin(_ raw: String) -> String {
        let allowed = CharacterSet.alphanumerics
        return raw
            .uppercased()
            .unicodeScalars
            .filter { allowed.contains($0) }
            .map(String.init)
            .joined()
    }

    private func suggestedNickname() -> String {
        [brand, model]
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }

    private func syncNicknameIfNeeded() {
        guard !hasManualNicknameOverride else { return }
        let suggested = suggestedNickname()
        guard !suggested.isEmpty else { return }
        isSyncingNickname = true
        nickname = suggested
        isSyncingNickname = false
    }
}
