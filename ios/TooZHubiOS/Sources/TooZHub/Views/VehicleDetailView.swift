import SwiftUI
import PhotosUI
import UniformTypeIdentifiers
import VisionKit
@preconcurrency import Vision
import PDFKit
import CoreImage
import ImageIO
import UIKit
import AVFoundation

struct VehicleDetailView: View {
    @EnvironmentObject private var env: AppEnvironment
    @StateObject private var viewModel: VehicleDetailViewModel
    let vehicleId: Int

    @State private var showAddRecord = false
    @State private var editingRecord: ServiceRecord?
    @State private var recordSearchText = ""
    @State private var selectedRecordFilter: RecordListFilter = .all

    init(vehicleId: Int) {
        self.vehicleId = vehicleId
        let api = APIClient()
        _viewModel = StateObject(wrappedValue: VehicleDetailViewModel(service: VehicleService(api: api), featureService: UserFeatureService(api: api)))
    }

    var body: some View {
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
                    detailHero
                    recordsSection
                }
            }
            .padding(Theme.Spacing.md)
            .padding(.bottom, Theme.Spacing.xxl + 26)
        }
        .hubPageBackground()
        .navigationTitle("Detail vozidla")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .toolbarBackground(.hidden, for: .navigationBar)
        .sheet(isPresented: $showAddRecord) {
            AddServiceRecordSheet(vehicleId: vehicleId) { request in
                guard let token = env.authManager.token else { return }
                Task { await viewModel.addRecord(vehicleId: vehicleId, request: request, token: token) }
            }
        }
        .sheet(item: $editingRecord) { record in
            AddServiceRecordSheet(initial: record, vehicleId: vehicleId) { request in
                guard let token = env.authManager.token else { return }
                Task {
                    await viewModel.updateRecord(
                        vehicleId: vehicleId,
                        recordId: record.id,
                        request: ServiceRecordUpdateRequest(
                            performedAt: request.performedAt,
                            mileage: request.mileage,
                            description: request.description,
                            price: request.price,
                            note: request.note,
                            category: request.category,
                            attachments: request.attachments,
                            nextServiceDueDate: request.nextServiceDueDate
                        ),
                        token: token
                    )
                }
            }
        }
        .task { await reload() }
    }

    private var detailHero: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            if let vehicle = viewModel.vehicle {
                VehicleCard(vehicle: vehicle)
            } else {
                EmptyStateView(
                    icon: "car.fill",
                    title: "Vozidlo nebylo nalezeno",
                    subtitle: "Zkuste načtení zopakovat."
                )
            }

            HStack(spacing: Theme.Spacing.sm) {
                StatCard(
                    title: "Servisních záznamů",
                    value: "\(viewModel.records.count)",
                    subtitle: "Celkem",
                    icon: "wrench.and.screwdriver.fill"
                )

                StatCard(
                    title: "Náklady",
                    value: "\(Int(viewModel.records.compactMap { $0.price }.reduce(0, +))) Kč",
                    subtitle: "Dle historie",
                    icon: "banknote.fill"
                )
            }
        }
    }

    private var recordsSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader(
                title: "Servisní historie",
                subtitle: "Přehled záznamů, rychlé filtry a úpravy",
                trailing: AnyView(
                    Button {
                        showAddRecord = true
                    } label: {
                        Image(systemName: "plus")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundStyle(Theme.Colors.textOnLight)
                            .frame(width: 30, height: 30)
                            .background(Theme.Colors.primary, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    }
                    .buttonStyle(.plain)
                )
            )

            if viewModel.records.isEmpty {
                EmptyStateView(
                    icon: "wrench.and.screwdriver",
                    title: "Bez servisních záznamů",
                    subtitle: "Historie zatím neobsahuje žádné úkony.",
                    actionTitle: "Přidat záznam"
                ) {
                    showAddRecord = true
                }
            } else {
                recordOverviewCard

                VStack(spacing: Theme.Spacing.sm) {
                    if filteredRecords.isEmpty {
                        emptyFilteredRecordsCard
                    } else {
                        ForEach(filteredRecords) { record in
                            recordCard(record)
                        }
                    }
                }
            }
        }
    }

    private var filteredRecords: [ServiceRecord] {
        viewModel.records.filter { record in
            guard selectedRecordFilter.matches(record) else { return false }

            let query = recordSearchText.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !query.isEmpty else { return true }

            let haystack = [
                record.description,
                record.note,
                record.category,
                record.price.map { String(Int($0)) },
                record.mileage.map { String($0) }
            ]
            .compactMap { $0?.lowercased() }
            .joined(separator: " ")

            return haystack.contains(query.lowercased())
        }
    }

    private var recordOverviewCard: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            HStack(spacing: Theme.Spacing.sm) {
                compactRecordMetric(
                    title: "Celkem",
                    value: "\(viewModel.records.count)",
                    subtitle: "záznamů",
                    tint: Theme.Colors.primary
                )
                compactRecordMetric(
                    title: "S cenou",
                    value: "\(viewModel.records.filter { $0.price != nil }.count)",
                    subtitle: "položek",
                    tint: Theme.Colors.warning
                )
                compactRecordMetric(
                    title: "Náklady",
                    value: formatCompactCost(viewModel.records.compactMap(\.price).reduce(0, +)),
                    subtitle: "součet",
                    tint: Theme.Colors.accent
                )
            }

            if let latestRecord = viewModel.records.sorted(by: { ($0.performedAt ?? .distantPast) > ($1.performedAt ?? .distantPast) }).first {
                HStack(spacing: Theme.Spacing.sm) {
                    Image(systemName: "clock.arrow.circlepath")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(Theme.Colors.accent)
                        .frame(width: 30, height: 30)
                        .background(Theme.Colors.accent.opacity(0.14), in: RoundedRectangle(cornerRadius: 10, style: .continuous))

                    VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                        Text("Poslední záznam")
                            .font(Theme.Typography.tiny)
                            .foregroundStyle(Theme.Colors.textSecondary)
                        Text(latestRecord.description)
                            .font(Theme.Typography.captionStrong)
                            .foregroundStyle(.white)
                            .lineLimit(1)
                        Text(latestRecord.performedAt?.formatted(date: .abbreviated, time: .omitted) ?? "Bez data")
                            .font(Theme.Typography.tiny)
                            .foregroundStyle(Theme.Colors.textSecondary)
                    }

                    Spacer(minLength: 0)
                }
                .padding(Theme.Spacing.sm)
                .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
            }

            HStack(spacing: Theme.Spacing.sm) {
                searchField
                Menu {
                    ForEach(RecordListFilter.allCases) { filter in
                        Button(filter.label) {
                            selectedRecordFilter = filter
                        }
                    }
                } label: {
                    HStack(spacing: Theme.Spacing.xs) {
                        Image(systemName: selectedRecordFilter.iconName)
                        Text(selectedRecordFilter.shortLabel)
                        Image(systemName: "chevron.down")
                            .font(.system(size: 11, weight: .semibold))
                    }
                    .font(Theme.Typography.captionStrong)
                    .foregroundStyle(Theme.Colors.textPrimary)
                    .padding(.horizontal, Theme.Spacing.sm)
                    .padding(.vertical, Theme.Spacing.sm)
                    .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
                }
                .buttonStyle(.plain)
            }

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: Theme.Spacing.xs) {
                    ForEach(RecordListFilter.allCases) { filter in
                        Button(filter.label) {
                            selectedRecordFilter = filter
                        }
                        .buttonStyle(InlineChipButtonStyle(isSelected: selectedRecordFilter == filter))
                    }
                }
            }
        }
        .hubDarkCard()
    }

    private var searchField: some View {
        HStack(spacing: Theme.Spacing.xs) {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(Theme.Colors.textSecondary)
            TextField("Hledat popis, kategorii nebo poznámku", text: $recordSearchText)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textPrimary)
            if !recordSearchText.isEmpty {
                Button {
                    recordSearchText = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(Theme.Colors.textSecondary)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, Theme.Spacing.sm)
        .padding(.vertical, Theme.Spacing.sm)
        .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
    }

    private func compactRecordMetric(title: String, value: String, subtitle: String, tint: Color) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
            Text(title)
                .font(Theme.Typography.tiny)
                .foregroundStyle(Theme.Colors.textSecondary)
            Text(value)
                .font(Theme.Typography.bodyStrong)
                .foregroundStyle(.white)
            Text(subtitle)
                .font(Theme.Typography.tiny)
                .foregroundStyle(Theme.Colors.textSecondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(Theme.Spacing.sm)
        .background(tint.opacity(0.12), in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
    }

    private var emptyFilteredRecordsCard: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Text("Vybranému filtru neodpovídá žádný záznam")
                .font(Theme.Typography.bodyStrong)
                .foregroundStyle(Theme.Colors.textOnLight)
            Text("Upravte hledání nebo přepněte filtr. Historii tím nesmažete, jen ji dočasně omezíte.")
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textOnLightSecondary)
            Button("Zobrazit vše") {
                recordSearchText = ""
                selectedRecordFilter = .all
            }
            .buttonStyle(InlineChipButtonStyle(isSelected: true))
        }
        .hubLightCard()
    }

    private func recordCard(_ record: ServiceRecord) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                    HStack(spacing: Theme.Spacing.xs) {
                        if let category = record.category, !category.isEmpty {
                            PillBadge(title: category.uppercased(), style: .neutral)
                        }
                        if record.createdByAI {
                            PillBadge(title: "AI", style: .warning)
                        }
                    }
                    Text(record.description)
                        .font(Theme.Typography.bodyStrong)
                        .foregroundStyle(Theme.Colors.textOnLight)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: Theme.Spacing.sm)

                VStack(alignment: .trailing, spacing: Theme.Spacing.xxs) {
                    Text(record.price.map(formatCompactCost) ?? "Bez ceny")
                        .font(Theme.Typography.captionStrong)
                        .foregroundStyle(Theme.Colors.textOnLight)
                    Text(record.performedAt?.formatted(date: .abbreviated, time: .omitted) ?? "Bez data")
                        .font(Theme.Typography.tiny)
                        .foregroundStyle(Theme.Colors.textOnLightSecondary)
                }
            }

            HStack(spacing: Theme.Spacing.xs) {
                miniMetaPill(icon: "gauge.with.dots.needle.33percent", text: record.mileage.map { "\($0) km" } ?? "Nájezd neuveden")
                if let nextServiceDueDate = record.nextServiceDueDate {
                    miniMetaPill(icon: "calendar", text: "Další servis \(nextServiceDueDate.formatted(date: .numeric, time: .omitted))")
                }
            }

            if let note = record.note, !note.isEmpty {
                Text(note)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colors.textOnLightSecondary)
                    .lineLimit(2)
            }

            HStack(spacing: Theme.Spacing.sm) {
                Button("Upravit") {
                    editingRecord = record
                }
                .buttonStyle(InlineChipButtonStyle(isSelected: true))

                Button("Smazat") {
                    guard let token = env.authManager.token else { return }
                    Task { await viewModel.deleteRecord(vehicleId: vehicleId, recordId: record.id, token: token) }
                }
                .buttonStyle(InlineChipButtonStyle(isSelected: false))
            }
        }
        .hubLightCard()
    }

    private func miniMetaPill(icon: String, text: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
            Text(text)
        }
        .font(Theme.Typography.tiny)
        .foregroundStyle(Theme.Colors.textOnLightSecondary)
        .padding(.horizontal, Theme.Spacing.sm)
        .padding(.vertical, 6)
        .background(Theme.Colors.lightMuted, in: Capsule())
    }

    private func formatCompactCost(_ value: Double) -> String {
        "\(Int(value.rounded())) Kč"
    }

    private func reload() async {
        guard let token = env.authManager.token else { return }
        await viewModel.load(vehicleId: vehicleId, token: token)
    }
}

struct AddServiceRecordSheet: View {
    let initial: ServiceRecord?
    let vehicleId: Int
    let onSubmit: (ServiceRecordCreateRequest) -> Void

    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var env: AppEnvironment

    private let featureService = UserFeatureService(api: APIClient())
    private let sourceTypeOptions: [DocumentSourceOption] = DocumentSourceOption.defaultOptions
    private let maxAttachmentBytes = 15 * 1024 * 1024

    @State private var performedAt = Date()
    @State private var mileage = ""
    @State private var description = ""
    @State private var price = ""
    @State private var note = ""
    @State private var category = "JINE"
    @State private var hasNextServiceDueDate = false
    @State private var nextServiceDueDate = Date()

    @State private var selectedSourceType = "invoice"
    @State private var manualDocumentText = ""
    @State private var autoPrefillEnabled = true
    @State private var pendingAttachment: PendingAttachment?
    @State private var selectedPhotoItem: PhotosPickerItem?
    @State private var showFileImporter = false
    @State private var showCameraCapture = false
    @State private var showSourceDialog = false

    @State private var isAnalyzingDocument = false
    @State private var isExtractingLocalText = false
    @State private var isSaving = false
    @State private var analysisMessage: String?
    @State private var analysisTone: AnalysisTone = .info
    @State private var analysisConfidence: Int?
    @State private var analysisFieldCount = 0
    @State private var analysisSourceLabel: String?
    @State private var formError: String?
    @State private var extractedAttachmentCacheKey: String?
    @State private var extractedAttachmentText: String?
    @State private var entryMode: RecordEntryMode?
    @State private var showTemplateNameDialog = false
    @State private var templateNameDraft = ""
    @State private var isDocumentSectionExpanded = true
    @State private var isReportSectionExpanded = false
    @State private var isItemsSectionExpanded = false
    @State private var isTotalsSectionExpanded = false
    @State private var pendingScrollTarget: EditorSectionAnchor?

    @State private var existingAttachmentObjects: [[String: Any]] = []

    @State private var reportDocumentNumber = ""
    @State private var reportSupplierName = ""
    @State private var reportSupplierEmail = ""
    @State private var reportSupplierWebsite = ""
    @State private var reportServiceLink = ""
    @State private var reportCustomerName = ""
    @State private var reportServiceSummary = ""
    @State private var reportIssueDescription = ""
    @State private var reportTechnicianName = ""
    @State private var reportTechnicianInitials = ""
    @State private var reportCurrency = "CZK"
    @State private var hasIssueDate = false
    @State private var reportIssueDate = Date()
    @State private var hasDueDate = false
    @State private var reportDueDate = Date()
    @State private var reportLaborHours = ""
    @State private var reportLaborHourRate = ""
    @State private var reportLaborTotal = ""
    @State private var reportMaterialsTotal = ""
    @State private var reportSubtotalWithoutVat = ""
    @State private var reportVatRate = ""
    @State private var reportVatAmount = ""
    @State private var reportTotalWithVat = ""
    @State private var reportItems: [ServiceReportItemDraft] = [.empty]

    init(initial: ServiceRecord? = nil, vehicleId: Int, onSubmit: @escaping (ServiceRecordCreateRequest) -> Void) {
        self.initial = initial
        self.vehicleId = vehicleId
        self.onSubmit = onSubmit
    }

    private var normalizedDescription: String {
        description.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var knownCategoryIDs: Set<String> {
        Set(categoryOptions.map(\.id))
    }

    private var categoryOptions: [ServiceCategoryOption] {
        env.recordConfigurationStore.categoryOptions
    }

    private var knownSourceTypeIDs: Set<String> {
        Set(sourceTypeOptions.map(\.id))
    }

    private var parsedMileage: Int? {
        let normalized = mileage
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "\u{00A0}", with: " ")
            .replacingOccurrences(of: " ", with: "")
        guard !normalized.isEmpty else { return nil }
        guard normalized.range(of: #"^\d+$"#, options: .regularExpression) != nil else { return nil }
        return Int(normalized)
    }

    private var effectivePrice: Double? {
        if let direct = parseOptionalNumber(price), direct >= 0 {
            return direct
        }
        if let payloadTotal = serviceReportPayload.totalWithVat, payloadTotal >= 0 {
            return payloadTotal
        }
        return nil
    }

    private var effectiveDescriptionForSave: String {
        if !normalizedDescription.isEmpty {
            return normalizedDescription
        }

        if let trustedSummary = trustedDescriptionCandidate(reportServiceSummary) {
            return trustedSummary
        }

        if let trustedIssue = trustedDescriptionCandidate(reportIssueDescription) {
            return trustedIssue
        }

        if let inferred = inferredDescription(
            from: normalizedReportItems,
            category: category,
            supplierName: reportSupplierName,
            documentNumber: reportDocumentNumber
        ) {
            return inferred
        }

        return ""
    }

    private var saveDisabled: Bool {
        isSaving || effectiveDescriptionForSave.count < 3 || effectivePrice == nil
    }

    private var effectiveEntryMode: RecordEntryMode? {
        initial == nil ? entryMode : .manual
    }

    private var showsModePicker: Bool {
        initial == nil && effectiveEntryMode != nil && effectiveEntryMode != .template
    }

    private var canSaveTemplate: Bool {
        trimToNil(description) != nil || trimToNil(reportServiceSummary) != nil || trimToNil(note) != nil
    }

    private var allTemplates: [ServiceRecordTemplate] {
        env.recordConfigurationStore.allTemplates
    }

    private var derivedTotals: ServiceReportTotals {
        let items = normalizedReportItems
        let inferred = inferLaborMaterialBreakdown(items: items)

        let laborTotal = parseOptionalNumber(reportLaborTotal) ?? inferred.laborTotal
        let materialsTotal = parseOptionalNumber(reportMaterialsTotal) ?? inferred.materialsTotal
        let subtotal = parseOptionalNumber(reportSubtotalWithoutVat) ?? {
            let value = (laborTotal ?? 0) + (materialsTotal ?? 0)
            return value > 0 ? roundTo2(value) : nil
        }()

        let vatAmount: Double? = {
            if let manual = parseOptionalNumber(reportVatAmount) {
                return roundTo2(manual)
            }
            if let vatRate = parseOptionalNumber(reportVatRate), let subtotal, subtotal > 0 {
                return roundTo2(subtotal * vatRate / 100.0)
            }
            return nil
        }()

        let total: Double? = {
            if let manual = parseOptionalNumber(reportTotalWithVat) {
                return roundTo2(manual)
            }
            let value = (subtotal ?? 0) + (vatAmount ?? 0)
            return value > 0 ? roundTo2(value) : nil
        }()

        return ServiceReportTotals(
            laborTotal: laborTotal.map(roundTo2),
            materialsTotal: materialsTotal.map(roundTo2),
            subtotalWithoutVat: subtotal.map(roundTo2),
            vatAmount: vatAmount.map(roundTo2),
            totalWithVat: total.map(roundTo2)
        )
    }

    private var normalizedReportItems: [ServiceReportItemPayload] {
        let currency = reportCurrency.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "CZK" : reportCurrency.uppercased()
        return reportItems.compactMap { row in
            let name = row.name.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !name.isEmpty else { return nil }
            let quantity = parseOptionalNumber(row.quantity)
            let unitPrice = parseOptionalNumber(row.unitPrice)
            let totalPrice = parseOptionalNumber(row.totalPrice) ?? {
                guard let quantity, let unitPrice else { return nil }
                return roundTo2(quantity * unitPrice)
            }()
            let unit = row.unit.trimmingCharacters(in: .whitespacesAndNewlines)
            return ServiceReportItemPayload(
                name: name,
                quantity: quantity,
                unit: unit.isEmpty ? nil : unit,
                unitPrice: unitPrice,
                totalPrice: totalPrice,
                currency: currency
            )
        }
    }

    private var prefillHighlights: [(title: String, value: String)] {
        var rows: [(String, String)] = []
        if let supplier = trimToNil(reportSupplierName) {
            rows.append(("Dodavatel", supplier))
        }
        if let docNo = trimToNil(reportDocumentNumber) {
            rows.append(("Doklad", docNo))
        }
        if let value = parseOptionalNumber(price) {
            rows.append(("Cena", formatMoney(value)))
        } else if let value = serviceReportPayload.totalWithVat {
            rows.append(("Cena", formatMoney(value)))
        }
        if let km = parsedMileage {
            rows.append(("Nájezd", "\(km) km"))
        }
        if let summary = meaningfulServiceField(reportServiceSummary) {
            rows.append(("Rozsah", summary))
        }
        return Array(rows.prefix(5))
    }

    private var scanChecklistRows: [ScanChecklistRow] {
        [
            ScanChecklistRow(
                title: "Doklad",
                value: pendingAttachment?.fileName ?? "Chybí příloha",
                isComplete: pendingAttachment != nil,
                accent: Theme.Colors.accent
            ),
            ScanChecklistRow(
                title: "Dodavatel",
                value: trimToNil(reportSupplierName) ?? "Doplňte servis nebo firmu",
                isComplete: trimToNil(reportSupplierName) != nil,
                accent: Theme.Colors.primary
            ),
            ScanChecklistRow(
                title: "Číslo dokladu",
                value: trimToNil(reportDocumentNumber) ?? "Doplňte číslo dokladu",
                isComplete: trimToNil(reportDocumentNumber) != nil,
                accent: Theme.Colors.warning
            ),
            ScanChecklistRow(
                title: "Cena",
                value: effectivePrice.map(formatMoney) ?? "Doplňte cenu",
                isComplete: effectivePrice != nil,
                accent: Theme.Colors.primaryDark
            ),
            ScanChecklistRow(
                title: "Popis úkonu",
                value: effectiveDescriptionForSave.isEmpty ? "Upřesněte, co se na vozidle dělalo" : effectiveDescriptionForSave,
                isComplete: !effectiveDescriptionForSave.isEmpty,
                accent: Theme.Colors.accent
            )
        ]
    }

    private var scanCompletionRatio: Double {
        guard !scanChecklistRows.isEmpty else { return 0 }
        let completed = scanChecklistRows.filter(\.isComplete).count
        return Double(completed) / Double(scanChecklistRows.count)
    }

    private var manualQuickPresets: [ManualQuickPreset] {
        [
            ManualQuickPreset(
                id: "oil-service",
                title: "Olej + filtry",
                subtitle: "Pravidelná údržba",
                categoryID: "OLEJ",
                description: "Výměna motorového oleje a filtrů",
                summary: "Olej, olejový filtr a základní kontrola vozu",
                note: "Zkontrolovat kapaliny a servisní interval.",
                items: [
                    .init(name: "Motorový olej", quantity: "1", unit: "set", unitPrice: "", totalPrice: ""),
                    .init(name: "Olejový filtr", quantity: "1", unit: "ks", unitPrice: "", totalPrice: "")
                ]
            ),
            ManualQuickPreset(
                id: "tyres",
                title: "Pneuservis",
                subtitle: "Přezutí a vyvážení",
                categoryID: "PNEU",
                description: "Pneuservis",
                summary: "Přezutí kol, vyvážení a kontrola vzorku",
                note: "Dopsat tlak a stav pneumatik.",
                items: [
                    .init(name: "Přezutí kol", quantity: "1", unit: "úkon", unitPrice: "", totalPrice: ""),
                    .init(name: "Vyvážení", quantity: "4", unit: "ks", unitPrice: "", totalPrice: "")
                ]
            ),
            ManualQuickPreset(
                id: "brakes",
                title: "Brzdy",
                subtitle: "Destičky a kontrola",
                categoryID: "BRZDY",
                description: "Servis brzdové soustavy",
                summary: "Kontrola brzd, destiček a kotoučů",
                note: "Doplnit tloušťku destiček po servisu.",
                items: [
                    .init(name: "Brzdové destičky", quantity: "1", unit: "sada", unitPrice: "", totalPrice: ""),
                    .init(name: "Práce na brzdách", quantity: "1", unit: "úkon", unitPrice: "", totalPrice: "")
                ]
            ),
            ManualQuickPreset(
                id: "diagnostics",
                title: "Diagnostika",
                subtitle: "Kontrola chyb",
                categoryID: "DIAGNOSTIKA",
                description: "Diagnostika vozidla",
                summary: "Načtení chybových hlášení a základní testy",
                note: "Zapsat výsledek diagnostiky a doporučení.",
                items: []
            )
        ]
    }

    private var scanReviewFields: [ScanReviewField] {
        [
            ScanReviewField(
                title: "Dodavatel",
                value: trimToNil(reportSupplierName),
                placeholder: "Doplňte servis nebo firmu",
                status: trimToNil(reportSupplierName) != nil ? .ready : .missing,
                icon: "building.2.crop.circle",
                accent: Theme.Colors.primary,
                actionTitle: "Servisní zpráva",
                action: {
                    focusEditorSection(.report)
                }
            ),
            ScanReviewField(
                title: "Číslo dokladu",
                value: trimToNil(reportDocumentNumber),
                placeholder: "Zkontrolujte číslo faktury",
                status: trimToNil(reportDocumentNumber) != nil ? .ready : .missing,
                icon: "number.circle",
                accent: Theme.Colors.warning,
                actionTitle: "Servisní zpráva",
                action: {
                    focusEditorSection(.report)
                }
            ),
            ScanReviewField(
                title: "Cena",
                value: effectivePrice.map(formatMoney),
                placeholder: "Doplňte cenu z dokladu",
                status: effectivePrice != nil ? .ready : .missing,
                icon: "banknote",
                accent: Theme.Colors.primaryDark,
                actionTitle: "Součty",
                action: {
                    focusEditorSection(.totals)
                }
            ),
            ScanReviewField(
                title: "Popis úkonu",
                value: trimToNil(effectiveDescriptionForSave),
                placeholder: "Doplňte stručný popis úkonu",
                status: trimToNil(effectiveDescriptionForSave) != nil ? .ready : .missing,
                icon: "text.alignleft",
                accent: Theme.Colors.accent,
                actionTitle: "Základní údaje",
                action: {
                    focusEditorSection(.basic)
                }
            ),
            ScanReviewField(
                title: "Položky",
                value: normalizedReportItems.isEmpty ? nil : "\(normalizedReportItems.count) položek",
                placeholder: "Zkontrolujte rozepsané položky",
                status: normalizedReportItems.isEmpty ? .missing : .ready,
                icon: "list.bullet.rectangle",
                accent: Theme.Colors.accent,
                actionTitle: "Položky",
                action: {
                    focusEditorSection(.items)
                }
            )
        ]
    }

    private func attachmentCacheKey(for attachment: PendingAttachment) -> String {
        let fingerprint = attachment.data.prefix(32).base64EncodedString()
        return "\(attachment.fileName)|\(attachment.mimeType)|\(attachment.data.count)|\(fingerprint)"
    }

    private func cachedExtractedText(for attachment: PendingAttachment) -> String? {
        guard extractedAttachmentCacheKey == attachmentCacheKey(for: attachment) else { return nil }
        return extractedAttachmentText
    }

    @MainActor
    private func storeExtractedText(_ text: String?, for attachment: PendingAttachment) {
        extractedAttachmentCacheKey = attachmentCacheKey(for: attachment)
        extractedAttachmentText = text
    }

    private func canonicalWebsiteIdentity(_ raw: String?) -> String? {
        guard let normalized = meaningfulWebsite(raw) else { return nil }
        var candidate = normalized.lowercased()
        if candidate.hasPrefix("https://") {
            candidate.removeFirst(8)
        } else if candidate.hasPrefix("http://") {
            candidate.removeFirst(7)
        }
        if candidate.hasPrefix("www.") {
            candidate.removeFirst(4)
        }
        if let slash = candidate.firstIndex(of: "/") {
            candidate = String(candidate[..<slash])
        }
        if let question = candidate.firstIndex(of: "?") {
            candidate = String(candidate[..<question])
        }
        return candidate.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    }

    private var serviceReportPayload: ServiceReportPayload {
        let totals = derivedTotals
        return ServiceReportPayload(
            sourceType: selectedSourceType,
            documentNumber: trimToNil(reportDocumentNumber),
            supplierName: trimToNil(reportSupplierName),
            supplierEmail: trimToNil(reportSupplierEmail),
            supplierWebsite: trimToNil(reportSupplierWebsite),
            serviceLink: normalizeServiceLink(trimToNil(reportServiceLink)),
            customerName: trimToNil(reportCustomerName),
            serviceSummary: trimToNil(reportServiceSummary),
            issueDescription: trimToNil(reportIssueDescription),
            technicianName: trimToNil(reportTechnicianName),
            technicianInitials: trimToNil(reportTechnicianInitials),
            issueDate: hasIssueDate ? isoDateString(reportIssueDate) : nil,
            dueDate: hasDueDate ? isoDateString(reportDueDate) : nil,
            currency: trimToNil(reportCurrency)?.uppercased() ?? "CZK",
            laborHours: parseOptionalNumber(reportLaborHours),
            laborHourRate: parseOptionalNumber(reportLaborHourRate),
            laborTotal: totals.laborTotal,
            materialsTotal: totals.materialsTotal,
            subtotalWithoutVat: totals.subtotalWithoutVat,
            vatRate: parseOptionalNumber(reportVatRate),
            vatAmount: totals.vatAmount,
            totalWithVat: totals.totalWithVat,
            items: normalizedReportItems
        )
    }

    var body: some View {
        NavigationStack {
            Group {
                if initial == nil, effectiveEntryMode == nil {
                    entryModeSelectionView
                } else if effectiveEntryMode == .template {
                    templateLibraryView
                } else {
                    editorView
                }
            }
            .navigationTitle(initial == nil ? "Nový záznam" : "Upravit záznam")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Zrušit") { dismiss() }
                        .disabled(isSaving)
                }
                if effectiveEntryMode == .manual || effectiveEntryMode == .scan || initial != nil {
                    ToolbarItem(placement: .confirmationAction) {
                        Button {
                            Task { await saveRecord() }
                        } label: {
                            if isSaving {
                                ProgressView()
                                    .tint(.accentColor)
                            } else {
                                Text("Uložit")
                            }
                        }
                        .disabled(saveDisabled)
                    }
                }
            }
            .onAppear {
                loadInitial()
            }
            .confirmationDialog("Přidat doklad", isPresented: $showSourceDialog, titleVisibility: .visible) {
                Button("Vyfotit doklad") {
                    showCameraCapture = true
                }
                Button("Vybrat soubor") {
                    showFileImporter = true
                }
                Button("Zrušit", role: .cancel) {}
            }
            .fileImporter(
                isPresented: $showFileImporter,
                allowedContentTypes: [.pdf, .image, .plainText, .utf8PlainText, .commaSeparatedText, .json, .xml],
                allowsMultipleSelection: false
            ) { result in
                handleFileImportResult(result)
            }
            .fullScreenCover(isPresented: $showCameraCapture) {
                ServiceRecordCameraCapture { attachment in
                    showCameraCapture = false
                    handlePendingAttachment(attachment)
                } onCancel: {
                    showCameraCapture = false
                }
            }
            .alert("Uložit vlastní šablonu", isPresented: $showTemplateNameDialog) {
                TextField("Název šablony", text: $templateNameDraft)
                Button("Uložit") {
                    saveCurrentAsTemplate()
                }
                Button("Zrušit", role: .cancel) {
                    templateNameDraft = ""
                }
            } message: {
                Text("Uloží aktuální rozpracovaný formulář jako vlastní šablonu.")
            }
            .onChange(of: selectedPhotoItem) { _, newValue in
                guard let newValue else { return }
                Task { await handlePhotoPickerItem(newValue) }
            }
        }
    }

    private var entryModeSelectionView: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                    Text("Vyberte způsob vložení")
                        .font(Theme.Typography.sectionTitle)
                        .foregroundStyle(Theme.Colors.textPrimary)
                    Text("Každý režim otevře jiný tok práce. Ruční je detailní, sken je rychlý a šablony zrychlí opakované úkony.")
                        .font(Theme.Typography.body)
                        .foregroundStyle(Theme.Colors.textSecondary)
                }
                .padding(.top, Theme.Spacing.sm)

                VStack(spacing: Theme.Spacing.md) {
                    entryModeCard(
                        mode: .manual,
                        title: "Ruční zadání",
                        subtitle: "Detailní formulář pro servis, opravu i vlastní poznámky",
                        points: ["volná pole", "více položek", "vlastní součty"],
                        tint: Theme.Colors.primary
                    )

                    entryModeCard(
                        mode: .scan,
                        title: "Skenování dokladu",
                        subtitle: "Vyfoťte nebo nahrajte doklad a nechte formulář předvyplnit",
                        points: ["OCR předvyplnění", "kontrola polí", "rychlé doplnění"],
                        tint: Theme.Colors.accent
                    )

                    entryModeCard(
                        mode: .template,
                        title: "Šablony",
                        subtitle: "Předpřipravené scénáře a vlastní šablony pro opakované úkony",
                        points: ["olej", "pneuservis", "vlastní šablony"],
                        tint: Theme.Colors.warning
                    )
                }
            }
            .padding(Theme.Spacing.md)
            .padding(.bottom, Theme.Spacing.xxl)
        }
        .hubPageBackground()
    }

    private var templateLibraryView: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                templateHeroCard

                if !env.recordConfigurationStore.customTemplates.isEmpty {
                    editorSection(title: "Moje šablony", subtitle: "Vlastní připravené zápisy") {
                        VStack(spacing: Theme.Spacing.sm) {
                            ForEach(env.recordConfigurationStore.customTemplates) { template in
                                templateRow(template, isCustom: true)
                            }
                        }
                    }
                }

                editorSection(title: "Předpřipravené", subtitle: "Nejčastější servisní scénáře") {
                    VStack(spacing: Theme.Spacing.sm) {
                        ForEach(ServiceRecordTemplate.presets) { template in
                            templateRow(template, isCustom: false)
                        }
                    }
                }

                Button {
                    configureSectionVisibility(for: .manual)
                    entryMode = .manual
                } label: {
                    Label("Začít bez šablony", systemImage: "square.and.pencil")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(SecondaryActionButtonStyle())
            }
            .padding(Theme.Spacing.md)
            .padding(.bottom, Theme.Spacing.xxl)
        }
        .hubPageBackground()
    }

    private var editorView: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                    editorHeroCard

                    editorProgressCard

                    if showsModePicker {
                        modePickerRow
                    }

                    if effectiveEntryMode == .scan {
                        documentSectionCard
                        basicDataSectionCard
                    } else {
                        basicDataSectionCard
                        documentSectionCard
                    }

                    reportSectionCard
                    itemsSectionCard
                    totalsSectionCard

                    if canSaveTemplate && initial == nil {
                        editorSection(title: "Šablony", subtitle: "Uložte si tento rozpis pro příště") {
                            Button {
                                templateNameDraft = trustedTemplateNameSeed()
                                showTemplateNameDialog = true
                            } label: {
                                Label("Uložit aktuální formulář jako šablonu", systemImage: "square.stack.badge.plus")
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(SecondaryActionButtonStyle())
                        }
                    }

                    if let formError {
                        editorSection(title: "Chyba", subtitle: "Záznam nelze uložit") {
                            Text(formError)
                                .font(Theme.Typography.body)
                                .foregroundStyle(Theme.Colors.danger)
                        }
                    }
                }
                .padding(Theme.Spacing.md)
                .padding(.bottom, Theme.Spacing.xxl)
            }
            .onChange(of: pendingScrollTarget) { _, target in
                guard let target else { return }
                withAnimation(.easeInOut(duration: 0.24)) {
                    proxy.scrollTo(target, anchor: .top)
                }
                DispatchQueue.main.async {
                    pendingScrollTarget = nil
                }
            }
        }
        .hubPageBackground()
    }

    private var templateHeroCard: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Text("Šablony záznamů")
                .font(Theme.Typography.cardTitle)
                .foregroundStyle(Theme.Colors.textPrimary)
            Text("Vyberte hotový základ a potom ho jen upravte podle konkrétního zásahu.")
                .font(Theme.Typography.body)
                .foregroundStyle(Theme.Colors.textSecondary)
        }
        .hubDarkCard()
    }

    private var editorHeroCard: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Text(editorHeroTitle)
                .font(Theme.Typography.cardTitle)
                .foregroundStyle(Theme.Colors.textPrimary)
            Text(editorHeroSubtitle)
                .font(Theme.Typography.body)
                .foregroundStyle(Theme.Colors.textSecondary)

            if effectiveEntryMode == .scan, pendingAttachment == nil {
                Button {
                    showSourceDialog = true
                } label: {
                    Label("Přidat doklad hned teď", systemImage: "doc.viewfinder")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(PrimaryActionButtonStyle())
                .padding(.top, Theme.Spacing.xs)
            }
        }
        .hubDarkCard()
    }

    private var editorProgressCard: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                    Text("Pracovní stav")
                        .font(Theme.Typography.captionStrong)
                        .foregroundStyle(Theme.Colors.textPrimary)
                    Text(editorProgressSubtitle)
                        .font(Theme.Typography.tiny)
                        .foregroundStyle(Theme.Colors.textSecondary)
                }

                Spacer(minLength: 0)

                analysisChip("\(Int((editorCompletionRatio * 100).rounded())) %", color: editorCompletionRatio >= 0.8 ? Theme.Colors.primary : Theme.Colors.warning)
            }

            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Theme.Colors.hairline.opacity(0.65))
                    Capsule()
                        .fill(
                            LinearGradient(
                                colors: [Theme.Colors.primary, Theme.Colors.accent],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                        .frame(width: max(18, geometry.size.width * editorCompletionRatio))
                }
            }
            .frame(height: 8)

            HStack(spacing: Theme.Spacing.xs) {
                editorStatePill(icon: "doc.text", text: pendingAttachment == nil ? "Bez dokladu" : "Doklad připraven", active: pendingAttachment != nil)
                editorStatePill(icon: "text.alignleft", text: effectiveDescriptionForSave.isEmpty ? "Chybí popis" : "Popis připraven", active: !effectiveDescriptionForSave.isEmpty)
                editorStatePill(icon: "banknote", text: effectivePrice == nil ? "Chybí cena" : "Cena připravena", active: effectivePrice != nil)
            }

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: Theme.Spacing.xs) {
                    editorJumpChip("Základ", target: .basic)
                    editorJumpChip("Doklad", target: .document)
                    editorJumpChip("Servisní zpráva", target: .report)
                    editorJumpChip("Položky", target: .items)
                    editorJumpChip("Součty", target: .totals)
                }
            }
        }
        .hubDarkCard()
    }

    private var modePickerRow: some View {
        HStack(spacing: Theme.Spacing.sm) {
            modeChip("Ruční", mode: .manual)
            modeChip("Sken", mode: .scan)
            modeChip("Šablony", mode: .template)
        }
    }

    private var basicDataSectionCard: some View {
        editorSection(title: "Základní údaje", subtitle: "Jádro servisního záznamu") {
            VStack(spacing: Theme.Spacing.sm) {
                if effectiveEntryMode == .manual && initial == nil {
                    manualPresetStrip
                }

                cardPickerRow("Kategorie", selection: $category) {
                    ForEach(categoryOptions) { option in
                        Text("\(option.icon) \(option.label)").tag(option.id)
                    }
                }

                HStack(spacing: Theme.Spacing.sm) {
                    labeledCompactDate("Datum", selection: $performedAt, components: .date)
                    labeledCompactDate("Čas", selection: $performedAt, components: .hourAndMinute)
                }

                cardTextField("Popis úkonu", text: $description, prompt: "Např. výměna oleje a filtru")
                cardTextField("Nájezd (km)", text: $mileage, prompt: "Zadejte aktuální stav tachometru", keyboard: .numberPad)
                cardTextField("Cena (Kč)", text: $price, prompt: "Celková cena nebo odhad", keyboard: .decimalPad)
                cardTextField("Poznámka", text: $note, prompt: "Volitelné poznámky", axis: .vertical)

                Toggle("Nastavit příští servis", isOn: $hasNextServiceDueDate)
                    .tint(Theme.Colors.primary)

                if hasNextServiceDueDate {
                    labeledCompactDate("Příští servis", selection: $nextServiceDueDate, components: .date)
                }
            }
        }
        .id(EditorSectionAnchor.basic)
    }

    private var documentSectionCard: some View {
        editorSection(
            title: "Doklad a automatické vyčtení",
            subtitle: "Fotka nebo soubor pro OCR předvyplnění",
            isExpanded: $isDocumentSectionExpanded
        ) {
            VStack(spacing: Theme.Spacing.sm) {
                cardPickerRow("Typ dokladu", selection: $selectedSourceType) {
                    ForEach(sourceTypeOptions) { option in
                        Text(option.label).tag(option.id)
                    }
                }

                Toggle("Automaticky předvyplnit formulář", isOn: $autoPrefillEnabled)
                    .tint(Theme.Colors.primary)

                HStack(spacing: Theme.Spacing.sm) {
                    Button {
                        showSourceDialog = true
                    } label: {
                        Label("Vyfotit nebo vložit doklad", systemImage: "doc.badge.plus")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(PrimaryActionButtonStyle())

                    PhotosPicker(selection: $selectedPhotoItem, matching: .images) {
                        Label("Galerie", systemImage: "photo")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(SecondaryActionButtonStyle())
                }

                if let pendingAttachment {
                    VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                        HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                            Image(systemName: "doc.text.viewfinder")
                                .font(.system(size: 16, weight: .semibold))
                                .foregroundStyle(Theme.Colors.accent)
                                .frame(width: 34, height: 34)
                                .background(Theme.Colors.accent.opacity(0.14), in: RoundedRectangle(cornerRadius: 10, style: .continuous))

                            VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                                Text(pendingAttachment.fileName)
                                    .font(Theme.Typography.captionStrong)
                                    .foregroundStyle(Theme.Colors.textPrimary)
                                    .lineLimit(2)
                                Text("\(pendingAttachment.sourceLabel) • \(pendingAttachment.mimeType) • \(pendingAttachment.sizeDescription)")
                                    .font(Theme.Typography.tiny)
                                    .foregroundStyle(Theme.Colors.textSecondary)
                            }

                            Spacer(minLength: Theme.Spacing.xs)

                            Button(role: .destructive) {
                                self.pendingAttachment = nil
                                self.analysisMessage = nil
                                self.analysisConfidence = nil
                                self.analysisFieldCount = 0
                                self.analysisSourceLabel = nil
                            } label: {
                                Image(systemName: "trash")
                            }
                            .buttonStyle(.plain)
                        }

                        if isExtractingLocalText {
                            statusLine("Lokálně čtu text z dokumentu…", color: Theme.Colors.accent, icon: "text.viewfinder")
                        }

                        if autoPrefillEnabled {
                            Button {
                                Task { await analyzeAttachment() }
                            } label: {
                                HStack {
                                    if isAnalyzingDocument {
                                        ProgressView()
                                            .tint(Theme.Colors.textOnLight)
                                    }
                                    Text("Načíst data z dokladu")
                                        .frame(maxWidth: .infinity)
                                }
                            }
                            .buttonStyle(PrimaryActionButtonStyle())
                            .disabled(isAnalyzingDocument || isSaving)
                        }
                    }
                    .padding(Theme.Spacing.sm)
                    .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
                }

                if !prefillHighlights.isEmpty {
                    VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                        statusLine("Vyčtené hodnoty", color: Theme.Colors.primary, icon: "checkmark.seal.fill")
                        LazyVGrid(
                            columns: [
                                GridItem(.flexible(minimum: 120), spacing: Theme.Spacing.sm),
                                GridItem(.flexible(minimum: 120), spacing: Theme.Spacing.sm)
                            ],
                            spacing: Theme.Spacing.sm
                        ) {
                            ForEach(prefillHighlights, id: \.title) { row in
                                VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                                    Text(row.title.uppercased())
                                        .font(Theme.Typography.tiny)
                                        .foregroundStyle(Theme.Colors.textSecondary)
                                    Text(row.value)
                                        .font(Theme.Typography.captionStrong)
                                        .foregroundStyle(Theme.Colors.textPrimary)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                                .frame(maxWidth: .infinity, minHeight: 56, alignment: .leading)
                                .padding(Theme.Spacing.sm)
                                .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
                            }
                        }
                    }
                }

                if effectiveEntryMode == .scan {
                    scanReviewChecklistCard
                    scanFieldReviewCard
                }

                if let analysisMessage, shouldShowDocumentAnalysisStatus {
                    documentAnalysisStatusCard(message: analysisMessage)
                }
            }
        }
        .id(EditorSectionAnchor.document)
    }

    private var reportSectionCard: some View {
        editorSection(
            title: "Servisní zpráva",
            subtitle: "Dodavatel, doklad a základní kontext práce",
            isExpanded: $isReportSectionExpanded
        ) {
            VStack(spacing: Theme.Spacing.sm) {
                cardTextField("Dodavatel / servis", text: $reportSupplierName, prompt: "Název servisu")
                cardTextField("Kontakt servisu", text: $reportSupplierEmail, prompt: "E-mail", textInputAutocapitalization: .never, disableAutocorrection: true)
                cardTextField("Web servisu", text: $reportSupplierWebsite, prompt: "https://...", textInputAutocapitalization: .never, disableAutocorrection: true)
                cardTextField("Odkaz na servis", text: $reportServiceLink, prompt: "Specifický odkaz na zakázku", textInputAutocapitalization: .never, disableAutocorrection: true)
                cardTextField("Odběratel", text: $reportCustomerName, prompt: "Jméno nebo firma")
                cardTextField("Číslo dokladu", text: $reportDocumentNumber, prompt: "Číslo faktury nebo zakázky")
                cardTextField("Rozsah prací", text: $reportServiceSummary, prompt: "Např. výměna pneu + geometrie", axis: .vertical)
                cardTextField("Popis závady", text: $reportIssueDescription, prompt: "Co se řešilo", axis: .vertical)
                cardTextField("Technik", text: $reportTechnicianName, prompt: "Jméno technika")
                cardTextField("Iniciály technika", text: $reportTechnicianInitials, prompt: "Např. TS")
                cardTextField("Měna", text: $reportCurrency, prompt: "CZK", textInputAutocapitalization: .characters, disableAutocorrection: true)

                Toggle("Datum dokladu", isOn: $hasIssueDate)
                    .tint(Theme.Colors.primary)
                if hasIssueDate {
                    labeledCompactDate("Datum vystavení", selection: $reportIssueDate, components: .date)
                }

                Toggle("Splatnost", isOn: $hasDueDate)
                    .tint(Theme.Colors.primary)
                if hasDueDate {
                    labeledCompactDate("Datum splatnosti", selection: $reportDueDate, components: .date)
                }
            }
        }
        .id(EditorSectionAnchor.report)
    }

    private var itemsSectionCard: some View {
        editorSection(
            title: "Položky",
            subtitle: "Materiál a práce po jednotlivých řádcích",
            isExpanded: $isItemsSectionExpanded
        ) {
            VStack(spacing: Theme.Spacing.sm) {
                ForEach(Array(reportItems.enumerated()), id: \.element.id) { index, _ in
                    VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                        cardTextField("Položka", text: Binding(
                            get: { reportItems[safe: index]?.name ?? "" },
                            set: { newValue in
                                guard reportItems.indices.contains(index) else { return }
                                reportItems[index].name = newValue
                            }
                        ), prompt: "Např. olejový filtr")

                        HStack(spacing: Theme.Spacing.sm) {
                            cardTextField("Počet", text: Binding(
                                get: { reportItems[safe: index]?.quantity ?? "" },
                                set: { newValue in
                                    guard reportItems.indices.contains(index) else { return }
                                    reportItems[index].quantity = newValue
                                }
                            ), prompt: "1", keyboard: .decimalPad)

                            cardTextField("Jedn.", text: Binding(
                                get: { reportItems[safe: index]?.unit ?? "" },
                                set: { newValue in
                                    guard reportItems.indices.contains(index) else { return }
                                    reportItems[index].unit = newValue
                                }
                            ), prompt: "ks")
                        }

                        HStack(spacing: Theme.Spacing.sm) {
                            cardTextField("Cena/ks", text: Binding(
                                get: { reportItems[safe: index]?.unitPrice ?? "" },
                                set: { newValue in
                                    guard reportItems.indices.contains(index) else { return }
                                    reportItems[index].unitPrice = newValue
                                }
                            ), prompt: "0", keyboard: .decimalPad)

                            cardTextField("Celkem", text: Binding(
                                get: { reportItems[safe: index]?.totalPrice ?? "" },
                                set: { newValue in
                                    guard reportItems.indices.contains(index) else { return }
                                    reportItems[index].totalPrice = newValue
                                }
                            ), prompt: "0", keyboard: .decimalPad)
                        }

                        if reportItems.count > 1 {
                            Button(role: .destructive) {
                                reportItems.remove(at: index)
                            } label: {
                                Label("Smazat položku", systemImage: "trash")
                            }
                            .buttonStyle(.plain)
                            .foregroundStyle(Theme.Colors.danger)
                        }
                    }
                    .padding(Theme.Spacing.sm)
                    .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
                }

                Button {
                    reportItems.append(.empty)
                } label: {
                    Label("Přidat položku", systemImage: "plus.circle")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(SecondaryActionButtonStyle())
            }
        }
        .id(EditorSectionAnchor.items)
    }

    private var totalsSectionCard: some View {
        editorSection(
            title: "Součty",
            subtitle: "Rozpad práce, materiálu a DPH",
            isExpanded: $isTotalsSectionExpanded
        ) {
            VStack(spacing: Theme.Spacing.sm) {
                cardTextField("Hodiny práce", text: $reportLaborHours, prompt: "0", keyboard: .decimalPad)
                cardTextField("Sazba práce / hod", text: $reportLaborHourRate, prompt: "0", keyboard: .decimalPad)
                cardTextField("DPH %", text: $reportVatRate, prompt: "21", keyboard: .decimalPad)
                cardTextField("Práce celkem", text: $reportLaborTotal, prompt: "0", keyboard: .decimalPad)
                cardTextField("Materiál celkem", text: $reportMaterialsTotal, prompt: "0", keyboard: .decimalPad)
                cardTextField("Základ bez DPH", text: $reportSubtotalWithoutVat, prompt: "0", keyboard: .decimalPad)
                cardTextField("DPH částka", text: $reportVatAmount, prompt: "0", keyboard: .decimalPad)
                cardTextField("Celkem s DPH", text: $reportTotalWithVat, prompt: "0", keyboard: .decimalPad)

                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    Text("Vypočtené součty")
                        .font(Theme.Typography.captionStrong)
                        .foregroundStyle(Theme.Colors.textSecondary)
                    totalLine("Materiál", value: derivedTotals.materialsTotal)
                    totalLine("Práce", value: derivedTotals.laborTotal)
                    totalLine("Základ", value: derivedTotals.subtotalWithoutVat)
                    totalLine("DPH", value: derivedTotals.vatAmount)
                    totalLine("Celkem", value: derivedTotals.totalWithVat, emphasize: true)
                }
                .padding(Theme.Spacing.sm)
                .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
            }
        }
        .id(EditorSectionAnchor.totals)
    }

    private func entryModeCard(
        mode: RecordEntryMode,
        title: String,
        subtitle: String,
        points: [String],
        tint: Color
    ) -> some View {
        Button {
            configureSectionVisibility(for: mode)
            entryMode = mode
        } label: {
            VStack(alignment: .leading, spacing: Theme.Spacing.md) {
                HStack {
                    Image(systemName: mode.iconName)
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(tint)
                        .frame(width: 42, height: 42)
                        .background(tint.opacity(0.16), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    Spacer()
                    Image(systemName: "arrow.right")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(Theme.Colors.textSecondary)
                }

                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    Text(title)
                        .font(Theme.Typography.cardTitle)
                        .foregroundStyle(Theme.Colors.textPrimary)
                    Text(subtitle)
                        .font(Theme.Typography.body)
                        .foregroundStyle(Theme.Colors.textSecondary)
                }

                HStack(spacing: Theme.Spacing.xs) {
                    ForEach(points, id: \.self) { point in
                        Text(point)
                            .font(Theme.Typography.tiny)
                            .foregroundStyle(Theme.Colors.textPrimary)
                            .padding(.horizontal, Theme.Spacing.sm)
                            .padding(.vertical, Theme.Spacing.xs)
                            .background(Theme.Colors.elevated, in: Capsule())
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .buttonStyle(.plain)
        .hubDarkCard()
    }

    private func templateRow(_ template: ServiceRecordTemplate, isCustom: Bool) -> some View {
        HStack(alignment: .top, spacing: Theme.Spacing.sm) {
            Text(template.icon)
                .font(.system(size: 24))
                .frame(width: 42, height: 42)
                .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: 12, style: .continuous))

            VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                Text(template.name)
                    .font(Theme.Typography.bodyStrong)
                    .foregroundStyle(Theme.Colors.textPrimary)
                if let subtitle = trimToNil(template.templateDescription) {
                    Text(subtitle)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textSecondary)
                }
                Text(categoryOptions.first(where: { $0.id == template.category })?.label ?? template.category)
                    .font(Theme.Typography.tiny)
                    .foregroundStyle(Theme.Colors.accent)
            }

            Spacer()

            VStack(alignment: .trailing, spacing: Theme.Spacing.xs) {
                Button("Použít") {
                    applyTemplate(template)
                }
                .buttonStyle(InlineChipButtonStyle(isSelected: true))

                if isCustom {
                    Button(role: .destructive) {
                        deleteCustomTemplate(template)
                    } label: {
                        Image(systemName: "trash")
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(Theme.Colors.danger)
                }
            }
        }
        .padding(Theme.Spacing.sm)
        .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
    }

    private func editorSection<Content: View>(
        title: String,
        subtitle: String? = nil,
        isExpanded: Binding<Bool>? = nil,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            if let isExpanded {
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        isExpanded.wrappedValue.toggle()
                    }
                } label: {
                    HStack(spacing: Theme.Spacing.sm) {
                        VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                            Text(title)
                                .font(Theme.Typography.headline)
                                .foregroundStyle(Theme.Colors.textPrimary)
                            if let subtitle {
                                Text(subtitle)
                                    .font(Theme.Typography.caption)
                                    .foregroundStyle(Theme.Colors.textSecondary)
                            }
                        }

                        Spacer(minLength: 0)

                        Image(systemName: isExpanded.wrappedValue ? "chevron.up" : "chevron.down")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(Theme.Colors.textSecondary)
                            .frame(width: 28, height: 28)
                            .background(Theme.Colors.elevated, in: Circle())
                    }
                }
                .buttonStyle(.plain)
            } else {
                VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                    Text(title)
                        .font(Theme.Typography.headline)
                        .foregroundStyle(Theme.Colors.textPrimary)
                    if let subtitle {
                        Text(subtitle)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.textSecondary)
                    }
                }
            }

            if isExpanded?.wrappedValue ?? true {
                content()
            }
        }
        .hubDarkCard()
    }

    private func modeChip(_ title: String, mode: RecordEntryMode) -> some View {
        Button(title) {
            configureSectionVisibility(for: mode)
            entryMode = mode
        }
        .buttonStyle(InlineChipButtonStyle(isSelected: effectiveEntryMode == mode))
    }

    private func editorJumpChip(_ title: String, target: EditorSectionAnchor) -> some View {
        Button(title) {
            focusEditorSection(target)
        }
        .buttonStyle(InlineChipButtonStyle(isSelected: false))
    }

    private func editorStatePill(icon: String, text: String, active: Bool) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
            Text(text)
                .lineLimit(1)
        }
        .font(Theme.Typography.tiny)
        .foregroundStyle(active ? Theme.Colors.textPrimary : Theme.Colors.textSecondary)
        .padding(.horizontal, Theme.Spacing.sm)
        .padding(.vertical, 6)
        .background((active ? Theme.Colors.primary.opacity(0.14) : Theme.Colors.elevated), in: Capsule())
    }

    private func cardTextField(
        _ title: String,
        text: Binding<String>,
        prompt: String,
        keyboard: UIKeyboardType = .default,
        axis: Axis = .horizontal,
        textInputAutocapitalization: TextInputAutocapitalization = .sentences,
        disableAutocorrection: Bool = false
    ) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
            Text(title)
                .font(Theme.Typography.tiny)
                .foregroundStyle(Theme.Colors.textSecondary)
            TextField(prompt, text: text, axis: axis)
                .lineLimit(axis == .vertical ? 2...5 : 1...1)
                .keyboardType(keyboard)
                .textInputAutocapitalization(textInputAutocapitalization)
                .autocorrectionDisabled(disableAutocorrection)
                .font(Theme.Typography.body)
                .foregroundStyle(Theme.Colors.textPrimary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(Theme.Spacing.sm)
        .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
    }

    private func cardPickerRow<Content: View>(
        _ title: String,
        selection: Binding<String>,
        @ViewBuilder content: () -> Content
    ) -> some View {
        HStack(spacing: Theme.Spacing.sm) {
            VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                Text(title)
                    .font(Theme.Typography.tiny)
                    .foregroundStyle(Theme.Colors.textSecondary)
                Picker(title, selection: selection) {
                    content()
                }
                .pickerStyle(.menu)
                .tint(Theme.Colors.textPrimary)
            }
            Spacer(minLength: 0)
        }
        .padding(Theme.Spacing.sm)
        .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
    }

    private func labeledCompactDate(_ title: String, selection: Binding<Date>, components: DatePickerComponents) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
            Text(title)
                .font(Theme.Typography.tiny)
                .foregroundStyle(Theme.Colors.textSecondary)
            DatePicker(title, selection: selection, displayedComponents: components)
                .labelsHidden()
                .datePickerStyle(.compact)
                .tint(Theme.Colors.primary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(Theme.Spacing.sm)
        .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
    }

    private func totalLine(_ title: String, value: Double?, emphasize: Bool = false) -> some View {
        HStack {
            Text(title)
            Spacer()
            Text(formatMoney(value))
                .fontWeight(emphasize ? .semibold : .regular)
        }
        .font(emphasize ? Theme.Typography.captionStrong : Theme.Typography.caption)
        .foregroundStyle(Theme.Colors.textPrimary)
    }

    private var manualPresetStrip: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            HStack {
                Text("Rychlý start")
                    .font(Theme.Typography.captionStrong)
                    .foregroundStyle(Theme.Colors.textPrimary)
                Spacer()
                Text("Předvyplní běžné typy zásahu")
                    .font(Theme.Typography.tiny)
                    .foregroundStyle(Theme.Colors.textSecondary)
            }

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: Theme.Spacing.sm) {
                    ForEach(manualQuickPresets) { preset in
                        Button {
                            applyManualQuickPreset(preset)
                        } label: {
                            VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                                Text(preset.title)
                                    .font(Theme.Typography.captionStrong)
                                    .foregroundStyle(Theme.Colors.textPrimary)
                                Text(preset.subtitle)
                                    .font(Theme.Typography.tiny)
                                    .foregroundStyle(Theme.Colors.textSecondary)
                            }
                            .frame(width: 144, alignment: .leading)
                            .padding(Theme.Spacing.sm)
                            .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }

    private var scanReviewChecklistCard: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                    Text("Kontrola před uložením")
                        .font(Theme.Typography.captionStrong)
                        .foregroundStyle(Theme.Colors.textPrimary)
                    Text("Nejdřív zkontrolujte klíčové údaje z dokladu.")
                        .font(Theme.Typography.tiny)
                        .foregroundStyle(Theme.Colors.textSecondary)
                }
                Spacer()
                analysisChip("\(Int((scanCompletionRatio * 100).rounded())) % připraveno", color: Theme.Colors.primary)
            }

            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Theme.Colors.hairline.opacity(0.6))
                    Capsule()
                        .fill(LinearGradient(colors: [Theme.Colors.primary, Theme.Colors.accent], startPoint: .leading, endPoint: .trailing))
                        .frame(width: max(18, geometry.size.width * scanCompletionRatio))
                }
            }
            .frame(height: 8)

            VStack(spacing: Theme.Spacing.sm) {
                ForEach(scanChecklistRows) { row in
                    HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                        Image(systemName: row.isComplete ? "checkmark.circle.fill" : "circle.dashed")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(row.isComplete ? row.accent : Theme.Colors.textSecondary)
                            .padding(.top, 2)

                        VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                            Text(row.title)
                                .font(Theme.Typography.tiny)
                                .foregroundStyle(Theme.Colors.textSecondary)
                            Text(row.value)
                                .font(Theme.Typography.caption)
                                .foregroundStyle(Theme.Colors.textPrimary)
                                .fixedSize(horizontal: false, vertical: true)
                        }

                        Spacer(minLength: 0)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(Theme.Spacing.sm)
                    .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
                }
            }

            HStack(spacing: Theme.Spacing.sm) {
                Button("Servisní zpráva") {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        isReportSectionExpanded = true
                    }
                }
                .buttonStyle(InlineChipButtonStyle(isSelected: true))

                Button("Položky") {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        isItemsSectionExpanded = true
                    }
                }
                .buttonStyle(InlineChipButtonStyle(isSelected: false))

                Button("Součty") {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        isTotalsSectionExpanded = true
                    }
                }
                .buttonStyle(InlineChipButtonStyle(isSelected: false))
            }
        }
        .padding(Theme.Spacing.sm)
        .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
    }

    private var scanFieldReviewCard: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                    Text("Rychlá revize polí")
                        .font(Theme.Typography.captionStrong)
                        .foregroundStyle(Theme.Colors.textPrimary)
                    Text("Potvrďte klíčové hodnoty a otevřete jen tu sekci, která potřebuje opravu.")
                        .font(Theme.Typography.tiny)
                        .foregroundStyle(Theme.Colors.textSecondary)
                }
                Spacer()
                analysisChip("\(scanReviewFields.filter { $0.status == .ready }.count)/\(scanReviewFields.count)", color: Theme.Colors.accent)
            }

            VStack(spacing: Theme.Spacing.sm) {
                ForEach(scanReviewFields) { field in
                    HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                        Image(systemName: field.icon)
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(field.accent)
                            .frame(width: 34, height: 34)
                            .background(field.accent.opacity(0.14), in: RoundedRectangle(cornerRadius: 10, style: .continuous))

                        VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                            HStack(spacing: Theme.Spacing.xs) {
                                Text(field.title)
                                    .font(Theme.Typography.tiny)
                                    .foregroundStyle(Theme.Colors.textSecondary)
                                Text(field.status.label)
                                    .font(Theme.Typography.tiny)
                                    .foregroundStyle(field.status.color)
                            }

                            Text(field.value ?? field.placeholder)
                                .font(Theme.Typography.caption)
                                .foregroundStyle(field.value == nil ? Theme.Colors.textSecondary : Theme.Colors.textPrimary)
                                .fixedSize(horizontal: false, vertical: true)
                        }

                        Spacer(minLength: 0)

                        Button(field.actionTitle) {
                            field.action()
                        }
                        .buttonStyle(InlineChipButtonStyle(isSelected: field.status == .missing))
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(Theme.Spacing.sm)
                    .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
                }
            }
        }
        .padding(Theme.Spacing.sm)
        .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
    }

    private func statusLine(_ title: String, color: Color, icon: String) -> some View {
        Label(title, systemImage: icon)
            .font(Theme.Typography.captionStrong)
            .foregroundStyle(color)
    }

    private var shouldShowDocumentAnalysisStatus: Bool {
        analysisMessage != nil || analysisConfidence != nil || analysisFieldCount > 0
    }

    private var editorCompletionRatio: Double {
        let checks: [Bool] = [
            !effectiveDescriptionForSave.isEmpty,
            effectivePrice != nil,
            parsedMileage != nil || trimToNil(mileage) == nil,
            trimToNil(reportSupplierName) != nil || pendingAttachment == nil,
            normalizedReportItems.isEmpty == false || trimToNil(reportServiceSummary) != nil || effectiveEntryMode != .scan
        ]
        let completed = checks.filter { $0 }.count
        return Double(completed) / Double(checks.count)
    }

    private var editorProgressSubtitle: String {
        if effectiveEntryMode == .scan {
            return pendingAttachment == nil
                ? "Nejdřív vložte doklad, potom potvrďte klíčová pole."
                : "Doklad je načtený. Zkontrolujte servisní zprávu, cenu a položky."
        }
        if effectiveEntryMode == .template {
            return "Šablona urychlí vstup, ale finální údaje ještě zkontrolujte."
        }
        return "Vyplňte jen to, co chcete sledovat. Zbytek nechte prázdný."
    }

    private func documentAnalysisStatusCard(message: String) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                Image(systemName: analysisTone.iconName)
                    .font(.system(size: 15, weight: .bold))
                    .foregroundStyle(analysisTone.color)
                    .frame(width: 34, height: 34)
                    .background(analysisTone.color.opacity(0.14), in: RoundedRectangle(cornerRadius: 10, style: .continuous))

                VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                    Text(analysisTone.title)
                        .font(Theme.Typography.captionStrong)
                        .foregroundStyle(Theme.Colors.textPrimary)
                    Text(message)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 0)
            }

            HStack(spacing: Theme.Spacing.xs) {
                if let analysisConfidence {
                    analysisChip("\(analysisConfidence) % jistota", color: analysisTone.color)
                }
                if analysisFieldCount > 0 {
                    analysisChip("\(analysisFieldCount) polí", color: Theme.Colors.accent)
                }
                if let analysisSourceLabel {
                    analysisChip(analysisSourceLabel, color: Theme.Colors.textSecondary)
                }
            }
        }
        .padding(Theme.Spacing.sm)
        .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
    }

    private func analysisChip(_ title: String, color: Color) -> some View {
        Text(title)
            .font(Theme.Typography.tiny)
            .foregroundStyle(Theme.Colors.textPrimary)
            .padding(.horizontal, Theme.Spacing.sm)
            .padding(.vertical, Theme.Spacing.xs)
            .background(color.opacity(0.12), in: Capsule())
    }

    private var editorHeroTitle: String {
        switch effectiveEntryMode {
        case .manual:
            return initial == nil ? "Ruční zápis" : "Úprava záznamu"
        case .scan:
            return "Skenovaný záznam"
        case .template:
            return "Šablona záznamu"
        case .none:
            return initial == nil ? "Nový záznam" : "Úprava záznamu"
        }
    }

    private var editorHeroSubtitle: String {
        switch effectiveEntryMode {
        case .manual:
            return "Vyplňte přesně to, co chcete uložit. Formulář je otevřený a plně pod kontrolou uživatele."
        case .scan:
            return "Nejdřív načtěte doklad, potom zkontrolujte předvyplněná pole a doplňte chybějící údaje."
        case .template:
            return "Vyberte šablonu a otevřete ji do editoru."
        case .none:
            return "Připravte nový servisní záznam."
        }
    }

    private func configureSectionVisibility(
        for mode: RecordEntryMode,
        prefersItems: Bool = false,
        prefersReport: Bool = false
    ) {
        switch mode {
        case .manual:
            isDocumentSectionExpanded = false
            isReportSectionExpanded = prefersReport
            isItemsSectionExpanded = prefersItems
            isTotalsSectionExpanded = false
        case .scan:
            isDocumentSectionExpanded = true
            isReportSectionExpanded = true
            isItemsSectionExpanded = false
            isTotalsSectionExpanded = false
        case .template:
            isDocumentSectionExpanded = false
            isReportSectionExpanded = true
            isItemsSectionExpanded = true
            isTotalsSectionExpanded = false
        }
    }

    private func focusEditorSection(_ target: EditorSectionAnchor) {
        withAnimation(.easeInOut(duration: 0.2)) {
            switch target {
            case .basic:
                break
            case .document:
                isDocumentSectionExpanded = true
            case .report:
                isReportSectionExpanded = true
            case .items:
                isItemsSectionExpanded = true
            case .totals:
                isTotalsSectionExpanded = true
            }
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
            pendingScrollTarget = target
        }
    }

    private func applyManualQuickPreset(_ preset: ManualQuickPreset) {
        category = normalizeCategoryID(preset.categoryID)
        if normalizedDescription.isEmpty {
            description = preset.description
        }
        if trimToNil(reportServiceSummary) == nil {
            reportServiceSummary = preset.summary
        }
        if trimToNil(note) == nil {
            note = preset.note
        }
        if !preset.items.isEmpty, normalizedReportItems.isEmpty {
            reportItems = preset.items
        }
        configureSectionVisibility(for: .manual, prefersItems: !preset.items.isEmpty, prefersReport: true)
        analysisMessage = "Předvolba „\(preset.title)“ byla načtena do editoru."
        analysisTone = .success
    }

    private func saveCurrentAsTemplate() {
        let fallbackName = trustedTemplateNameSeed()
        let finalName = trimToNil(templateNameDraft) ?? fallbackName

        let template = ServiceRecordTemplate(
            id: UUID(),
            name: finalName,
            icon: categoryOptions.first(where: { $0.id == category })?.icon ?? "🛠️",
            category: category,
            templateDescription: trimToNil(description) ?? trimToNil(reportServiceSummary) ?? "Vlastní servisní šablona",
            note: trimToNil(note),
            sourceType: selectedSourceType,
            description: trimToNil(description),
            serviceSummary: trimToNil(reportServiceSummary),
            issueDescription: trimToNil(reportIssueDescription),
            currency: meaningfulCurrency(reportCurrency) ?? "CZK",
            hasNextServiceDueDate: hasNextServiceDueDate,
            items: reportItems
                .filter { !$0.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
                .map {
                    ServiceRecordTemplateItem(
                        name: $0.name,
                        quantity: $0.quantity,
                        unit: $0.unit,
                        unitPrice: $0.unitPrice,
                        totalPrice: $0.totalPrice
                    )
                }
        )

        env.recordConfigurationStore.saveTemplate(template)
        templateNameDraft = ""
        analysisMessage = "Šablona byla uložena."
        analysisTone = .success
    }

    private func deleteCustomTemplate(_ template: ServiceRecordTemplate) {
        env.recordConfigurationStore.deleteTemplate(template)
    }

    private func applyTemplate(_ template: ServiceRecordTemplate) {
        category = normalizeCategoryID(template.category)
        selectedSourceType = normalizeSourceTypeID(template.sourceType)
        description = template.description ?? ""
        note = template.note ?? ""
        reportServiceSummary = template.serviceSummary ?? ""
        reportIssueDescription = template.issueDescription ?? ""
        reportCurrency = meaningfulCurrency(template.currency) ?? "CZK"
        hasNextServiceDueDate = template.hasNextServiceDueDate
        if hasNextServiceDueDate {
            nextServiceDueDate = Calendar.current.date(byAdding: .month, value: 12, to: Date()) ?? Date()
        }

        let templateItems = template.items.map(ServiceReportItemDraft.init)
        reportItems = templateItems.isEmpty ? [.empty] : templateItems

        if let seededDescription = trimToNil(template.description) {
            analysisMessage = "Šablona „\(template.name)“ byla načtena do editoru."
            analysisTone = .success
            if description.isEmpty {
                description = seededDescription
            }
        }

        configureSectionVisibility(for: .manual, prefersItems: !templateItems.isEmpty, prefersReport: true)
        entryMode = .manual
    }

    private func trustedTemplateNameSeed() -> String {
        if let description = trimToNil(description) {
            return String(description.prefix(40))
        }
        if let summary = trimToNil(reportServiceSummary) {
            return String(summary.prefix(40))
        }
        let categoryLabel = categoryOptions.first(where: { $0.id == category })?.label ?? "Servis"
        return "\(categoryLabel) šablona"
    }

    private func loadInitial() {
        guard let initial else {
            reportItems = [.empty]
            return
        }

        configureSectionVisibility(for: .manual, prefersReport: true)
        entryMode = .manual

        performedAt = initial.performedAt ?? Date()
        mileage = initial.mileage.map(String.init) ?? ""
        description = initial.description
        price = initial.price.map(formatEditablePrice) ?? ""
        note = initial.note ?? ""
        category = normalizeCategoryID(initial.category)

        if let nextDate = initial.nextServiceDueDate {
            hasNextServiceDueDate = true
            nextServiceDueDate = nextDate
        }

        existingAttachmentObjects = parseAttachmentObjects(initial.attachments)
            .filter { String(describing: ($0["kind"] ?? "")).lowercased() != "service_report_meta" }

        if let parsedSummary = firstParsedSummary(from: initial.attachments) {
            applyServiceReport(parsedSummary)
        }
    }

    private func handleFileImportResult(_ result: Result<[URL], Error>) {
        switch result {
        case .failure(let error):
            formError = "Nepodařilo se načíst soubor: \(error.localizedDescription)"
        case .success(let urls):
            guard let url = urls.first else { return }
            do {
                let needsSecurityScope = url.startAccessingSecurityScopedResource()
                defer {
                    if needsSecurityScope {
                        url.stopAccessingSecurityScopedResource()
                    }
                }
                let data = try Data(contentsOf: url)
                let mimeType = mimeTypeFrom(url: url) ?? "application/octet-stream"
                let attachment: PendingAttachment
                if mimeType.hasPrefix("image/"), let image = UIImage(data: data) {
                    attachment = normalizedImageAttachment(
                        from: image,
                        fileName: url.lastPathComponent.isEmpty ? "doklad.jpg" : url.lastPathComponent,
                        sourceLabel: "Soubor"
                    )
                } else {
                    attachment = PendingAttachment(
                        data: data,
                        fileName: url.lastPathComponent.isEmpty ? "doklad" : url.lastPathComponent,
                        mimeType: mimeType,
                        sourceLabel: "Soubor",
                        ocrImages: nil
                    )
                }
                handlePendingAttachment(attachment)
            } catch {
                formError = "Nepodařilo se načíst vybraný soubor."
            }
        }
    }

    @MainActor
    private func handlePhotoPickerItem(_ item: PhotosPickerItem) async {
        defer { selectedPhotoItem = nil }
        do {
            guard let data = try await item.loadTransferable(type: Data.self) else { return }
            guard let image = UIImage(data: data) else {
                formError = "Fotku se nepodařilo otevřít."
                return
            }
            let formatter = DateFormatter()
            formatter.dateFormat = "yyyyMMdd_HHmmss"
            let attachment = normalizedImageAttachment(
                from: image,
                fileName: "photo_\(formatter.string(from: Date())).jpg",
                sourceLabel: "Galerie"
            )
            handlePendingAttachment(attachment)
        } catch {
            formError = "Fotku se nepodařilo načíst."
        }
    }

    private func normalizedImageAttachment(from image: UIImage, fileName: String, sourceLabel: String) -> PendingAttachment {
        let normalizedImage = optimizedDocumentImage(from: image, maxLongEdge: 2400)
        let normalizedData = normalizedImage.jpegData(compressionQuality: 0.82) ?? image.jpegData(compressionQuality: 0.9) ?? Data()
        return PendingAttachment(
            data: normalizedData,
            fileName: fileName.hasSuffix(".jpg") || fileName.hasSuffix(".jpeg") ? fileName : "\(fileName).jpg",
            mimeType: "image/jpeg",
            sourceLabel: sourceLabel,
            ocrImages: [normalizedImage]
        )
    }

    private func handlePendingAttachment(_ attachment: PendingAttachment) {
        if attachment.data.count > maxAttachmentBytes {
            formError = "Soubor je příliš velký (max 15 MB)."
            return
        }
        if extractedAttachmentCacheKey != attachmentCacheKey(for: attachment) {
            extractedAttachmentCacheKey = nil
            extractedAttachmentText = nil
        }
        pendingAttachment = attachment
        manualDocumentText = ""
        formError = nil
        analysisConfidence = nil
        analysisFieldCount = 0
        analysisSourceLabel = attachment.sourceLabel
        analysisMessage = "Připraveno k analýze (\(attachment.sourceLabel)): \(attachment.fileName)"
        analysisTone = .info
        Task {
            await fillManualTextFromAttachmentIfNeeded(attachment)
            if autoPrefillEnabled {
                await analyzeAttachment()
            }
        }
    }

    @MainActor
    private func fillManualTextFromAttachmentIfNeeded(_ attachment: PendingAttachment) async {
        isExtractingLocalText = true
        defer { isExtractingLocalText = false }

        let extractedText: String?
        if let cached = cachedExtractedText(for: attachment) {
            extractedText = cached
        } else {
            let fresh = await extractTextFromAttachment(attachment)
            storeExtractedText(fresh, for: attachment)
            extractedText = fresh
        }

        guard let extractedText else { return }
        let trimmed = extractedText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        analysisFieldCount = max(analysisFieldCount, 1)
        analysisMessage = "Doklad lokálně přečten (\(trimmed.count) znaků). Připravuji strukturované předvyplnění."
        analysisTone = .info
    }

    private func extractTextFromAttachment(_ attachment: PendingAttachment) async -> String? {
        if let cached = cachedExtractedText(for: attachment) {
            return cached
        }
        return await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                continuation.resume(returning: extractTextFromAttachmentSync(attachment))
            }
        }
    }

    private func extractTextFromAttachmentSync(_ attachment: PendingAttachment) -> String? {
        let normalizedMimeType = attachment.mimeType.lowercased()

        if let images = attachment.ocrImages, !images.isEmpty {
            return recognizeTextSync(in: images)
        }
        if normalizedMimeType == "application/pdf" {
            return extractTextFromPDFSync(attachment.data)
        }
        if normalizedMimeType.hasPrefix("image/") || normalizedMimeType == "application/octet-stream",
           let image = UIImage(data: attachment.data) {
            return recognizeTextSync(in: [image])
        }
        if normalizedMimeType.hasPrefix("text/"), let text = String(data: attachment.data, encoding: .utf8) {
            return text
        }
        return nil
    }

    private func extractTextFromPDFSync(_ data: Data) -> String? {
        guard let document = PDFDocument(data: data) else { return nil }

        let embeddedText = document.string?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if embeddedText.count >= 30 {
            return embeddedText
        }

        let images = rasterizedImages(from: document, limit: 6)
        guard !images.isEmpty else {
            return embeddedText.isEmpty ? nil : embeddedText
        }
        let recognized = recognizeTextSync(in: images)
        if let recognized, !recognized.isEmpty {
            return recognized
        }
        return embeddedText.isEmpty ? nil : embeddedText
    }

    private func rasterizedImages(from document: PDFDocument, limit: Int) -> [UIImage] {
        let count = min(limit, document.pageCount)
        guard count > 0 else { return [] }

        var images: [UIImage] = []
        for index in 0..<count {
            guard let page = document.page(at: index) else { continue }
            let pageBounds = page.bounds(for: .mediaBox)
            let renderWidth: CGFloat = 2200
            let scale = max(renderWidth / max(pageBounds.width, 1), 1.0)
            let renderSize = CGSize(width: pageBounds.width * scale, height: pageBounds.height * scale)
            let renderer = UIGraphicsImageRenderer(size: renderSize)
            let image = renderer.image { context in
                UIColor.white.set()
                context.fill(CGRect(origin: .zero, size: renderSize))
                context.cgContext.saveGState()
                context.cgContext.scaleBy(x: scale, y: scale)
                page.draw(with: .mediaBox, to: context.cgContext)
                context.cgContext.restoreGState()
            }
            images.append(image)
        }
        return images
    }

    private func recognizeTextSync(in images: [UIImage]) -> String? {
        var blocks: [String] = []
        for image in images {
            let candidates = recognitionCandidateImages(from: image)
            for candidate in candidates {
                let text = recognizeTextSync(in: candidate)
                let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmed.isEmpty {
                    blocks.append(trimmed)
                }
                if trimmed.count >= 40 {
                    break
                }
            }
        }

        let merged = blocks.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
        return merged.isEmpty ? nil : merged
    }

    private func recognizeTextSync(in image: UIImage) -> String {
        guard let cgImage = renderedCGImage(from: image) else { return "" }
        let orientation = CGImagePropertyOrientation(image.imageOrientation)
        let primary = runTextRecognitionSync(
            in: cgImage,
            orientation: orientation,
            recognitionLevel: .accurate,
            minimumTextHeight: 0.007
        )
        if primary.count >= 30 {
            return primary
        }

        let secondary = runTextRecognitionSync(
            in: cgImage,
            orientation: orientation,
            recognitionLevel: .fast,
            minimumTextHeight: 0.0
        )
        return secondary.count > primary.count ? secondary : primary
    }

    private func runTextRecognitionSync(
        in cgImage: CGImage,
        orientation: CGImagePropertyOrientation,
        recognitionLevel: VNRequestTextRecognitionLevel,
        minimumTextHeight: Float
    ) -> String {
        var recognizedLines: [String] = []
        let request = VNRecognizeTextRequest { request, _ in
            let observations = request.results as? [VNRecognizedTextObservation] ?? []
            recognizedLines = observations.compactMap { $0.topCandidates(1).first?.string }
        }
        request.recognitionLevel = recognitionLevel
        request.usesLanguageCorrection = true
        request.recognitionLanguages = ["cs-CZ", "sk-SK", "en-US", "de-DE"]
        request.automaticallyDetectsLanguage = true
        request.customWords = ["faktura", "doklad", "servis", "servisní", "servisni", "nájezd", "najedz", "tachometr", "VIN", "DPH", "emise", "STK"]
        if minimumTextHeight > 0 {
            request.minimumTextHeight = minimumTextHeight
        }

        let handler = VNImageRequestHandler(cgImage: cgImage, orientation: orientation, options: [:])
        do {
            try handler.perform([request])
        } catch {
            return ""
        }
        return recognizedLines.joined(separator: "\n")
    }

    private func recognitionCandidateImages(from image: UIImage) -> [UIImage] {
        let baseImage = scaledImageForOCR(image)
        var candidates: [UIImage] = [baseImage]
        if let documentCrop = detectedDocumentImage(from: baseImage) {
            candidates.append(documentCrop)
            if let thresholded = thresholdedImage(documentCrop) {
                candidates.append(thresholded)
            }
            if let monochrome = monochromeSharpenedImage(documentCrop) {
                candidates.append(monochrome)
            }
        }
        guard let cgImage = renderedCGImage(from: baseImage) else { return candidates }

        let ciImage = CIImage(cgImage: cgImage)
        let context = CIContext(options: nil)
        let pipelines: [(contrast: Double, brightness: Double, saturation: Double, sharpen: Double)] = [
            (1.65, 0.04, 0.0, 0.35),
            (2.05, 0.10, 0.0, 0.65),
        ]

        for pipeline in pipelines {
            guard let colorFilter = CIFilter(name: "CIColorControls") else { continue }
            colorFilter.setValue(ciImage, forKey: kCIInputImageKey)
            colorFilter.setValue(pipeline.contrast, forKey: kCIInputContrastKey)
            colorFilter.setValue(pipeline.brightness, forKey: kCIInputBrightnessKey)
            colorFilter.setValue(pipeline.saturation, forKey: kCIInputSaturationKey)

            var output = colorFilter.outputImage
            if let sharpenFilter = CIFilter(name: "CISharpenLuminance"), let current = output {
                sharpenFilter.setValue(current, forKey: kCIInputImageKey)
                sharpenFilter.setValue(pipeline.sharpen, forKey: kCIInputSharpnessKey)
                output = sharpenFilter.outputImage
            }

            guard let output, let enhanced = context.createCGImage(output, from: output.extent) else { continue }
            candidates.append(UIImage(cgImage: enhanced, scale: baseImage.scale, orientation: baseImage.imageOrientation))
        }
        return candidates
    }

    private func monochromeSharpenedImage(_ image: UIImage) -> UIImage? {
        guard let cgImage = renderedCGImage(from: image) else { return nil }
        let ciImage = CIImage(cgImage: cgImage)
        let context = CIContext()

        guard let mono = CIFilter(name: "CIPhotoEffectMono") else { return nil }
        mono.setValue(ciImage, forKey: kCIInputImageKey)
        guard let monoOutput = mono.outputImage else { return nil }

        guard let sharpen = CIFilter(name: "CISharpenLuminance") else { return nil }
        sharpen.setValue(monoOutput, forKey: kCIInputImageKey)
        sharpen.setValue(1.1, forKey: kCIInputSharpnessKey)
        guard let sharpened = sharpen.outputImage else { return nil }

        guard let controls = CIFilter(name: "CIColorControls") else { return nil }
        controls.setValue(sharpened, forKey: kCIInputImageKey)
        controls.setValue(2.3, forKey: kCIInputContrastKey)
        controls.setValue(0.0, forKey: kCIInputSaturationKey)
        controls.setValue(0.03, forKey: kCIInputBrightnessKey)
        guard let output = controls.outputImage,
              let enhanced = context.createCGImage(output, from: output.extent) else { return nil }
        return UIImage(cgImage: enhanced, scale: image.scale, orientation: image.imageOrientation)
    }

    private func detectedDocumentImage(from image: UIImage) -> UIImage? {
        guard let cgImage = renderedCGImage(from: image) else { return nil }
        let request = VNDetectRectanglesRequest()
        request.maximumObservations = 1
        request.minimumAspectRatio = 0.5
        request.minimumConfidence = 0.4
        let handler = VNImageRequestHandler(cgImage: cgImage, orientation: .up, options: [:])
        do {
            try handler.perform([request])
            guard let observation = request.results?.first as? VNRectangleObservation else { return nil }
            return croppedImage(from: image, observation: observation)
        } catch {
            return nil
        }
    }

    private func thresholdedImage(_ image: UIImage) -> UIImage? {
        guard let cgImage = renderedCGImage(from: image) else { return nil }
        let ciImage = CIImage(cgImage: cgImage)
        guard let colorFilter = CIFilter(name: "CIColorControls") else { return nil }
        colorFilter.setValue(ciImage, forKey: kCIInputImageKey)
        colorFilter.setValue(-0.12, forKey: kCIInputBrightnessKey)
        colorFilter.setValue(2.6, forKey: kCIInputContrastKey)
        colorFilter.setValue(0.0, forKey: kCIInputSaturationKey)
        guard let contrasted = colorFilter.outputImage else { return nil }
        guard let posterize = CIFilter(name: "CIColorPosterize") else { return nil }
        posterize.setValue(contrasted, forKey: kCIInputImageKey)
        posterize.setValue(2, forKey: "inputLevels")
        guard let output = posterize.outputImage else { return nil }
        let context = CIContext()
        guard let enhanced = context.createCGImage(output, from: output.extent) else { return nil }
        return UIImage(cgImage: enhanced, scale: image.scale, orientation: image.imageOrientation)
    }

    private func croppedImage(from image: UIImage, observation: VNRectangleObservation) -> UIImage? {
        guard let cgImage = renderedCGImage(from: image) else { return nil }
        let width = CGFloat(cgImage.width)
        let height = CGFloat(cgImage.height)
        let minX = max(0, observation.boundingBox.minX * width)
        let minY = max(0, (1 - observation.boundingBox.maxY) * height)
        let maxX = min(width, observation.boundingBox.maxX * width)
        let maxY = min(height, (1 - observation.boundingBox.minY) * height)
        let rect = CGRect(x: minX, y: minY, width: maxX - minX, height: maxY - minY).integral
        guard let cropped = cgImage.cropping(to: rect) else { return nil }
        return UIImage(cgImage: cropped, scale: image.scale, orientation: image.imageOrientation)
    }

    private func renderedCGImage(from image: UIImage) -> CGImage? {
        if let cgImage = image.cgImage {
            return cgImage
        }
        let renderer = UIGraphicsImageRenderer(size: image.size)
        let rendered = renderer.image { _ in
            image.draw(in: CGRect(origin: .zero, size: image.size))
        }
        return rendered.cgImage
    }

    private func scaledImageForOCR(_ image: UIImage) -> UIImage {
        let longEdge = max(image.size.width, image.size.height)
        let targetLongEdge: CGFloat = 2400
        guard longEdge > targetLongEdge, longEdge > 0 else { return image }
        let scale = targetLongEdge / longEdge
        let targetSize = CGSize(width: image.size.width * scale, height: image.size.height * scale)
        let renderer = UIGraphicsImageRenderer(size: targetSize)
        return renderer.image { _ in
            image.draw(in: CGRect(origin: .zero, size: targetSize))
        }
    }

    private func optimizedDocumentImage(from image: UIImage, maxLongEdge: CGFloat) -> UIImage {
        let normalized = normalizedUIImage(image)
        let longEdge = max(normalized.size.width, normalized.size.height)
        guard longEdge > maxLongEdge, longEdge > 0 else { return normalized }
        let scale = maxLongEdge / longEdge
        let targetSize = CGSize(width: normalized.size.width * scale, height: normalized.size.height * scale)
        let renderer = UIGraphicsImageRenderer(size: targetSize)
        return renderer.image { _ in
            normalized.draw(in: CGRect(origin: .zero, size: targetSize))
        }
    }

    private func normalizedUIImage(_ image: UIImage) -> UIImage {
        guard image.imageOrientation != .up else { return image }
        let renderer = UIGraphicsImageRenderer(size: image.size)
        return renderer.image { _ in
            image.draw(in: CGRect(origin: .zero, size: image.size))
        }
    }

    private func analyzeAttachment() async {
        guard !isAnalyzingDocument else { return }
        guard let token = env.authManager.token else {
            formError = "Nejste přihlášen. Přihlaste se znovu."
            return
        }
        guard let pendingAttachment else {
            formError = "Nejdříve vyberte doklad."
            return
        }

        isAnalyzingDocument = true
        analysisSourceLabel = pendingAttachment.sourceLabel
        analysisMessage = "Analyzuji doklad a připravuji předvyplnění…"
        analysisTone = .info
        formError = nil
        defer { isAnalyzingDocument = false }

        let localAnalysis = await buildLocalDocumentAnalysis(for: pendingAttachment)
        if let localPrefill = localAnalysis?.prefill {
            applyPrefill(localPrefill)
        }
        analysisFieldCount = localAnalysis?.fieldCount ?? 0

        do {
            let request = ServiceRecordDocumentPrefillRequest(
                sourceType: selectedSourceType,
                fileName: pendingAttachment.fileName,
                fileMimeType: pendingAttachment.mimeType,
                fileContentBase64: pendingAttachment.data.base64EncodedString(),
                manualText: trimToNil(manualDocumentText),
                manualNote: trimToNil(note),
                fallbackCategory: trimToNil(category),
                fallbackMileage: parsedMileage,
                fallbackPerformedAt: performedAt,
                fallbackDescription: trimToNil(description),
                fallbackPrice: parseOptionalNumber(price)
            )
            let response = try await featureService.previewServiceRecordFromDocument(vehicleId: vehicleId, request, token: token)
            if let prefill = response.prefill, hasMeaningfulPrefill(prefill) {
                applyPrefill(prefill)
            } else if let localPrefill = localAnalysis?.prefill {
                applyPrefill(localPrefill)
            }

            let backendHasMeaningfulPrefill = response.prefill.map(hasMeaningfulPrefill) ?? false
            let confidence = resolvedDocumentConfidence(
                backendConfidence: response.parseConfidence,
                parsedConfidence: response.parsedData?.confidence,
                localAnalysis: localAnalysis,
                backendHasMeaningfulPrefill: backendHasMeaningfulPrefill
            )
            let supplier = response.prefill?.serviceReport?.supplierName ?? response.parsedData?.supplierName ?? "neuvedeno"
            let total = response.prefill?.price ?? response.prefill?.serviceReport?.totalWithVat
            let totalLabel = total.map(formatMoney) ?? localAnalysis?.total.map(formatMoney) ?? "nezjištěno"
            let usedLocalFallback = !backendHasMeaningfulPrefill && localAnalysis != nil

            if usedLocalFallback, let localAnalysis {
                analysisConfidence = localAnalysis.confidence
                analysisFieldCount = localAnalysis.fieldCount
                analysisMessage = "Doklad předvyplněn lokálně (\(localAnalysis.confidence)% • \(localAnalysis.fieldCount) polí). Backend nedodal strukturovaná data. Dodavatel: \(localAnalysis.supplierName ?? supplier). Celkem: \(totalLabel)."
                analysisTone = .success
            } else {
                analysisConfidence = confidence > 0 ? confidence : localAnalysis?.confidence
                analysisFieldCount = max(localAnalysis?.fieldCount ?? 0, prefillHighlights.count)
                analysisMessage = "Doklad načten (\(confidence)%). Dodavatel: \(supplier). Celkem: \(totalLabel)."
                analysisTone = response.processingStatus == "needs_review" ? .warning : .success
            }
        } catch {
            if let localAnalysis {
                analysisConfidence = localAnalysis.confidence
                analysisFieldCount = localAnalysis.fieldCount
                analysisMessage = "Backend nedodal předvyplnění, ale doklad byl vytěžen lokálně (\(localAnalysis.confidence)% • \(localAnalysis.fieldCount) polí). Dodavatel: \(localAnalysis.supplierName ?? "neuvedeno"). Celkem: \(localAnalysis.total.map(formatMoney) ?? "nezjištěno")."
                analysisTone = .success
            } else {
                analysisConfidence = nil
                analysisFieldCount = 0
                analysisMessage = "Nepodařilo se načíst data z dokladu: \(error.localizedDescription)"
                analysisTone = .error
            }
        }
    }

    private func applyPrefill(_ prefill: ServiceRecordDocumentPrefillData?) {
        guard let prefill else { return }

        if let category = prefill.category {
            self.category = normalizeCategoryID(category)
        }
        if let performedAt = prefill.performedAt {
            self.performedAt = performedAt
        }
        if description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
           let description = trustedDescriptionCandidate(prefill.description) {
            self.description = description
        }
        if mileage.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, let mileage = prefill.mileage {
            self.mileage = String(mileage)
        }
        if price.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, let price = prefill.price {
            self.price = formatEditablePrice(price)
        }
        if note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, let note = prefill.note {
            self.note = note
        }

        if let serviceReport = prefill.serviceReport {
            applyServiceReport(serviceReport)
        }
    }

    private func applyServiceReport(_ report: ServiceReportPayload) {
        reportDocumentNumber = meaningfulDocumentValue(report.documentNumber) ?? ""
        reportSupplierName = meaningfulDocumentValue(report.supplierName) ?? ""
        reportSupplierEmail = meaningfulEmail(report.supplierEmail) ?? ""
        reportSupplierWebsite = meaningfulWebsite(report.supplierWebsite) ?? ""
        let cleanedServiceLink = meaningfulWebsite(report.serviceLink)
        let websiteIdentity = canonicalWebsiteIdentity(report.supplierWebsite)
        let serviceLinkIdentity = canonicalWebsiteIdentity(cleanedServiceLink)
        reportServiceLink = serviceLinkIdentity == websiteIdentity ? "" : (cleanedServiceLink ?? "")
        reportCustomerName = meaningfulCustomerName(report.customerName) ?? ""
        reportServiceSummary = trustedDescriptionCandidate(report.serviceSummary) ?? ""
        reportIssueDescription = trustedDescriptionCandidate(report.issueDescription) ?? ""
        reportTechnicianName = meaningfulPersonName(report.technicianName) ?? ""
        reportTechnicianInitials = meaningfulInitials(report.technicianInitials) ?? ""
        reportCurrency = meaningfulCurrency(report.currency) ?? "CZK"
        reportLaborHours = report.laborHours.map(formatEditablePrice) ?? ""
        reportLaborHourRate = report.laborHourRate.map(formatEditablePrice) ?? ""
        reportLaborTotal = report.laborTotal.map(formatEditablePrice) ?? ""
        reportMaterialsTotal = report.materialsTotal.map(formatEditablePrice) ?? ""
        reportSubtotalWithoutVat = report.subtotalWithoutVat.map(formatEditablePrice) ?? ""
        reportVatRate = report.vatRate.map(formatEditablePrice) ?? ""
        reportVatAmount = report.vatAmount.map(formatEditablePrice) ?? ""
        reportTotalWithVat = report.totalWithVat.map(formatEditablePrice) ?? ""

        if let issueDate = parseDateFromISO(report.issueDate),
           issueDate <= Date.now.addingTimeInterval(60 * 60 * 24 * 366 * 3) {
            hasIssueDate = true
            reportIssueDate = issueDate
        } else {
            hasIssueDate = false
        }
        if let dueDate = parseDateFromISO(report.dueDate),
           (!hasIssueDate || dueDate >= reportIssueDate),
           dueDate <= Date.now.addingTimeInterval(60 * 60 * 24 * 366 * 3) {
            hasDueDate = true
            reportDueDate = dueDate
        } else {
            hasDueDate = false
        }
        if let source = report.sourceType {
            selectedSourceType = normalizeSourceTypeID(source)
        }

        let mappedItems = (report.items ?? []).map { item in
            ServiceReportItemDraft(
                name: meaningfulServiceField(item.name) ?? "",
                quantity: item.quantity.map(formatEditablePrice) ?? "",
                unit: item.unit ?? "",
                unitPrice: item.unitPrice.map(formatEditablePrice) ?? "",
                totalPrice: item.totalPrice.map(formatEditablePrice) ?? ""
            )
        }
        let cleanedItems = mappedItems.filter { !$0.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        reportItems = cleanedItems.isEmpty ? [.empty] : cleanedItems
    }

    private func saveRecord() async {
        guard !isSaving else { return }
        formError = nil

        guard effectiveDescriptionForSave.count >= 3 else {
            formError = "Popis úkonu musí mít alespoň 3 znaky nebo být věrohodně odvozen z dokladu."
            return
        }
        if !mileage.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && parsedMileage == nil {
            formError = "Nájezd musí být celé kladné číslo v kilometrech."
            return
        }
        guard let priceValue = effectivePrice else {
            formError = "Cena je povinná."
            return
        }

        isSaving = true
        defer { isSaving = false }

        var attachmentsPayload = existingAttachmentObjects
        do {
            if let reportSummaryObject = try serviceReportJSONObject() {
                attachmentsPayload.insert(
                    [
                        "kind": "service_report_meta",
                        "source_type": selectedSourceType,
                        "parsed_summary": reportSummaryObject,
                    ],
                    at: 0
                )

                if let pendingAttachment {
                    guard let token = env.authManager.token else {
                        formError = "Nejste přihlášen. Přihlaste se znovu."
                        return
                    }
                    let uploadResponse = try await featureService.uploadServiceRecordAttachment(
                        vehicleId: vehicleId,
                        ServiceRecordAttachmentUploadRequest(
                            fileName: pendingAttachment.fileName,
                            fileMimeType: pendingAttachment.mimeType,
                            fileContentBase64: pendingAttachment.data.base64EncodedString()
                        ),
                        token: token
                    )
                    attachmentsPayload.append(
                        [
                            "kind": "user_document",
                            "file_name": uploadResponse.fileName,
                            "mime_type": uploadResponse.mimeType,
                            "file_size": uploadResponse.fileSize ?? pendingAttachment.data.count,
                            "storage_key": uploadResponse.storageKey,
                            "download_url": uploadResponse.downloadURL,
                            "source_type": selectedSourceType,
                            "parsed_summary": reportSummaryObject,
                        ]
                    )
                }
            }

            let attachmentsString: String? = {
                guard !attachmentsPayload.isEmpty else { return nil }
                guard let data = try? JSONSerialization.data(withJSONObject: attachmentsPayload, options: []) else { return nil }
                return String(data: data, encoding: .utf8)
            }()

            let request = ServiceRecordCreateRequest(
                performedAt: performedAt,
                mileage: parsedMileage,
                description: effectiveDescriptionForSave,
                price: priceValue,
                note: trimToNil(note),
                category: category,
                attachments: attachmentsString,
                nextServiceDueDate: hasNextServiceDueDate ? isoDateString(nextServiceDueDate) : nil
            )

            onSubmit(request)
            dismiss()
        } catch {
            formError = "Uložení se nezdařilo: \(error.localizedDescription)"
        }
    }

    private func parseAttachmentObjects(_ raw: String?) -> [[String: Any]] {
        guard
            let raw,
            let data = raw.data(using: .utf8),
            let payload = try? JSONSerialization.jsonObject(with: data, options: []) as? [[String: Any]]
        else {
            return []
        }
        return payload
    }

    private func firstParsedSummary(from raw: String?) -> ServiceReportPayload? {
        let attachments = parseAttachmentObjects(raw)
        for attachment in attachments {
            if let parsedSummary = attachment["parsed_summary"] {
                if let parsed = decodeServiceReport(from: parsedSummary) {
                    return parsed
                }
            }
        }
        return nil
    }

    private func decodeServiceReport(from object: Any) -> ServiceReportPayload? {
        guard let data = try? JSONSerialization.data(withJSONObject: object, options: []) else { return nil }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try? decoder.decode(ServiceReportPayload.self, from: data)
    }

    private func serviceReportJSONObject() throws -> [String: Any]? {
        let payload = serviceReportPayload
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(payload)
        guard let object = try JSONSerialization.jsonObject(with: data, options: []) as? [String: Any] else {
            return nil
        }
        return object
    }

    private func parseOptionalNumber(_ raw: String?) -> Double? {
        guard let raw else { return nil }
        let normalized = raw
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "\u{00A0}", with: " ")
            .replacingOccurrences(of: "Kč", with: "", options: .caseInsensitive)
            .replacingOccurrences(of: "CZK", with: "", options: .caseInsensitive)
            .replacingOccurrences(of: "EUR", with: "", options: .caseInsensitive)
            .replacingOccurrences(of: "USD", with: "", options: .caseInsensitive)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalized.isEmpty else { return nil }

        let stripped = normalized.replacingOccurrences(of: " ", with: "").replacingOccurrences(of: "'", with: "")
        let commaCount = stripped.filter { $0 == "," }.count
        let dotCount = stripped.filter { $0 == "." }.count

        let canonical: String
        if commaCount > 0 && dotCount > 0 {
            if let lastComma = stripped.lastIndex(of: ","), let lastDot = stripped.lastIndex(of: ".") {
                if lastComma > lastDot {
                    canonical = stripped.replacingOccurrences(of: ".", with: "").replacingOccurrences(of: ",", with: ".")
                } else {
                    canonical = stripped.replacingOccurrences(of: ",", with: "")
                }
            } else {
                canonical = stripped.replacingOccurrences(of: ",", with: ".")
            }
        } else if commaCount > 0 {
            canonical = commaCount > 1
                ? stripped.replacingOccurrences(of: ",", with: "")
                : stripped.replacingOccurrences(of: ",", with: ".")
        } else if dotCount > 1 {
            canonical = stripped.replacingOccurrences(of: ".", with: "")
        } else {
            canonical = stripped
        }

        guard let value = Double(canonical), value.isFinite else { return nil }
        return value
    }

    private func roundTo2(_ value: Double) -> Double {
        (value * 100).rounded() / 100
    }

    private func trimToNil(_ value: String?) -> String? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private func formatEditablePrice(_ value: Double) -> String {
        if value.rounded() == value {
            return String(format: "%.0f", value)
        }
        return String(format: "%.2f", value).replacingOccurrences(of: ".", with: ",")
    }

    private func formatMoney(_ value: Double?) -> String {
        guard let value else { return "—" }
        let formatted = value.formatted(.number.precision(.fractionLength(0...2)).grouping(.automatic))
        return "\(formatted) Kč"
    }

    private func isoDateString(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }

    private func parseDateFromISO(_ value: String?) -> Date? {
        guard let value = trimToNil(value) else { return nil }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.date(from: value)
    }

    private func normalizeServiceLink(_ raw: String?) -> String? {
        guard let raw = trimToNil(raw) else { return nil }
        let lower = raw.lowercased()
        if lower.hasPrefix("https://") || lower.hasPrefix("http://") || lower.hasPrefix("mailto:") {
            return raw
        }
        if raw.contains("@") {
            return "mailto:\(raw)"
        }
        if raw.range(of: #"^[A-Za-z0-9][A-Za-z0-9\.-]+\.[A-Za-z]{2,}.*$"#, options: .regularExpression) != nil {
            return "https://\(raw)"
        }
        return nil
    }

    private func normalizeCategoryID(_ raw: String?) -> String {
        guard let raw = trimToNil(raw) else { return "JINE" }
        let candidate = raw.uppercased()
        return knownCategoryIDs.contains(candidate) ? candidate : "JINE"
    }

    private func normalizeSourceTypeID(_ raw: String?) -> String {
        guard let raw = trimToNil(raw) else { return "invoice" }
        let candidate = raw.lowercased()
        return knownSourceTypeIDs.contains(candidate) ? candidate : "invoice"
    }

    private func hasMeaningfulPrefill(_ prefill: ServiceRecordDocumentPrefillData) -> Bool {
        if prefill.mileage != nil || prefill.price != nil || trimToNil(prefill.description) != nil {
            return true
        }
        if let report = prefill.serviceReport {
            if trimToNil(report.supplierName) != nil ||
                trimToNil(report.documentNumber) != nil ||
                trimToNil(report.serviceSummary) != nil ||
                report.totalWithVat != nil ||
                !(report.items ?? []).isEmpty {
                return true
            }
        }
        return false
    }

    private func buildLocalDocumentAnalysis(for attachment: PendingAttachment) async -> LocalDocumentAnalysis? {
        let rawText: String
        if let manual = trimToNil(manualDocumentText) {
            rawText = manual
        } else if let cached = cachedExtractedText(for: attachment) {
            rawText = cached
        } else if let extracted = await extractTextFromAttachment(attachment) {
            await MainActor.run {
                storeExtractedText(extracted, for: attachment)
            }
            rawText = extracted
        } else {
            return nil
        }

        return localDocumentAnalysis(from: rawText)
    }

    private func localDocumentAnalysis(from rawText: String) -> LocalDocumentAnalysis? {
        let lines = normalizedDocumentLines(from: rawText)
        guard !lines.isEmpty else { return nil }

        let supplierName = extractSupplierName(from: lines)
        let supplierEmail = extractEmail(from: rawText)
        let supplierWebsite = extractSupplierWebsite(from: lines, rawText: rawText, supplierEmail: supplierEmail)
        let documentNumber = extractDocumentNumber(from: rawText, lines: lines)
        let issueDate = extractLabeledDate(from: lines, labels: ["datum vystavení", "datum vystaveni", "datum dokladu", "vystaveno", "issue date"])
        let extractedDueDate = extractLabeledDate(from: lines, labels: ["datum splatnosti", "splatnost", "due date"])
        let dueDate: Date? = {
            guard let extractedDueDate else { return nil }
            if let issueDate, extractedDueDate < issueDate {
                return nil
            }
            return extractedDueDate
        }()
        let mileage = extractMileage(from: rawText, lines: lines)
        let total = extractTotalAmount(from: lines)
        let currency = detectCurrency(in: rawText)
        let items = extractServiceItems(from: lines, currency: currency)
        let serviceSummary = extractServiceSummary(from: rawText, lines: lines, items: items, supplierName: supplierName)
        let issueDescription = extractIssueDescription(from: lines)
        let customerName = meaningfulCustomerName(extractCustomerName(from: lines))
        let technicianName = meaningfulPersonName(extractTechnicianName(from: lines))
        let inferredCategory = inferCategory(from: rawText)
        let trustedSummary = trustedDescriptionCandidate(serviceSummary)
        let trustedIssueDescription = trustedDescriptionCandidate(issueDescription)

        let payload = ServiceReportPayload(
            sourceType: selectedSourceType,
            documentNumber: documentNumber,
            supplierName: supplierName,
            supplierEmail: supplierEmail,
            supplierWebsite: supplierWebsite,
            serviceLink: nil,
            customerName: customerName,
            serviceSummary: trustedSummary,
            issueDescription: trustedIssueDescription,
            technicianName: technicianName,
            technicianInitials: technicianName.flatMap(initials(from:)),
            issueDate: issueDate.map(isoDateString),
            dueDate: dueDate.map(isoDateString),
            currency: currency,
            laborHours: nil,
            laborHourRate: nil,
            laborTotal: nil,
            materialsTotal: nil,
            subtotalWithoutVat: total,
            vatRate: nil,
            vatAmount: nil,
            totalWithVat: total,
            items: items.isEmpty ? nil : items
        )

        let descriptionCandidate = trustedSummary ?? trustedIssueDescription

        let prefill = ServiceRecordDocumentPrefillData(
            performedAt: issueDate,
            mileage: mileage,
            description: descriptionCandidate,
            price: total,
            note: nil,
            category: inferredCategory,
            serviceReport: payload
        )

        var fieldCount = 0
        var confidenceScore = 0
        if supplierName != nil { fieldCount += 1 }
        if supplierName != nil { confidenceScore += 18 }
        if documentNumber != nil { fieldCount += 1 }
        if documentNumber != nil { confidenceScore += 16 }
        if descriptionCandidate != nil { fieldCount += 1 }
        if descriptionCandidate != nil { confidenceScore += 16 }
        if mileage != nil { fieldCount += 1 }
        if mileage != nil { confidenceScore += 12 }
        if total != nil { fieldCount += 1 }
        if total != nil { confidenceScore += 20 }
        fieldCount += min(items.count, 3)
        confidenceScore += min(items.count, 3) * 6
        if supplierEmail != nil { confidenceScore += 4 }
        if supplierWebsite != nil { confidenceScore += 4 }
        if issueDate != nil { confidenceScore += 4 }
        if dueDate != nil { confidenceScore += 2 }

        let confidence = max(12, min(confidenceScore, 96))

        guard hasMeaningfulPrefill(prefill) else { return nil }
        return LocalDocumentAnalysis(
            prefill: prefill,
            supplierName: supplierName,
            total: total,
            fieldCount: fieldCount,
            confidence: confidence
        )
    }

    private func resolvedDocumentConfidence(
        backendConfidence: Double?,
        parsedConfidence: Double?,
        localAnalysis: LocalDocumentAnalysis?,
        backendHasMeaningfulPrefill: Bool
    ) -> Int {
        let normalizedBackendConfidence: Int? = {
            guard let backendConfidence else { return nil }
            let percentage = Int((backendConfidence * 100).rounded())
            guard percentage > 0 else { return nil }
            return min(percentage, 99)
        }()

        let normalizedParsedConfidence: Int? = {
            guard let parsedConfidence else { return nil }
            let percentage = Int((parsedConfidence * 100).rounded())
            guard percentage > 0 else { return nil }
            return min(percentage, 99)
        }()

        if let normalizedBackendConfidence {
            return normalizedBackendConfidence
        }

        if backendHasMeaningfulPrefill, let normalizedParsedConfidence {
            return max(normalizedParsedConfidence, localAnalysis?.confidence ?? 0)
        }

        if let localAnalysis {
            return localAnalysis.confidence
        }

        return normalizedParsedConfidence ?? 0
    }

    private func normalizedDocumentLines(from rawText: String) -> [String] {
        let rawLines = rawText
            .replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: "\r", with: "\n")
            .components(separatedBy: .newlines)
            .map {
                $0
                    .replacingOccurrences(of: "\u{00A0}", with: " ")
                    .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
                    .trimmingCharacters(in: .whitespacesAndNewlines)
            }
            .filter { !$0.isEmpty }

        var seen = Set<String>()
        return rawLines
            .filter { !isLikelyNoiseDocumentLine($0) }
            .filter { seen.insert($0.lowercased()).inserted }
    }

    private func isLikelyNoiseDocumentLine(_ line: String) -> Bool {
        let folded = line.folding(options: .diacriticInsensitive, locale: .current).lowercased()
        let normalized = folded.trimmingCharacters(in: .whitespacesAndNewlines)

        if normalized.isEmpty { return true }

        let exactNoise = Set([
            "novy zaznam", "zrusit", "ulozit", "polozky", "sousty", "soucty",
            "doklad a automaticke vycteni", "pridat polozku", "odeslat"
        ])
        if exactNoise.contains(normalized) { return true }

        let containsNoise = [
            "haynespro", "autokelly", "realauto", "aci -", "auto kelly",
            "facebook", "instagram", "youtube", "cookies", "odeslat"
        ]
        if containsNoise.contains(where: normalized.contains) { return true }

        if normalized.contains("ail?f=") || normalized.contains("utm_") { return true }
        if normalized.contains("http://") || normalized.contains("https://") { return true }
        if normalized.count > 30 && normalized.range(of: #"[a-z0-9]{20,}"#, options: .regularExpression) != nil && !normalized.contains(" ") {
            return true
        }

        return false
    }

    private func extractSupplierName(from lines: [String]) -> String? {
        if let labeled = extractLabeledText(from: lines, labels: ["dodavatel", "servis", "provozovna", "supplier", "garage"]) {
            return cleanedSupplierName(labeled)
        }

        let ignorePrefixes = ["faktura", "daňový doklad", "danovy doklad", "invoice", "účtenka", "uctenka"]
        let ignoreContains = ["datum", "doklad", "ico", "dič", "dic", "iban", "www.", "@", "vin", "spz", "rz"]

        for line in lines.prefix(10) {
            let lower = line.lowercased()
            if ignorePrefixes.contains(where: { lower.hasPrefix($0) }) { continue }
            if ignoreContains.contains(where: { lower.contains($0) }) { continue }
            if lower.range(of: #"s\.r\.o|a\.s|servis|auto|garage|motors|pneu|autoservis|car"#, options: .regularExpression) != nil {
                return cleanedSupplierName(line)
            }
        }

        return lines.first.flatMap(cleanedSupplierName)
    }

    private func extractDocumentNumber(from rawText: String, lines: [String]) -> String? {
        let patterns = [
            #"(?i)(?:č(?:í|i)slo\s+dokladu|č\.\s*dokladu|doklad|faktura|invoice|objednávka|objednavka|zakázka|zakazka)\s*(?:č\.?|no\.?|nr\.?|#)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9/\-]{3,})"#,
            #"(?i)(?:variabilní symbol|variabilni symbol)\s*[:\-]?\s*([0-9]{4,})"#
        ]
        for pattern in patterns {
            if let match = firstRegexCapture(in: rawText, pattern: pattern) {
                return match
            }
        }
        return extractLabeledText(from: lines, labels: ["číslo dokladu", "cislo dokladu", "faktura", "doklad"])
    }

    private func extractLabeledDate(from lines: [String], labels: [String]) -> Date? {
        for (index, line) in lines.enumerated() {
            let lower = line.lowercased()
            guard labels.contains(where: { lower.contains($0) }) else { continue }
            if let date = extractFirstDate(from: line) {
                return trustedDocumentDate(date, labels: labels)
            }
            if let next = lines[safe: index + 1], let date = extractFirstDate(from: next) {
                return trustedDocumentDate(date, labels: labels)
            }
        }
        return nil
    }

    private func extractFirstDate(from raw: String) -> Date? {
        let patterns = [
            #"(\d{1,2}\.\d{1,2}\.\d{4})"#,
            #"(\d{1,2}/\d{1,2}/\d{4})"#,
            #"(\d{4}-\d{2}-\d{2})"#
        ]
        for pattern in patterns {
            guard let value = firstRegexCapture(in: raw, pattern: pattern) else { continue }
            if let date = parseFlexibleDate(value) {
                return date
            }
        }
        return nil
    }

    private func parseFlexibleDate(_ raw: String) -> Date? {
        let formats = ["dd.MM.yyyy", "d.M.yyyy", "dd/MM/yyyy", "d/M/yyyy", "yyyy-MM-dd"]
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "cs_CZ")
        formatter.timeZone = TimeZone.current
        for format in formats {
            formatter.dateFormat = format
            if let date = formatter.date(from: raw) {
                return date
            }
        }
        return nil
    }

    private func extractMileage(from rawText: String, lines: [String]) -> Int? {
        let mileagePatterns = [
            #"(?i)(?:nájezd|naj[eé]zd|stav\s*tachometru|tachometr|stav\s*km|km\s*stav)\s*[:\-]?\s*([0-9][0-9\s\.]{2,})"#,
            #"(?i)(?:kilometr(?:y|ů|u)?|km)\s*[:\-]?\s*([0-9][0-9\s\.]{2,})"#
        ]
        for pattern in mileagePatterns {
            if let match = firstRegexCapture(in: rawText, pattern: pattern),
               let mileage = parseIntegerLike(match) {
                return mileage
            }
        }

        for line in lines {
            let lower = line.lowercased()
            guard lower.contains(" km") || lower.contains("tachometr") || lower.contains("nájezd") || lower.contains("najedz") else { continue }
            if let value = firstRegexCapture(in: line, pattern: #"([0-9][0-9\s\.]{2,})"#),
               let mileage = parseIntegerLike(value) {
                return mileage
            }
        }
        return nil
    }

    private func extractTotalAmount(from lines: [String]) -> Double? {
        var best: (value: Double, score: Int) = (0, Int.min)

        for (index, line) in lines.enumerated() {
            let lower = line.lowercased()
            let values = regexCaptures(in: line, pattern: #"([0-9]{1,3}(?:[ \.\u{00A0}][0-9]{3})*(?:,[0-9]{2})?|[0-9]+(?:,[0-9]{2})?)"#)
            for rawValue in values {
                guard let value = parseOptionalNumber(rawValue), value > 0 else { continue }
                var score = 0
                if lower.contains("celkem k úhradě") || lower.contains("celkem k uhradě") || lower.contains("k úhradě") || lower.contains("k uhradě") || lower.contains("k zaplacení") || lower.contains("uhraďte") || lower.contains("uhradte") {
                    score += 8
                }
                if lower.contains("celkem") || lower.contains("total") {
                    score += 4
                }
                if lower.contains("s dph") || lower.contains("včetně dph") || lower.contains("vcetne dph") {
                    score += 3
                }
                if lower.contains("dph") && !lower.contains("s dph") && !lower.contains("včetně dph") && !lower.contains("vcetne dph") {
                    score -= 2
                }
                if lower.contains("základ") || lower.contains("zaklad") || lower.contains("mezisoučet") || lower.contains("mezisoucet") || lower.contains("jedn") {
                    score -= 2
                }
                if index >= max(lines.count - 8, 0) {
                    score += 1
                }
                if value > best.value {
                    score += 1
                }
                if score > best.score || (score == best.score && value > best.value) {
                    best = (value, score)
                }
            }
        }

        return best.score == Int.min ? nil : best.value
    }

    private func detectCurrency(in rawText: String) -> String {
        let lower = rawText.lowercased()
        if lower.contains("eur") || lower.contains("€") { return "EUR" }
        if lower.contains("usd") || lower.contains("$") { return "USD" }
        return "CZK"
    }

    private func extractServiceItems(from lines: [String], currency: String) -> [ServiceReportItemPayload] {
        var items: [ServiceReportItemPayload] = []
        let stopWords = ["celkem", "k úhradě", "k uhradě", "základ", "zaklad", "dph", "splatnost", "variabilní symbol", "variabilni symbol", "ico", "dič", "dic", "iban", "vin"]

        for line in lines {
            let lower = line.lowercased()
            if stopWords.contains(where: { lower.contains($0) }) { continue }
            if lower.contains("@") || lower.contains("www.") || lower.contains("http") { continue }
            let matches = regexCaptures(in: line, pattern: #"([0-9]{1,3}(?:[ \.\u{00A0}][0-9]{3})*(?:,[0-9]{2})?|[0-9]+(?:,[0-9]{2})?)"#)
            guard let rawAmount = matches.last, let amount = parseOptionalNumber(rawAmount), amount > 0 else { continue }

            let name = line
                .replacingOccurrences(of: rawAmount, with: "")
                .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
                .trimmingCharacters(in: .whitespacesAndNewlines)

            guard name.count >= 4 else { continue }
            guard name.range(of: #"[A-Za-zÁ-Žá-ž]"#, options: .regularExpression) != nil else { continue }
            guard isMeaningfulServiceText(name) else { continue }

            items.append(
                ServiceReportItemPayload(
                    name: name,
                    quantity: nil,
                    unit: nil,
                    unitPrice: nil,
                    totalPrice: amount,
                    currency: currency
                )
            )
        }

        var seen = Set<String>()
        return items.filter {
            let key = "\($0.name.lowercased())-\($0.totalPrice ?? 0)"
            return seen.insert(key).inserted
        }
        .prefix(8)
        .map { $0 }
    }

    private func extractServiceSummary(
        from rawText: String,
        lines: [String],
        items: [ServiceReportItemPayload],
        supplierName: String?
    ) -> String? {
        if let labeled = extractLabeledText(from: lines, labels: ["provedené práce", "provedene prace", "rozsah prací", "rozsah praci", "předmět", "predmet", "popis", "servisní práce", "servisni prace"]) {
            if isMeaningfulServiceText(labeled) {
                return labeled
            }
        }
        if !items.isEmpty {
            let summary = items.prefix(3).map(\.name).joined(separator: ", ")
            if isMeaningfulServiceText(summary), summary.count <= 120 {
                return summary
            }
        }
        return extractIssueDescription(from: lines)
    }

    private func extractIssueDescription(from lines: [String]) -> String? {
        guard let text = extractLabeledText(from: lines, labels: ["závada", "zavada", "poznámka", "poznamka", "oprava", "reklamace", "diagnostika"]) else { return nil }
        return isMeaningfulServiceText(text) ? text : nil
    }

    private func extractCustomerName(from lines: [String]) -> String? {
        extractLabeledText(from: lines, labels: ["odběratel", "odberatel", "zákazník", "zakaznik", "customer"])
    }

    private func extractTechnicianName(from lines: [String]) -> String? {
        extractLabeledText(from: lines, labels: ["technik", "mechanik", "provedl", "přijal", "prijal"])
    }

    private func extractLabeledText(from lines: [String], labels: [String]) -> String? {
        for (index, line) in lines.enumerated() {
            let lower = line.lowercased()
            guard let label = labels.first(where: { lower.contains($0) }) else { continue }

            if let range = lower.range(of: label) {
                let suffix = String(line[range.upperBound...])
                    .trimmingCharacters(in: CharacterSet(charactersIn: ":.- ").union(.whitespacesAndNewlines))
                if suffix.count >= 2, isMeaningfulServiceText(suffix) {
                    return suffix
                }
            }

            if let next = lines[safe: index + 1], next.count >= 2, isMeaningfulServiceText(next) {
                return next
            }
        }
        return nil
    }

    private func cleanedSupplierName(_ raw: String) -> String? {
        let cleaned = raw
            .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard cleaned.count >= 3 else { return nil }
        guard !isLikelyNoiseDocumentLine(cleaned) else { return nil }
        return cleaned
    }

    private func isMeaningfulServiceText(_ raw: String) -> Bool {
        let folded = raw.folding(options: .diacriticInsensitive, locale: .current).lowercased()
        let text = folded.trimmingCharacters(in: .whitespacesAndNewlines)
        guard text.count >= 3 else { return false }
        if isLikelyNoiseDocumentLine(text) { return false }

        let generic = [
            "polozky", "polozka", "soucty", "souhrn", "celkem", "cena", "datum",
            "dodavatel", "odberatel", "technik", "doklad", "faktura", "cislo dokladu"
        ]
        if generic.contains(text) { return false }
        if text.contains("@") || text.contains("www.") || text.contains("http") { return false }
        return text.range(of: #"[a-zá-ž]"#, options: .regularExpression) != nil
    }

    private func extractEmail(from rawText: String) -> String? {
        firstRegexCapture(in: rawText, pattern: #"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}"#, options: [.caseInsensitive])
    }

    private func extractWebsite(from rawText: String) -> String? {
        if let direct = firstRegexCapture(in: rawText, pattern: #"https?://[^\s]+"#, options: [.caseInsensitive]) {
            return direct.trimmingCharacters(in: CharacterSet(charactersIn: ".,);"))
        }
        if let domain = firstRegexCapture(in: rawText, pattern: #"\b(?:www\.)?[a-z0-9.-]+\.[a-z]{2,}(?:/[^\s]*)?"#, options: [.caseInsensitive]) {
            return domain
        }
        return nil
    }

    private func extractSupplierWebsite(from lines: [String], rawText: String, supplierEmail: String?) -> String? {
        for (index, line) in lines.enumerated() {
            let lower = line.lowercased()
            guard lower.contains("web") || lower.contains("www") || lower.contains("http") || lower.contains("odkaz") else { continue }
            if let direct = meaningfulWebsite(extractWebsite(from: line)) {
                return direct
            }
            if let next = lines[safe: index + 1], let direct = meaningfulWebsite(extractWebsite(from: next)) {
                return direct
            }
        }

        if let supplierEmail,
           let emailDomain = supplierEmail.split(separator: "@").last.map(String.init)?.lowercased(),
           emailDomain.contains(".") {
            return "https://\(emailDomain)"
        }

        return meaningfulWebsite(extractWebsite(from: rawText))
    }

    private func meaningfulDocumentValue(_ raw: String?) -> String? {
        guard let value = trimToNil(raw) else { return nil }
        guard !isLikelyNoiseDocumentLine(value) else { return nil }
        return value
    }

    private func meaningfulServiceField(_ raw: String?) -> String? {
        guard let value = trimToNil(raw), isMeaningfulServiceText(value) else { return nil }
        return value
    }

    private func meaningfulWebsite(_ raw: String?) -> String? {
        guard let value = normalizeServiceLink(raw) else { return nil }
        let lower = value.lowercased()
        let blocked = ["facebook.com", "instagram.com", "youtube.com", "autokelly", "haynespro", "realauto"]
        guard !blocked.contains(where: lower.contains) else { return nil }
        return value
    }

    private func meaningfulEmail(_ raw: String?) -> String? {
        guard let value = trimToNil(raw), value.contains("@") else { return nil }
        return value
    }

    private func meaningfulPersonName(_ raw: String?) -> String? {
        guard let value = trimToNil(raw), value.count >= 3 else { return nil }
        let lower = value.folding(options: .diacriticInsensitive, locale: .current).lowercased()
        let blocked = ["dodavatel", "odberatel", "servis", "technik", "doklad", "faktura", "email", "web", "odkaz"]
        guard !blocked.contains(where: lower.contains) else { return nil }
        guard value.range(of: #"[A-Za-zÁ-Žá-ž]"#, options: .regularExpression) != nil else { return nil }
        return value
    }

    private func meaningfulInitials(_ raw: String?) -> String? {
        guard let value = trimToNil(raw) else { return nil }
        let upper = value.uppercased()
        guard upper.range(of: #"^[A-Z]{1,4}$"#, options: .regularExpression) != nil else { return nil }
        return upper
    }

    private func meaningfulCustomerName(_ raw: String?) -> String? {
        guard let value = trimToNil(raw), value.count >= 3 else { return nil }
        guard value.range(of: #"[A-Za-zÁ-Žá-ž]"#, options: .regularExpression) != nil else { return nil }
        let lower = value.folding(options: .diacriticInsensitive, locale: .current).lowercased()
        let blocked = ["faktura", "doklad", "cislo", "objednavka", "zakazka", "ico", "dic", "vin", "spz"]
        guard !blocked.contains(where: lower.contains) else { return nil }
        return value
    }

    private func meaningfulCurrency(_ raw: String?) -> String? {
        guard let value = trimToNil(raw)?.uppercased() else { return nil }
        let allowed = Set(["CZK", "EUR", "USD", "PLN", "HUF"])
        return allowed.contains(value) ? value : nil
    }

    private func trustedDescriptionCandidate(_ raw: String?) -> String? {
        guard let value = meaningfulServiceField(raw) else { return nil }
        let normalized = value.folding(options: .diacriticInsensitive, locale: .current).lowercased()
        let blocked = [
            "polozky", "polozka", "soucty", "souhrn", "dodavatel", "odberatel",
            "cislo dokladu", "doklad", "faktura", "datum", "splatnost", "odeslat"
        ]
        guard !blocked.contains(where: { normalized == $0 || normalized.hasPrefix("\($0) ") }) else { return nil }
        guard !normalized.contains("http://"), !normalized.contains("https://"), !normalized.contains("@") else { return nil }
        guard value.count <= 140 else { return nil }
        let wordCount = value.split(whereSeparator: \.isWhitespace).count
        guard wordCount >= 2 else { return nil }
        return value
    }

    private func trustedDocumentDate(_ date: Date, labels: [String]) -> Date? {
        let now = Date()
        let thirtyDaysAhead = now.addingTimeInterval(60 * 60 * 24 * 30)
        let oneYearAhead = now.addingTimeInterval(60 * 60 * 24 * 366)
        let lowerLabels = labels.joined(separator: " ").lowercased()

        if lowerLabels.contains("splatnost") || lowerLabels.contains("due") {
            return date <= oneYearAhead ? date : nil
        }
        return date <= thirtyDaysAhead ? date : nil
    }

    private func inferredDescription(
        from items: [ServiceReportItemPayload],
        category: String,
        supplierName: String?,
        documentNumber: String?
    ) -> String? {
        if let firstItem = items.first?.name, isMeaningfulServiceText(firstItem) {
            return firstItem
        }

        let categoryLabel = categoryOptions.first(where: { $0.id == category })?.label ?? "Servis"
        if let supplierName = meaningfulDocumentValue(supplierName) {
            return "\(categoryLabel) – \(supplierName)"
        }
        if let documentNumber = meaningfulDocumentValue(documentNumber) {
            return "\(categoryLabel) – doklad \(documentNumber)"
        }
        return categoryLabel
    }

    private func inferCategory(from rawText: String) -> String {
        let lower = rawText.folding(options: .diacriticInsensitive, locale: .current).lowercased()
        let mapping: [(String, [String])] = [
            ("OLEJ", ["olej", "mazivo"]),
            ("BRZDY", ["brzdy", "brzd", "kotouc", "desticky"]),
            ("PNEU", ["pneu", "pneumatik", "guma", "geometrie", "vyvazeni"]),
            ("STK", ["stk", "emise", "technicka"]),
            ("DIAGNOSTIKA", ["diagnost", "diagnosis"]),
            ("FILTRY", ["filtr"]),
            ("CHLADICI", ["chlazeni", "chladic", "antifreeze"]),
            ("VYFUK", ["vyfuk", "katalyzator"]),
            ("OSVETLENI", ["svetlo", "osvetleni", "zarovka"]),
            ("ELEKTRIKA", ["baterie", "alternator", "starter", "elektr"]),
            ("KLIMATIZACE", ["klimatiz", "ac"]),
            ("PREVENTIVNI", ["kontrola", "prohlidka"]),
            ("OPRAVA", ["oprava", "servis", "udrzba", "vymena"])
        ]
        for (categoryID, keywords) in mapping {
            if keywords.contains(where: { lower.contains($0) }) {
                return categoryID
            }
        }
        return category
    }

    private func initials(from name: String) -> String? {
        let initials = name
            .split(separator: " ")
            .prefix(2)
            .compactMap { $0.first }
            .map { String($0) }
            .joined()
        return initials.isEmpty ? nil : initials.uppercased()
    }

    private func parseIntegerLike(_ raw: String) -> Int? {
        let normalized = raw
            .replacingOccurrences(of: "\u{00A0}", with: "")
            .replacingOccurrences(of: " ", with: "")
            .replacingOccurrences(of: ".", with: "")
            .replacingOccurrences(of: ",", with: "")
        return Int(normalized)
    }

    private func firstRegexCapture(
        in raw: String,
        pattern: String,
        options: NSRegularExpression.Options = []
    ) -> String? {
        regexCaptures(in: raw, pattern: pattern, options: options).first
    }

    private func regexCaptures(
        in raw: String,
        pattern: String,
        options: NSRegularExpression.Options = []
    ) -> [String] {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: options) else { return [] }
        let nsRange = NSRange(raw.startIndex..<raw.endIndex, in: raw)
        return regex.matches(in: raw, options: [], range: nsRange).compactMap { match in
            let rangeIndex = match.numberOfRanges > 1 ? 1 : 0
            guard let range = Range(match.range(at: rangeIndex), in: raw) else { return nil }
            return String(raw[range]).trimmingCharacters(in: .whitespacesAndNewlines)
        }
    }

    private func inferLaborMaterialBreakdown(items: [ServiceReportItemPayload]) -> ServiceReportLaborMaterial {
        var labor = 0.0
        var materials = 0.0
        var hasLabor = false
        var hasMaterials = false

        for item in items {
            guard let total = item.totalPrice, total > 0 else { continue }
            if isLaborItem(item) {
                hasLabor = true
                labor += total
            } else {
                hasMaterials = true
                materials += total
            }
        }

        return ServiceReportLaborMaterial(
            laborTotal: hasLabor ? roundTo2(labor) : nil,
            materialsTotal: hasMaterials ? roundTo2(materials) : nil
        )
    }

    private func isLaborItem(_ item: ServiceReportItemPayload) -> Bool {
        let unit = (item.unit ?? "").lowercased()
        if ["h", "hod", "hod.", "hodina", "hodiny", "hr", "nh"].contains(unit) {
            return true
        }
        let text = item.name.lowercased()
        let keywords = ["práce", "prace", "servisní práce", "servisni prace", "diagnost", "montáž", "montaz", "oprava", "seřízení", "serizeni"]
        return keywords.contains { text.contains($0) }
    }

    private func mimeTypeFrom(url: URL) -> String? {
        let ext = url.pathExtension
        guard !ext.isEmpty else { return nil }
        return UTType(filenameExtension: ext)?.preferredMIMEType
    }
}

private struct ServiceReportItemDraft: Identifiable, Equatable {
    let id = UUID()
    var name: String
    var quantity: String
    var unit: String
    var unitPrice: String
    var totalPrice: String

    init(name: String, quantity: String, unit: String, unitPrice: String, totalPrice: String) {
        self.name = name
        self.quantity = quantity
        self.unit = unit
        self.unitPrice = unitPrice
        self.totalPrice = totalPrice
    }

    static let empty = ServiceReportItemDraft(name: "", quantity: "", unit: "", unitPrice: "", totalPrice: "")

    init(_ item: ServiceRecordTemplateItem) {
        self.name = item.name
        self.quantity = item.quantity
        self.unit = item.unit
        self.unitPrice = item.unitPrice
        self.totalPrice = item.totalPrice
    }
}

private struct ManualQuickPreset: Identifiable {
    let id: String
    let title: String
    let subtitle: String
    let categoryID: String
    let description: String
    let summary: String
    let note: String
    let items: [ServiceReportItemDraft]
}

private struct ScanChecklistRow: Identifiable {
    let id = UUID()
    let title: String
    let value: String
    let isComplete: Bool
    let accent: Color
}

private struct ScanReviewField: Identifiable {
    let id = UUID()
    let title: String
    let value: String?
    let placeholder: String
    let status: ScanReviewFieldStatus
    let icon: String
    let accent: Color
    let actionTitle: String
    let action: () -> Void
}

private enum RecordListFilter: String, CaseIterable, Identifiable {
    case all
    case priced
    case upcoming
    case ai

    var id: String { rawValue }

    var label: String {
        switch self {
        case .all:
            return "Vše"
        case .priced:
            return "S cenou"
        case .upcoming:
            return "Brzy znovu"
        case .ai:
            return "AI záznamy"
        }
    }

    var shortLabel: String {
        switch self {
        case .all:
            return "Vše"
        case .priced:
            return "Cena"
        case .upcoming:
            return "Další servis"
        case .ai:
            return "AI"
        }
    }

    var iconName: String {
        switch self {
        case .all:
            return "line.3.horizontal.decrease.circle"
        case .priced:
            return "banknote"
        case .upcoming:
            return "calendar.badge.clock"
        case .ai:
            return "sparkles"
        }
    }

    func matches(_ record: ServiceRecord) -> Bool {
        switch self {
        case .all:
            return true
        case .priced:
            return record.price != nil
        case .upcoming:
            guard let date = record.nextServiceDueDate else { return false }
            return date >= Calendar.current.startOfDay(for: Date())
        case .ai:
            return record.createdByAI
        }
    }
}

private enum ScanReviewFieldStatus {
    case ready
    case missing

    var label: String {
        switch self {
        case .ready:
            return "připraveno"
        case .missing:
            return "zkontrolovat"
        }
    }

    var color: Color {
        switch self {
        case .ready:
            return Theme.Colors.primary
        case .missing:
            return Theme.Colors.warning
        }
    }
}

private enum EditorSectionAnchor: String, Hashable {
    case basic
    case document
    case report
    case items
    case totals
}

private struct ServiceReportLaborMaterial {
    let laborTotal: Double?
    let materialsTotal: Double?
}

private struct ServiceReportTotals {
    let laborTotal: Double?
    let materialsTotal: Double?
    let subtotalWithoutVat: Double?
    let vatAmount: Double?
    let totalWithVat: Double?
}

private struct LocalDocumentAnalysis {
    let prefill: ServiceRecordDocumentPrefillData
    let supplierName: String?
    let total: Double?
    let fieldCount: Int
    let confidence: Int
}

private struct PendingAttachment {
    let data: Data
    let fileName: String
    let mimeType: String
    let sourceLabel: String
    let ocrImages: [UIImage]?

    var sizeDescription: String {
        ByteCountFormatter.string(fromByteCount: Int64(data.count), countStyle: .file)
    }
}

private enum AnalysisTone {
    case info
    case success
    case warning
    case error

    var color: Color {
        switch self {
        case .info:
            return .blue
        case .success:
            return .green
        case .warning:
            return .orange
        case .error:
            return .red
        }
    }

    var iconName: String {
        switch self {
        case .info:
            return "info.circle.fill"
        case .success:
            return "checkmark.seal.fill"
        case .warning:
            return "exclamationmark.triangle.fill"
        case .error:
            return "xmark.octagon.fill"
        }
    }

    var title: String {
        switch self {
        case .info:
            return "Průběh analýzy"
        case .success:
            return "Doklad zpracován"
        case .warning:
            return "Vyžaduje kontrolu"
        case .error:
            return "Analýza selhala"
        }
    }
}

private extension Array {
    subscript(safe index: Int) -> Element? {
        get {
            indices.contains(index) ? self[index] : nil
        }
        set {
            guard indices.contains(index), let newValue else { return }
            self[index] = newValue
        }
    }
}

private extension CGImagePropertyOrientation {
    init(_ orientation: UIImage.Orientation) {
        switch orientation {
        case .up:
            self = .up
        case .down:
            self = .down
        case .left:
            self = .left
        case .right:
            self = .right
        case .upMirrored:
            self = .upMirrored
        case .downMirrored:
            self = .downMirrored
        case .leftMirrored:
            self = .leftMirrored
        case .rightMirrored:
            self = .rightMirrored
        @unknown default:
            self = .up
        }
    }
}

private struct ServiceRecordDocumentScanner: UIViewControllerRepresentable {
    let onComplete: (PendingAttachment) -> Void
    let onCancel: () -> Void

    func makeUIViewController(context: Context) -> VNDocumentCameraViewController {
        let controller = VNDocumentCameraViewController()
        controller.delegate = context.coordinator
        return controller
    }

    func updateUIViewController(_ uiViewController: VNDocumentCameraViewController, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(onComplete: onComplete, onCancel: onCancel)
    }

    final class Coordinator: NSObject, VNDocumentCameraViewControllerDelegate {
        private let onComplete: (PendingAttachment) -> Void
        private let onCancel: () -> Void

        init(onComplete: @escaping (PendingAttachment) -> Void, onCancel: @escaping () -> Void) {
            self.onComplete = onComplete
            self.onCancel = onCancel
        }

        func documentCameraViewControllerDidCancel(_ controller: VNDocumentCameraViewController) {
            controller.dismiss(animated: true)
            onCancel()
        }

        func documentCameraViewController(_ controller: VNDocumentCameraViewController, didFailWithError error: Error) {
            controller.dismiss(animated: true)
            onCancel()
        }

        func documentCameraViewController(_ controller: VNDocumentCameraViewController, didFinishWith scan: VNDocumentCameraScan) {
            let images = (0..<scan.pageCount).map { Self.optimizedScanImage(from: scan.imageOfPage(at: $0)) }
            controller.dismiss(animated: true) {
                let formatter = DateFormatter()
                formatter.dateFormat = "yyyyMMdd_HHmmss"
                let stamp = formatter.string(from: Date())

                if images.count == 1, let jpeg = images[0].jpegData(compressionQuality: 0.82) {
                    self.onComplete(
                        PendingAttachment(
                            data: jpeg,
                            fileName: "scan_\(stamp).jpg",
                            mimeType: "image/jpeg",
                            sourceLabel: "Sken",
                            ocrImages: [images[0]]
                        )
                    )
                    return
                }

                guard let data = Self.pdfData(from: images) else {
                    self.onCancel()
                    return
                }

                self.onComplete(
                    PendingAttachment(
                        data: data,
                        fileName: "scan_\(stamp).pdf",
                        mimeType: "application/pdf",
                        sourceLabel: "Sken",
                        ocrImages: images
                    )
                )
            }
        }

        private static func optimizedScanImage(from image: UIImage) -> UIImage {
            let normalized = normalizedImage(from: image)
            let maxLongEdge: CGFloat = 2400
            let longEdge = max(normalized.size.width, normalized.size.height)
            guard longEdge > maxLongEdge, longEdge > 0 else { return normalized }
            let scale = maxLongEdge / longEdge
            let targetSize = CGSize(width: normalized.size.width * scale, height: normalized.size.height * scale)
            let renderer = UIGraphicsImageRenderer(size: targetSize)
            return renderer.image { _ in
                normalized.draw(in: CGRect(origin: .zero, size: targetSize))
            }
        }

        private static func pdfData(from images: [UIImage]) -> Data? {
            guard !images.isEmpty else { return nil }
            let fallbackSize = CGSize(width: 2480, height: 3508)
            let firstSize = images.first?.size ?? fallbackSize
            let pageRect = CGRect(origin: .zero, size: firstSize)
            let renderer = UIGraphicsPDFRenderer(bounds: pageRect)
            return renderer.pdfData { context in
                for image in images {
                    let size = image.size.width > 0 && image.size.height > 0 ? image.size : fallbackSize
                    let dynamicPageRect = CGRect(origin: .zero, size: size)
                    context.beginPage(withBounds: dynamicPageRect, pageInfo: [:])
                    image.draw(in: dynamicPageRect)
                }
            }
        }

        private static func normalizedImage(from image: UIImage) -> UIImage {
            guard image.imageOrientation != .up else { return image }
            let renderer = UIGraphicsImageRenderer(size: image.size)
            return renderer.image { _ in
                image.draw(in: CGRect(origin: .zero, size: image.size))
            }
        }
    }
}

private struct ServiceRecordCameraCapture: UIViewControllerRepresentable {
    let onComplete: (PendingAttachment) -> Void
    let onCancel: () -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onComplete: onComplete, onCancel: onCancel)
    }

    func makeUIViewController(context: Context) -> CameraViewController {
        let controller = CameraViewController()
        controller.coordinator = context.coordinator
        context.coordinator.controller = controller
        return controller
    }

    func updateUIViewController(_ uiViewController: CameraViewController, context: Context) {}

    final class Coordinator: NSObject, AVCapturePhotoCaptureDelegate {
        private let onComplete: (PendingAttachment) -> Void
        private let onCancel: () -> Void
        weak var controller: CameraViewController?

        init(onComplete: @escaping (PendingAttachment) -> Void, onCancel: @escaping () -> Void) {
            self.onComplete = onComplete
            self.onCancel = onCancel
        }

        func cancel() {
            onCancel()
        }

        func complete(_ attachment: PendingAttachment) {
            onComplete(attachment)
        }

        func photoOutput(_ output: AVCapturePhotoOutput, didFinishProcessingPhoto photo: AVCapturePhoto, error: Error?) {
            guard error == nil,
                  let data = photo.fileDataRepresentation(),
                  let image = UIImage(data: data) else {
                DispatchQueue.main.async {
                    self.controller?.finishCancel()
                }
                return
            }

            let preparedImage = Self.preparedCaptureImage(from: image)
            guard let jpegData = preparedImage.jpegData(compressionQuality: 0.82) else {
                DispatchQueue.main.async {
                    self.controller?.finishCancel()
                }
                return
            }

            let formatter = DateFormatter()
            formatter.dateFormat = "yyyyMMdd_HHmmss"
            let stamp = formatter.string(from: Date())

            let attachment = PendingAttachment(
                data: jpegData,
                fileName: "photo_\(stamp).jpg",
                mimeType: "image/jpeg",
                sourceLabel: "Fotoaparát",
                ocrImages: [preparedImage]
            )

            DispatchQueue.main.async {
                self.controller?.finishCapture(attachment)
            }
        }

        private static func preparedCaptureImage(from image: UIImage) -> UIImage {
            let normalized = normalizedImage(from: image)
            let maxLongEdge: CGFloat = 2400
            let longEdge = max(normalized.size.width, normalized.size.height)
            guard longEdge > maxLongEdge, longEdge > 0 else { return normalized }

            let scale = maxLongEdge / longEdge
            let targetSize = CGSize(width: normalized.size.width * scale, height: normalized.size.height * scale)
            let renderer = UIGraphicsImageRenderer(size: targetSize)
            return renderer.image { _ in
                normalized.draw(in: CGRect(origin: .zero, size: targetSize))
            }
        }

        private static func normalizedImage(from image: UIImage) -> UIImage {
            guard image.imageOrientation != .up else { return image }
            let renderer = UIGraphicsImageRenderer(size: image.size)
            return renderer.image { _ in
                image.draw(in: CGRect(origin: .zero, size: image.size))
            }
        }
    }

    final class CameraViewController: UIViewController {
        fileprivate var coordinator: Coordinator?

        private let session = AVCaptureSession()
        private let photoOutput = AVCapturePhotoOutput()
        private let sessionQueue = DispatchQueue(label: "ServiceRecordCameraCapture.session")
        private var previewLayer: AVCaptureVideoPreviewLayer?
        private var captureDevice: AVCaptureDevice?
        private var isSessionConfigured = false
        private var isCapturing = false
        private var isClosing = false

        private let closeButton = UIButton(type: .system)
        private let shutterButton = UIButton(type: .system)
        private let helperLabel = UILabel()
        private let focusRing = UIView()

        override func viewDidLoad() {
            super.viewDidLoad()
            view.backgroundColor = .black
            configurePreview()
            configureOverlay()
            configureGestures()
            configureSession()
        }

        override func viewDidAppear(_ animated: Bool) {
            super.viewDidAppear(animated)
            startSession()
        }

        override func viewWillDisappear(_ animated: Bool) {
            super.viewWillDisappear(animated)
            stopSession()
        }

        override func viewDidLayoutSubviews() {
            super.viewDidLayoutSubviews()
            previewLayer?.frame = view.bounds
        }

        private func configurePreview() {
            let previewLayer = AVCaptureVideoPreviewLayer(session: session)
            previewLayer.videoGravity = .resizeAspectFill
            view.layer.addSublayer(previewLayer)
            self.previewLayer = previewLayer
        }

        private func configureOverlay() {
            closeButton.translatesAutoresizingMaskIntoConstraints = false
            var closeConfiguration = UIButton.Configuration.plain()
            closeConfiguration.title = "Zrušit"
            closeConfiguration.baseForegroundColor = .white
            closeConfiguration.contentInsets = NSDirectionalEdgeInsets(top: 12, leading: 16, bottom: 12, trailing: 16)
            closeButton.configuration = closeConfiguration
            closeButton.titleLabel?.font = .systemFont(ofSize: 18, weight: .semibold)
            closeButton.backgroundColor = UIColor.black.withAlphaComponent(0.45)
            closeButton.layer.cornerRadius = 18
            closeButton.addTarget(self, action: #selector(cancelTapped), for: .touchUpInside)

            shutterButton.translatesAutoresizingMaskIntoConstraints = false
            shutterButton.backgroundColor = .white
            shutterButton.layer.cornerRadius = 38
            shutterButton.layer.borderWidth = 6
            shutterButton.layer.borderColor = UIColor.white.withAlphaComponent(0.35).cgColor
            shutterButton.addTarget(self, action: #selector(captureTapped), for: .touchUpInside)
            shutterButton.isEnabled = false
            shutterButton.alpha = 0.55

            helperLabel.translatesAutoresizingMaskIntoConstraints = false
            helperLabel.text = "Načítám kameru…"
            helperLabel.textColor = .white
            helperLabel.font = .systemFont(ofSize: 15, weight: .medium)
            helperLabel.textAlignment = .center
            helperLabel.numberOfLines = 2
            helperLabel.backgroundColor = UIColor.black.withAlphaComponent(0.35)
            helperLabel.layer.cornerRadius = 14
            helperLabel.clipsToBounds = true

            focusRing.translatesAutoresizingMaskIntoConstraints = true
            focusRing.frame = CGRect(x: 0, y: 0, width: 92, height: 92)
            focusRing.layer.cornerRadius = 20
            focusRing.layer.borderWidth = 2
            focusRing.layer.borderColor = UIColor.systemYellow.cgColor
            focusRing.alpha = 0

            view.addSubview(closeButton)
            view.addSubview(shutterButton)
            view.addSubview(helperLabel)
            view.addSubview(focusRing)

            NSLayoutConstraint.activate([
                closeButton.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 20),
                closeButton.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 12),

                helperLabel.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 20),
                helperLabel.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -20),
                helperLabel.bottomAnchor.constraint(equalTo: shutterButton.topAnchor, constant: -22),
                helperLabel.heightAnchor.constraint(greaterThanOrEqualToConstant: 52),

                shutterButton.centerXAnchor.constraint(equalTo: view.centerXAnchor),
                shutterButton.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -28),
                shutterButton.widthAnchor.constraint(equalToConstant: 76),
                shutterButton.heightAnchor.constraint(equalToConstant: 76),
            ])
        }

        private func configureGestures() {
            let tap = UITapGestureRecognizer(target: self, action: #selector(handleFocusTap(_:)))
            view.addGestureRecognizer(tap)
        }

        private func configureSession() {
            sessionQueue.async {
                let status = AVCaptureDevice.authorizationStatus(for: .video)
                if status == .authorized {
                    self.setupSessionInput()
                    return
                }
                if status == .notDetermined {
                    AVCaptureDevice.requestAccess(for: .video) { granted in
                        if granted {
                            self.setupSessionInput()
                        } else {
                            DispatchQueue.main.async {
                                self.coordinator?.cancel()
                            }
                        }
                    }
                    return
                }
                DispatchQueue.main.async {
                    self.coordinator?.cancel()
                }
            }
        }

        private func setupSessionInput() {
            session.beginConfiguration()
            session.sessionPreset = .photo

            guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
                  let input = try? AVCaptureDeviceInput(device: device),
                  session.canAddInput(input),
                  session.canAddOutput(photoOutput) else {
                session.commitConfiguration()
                DispatchQueue.main.async {
                    self.coordinator?.cancel()
                }
                return
            }

            if session.inputs.isEmpty {
                session.addInput(input)
            }
            if session.outputs.isEmpty {
                session.addOutput(photoOutput)
            }

            captureDevice = device
            configure(device: device)
            photoOutput.maxPhotoQualityPrioritization = .quality
            isSessionConfigured = true
            session.commitConfiguration()

            DispatchQueue.main.async {
                self.shutterButton.isEnabled = true
                self.shutterButton.alpha = 1
                self.helperLabel.text = "Vyfoťte doklad ostře. Klepnutím nastavíte zaostření."
            }
        }

        private func configure(device: AVCaptureDevice) {
            do {
                try device.lockForConfiguration()
                if device.isFocusModeSupported(.continuousAutoFocus) {
                    device.focusMode = .continuousAutoFocus
                }
                if device.isExposureModeSupported(.continuousAutoExposure) {
                    device.exposureMode = .continuousAutoExposure
                }
                if device.isWhiteBalanceModeSupported(.continuousAutoWhiteBalance) {
                    device.whiteBalanceMode = .continuousAutoWhiteBalance
                }
                if device.isSmoothAutoFocusSupported {
                    device.isSmoothAutoFocusEnabled = true
                }
                device.isSubjectAreaChangeMonitoringEnabled = true
                device.unlockForConfiguration()
            } catch {
                return
            }
        }

        private func startSession() {
            sessionQueue.async {
                guard self.isSessionConfigured, !self.session.isRunning else { return }
                self.session.startRunning()
            }
        }

        private func stopSession() {
            sessionQueue.async {
                guard self.session.isRunning else { return }
                self.session.stopRunning()
            }
        }

        @objc private func cancelTapped() {
            finishCancel()
        }

        @objc private func captureTapped() {
            guard isSessionConfigured, !isCapturing, !isClosing else { return }
            isCapturing = true
            closeButton.isEnabled = false
            shutterButton.isEnabled = false
            shutterButton.alpha = 0.55
            helperLabel.text = "Zpracovávám snímek…"
            let settings = AVCapturePhotoSettings()
            settings.photoQualityPrioritization = .quality
            settings.flashMode = .off
            photoOutput.capturePhoto(with: settings, delegate: coordinator ?? Coordinator(onComplete: { _ in }, onCancel: {}))
        }

        @objc private func handleFocusTap(_ gesture: UITapGestureRecognizer) {
            guard !isClosing else { return }
            let point = gesture.location(in: view)
            showFocusRing(at: point)

            guard let previewLayer,
                  let device = captureDevice else { return }

            let devicePoint = previewLayer.captureDevicePointConverted(fromLayerPoint: point)
            sessionQueue.async {
                do {
                    try device.lockForConfiguration()
                    if device.isFocusPointOfInterestSupported {
                        device.focusPointOfInterest = devicePoint
                    }
                    if device.isFocusModeSupported(.autoFocus) {
                        device.focusMode = .autoFocus
                    }
                    if device.isExposurePointOfInterestSupported {
                        device.exposurePointOfInterest = devicePoint
                    }
                    if device.isExposureModeSupported(.continuousAutoExposure) {
                        device.exposureMode = .continuousAutoExposure
                    }
                    device.unlockForConfiguration()
                } catch {
                    return
                }
            }
        }

        fileprivate func finishCancel() {
            guard !isClosing else { return }
            isClosing = true
            helperLabel.text = "Zavírám kameru…"
            closeButton.isEnabled = false
            shutterButton.isEnabled = false
            shutterButton.alpha = 0.55
            stopSession()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
                self.coordinator?.cancel()
            }
        }

        fileprivate func finishCapture(_ attachment: PendingAttachment) {
            guard !isClosing else { return }
            isClosing = true
            helperLabel.text = "Doklad načten."
            closeButton.isEnabled = false
            shutterButton.isEnabled = false
            shutterButton.alpha = 0.55
            stopSession()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
                self.coordinator?.complete(attachment)
            }
        }

        private func showFocusRing(at point: CGPoint) {
            focusRing.center = point
            focusRing.transform = CGAffineTransform(scaleX: 1.22, y: 1.22)
            focusRing.alpha = 1
            UIView.animate(withDuration: 0.2, animations: {
                self.focusRing.transform = .identity
            }) { _ in
                UIView.animate(withDuration: 0.35, delay: 0.55) {
                    self.focusRing.alpha = 0
                }
            }
        }
    }
}
