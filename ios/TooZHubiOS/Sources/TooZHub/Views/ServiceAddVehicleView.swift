import SwiftUI
import UIKit

private struct ServiceTachometerCaptchaSheet: View {
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
            VStack(spacing: Theme.Spacing.lg) {
                Text("Ověření tachometru")
                    .font(Theme.Typography.sectionTitle)
                    .foregroundStyle(Theme.Colors.textPrimary)

                if let captchaImage {
                    Image(uiImage: captchaImage)
                        .resizable()
                        .scaledToFit()
                        .frame(maxHeight: 100)
                        .padding(.horizontal, Theme.Spacing.md)
                        .background(
                            RoundedRectangle(cornerRadius: Theme.Radius.md)
                                .fill(Theme.Colors.surface)
                        )
                } else {
                    Text("Captcha obrázek se nepodařilo načíst.")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textSecondary)
                }

                TextField("Kód z obrázku", text: $captchaCode)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled(true)
                    .padding(.horizontal, Theme.Spacing.md)
                    .padding(.vertical, Theme.Spacing.sm)
                    .background(
                        RoundedRectangle(cornerRadius: Theme.Radius.md)
                            .fill(Theme.Colors.surface)
                    )

                HStack(spacing: Theme.Spacing.md) {
                    Button("Zrušit", role: .cancel, action: onCancel)
                        .buttonStyle(.bordered)

                    Button {
                        onSubmit(captchaCode)
                    } label: {
                        if isSubmitting {
                            ProgressView()
                                .progressViewStyle(.circular)
                        } else {
                            Text("Načíst km")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(captchaCode.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSubmitting)
                }
            }
            .padding(Theme.Spacing.lg)
            .navigationTitle("Kontrola tachometru")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

struct ServiceAddVehicleView: View {
    @EnvironmentObject private var env: AppEnvironment
    @State private var customers: [ServiceWorkspaceCustomer] = []
    @State private var selectedCustomerId: Int = 0
    @State private var nickname = ""
    @State private var brand = ""
    @State private var model = ""
    @State private var year = ""
    @State private var plate = ""
    @State private var vin = ""
    @State private var currentMileageKm = ""
    @State private var lastStkMileageKm = ""
    @State private var stkDate = Date().addingTimeInterval(60 * 60 * 24 * 365)
    @State private var message: String?
    @State private var vinInfo: String?
    @State private var isLoading = false
    @State private var vinLoading = false
    @State private var isLookingUpTachometer = false
    @State private var tachometerChallenge: TachometerChallengeResponse?
    @State private var showTachometerCaptchaSheet = false
    @State private var hasManualNicknameOverride = false
    @State private var isSyncingNickname = false

    private let service = ServiceWorkspaceService(api: APIClient())
    private let vehicleService = VehicleService(api: APIClient())
    private var parsedCurrentMileageKm: Int? { parseMileageInput(currentMileageKm) }
    private var parsedLastStkMileageKm: Int? { parseMileageInput(lastStkMileageKm) }
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
                Section("Klient") {
                    Picker("Vyberte klienta", selection: $selectedCustomerId) {
                        ForEach(customers) { customer in
                            Text(customer.name ?? customer.email).tag(customer.customerId)
                        }
                    }
                }

                Section("Vozidlo") {
                    HStack {
                        TextField("VIN", text: $vin)
                            .textInputAutocapitalization(.characters)
                            .autocorrectionDisabled(true)
                        Button("Načíst") {
                            Task { await decodeVIN() }
                        }
                        .disabled(vinLoading || vin.trimmingCharacters(in: .whitespacesAndNewlines).count != 17)
                    }
                    TextField("Název", text: $nickname)
                    TextField("Značka", text: $brand)
                    TextField("Model", text: $model)
                    TextField("Rok výroby", text: $year)
                        .keyboardType(.numberPad)
                    HStack {
                        TextField("SPZ", text: $plate)
                            .textInputAutocapitalization(.characters)
                            .autocorrectionDisabled(true)
                        Button("Načíst") {
                            Task { await decodePlate() }
                        }
                        .disabled(vinLoading || plate.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                    DatePicker("Platnost STK", selection: $stkDate, displayedComponents: .date)
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
                                    .progressViewStyle(.circular)
                            }
                            Text("Načíst poslední km z Kontroly tachometru")
                        }
                    }
                    .disabled(
                        isLookingUpTachometer ||
                        normalizeVin(vin).count != 17
                    )
                }

                if let vinInfo {
                    Section {
                        Text(vinInfo)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.accent)
                    }
                }

                if let mileageValidationError {
                    Section {
                        Text(mileageValidationError)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(.red)
                    }
                }

                if let message {
                    Section {
                        Text(message)
                            .font(Theme.Typography.caption)
                    }
                }

                Section {
                    Button("Přidat vozidlo klientovi") {
                        Task { await submit() }
                    }
                    .disabled(
                        isLoading ||
                        selectedCustomerId == 0 ||
                        nickname.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
                        mileageValidationError != nil
                    )
                }
            }
            .navigationTitle("Přidat vozidlo")
            .task { await loadCustomers() }
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
            .sheet(isPresented: $showTachometerCaptchaSheet) {
                if let challenge = tachometerChallenge {
                    ServiceTachometerCaptchaSheet(
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
        }
    }

    private func loadCustomers() async {
        guard let token = env.authManager.token else { return }
        do {
            customers = try await service.fetchCustomers(token: token)
            selectedCustomerId = customers.first?.customerId ?? 0
        } catch {
            message = error.localizedDescription
        }
    }

    private func submit() async {
        guard let token = env.authManager.token else { return }
        isLoading = true
        defer { isLoading = false }

        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"

        do {
            try await service.createCustomerVehicle(
                customerId: selectedCustomerId,
                request: ServiceWorkspaceVehicleCreateRequest(
                    nickname: nickname,
                    brand: brand.isEmpty ? nil : brand,
                    model: model.isEmpty ? nil : model,
                    year: Int(year),
                    plate: plate.isEmpty ? nil : plate,
                    vin: vin.isEmpty ? nil : vin,
                    stkValidUntil: formatter.string(from: stkDate),
                    currentMileageKm: parsedCurrentMileageKm,
                    lastStkMileageKm: parsedLastStkMileageKm
                ),
                token: token
            )
            message = "Vozidlo bylo úspěšně přidáno."
            nickname = ""
            brand = ""
            model = ""
            year = ""
            plate = ""
            vin = ""
            currentMileageKm = ""
            lastStkMileageKm = ""
            hasManualNicknameOverride = false
        } catch {
            message = error.localizedDescription
        }
    }

    private func decodeVIN() async {
        guard let token = env.authManager.token else { return }
        let vinValue = normalizeVin(vin)
        guard vinValue.count == 17 else {
            message = "VIN musí mít přesně 17 znaků."
            return
        }

        vinLoading = true
        message = nil
        vinInfo = nil
        defer { vinLoading = false }

        do {
            let decoded = try await vehicleService.decodeVINDetailed(vinValue, token: token)
            if decoded.success, let data = decoded.data {
                vin = data.vin ?? vinValue
                if let make = data.make, !make.isEmpty { brand = make }
                if let modelValue = data.model, !modelValue.isEmpty { model = modelValue }
                if let yearValue = data.productionYear ?? data.modelYear { year = String(yearValue) }

                if let displacement = data.engineDisplacementCc, let power = data.enginePowerKw {
                    vinInfo = "Motor: \(displacement) cm3 / \(power) kW"
                } else if let code = data.engineCode, !code.isEmpty {
                    vinInfo = "Motor: \(code)"
                } else {
                    vinInfo = "VIN dekódováno."
                }

                if let stk = data.stkValidUntil ?? data.techInspectionValidTo, let parsed = parseDate(stk) {
                    stkDate = parsed
                    vinInfo = "\(vinInfo ?? "VIN dekódováno.") STK aktualizována."
                }
                return
            }

            // Fallback na původní VIN endpoint, pokud detailní dekodér nevrátí data.
            let fallback = try await vehicleService.lookupVIN(vinValue, token: token)
            vin = fallback.vin
            if let make = fallback.make, !make.isEmpty { brand = make }
            if let modelValue = fallback.model, !modelValue.isEmpty { model = modelValue }
            if let yearValue = fallback.year { year = String(yearValue) }
            if let engine = fallback.engine, !engine.isEmpty {
                vinInfo = "Motor: \(engine)"
            } else {
                vinInfo = "VIN dekódováno (\(fallback.source))."
            }
        } catch {
            message = error.localizedDescription
        }
    }

    private func decodePlate() async {
        guard let token = env.authManager.token else { return }
        let plateValue = plate.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard !plateValue.isEmpty else { return }

        vinLoading = true
        message = nil
        vinInfo = nil
        defer { vinLoading = false }

        do {
            let decoded = try await vehicleService.decodePlate(plateValue, token: token)
            guard decoded.success, let data = decoded.data else {
                message = decoded.errors.first ?? "Dekódování SPZ se nezdařilo."
                return
            }
            plate = data.plate ?? plateValue
            if let vinValue = data.vin, !vinValue.isEmpty { vin = vinValue }
            if let make = data.make, !make.isEmpty { brand = make }
            if let modelValue = data.model, !modelValue.isEmpty { model = modelValue }
            if let yearValue = data.productionYear ?? data.modelYear { year = String(yearValue) }
            if let displacement = data.engineDisplacementCc, let power = data.enginePowerKw {
                vinInfo = "Motor: \(displacement) cm3 / \(power) kW"
            } else if let code = data.engineCode, !code.isEmpty {
                vinInfo = "Motor: \(code)"
            } else {
                vinInfo = "Data vozidla načtena podle SPZ."
            }
            if let stk = data.stkValidUntil ?? data.techInspectionValidTo, let parsed = parseDate(stk) {
                stkDate = parsed
            }
        } catch {
            message = error.localizedDescription
        }
    }

    private func startTachometerLookup() async {
        guard let token = env.authManager.token else { return }
        message = nil
        let normalizedVin = normalizeVin(vin)
        guard normalizedVin.count == 17 else {
            message = "VIN musí mít 17 znaků, aby šlo načíst STK tachometr."
            return
        }

        isLookingUpTachometer = true
        defer { isLookingUpTachometer = false }

        do {
            tachometerChallenge = try await vehicleService.createTachometerChallenge(token: token)
            showTachometerCaptchaSheet = true
        } catch {
            message = error.localizedDescription
        }
    }

    private func submitTachometerLookup(captchaCode: String) async {
        guard let token = env.authManager.token else { return }
        guard let challenge = tachometerChallenge else {
            message = "Captcha challenge vypršela, načtěte ji znovu."
            return
        }

        let code = captchaCode.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !code.isEmpty else {
            message = "Zadejte captcha kód z obrázku."
            return
        }

        isLookingUpTachometer = true
        defer { isLookingUpTachometer = false }

        do {
            let response = try await vehicleService.lookupTachometer(
                challengeId: challenge.challengeId,
                vin: vin,
                captchaCode: code,
                token: token
            )
            lastStkMileageKm = String(response.latestMileageKm)
            let checkDateText = response.latestCheckDate
                .map { date in
                    let formatter = DateFormatter()
                    formatter.locale = Locale(identifier: "cs_CZ")
                    formatter.dateStyle = .medium
                    formatter.timeStyle = .none
                    return formatter.string(from: date)
                } ?? "neznámé datum"
            message = "Poslední údaj STK načten: \(formatMileage(response.latestMileageKm)) km (\(checkDateText))."
            showTachometerCaptchaSheet = false
            tachometerChallenge = nil
        } catch {
            message = error.localizedDescription
            showTachometerCaptchaSheet = false
            tachometerChallenge = nil
        }
    }

    private func normalizeVin(_ value: String) -> String {
        value
            .uppercased()
            .replacingOccurrences(of: " ", with: "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
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
}
