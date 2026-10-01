// Explicit event handlers migrated from the legacy views. Arguments are data,
// not JavaScript source. No eval, Function constructor or window[name] dispatch.
function legacyActionAttributes(event, action, ...args) {
    return 'data-legacy-' + event + '="' + escapeHtml(action) + '" data-legacy-' + event + '-args="' + escapeHtml(JSON.stringify(args)) + '"';
}
// Return only navigable HTTP(S) links. Attribute encoding is applied at the sink.
function safeLegacyURL(value, allowMailto = false) {
    try {
        const raw = String(value || '').trim();
        if (!raw) return '';
        const url = new URL(raw, window.location.href);
        if (allowMailto && url.protocol === 'mailto:' && !/[\r\n]/.test(decodeURIComponent(raw))) return url.href;
        if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return '';
        return url.href;
    } catch { return ''; }
}
const legacyActions = Object.freeze({
    viewAIFeature: function(event, args) { return viewFeatureDetail(args[0]); },
    approveAIFeature: function(event, args) { return approveFeature(args[0]); },
    rejectAIFeature: function(event, args) { return rejectFeature(args[0]); },
    voteAIFeature: function(event, args) { return voteOnFeature(args[0], args[1]); },
    "remove_9744c335": function(event,args) {
    this.parentElement.parentElement.remove()
    },
    "showVehicleDetail_8ee4a012": function(event,args) {
    showVehicleDetail(args[0])
    },
    "stopPropagation_ae1e895d": function(event,args) {
    event.stopPropagation(); showVehicleDetail(args[0])
    },
    "stopPropagation_00b7832c": function(event,args) {
    event.stopPropagation(); deleteVehicle(args[0])
    },
    "handleServiceAddVehicleSubmit_ce285c5f": function(event,args) {
    handleServiceAddVehicleSubmit()
    },
    "resetServiceAddVehicleForm_e1b0258c": function(event,args) {
    resetServiceAddVehicleForm()
    },
    "saveVehicleFieldInline_b9b42868": function(event,args) {
    saveVehicleFieldInline('nickname', args[0])
    },
    "cancelEditInline_6b16e294": function(event,args) {
    cancelEditInline('nickname', args[0])
    },
    "startEditInline_78e44df3": function(event,args) {
    startEditInline('nickname', args[0])
    },
    "saveVehicleFieldInline_e2d47f23": function(event,args) {
    saveVehicleFieldInline('plate', args[0])
    },
    "cancelEditInline_6a45c869": function(event,args) {
    cancelEditInline('plate', args[0])
    },
    "startEditInline_3a976e52": function(event,args) {
    startEditInline('plate', args[0])
    },
    "saveVehicleFieldInline_42078fb0": function(event,args) {
    saveVehicleFieldInline('notes', args[0])
    },
    "cancelEditInline_bd54022a": function(event,args) {
    cancelEditInline('notes', args[0])
    },
    "startEditInline_9c9fa615": function(event,args) {
    startEditInline('notes', args[0])
    },
    "openServiceReservationComposer_e4398f77": function(event,args) {
    openServiceReservationComposer(null, args[0])
    },
    "openServiceReminderComposer_0a77658d": function(event,args) {
    openServiceReminderComposer(null, args[0])
    },
    "deleteVehicle_624fafe1": function(event,args) {
    deleteVehicle(args[0])
    },
    "handleVehiclePhotoUpload_4167fc86": function(event,args) {
    handleVehiclePhotoUpload(args[0], this)
    },
    "getElementById_a0ecb1b8": function(event,args) {
    document.getElementById(("vehicle-photo-upload-" + String(args[0]) + "")).click();
    },
    "saveVehicleFieldModal_ac7bea60": function(event,args) {
    saveVehicleFieldModal('nickname', args[0])
    },
    "cancelEditModal_f36251c7": function(event,args) {
    cancelEditModal('nickname', args[0])
    },
    "startEditModal_c9c8fba8": function(event,args) {
    startEditModal('nickname', args[0])
    },
    "saveVehicleFieldModal_744cb514": function(event,args) {
    saveVehicleFieldModal('plate', args[0])
    },
    "cancelEditModal_865ff583": function(event,args) {
    cancelEditModal('plate', args[0])
    },
    "startEditModal_4f44e6af": function(event,args) {
    startEditModal('plate', args[0])
    },
    "saveVehicleFieldModal_56abb99a": function(event,args) {
    saveVehicleFieldModal('notes', args[0])
    },
    "cancelEditModal_05232943": function(event,args) {
    cancelEditModal('notes', args[0])
    },
    "startEditModal_e8e688b9": function(event,args) {
    startEditModal('notes', args[0])
    },
    "generateServiceRecordsPDF_0c66ea62": function(event,args) {
    generateServiceRecordsPDF(args[0]); return false;
    },
    "openAddServiceRecordModal_384438cb": function(event,args) {
    openAddServiceRecordModal(args[0])
    },
    "deleteVehiclePhoto_0ab86de5": function(event,args) {
    deleteVehiclePhoto(args[0])
    },
    "updateServiceReportItemField_9e0f4764": function(event,args) {
    updateServiceReportItemField(("" + String(args[0]) + ""), args[1], 'name', this.value)
    },
    "updateServiceReportItemField_ad8afce2": function(event,args) {
    updateServiceReportItemField(("" + String(args[0]) + ""), args[1], 'quantity', this.value)
    },
    "updateServiceReportItemField_a414fc26": function(event,args) {
    updateServiceReportItemField(("" + String(args[0]) + ""), args[1], 'unit', this.value)
    },
    "updateServiceReportItemField_59aa0f06": function(event,args) {
    updateServiceReportItemField(("" + String(args[0]) + ""), args[1], 'unit_price', this.value)
    },
    "updateServiceReportItemField_ccaec052": function(event,args) {
    updateServiceReportItemField(("" + String(args[0]) + ""), args[1], 'total_price', this.value)
    },
    "removeServiceReportItemRow_c34afc59": function(event,args) {
    removeServiceReportItemRow(("" + String(args[0]) + ""), args[1])
    },
    "updateServiceReportField_ecbeffe9": function(event,args) {
    updateServiceReportField(("" + String(args[0]) + ""),'supplier_name',this.value)
    },
    "updateServiceReportField_1172f6b4": function(event,args) {
    updateServiceReportField(("" + String(args[0]) + ""),'supplier_email',this.value)
    },
    "updateServiceReportField_542de729": function(event,args) {
    updateServiceReportField(("" + String(args[0]) + ""),'technician_name',this.value)
    },
    "updateServiceReportField_a2c2ac4e": function(event,args) {
    updateServiceReportField(("" + String(args[0]) + ""),'currency',this.value)
    },
    "updateServiceReportField_da3733a5": function(event,args) {
    updateServiceReportField(("" + String(args[0]) + ""),'service_summary',this.value)
    },
    "updateServiceReportField_5c514df8": function(event,args) {
    updateServiceReportField(("" + String(args[0]) + ""),'issue_description',this.value)
    },
    "addServiceReportItemRow_64949d99": function(event,args) {
    addServiceReportItemRow(("" + String(args[0]) + ""))
    },
    "updateServiceReportField_7880e478": function(event,args) {
    updateServiceReportField(("" + String(args[0]) + ""),'labor_hours',this.value)
    },
    "updateServiceReportField_cd16696a": function(event,args) {
    updateServiceReportField(("" + String(args[0]) + ""),'labor_hour_rate',this.value)
    },
    "updateServiceReportField_f9802feb": function(event,args) {
    updateServiceReportField(("" + String(args[0]) + ""),'vat_rate',this.value)
    },
    "closeAttachmentPreviewModal_75e4c0dd": function(event,args) {
    closeAttachmentPreviewModal()
    },
    "handleAddServiceRecordSubmit_ecdf7283": function(event,args) {
    return handleAddServiceRecordSubmit(event)
    },
    "toggleCategoryDropdown_2fcbf668": function(event,args) {
    toggleCategoryDropdown('add')
    },
    "handleAddServiceAttachmentSelection_7214fe63": function(event,args) {
    handleAddServiceAttachmentSelection(event)
    },
    "closeAddServiceRecordModal_d539d5f4": function(event,args) {
    closeAddServiceRecordModal()
    },
    "selectCategory_d858679f": function(event,args) {
    selectCategory(("" + String(args[0]) + ""), ("" + String(args[1]) + ""), ("" + String(args[2]) + ""), 'add')
    },
    "showServiceRecordDetail_941afdd3": function(event,args) {
    showServiceRecordDetail(args[0], args[1])
    },
    "openServiceRecordAttachmentPreview_641bbe9b": function(event,args) {
    openServiceRecordAttachmentPreview(("" + String(args[0]) + ""), ("" + String(args[1]) + ""))
    },
    "openEditServiceRecordModal_544ccd45": function(event,args) {
    openEditServiceRecordModal(args[0], args[1])
    },
    "deleteServiceRecordFromDetail_4ad93f83": function(event,args) {
    deleteServiceRecordFromDetail(args[0], args[1])
    },
    "closeServiceRecordDetailModal_f01a2a03": function(event,args) {
    closeServiceRecordDetailModal()
    },
    "handleEditServiceRecordSubmit_229cc8e0": function(event,args) {
    handleEditServiceRecordSubmit(event, args[0], args[1])
    },
    "toggleCategoryDropdown_713f9a7a": function(event,args) {
    toggleCategoryDropdown(("edit-" + String(args[0]) + ""))
    },
    "selectCategory_66b8da76": function(event,args) {
    selectCategory(("" + String(args[0]) + ""), ("" + String(args[1]) + ""), ("" + String(args[2]) + ""), ("edit-" + String(args[3]) + ""))
    },
    "deleteServiceRecordInline_6d69444e": function(event,args) {
    deleteServiceRecordInline(args[0], args[1])
    },
    "deleteServiceRecord_08dc47d2": function(event,args) {
    deleteServiceRecord(args[0])
    },
    "openManagedServiceVehicleAccess_d8cf6829": function(event,args) {
    openManagedServiceVehicleAccess(args[0])
    },
    "disconnectManagedServiceContact_96e47cfb": function(event,args) {
    disconnectManagedServiceContact(args[0])
    },
    "setReminderFilter_8a7c9d6c": function(event,args) {
    setReminderFilter(("" + String(args[0]) + ""))
    },
    "openReminderDetailModalByIndex_76ed8689": function(event,args) {
    openReminderDetailModalByIndex(args[0])
    },
    "preventDefault_f85ab9e5": function(event,args) {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openReminderDetailModalByIndex(args[0]); }
    },
    "stopPropagation_f6bcd6dc": function(event,args) {
    event.stopPropagation(); openReminderDetailModalByIndex(args[0]);
    },
    "shiftReminderCalendarMonth_1001e74b": function(event,args) {
    shiftReminderCalendarMonth(-1)
    },
    "shiftReminderCalendarMonth_98aac5ae": function(event,args) {
    shiftReminderCalendarMonth(1)
    },
    "openReminderScheduleFromDetail_00360b1a": function(event,args) {
    openReminderScheduleFromDetail(args[0])
    },
    "openReminderEditFromDetail_43a18932": function(event,args) {
    openReminderEditFromDetail(args[0])
    },
    "deleteReminderFromDetail_ca5065e7": function(event,args) {
    deleteReminderFromDetail(args[0])
    },
    "openReminderVehicleFromDetail_509daa1f": function(event,args) {
    openReminderVehicleFromDetail(args[0])
    },
    "closeReminderDetailModal_adb51a2a": function(event,args) {
    if (event.target === this) closeReminderDetailModal()
    },
    "closeReminderDetailModal_55e91aa3": function(event,args) {
    closeReminderDetailModal()
    },
    "setServiceReminderStatusFilter_37619866": function(event,args) {
    setServiceReminderStatusFilter(("" + String(args[0]) + ""))
    },
    "openEditServiceReminder_5927b4f9": function(event,args) {
    openEditServiceReminder(args[0])
    },
    "toggleServiceReminderCompletion_3c831bda": function(event,args) {
    toggleServiceReminderCompletion(args[0], args[1])
    },
    "deleteServiceWorkspaceReminder_a615a2ea": function(event,args) {
    deleteServiceWorkspaceReminder(args[0])
    },
    "openVehicleFromShortcut_81e96af9": function(event,args) {
    openVehicleFromShortcut(args[0], 'service-reminders')
    },
    "setServiceReminderQuery_3c67ecc8": function(event,args) {
    setServiceReminderQuery(this.value)
    },
    "setServiceReminderCustomerFilter_3bcd171d": function(event,args) {
    setServiceReminderCustomerFilter(this.value)
    },
    "openServiceReminderComposer_89ec70ca": function(event,args) {
    openServiceReminderComposer()
    },
    "loadServiceWorkspaceReminders_04c8f9af": function(event,args) {
    loadServiceWorkspaceReminders(true)
    },
    "loadServiceWorkspaceReminders_457d84b2": function(event,args) {
    if (event.target === this) loadServiceWorkspaceReminders(true)
    },
    "handleCreateServiceReminder_a7b72be2": function(event,args) {
    handleCreateServiceReminder(); return false;
    },
    "handleServiceReminderCustomerChange_a5d5063a": function(event,args) {
    handleServiceReminderCustomerChange()
    },
    "handleUpdateServiceReminder_31b8d644": function(event,args) {
    handleUpdateServiceReminder(args[0]); return false;
    },
    "setReminderView_150bbeba": function(event,args) {
    setReminderView('grid')
    },
    "setReminderView_608a38ee": function(event,args) {
    setReminderView('list')
    },
    "setReminderView_0e978cf6": function(event,args) {
    setReminderView('compact')
    },
    "setReminderView_05df8aa6": function(event,args) {
    setReminderView('calendar')
    },
    "showCreateReminderForm_ff2a2251": function(event,args) {
    showCreateReminderForm()
    },
    "applyReminderTemplate_0b51db63": function(event,args) {
    applyReminderTemplate('STK', 'STK / technická prohlídka', null, true)
    },
    "applyReminderTemplate_ceada0dc": function(event,args) {
    applyReminderTemplate('OLEJ', 'Výměna oleje', 180)
    },
    "applyReminderTemplate_a3144fbf": function(event,args) {
    applyReminderTemplate('PNEU', 'Přezout pneumatiky', 120)
    },
    "applyReminderTemplate_cf38127f": function(event,args) {
    applyReminderTemplate('POJISTKA', 'Kontrola / obnova pojistky', 365)
    },
    "applyReminderTemplate_f6a1c20e": function(event,args) {
    applyReminderTemplate('SERVIS', 'Pravidelný servis', 180)
    },
    "openLicenseModal_5e411be2": function(event,args) {
    openLicenseModal()
    },
    "loadReminders_e3c8345d": function(event,args) {
    if (event.target === this) loadReminders()
    },
    "handleCreateReminder_5a2def2a": function(event,args) {
    handleCreateReminder(); return false;
    },
    "loadReminders_d8558427": function(event,args) {
    loadReminders()
    },
    "handleUpdateReminderSchedule_ca45dc6e": function(event,args) {
    handleUpdateReminderSchedule(args[0]); return false;
    },
    "handleUpdateReminder_9539beae": function(event,args) {
    handleUpdateReminder(args[0]); return false;
    },
    "shiftReservationCalendarRange_8a6e74fe": function(event,args) {
    shiftReservationCalendarRange(-1)
    },
    "goToReservationCalendarToday_2eee25da": function(event,args) {
    goToReservationCalendarToday()
    },
    "shiftReservationCalendarRange_3cc667c9": function(event,args) {
    shiftReservationCalendarRange(1)
    },
    "handleReservationCalendarDateInput_149bcc11": function(event,args) {
    handleReservationCalendarDateInput(event)
    },
    "exportReservationSelectedDayCsv_61effc93": function(event,args) {
    exportReservationSelectedDayCsv()
    },
    "suggestReservationNextFreeSlot_78d49974": function(event,args) {
    suggestReservationNextFreeSlot()
    },
    "setReservationStatusFilter_48fa4ff1": function(event,args) {
    setReservationStatusFilter(("" + String(args[0]) + ""))
    },
    "setReservationViewMode_3d65feab": function(event,args) {
    setReservationViewMode(("" + String(args[0]) + ""))
    },
    "handleReservationSearchInput_5f062054": function(event,args) {
    handleReservationSearchInput(event)
    },
    "handleReservationSortChange_8ab88d54": function(event,args) {
    handleReservationSortChange(event)
    },
    "handleReservationCustomerFilterChange_494a1ed6": function(event,args) {
    handleReservationCustomerFilterChange(event)
    },
    "openReservationQuickDetail_89beeb1b": function(event,args) {
    openReservationQuickDetail(args[0])
    },
    "openVehicleFromShortcut_e1272e05": function(event,args) {
    openVehicleFromShortcut(args[0], 'reservations')
    },
    "openReservationRescheduleModal_151f279c": function(event,args) {
    openReservationRescheduleModal(args[0])
    },
    "confirmReservation_eed62221": function(event,args) {
    confirmReservation(args[0])
    },
    "completeReservation_622da3d8": function(event,args) {
    completeReservation(args[0])
    },
    "cancelReservation_1410752e": function(event,args) {
    cancelReservation(args[0])
    },
    "selectReservationCalendarDate_c6dce091": function(event,args) {
    selectReservationCalendarDate(("" + String(args[0]) + ""))
    },
    "closeReservationRescheduleModal_06ba2dac": function(event,args) {
    if (event.target === this) closeReservationRescheduleModal()
    },
    "handleReservationRescheduleSubmit_1192bc4b": function(event,args) {
    handleReservationRescheduleSubmit(args[0]); return false;
    },
    "closeReservationRescheduleModal_b19ca30e": function(event,args) {
    closeReservationRescheduleModal()
    },
    "closeReservationQuickDetailModal_6c757235": function(event,args) {
    closeReservationQuickDetailModal(); openReservationRescheduleModal(args[0])
    },
    "closeReservationQuickDetailModal_00c72967": function(event,args) {
    closeReservationQuickDetailModal(); openVehicleFromShortcut(args[0], 'reservations')
    },
    "closeReservationQuickDetailModal_afdb30ff": function(event,args) {
    closeReservationQuickDetailModal()
    },
    "closeReservationQuickDetailModal_39bbfa52": function(event,args) {
    if (event.target === this) closeReservationQuickDetailModal()
    },
    "showCreateReservationForm_f65cf47c": function(event,args) {
    showCreateReservationForm()
    },
    "loadReservations_f26a788a": function(event,args) {
    loadReservations()
    },
    "handleServiceVehicleAccessSelection_62102903": function(event,args) {
    handleServiceVehicleAccessSelection(args[0])
    },
    "toggleServiceVehicleAccess_de541112": function(event,args) {
    toggleServiceVehicleAccess(args[0])
    },
    "loadServicesDirectory_d9500fe7": function(event,args) {
    loadServicesDirectory(true)
    },
    "closeReservationForm_8ad16ccd": function(event,args) {
    if (event.target === this) closeReservationForm()
    },
    "handleCreateReservation_a270c604": function(event,args) {
    handleCreateReservation(); return false;
    },
    "closeReservationForm_6cc4d37f": function(event,args) {
    closeReservationForm()
    },
    "handleServiceReservationCustomerChange_ccdff816": function(event,args) {
    handleServiceReservationCustomerChange()
    },
    "closeServiceClientModal_a4d59e29": function(event,args) {
    closeServiceClientModal(); openVehicleFromShortcut(args[0], 'service-client-modal')
    },
    "closeServiceClientModal_ad07d9ed": function(event,args) {
    closeServiceClientModal(); openServiceReservationComposer(args[0], args[1])
    },
    "closeServiceClientModal_648bac6a": function(event,args) {
    closeServiceClientModal(); openServiceReminderComposer(args[0], args[1])
    },
    "closeServiceClientModal_be06b081": function(event,args) {
    if (event.target === this) closeServiceClientModal()
    },
    "closeServiceClientModal_48f60cb7": function(event,args) {
    closeServiceClientModal()
    },
    "closeServiceClientModal_a6e7d7ac": function(event,args) {
    closeServiceClientModal(); openServiceAddVehicleForCustomer(args[0])
    },
    "closeServiceClientModal_ac3714d3": function(event,args) {
    closeServiceClientModal(); openServiceWorkspaceCustomerReservations(args[0])
    },
    "closeServiceClientModal_1a201e5f": function(event,args) {
    closeServiceClientModal(); openServiceWorkspaceCustomerReminders(args[0])
    },
    "openServiceReservationComposer_fd52392c": function(event,args) {
    openServiceReservationComposer(args[0], args[1])
    },
    "openServiceReminderComposer_ab64b1f8": function(event,args) {
    openServiceReminderComposer(args[0], args[1])
    },
    "prefillServiceWorkspaceDocumentTarget_0b744773": function(event,args) {
    prefillServiceWorkspaceDocumentTarget(args[0], args[1])
    },
    "openVehicleFromShortcut_82ac6bf3": function(event,args) {
    openVehicleFromShortcut(args[0], 'serviceWorkspace')
    },
    "openServiceWorkspaceCustomer_faefa5e5": function(event,args) {
    openServiceWorkspaceCustomer(args[0])
    },
    "loadServiceWorkspaceCustomerVehicles_6aec8672": function(event,args) {
    loadServiceWorkspaceCustomerVehicles(args[0])
    },
    "openServiceWorkspaceCustomerReservations_8b4ab9d5": function(event,args) {
    openServiceWorkspaceCustomerReservations(args[0])
    },
    "openServiceWorkspaceCustomerReminders_0411a86b": function(event,args) {
    openServiceWorkspaceCustomerReminders(args[0])
    },
    "openServiceAddVehicleForCustomer_9327e9bd": function(event,args) {
    openServiceAddVehicleForCustomer(args[0])
    },
    "openServiceClientModal_c7be19a8": function(event,args) {
    openServiceClientModal(args[0])
    },
    "resendServiceInvitation_ceea120d": function(event,args) {
    resendServiceInvitation(args[0])
    },
    "deleteServiceInvitation_5e4b9c08": function(event,args) {
    deleteServiceInvitation(args[0])
    },
    "linkServiceExistingCustomer_19053366": function(event,args) {
    linkServiceExistingCustomer()
    },
    "sendServiceInvitation_7750021b": function(event,args) {
    sendServiceInvitation()
    },
    "handleServiceWorkspaceCustomerChange_4af2f865": function(event,args) {
    handleServiceWorkspaceCustomerChange()
    },
    "ingestServiceDocument_646c7d3c": function(event,args) {
    ingestServiceDocument()
    },
    "setSettingsPanel_f5f3303d": function(event,args) {
    setSettingsPanel('account')
    },
    "setSettingsPanel_95747cd8": function(event,args) {
    setSettingsPanel('notifications')
    },
    "setSettingsPanel_4b5ae01d": function(event,args) {
    setSettingsPanel('security')
    },
    "setSettingsPanel_efbbe57d": function(event,args) {
    setSettingsPanel('data')
    },
    "handleSaveProfile_d7573d4d": function(event,args) {
    handleSaveProfile()
    },
    "handleProfileAresLookup_6d72ab6e": function(event,args) {
    handleProfileAresLookup()
    },
    "startTotpSetup_86b09af7": function(event,args) {
    startTotpSetup()
    },
    "toggleTotpDisableForm_30eac346": function(event,args) {
    toggleTotpDisableForm(true)
    },
    "copyTotpSecret_f501e39e": function(event,args) {
    copyTotpSecret()
    },
    "copyTotpUri_dcfc561b": function(event,args) {
    copyTotpUri()
    },
    "confirmTotpEnable_66bbb5e2": function(event,args) {
    confirmTotpEnable()
    },
    "cancelTotpSetup_42e90c93": function(event,args) {
    cancelTotpSetup()
    },
    "confirmTotpDisable_ac0dbb07": function(event,args) {
    confirmTotpDisable()
    },
    "toggleTotpDisableForm_9df89fb9": function(event,args) {
    toggleTotpDisableForm(false)
    },
    "toggleBiometricPreference_7337fd8f": function(event,args) {
    toggleBiometricPreference()
    },
    "handleChangePassword_4688b77d": function(event,args) {
    handleChangePassword(event); return false;
    },
    "handleAccountDataExport_089c7e18": function(event,args) {
    handleAccountDataExport()
    },
    "handleDeleteAccount_4f319180": function(event,args) {
    handleDeleteAccount()
    },
    "handleSendSupportRequest_52acbcec": function(event,args) {
    handleSendSupportRequest(event); return false;
    },
    "selectVehicleForCommand_27b22fb1": function(event,args) {
    selectVehicleForCommand(args[0], args[1], ("" + String(args[2]) + ""), ("" + String(args[3]) + ""))
    },
    "toggleMobileNavbarMenu_7d531cfa": function(event,args) {
    toggleMobileNavbarMenu()
    },
    "showApiUrlConfig_6d754d51": function(event,args) {
    showApiUrlConfig()
    },
    "toggleDebugPanel_315935f3": function(event,args) {
    toggleDebugPanel()
    },
    "handleLogout_5a797dca": function(event,args) {
    handleLogout()
    },
    "saveApiUrl_e5ed5198": function(event,args) {
    saveApiUrl()
    },
    "hideApiUrlConfig_92e7e2cb": function(event,args) {
    hideApiUrlConfig()
    },
    "resetApiUrl_b5aab129": function(event,args) {
    resetApiUrl()
    },
    "closeLicenseModal_fd6e19d7": function(event,args) {
    closeLicenseModal()
    },
    "handleLogin_be924de6": function(event,args) {
    handleLogin(); return false;
    },
    "setLoginMode_3da7dcd4": function(event,args) {
    setLoginMode('user')
    },
    "setLoginMode_d0380663": function(event,args) {
    setLoginMode('service')
    },
    "handleLoginTwoFactor_384d0215": function(event,args) {
    handleLoginTwoFactor()
    },
    "cancelLoginTwoFactor_c873cde9": function(event,args) {
    cancelLoginTwoFactor()
    },
    "showRegister_205b53fd": function(event,args) {
    showRegister()
    },
    "showForgotPasswordForm_59a66beb": function(event,args) {
    showForgotPasswordForm(); return false;
    },
    "handleForgotPassword_73d14458": function(event,args) {
    handleForgotPassword(); return false;
    },
    "hideForgotPasswordForm_fca8b76a": function(event,args) {
    hideForgotPasswordForm()
    },
    "setRegistrationMode_91a1b4b9": function(event,args) {
    setRegistrationMode('user')
    },
    "setRegistrationMode_046f27e7": function(event,args) {
    setRegistrationMode('service')
    },
    "handleRegister_2fc00a67": function(event,args) {
    handleRegister()
    },
    "showLogin_499f59df": function(event,args) {
    showLogin()
    },
    "switchTab_ffbaccdd": function(event,args) {
    switchTab('vehicles')
    },
    "switchTab_b6dc4abf": function(event,args) {
    switchTab('addVehicle')
    },
    "switchTab_073a0ddf": function(event,args) {
    switchTab('reminders')
    },
    "switchTab_8d0bfd00": function(event,args) {
    switchTab('reservations')
    },
    "switchTab_04fa5e52": function(event,args) {
    switchTab('servicesDirectory')
    },
    "switchTab_b9ddbb20": function(event,args) {
    switchTab('serviceWorkspace')
    },
    "switchTab_a5d14d2c": function(event,args) {
    switchTab('profile')
    },
    "switchTab_d1d2f5fa": function(event,args) {
    switchTab('support')
    },
    "openAddServiceRecordModal_6e8c4050": function(event,args) {
    openAddServiceRecordModal()
    },
    "setVehicleView_35da4b73": function(event,args) {
    setVehicleView('grid')
    },
    "setVehicleView_9f0d7be4": function(event,args) {
    setVehicleView('list')
    },
    "setVehicleView_c2bfb0ca": function(event,args) {
    setVehicleView('compact')
    },
    "closeVehicleModal_7d3898d3": function(event,args) {
    closeVehicleModal()
    },
    "showVehiclesList_6c5e5abe": function(event,args) {
    showVehiclesList()
    },
    "handleAddService_df70eb53": function(event,args) {
    handleAddService(event)
    },
    "previewAddVehiclePhoto_0fc0de15": function(event,args) {
    previewAddVehiclePhoto(this)
    },
    "handleAddVehicle_49bfd859": function(event,args) {
    handleAddVehicle()
    },
    "toggleCommandBotChat_45ff3bbe": function(event,args) {
    toggleCommandBotChat()
    },
    "if_f46af53b": function(event,args) {
    if(event.key === 'Enter') sendCommandBot()
    },
    "sendCommandBot_9a416fbd": function(event,args) {
    sendCommandBot()
    },
});
for (const type of ['click','submit','input','change','keypress','keydown','keyup','error','load','focus','blur']) {
    document.addEventListener(type, event => {
        let element = event.target instanceof Element ? event.target : event.target?.parentElement;
        while (element) {
            const name = element.getAttribute('data-legacy-' + type);
            if (name && Object.hasOwn(legacyActions, name) && !element.disabled) {
                try {
                    const args = JSON.parse(element.getAttribute('data-legacy-' + type + '-args') || '[]');
                    if (Array.isArray(args)) {
                        const result = legacyActions[name].call(element, event, args);
                        if (result === false) event.preventDefault();
                        if (result?.catch) result.catch(() => showAlert('Akci se nepodařilo dokončit.', 'error'));
                    }
                } catch { showAlert('Akci se nepodařilo dokončit. Obnovte stránku.', 'error'); }
            }
            if (event.cancelBubble) break;
            element = element.parentElement;
        }
    }, ['error','load','focus','blur'].includes(type));
}
