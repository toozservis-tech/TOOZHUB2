// Globální proměnné
        var API_URL = null; // Bude inicializována po načtení DOM pomocí getApiBaseUrl()
        var moduleCapabilities = {};
        var currentUser = null;
        var accessToken = null; // JWT token pro autentizaci
        var serverStatusCheckInterval = null;
        var licenseRefreshTimer = null;
        var licenseLastFetch = 0;
        var comgateConfigCache = null;
        var comgateConfigLoadedAt = 0;
        var selectedLicenseBillingPeriod = 'monthly';
        var currentLicensePlanForUi = 'free';
        var currentLicenseSubscriptionForUi = null;
        var pendingPaymentReturnInfo = null;
        var pendingPaidPlanForCheckout = '';
        var clientGeoTelemetry = null;
        var clientGeoLastAttemptAt = 0;
        var clientGeoRefreshTimer = null;
        var CLIENT_GEO_MAX_AGE_MS = 30 * 60 * 1000;
        var CLIENT_GEO_MIN_RETRY_MS = 5 * 60 * 1000;
        var pushSwRegistration = null;
        var pushSubscriptionSyncInProgress = false;

        // Debug tracking - poslední 3 requesty
        var debugRequests = [];
        var DEBUG_MAX_REQUESTS = 3;
        var loginMode = 'user'; // user | service
        var registrationMode = 'user'; // user | service
        var pendingTwoFactorChallenge = null;
        var pendingTwoFactorExpiresAt = 0;
        var authSecuritySettingsCache = null;
        var authSessionEstablishedAt = 0;
        var AUTH_AUTO_LOGOUT_GRACE_MS = 15000;
        var AUTH_STORAGE_KEYS = {
            token: 'accessToken',
            user: 'currentUser',
            loggedIn: 'wasLoggedIn',
            rememberedEmail: 'rememberedLoginEmail',
            rememberedEmailEnabled: 'rememberedLoginEmailEnabled',
            staySignedIn: 'staySignedIn',
            loginMode: 'loginMode'
        };
        var reservationsUiState = {
            isServiceView: false,
            all: [],
            statusFilter: 'ALL',
            customerFilter: 'ALL',
            query: '',
            sortBy: 'upcoming',
            viewMode: 'month',
            calendarAnchorDateKey: '',
            calendarMonthKey: '',
            selectedDateKey: '',
            loadedAt: 0,
            loadingPromise: null,
            ownerKey: ''
        };
        var profileUiState = {
            loadedAt: 0,
            loadingPromise: null,
            ownerKey: ''
        };
        var supportUiState = {
            loadedAt: 0,
            loadingPromise: null,
            ownerKey: ''
        };
        var systemCapabilitiesState = {
            loadedAt: 0,
            loadingPromise: null,
            ownerKey: ''
        };

        function getCapabilityModuleForTab(tabKey) {
            const mapping = {
                vehicles: 'vehicles',
                addVehicle: 'vehicles',
                reminders: 'vehicles',
                reservations: 'reservations',
                servicesDirectory: 'service_workspace',
                serviceWorkspace: 'service_workspace',
            };
            return mapping[tabKey] || null;
        }

        function isCapabilityAvailable(moduleKey) {
            if (!moduleKey) return true;
            const report = moduleCapabilities[moduleKey];
            return !report || report.available !== false;
        }

        function formatCapabilityHint(report) {
            if (!report || report.available !== false) return '';
            const missingTables = Array.isArray(report.missing_tables) ? report.missing_tables : [];
            const missingColumns = Array.isArray(report.missing_columns) ? report.missing_columns : [];
            const parts = [];
            if (missingTables.length) parts.push('chybí tabulky: ' + missingTables.join(', '));
            if (missingColumns.length) parts.push('chybí sloupce: ' + missingColumns.join(', '));
            return parts.join(' | ');
        }

        function applySystemCapabilitiesUi() {
            document.querySelectorAll('.tab[data-tab-key]').forEach((button) => {
                const tabKey = button.getAttribute('data-tab-key');
                const moduleKey = getCapabilityModuleForTab(tabKey);
                const report = moduleCapabilities[moduleKey];
                const unavailable = report && report.available === false;
                const baseLabel = String(button.getAttribute('data-base-label') || button.textContent || '').trim();
                if (!button.getAttribute('data-base-label')) {
                    button.setAttribute('data-base-label', baseLabel);
                }
                button.dataset.disabledReason = unavailable ? formatCapabilityHint(report) : '';
                button.title = unavailable ? ('Dočasně nedostupné po migraci: ' + button.dataset.disabledReason) : '';
                button.classList.toggle('disabled', !!unavailable);
                button.textContent = unavailable ? (baseLabel + ' (dočasně nedostupné)') : baseLabel;
            });
        }

        async function loadSystemCapabilities(force = true) {
            if (!isAuthenticated()) return;
            if (!force && isUiSectionCacheFresh(systemCapabilitiesState)) {
                applySystemCapabilitiesUi();
                return;
            }
            try {
                const response = await apiCall('/api/v1/system/capabilities', 'GET');
                moduleCapabilities = (response && response.modules) || {};
                markUiSectionLoaded(systemCapabilitiesState);
            } catch (error) {
                console.warn("[CAPABILITIES] Unable to load capabilities:");
                moduleCapabilities = {};
                systemCapabilitiesState.loadedAt = 0;
            }
            applySystemCapabilitiesUi();
        }

        var servicesDirectoryState = {
            loadedAt: 0,
            payload: null
        };
        var serviceVehicleAccessState = {
            grants: [],
            vehicles: [],
            apiAvailable: true
        };
        var managedServiceContactsState = {
            loadedAt: 0,
            items: [],
            loadingPromise: null
        };
        var serviceWorkspaceState = {
            customers: [],
            invitations: [],
            documents: [],
            customerVehicles: {},
            selectedCustomerId: null,
            loadingCustomerVehiclesId: null
        };
        var serviceClientModalState = {
            customerId: null,
        };
        var serviceWorkspaceRemindersState = {
            loadedAt: 0,
            items: [],
            statusFilter: 'ACTIVE',
            customerFilter: 'ALL',
            query: '',
            catalog: [],
        };
        var serviceAddVehicleState = {
            submitting: false,
            initialized: false,
        };
        var serviceReservationDraftState = {
            customerId: null,
            vehicleId: null,
            serviceType: '',
            note: '',
            startDate: '',
            startTime: '',
            endDate: '',
            endTime: '',
            catalog: []
        };
        var reservationCreateState = {
            submitting: false,
        };
        var reservationRescheduleState = {
            submitting: false,
            reservationId: 0,
        };
        var pendingServiceReservationsCustomerFilter = null;
        var pendingServicesDirectoryFocusServiceId = null;
        var pendingServiceInviteToken = null;
        var pendingReservationClaimToken = null;
        var pendingReservationClaimReservationId = null;
        var APP_FLOATING_MODAL_ROOT_ID = 'appFloatingModalRoot';
        var bodyScrollLockDepth = 0;
        var bodyScrollLockY = 0;
        var viewportTrackingInitialized = false;
        var mobileModalViewportFreezeHeight = 0;

        function isCoarsePointerMobileViewport() {
            if (!window.matchMedia) return false;
            return window.matchMedia('(max-width: 768px) and (hover: none) and (pointer: coarse)').matches;
        }

        function isTextEntryElement(element) {
            if (!element || typeof element.matches !== 'function') return false;
            return element.matches(
                'textarea, select, input:not([type="checkbox"]):not([type="radio"]):not([type="range"]):not([type="file"]):not([type="button"]):not([type="submit"]):not([type="reset"]), [contenteditable="true"]'
            );
        }

        function hasAnyActiveOverlayModal() {
            const floatingRoot = document.getElementById(APP_FLOATING_MODAL_ROOT_ID);
            if (floatingRoot) return true;

            const staticModalIds = ['licenseModal', 'vehicleDetailModal', 'addServiceRecordModal', 'serviceRecordDetailModal', 'attachmentPreviewModal'];
            return staticModalIds.some((modalId) => {
                const modalEl = document.getElementById(modalId);
                if (!modalEl) return false;
                if (modalEl.classList.contains('hidden')) return false;
                if (modalEl.style.display === 'none') return false;
                return modalEl.classList.contains('active') || modalEl.style.display === 'flex';
            });
        }

        function shouldFreezeModalViewportDuringKeyboard() {
            if (!isCoarsePointerMobileViewport()) return false;
            if (!hasAnyActiveOverlayModal()) return false;
            return isTextEntryElement(document.activeElement);
        }

        function readCurrentAppVhValue() {
            const rawValue = String(document.documentElement.style.getPropertyValue('--app-vh') || '').trim();
            const parsedValue = Number.parseInt(rawValue.replace('px', ''), 10);
            return Number.isFinite(parsedValue) ? parsedValue : 0;
        }

        function updateAppViewportHeightVar() {
            if (shouldFreezeModalViewportDuringKeyboard()) {
                if (!mobileModalViewportFreezeHeight) {
                    mobileModalViewportFreezeHeight = readCurrentAppVhValue() || Math.max(320, Math.round(Number(window.innerHeight) || 0));
                }
                document.documentElement.style.setProperty('--app-vh', `${mobileModalViewportFreezeHeight}px`);
                return;
            }

            mobileModalViewportFreezeHeight = 0;
            const visualViewport = window.visualViewport;
            const viewportHeight = visualViewport && Number.isFinite(visualViewport.height)
                ? visualViewport.height
                : window.innerHeight;
            const safeHeight = Math.max(320, Math.round(Number(viewportHeight) || 0));
            if (safeHeight > 0) {
                document.documentElement.style.setProperty('--app-vh', `${safeHeight}px`);
            }
        }

        function initAppViewportHeightTracking() {
            if (viewportTrackingInitialized) return;
            viewportTrackingInitialized = true;
            updateAppViewportHeightVar();
            window.addEventListener('resize', updateAppViewportHeightVar, { passive: true });
            window.addEventListener('orientationchange', () => {
                setTimeout(updateAppViewportHeightVar, 120);
                setTimeout(updateAppViewportHeightVar, 420);
            });
            if (window.visualViewport) {
                window.visualViewport.addEventListener('resize', updateAppViewportHeightVar, { passive: true });
                window.visualViewport.addEventListener('scroll', updateAppViewportHeightVar, { passive: true });
            }
            document.addEventListener('focusin', () => {
                setTimeout(updateAppViewportHeightVar, 40);
            });
            document.addEventListener('focusout', () => {
                setTimeout(updateAppViewportHeightVar, 140);
            });
        }

        function lockBodyScrollForModal() {
            if (bodyScrollLockDepth === 0) {
                bodyScrollLockY = window.scrollY || window.pageYOffset || 0;
                document.body.classList.add('modal-open');
                document.body.style.overflow = 'hidden';
                document.body.style.position = 'fixed';
                document.body.style.top = `-${bodyScrollLockY}px`;
                document.body.style.left = '0';
                document.body.style.right = '0';
                document.body.style.width = '100%';
                document.body.style.height = 'var(--app-vh, 100dvh)';
            }
            bodyScrollLockDepth += 1;
        }

        function unlockBodyScrollForModal(force = false) {
            const wasLocked = bodyScrollLockDepth > 0 || document.body.style.position === 'fixed';
            if (force) {
                bodyScrollLockDepth = 0;
            } else if (bodyScrollLockDepth > 0) {
                bodyScrollLockDepth -= 1;
            } else {
                return;
            }
            if (bodyScrollLockDepth > 0) {
                return;
            }

            const restoreY = Number.isFinite(bodyScrollLockY) ? bodyScrollLockY : 0;
            document.body.classList.remove('modal-open');
            document.body.style.overflow = '';
            document.body.style.position = '';
            document.body.style.width = '';
            document.body.style.height = '';
            document.body.style.top = '';
            document.body.style.left = '';
            document.body.style.right = '';
            bodyScrollLockY = 0;

            if (wasLocked) {
                window.scrollTo(0, restoreY);
            }
        }

        function bindFloatingModalInputAssist(rootElement) {
            if (!rootElement) return;
            const fields = rootElement.querySelectorAll('input, textarea, select');
            fields.forEach((field) => {
                field.addEventListener('focus', () => {
                    if (isCoarsePointerMobileViewport()) return;
                    setTimeout(() => {
                        try {
                            field.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'smooth' });
                        } catch (error) {
                            try {
                                field.scrollIntoView(true);
                            } catch (_) {
                                // ignore scroll errors
                            }
                        }
                    }, 140);
                });
            });
        }

        function mountFloatingModal(modalHtml) {
            if (!modalHtml) return;
            const existingRoot = document.getElementById(APP_FLOATING_MODAL_ROOT_ID);
            const hadExistingLock = existingRoot && existingRoot.dataset.locked === '1';
            if (existingRoot) {
                existingRoot.remove();
            }
            if (!hadExistingLock) {
                lockBodyScrollForModal();
            }

            const root = document.createElement('div');
            root.id = APP_FLOATING_MODAL_ROOT_ID;
            root.className = 'app-floating-modal-root';
            root.dataset.locked = '1';
            root.innerHTML = String(modalHtml);
            document.body.appendChild(root);
            bindFloatingModalInputAssist(root);
            updateAppViewportHeightVar();
        }

        function unmountFloatingModal() {
            const root = document.getElementById(APP_FLOATING_MODAL_ROOT_ID);
            if (!root) return false;
            const hadLock = root.dataset.locked === '1';
            root.remove();
            if (hadLock) {
                unlockBodyScrollForModal();
            }
            mobileModalViewportFreezeHeight = 0;
            updateAppViewportHeightVar();
            return true;
        }

        function focusModalPrimaryControl(modalElement, preferredSelector = '') {
            if (!modalElement) return;
            const selector = preferredSelector && String(preferredSelector).trim()
                ? String(preferredSelector).trim()
                : 'input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled])';
            const target = modalElement.querySelector(selector);
            if (target && typeof target.focus === 'function') {
                try {
                    target.focus({ preventScroll: true });
                } catch (error) {
                    target.focus();
                }
            }
        }

        function isStaticOverlayModalVisible(modalElement) {
            if (!modalElement) return false;
            if (modalElement.style.display === 'none') return false;
            return modalElement.classList.contains('active') || modalElement.style.display === 'flex';
        }

        function syncVehicleDetailNestedOverlayState() {
            const vehicleModal = document.getElementById('vehicleDetailModal');
            if (!vehicleModal) return;

            const nestedModalIds = ['addServiceRecordModal', 'serviceRecordDetailModal', 'attachmentPreviewModal'];
            const hasNestedModal = nestedModalIds.some((modalId) => {
                const modalEl = document.getElementById(modalId);
                return isStaticOverlayModalVisible(modalEl);
            });

            vehicleModal.dataset.nestedModalOpen = hasNestedModal ? '1' : '0';
        }

        function openStaticOverlayModal(modalOrId, options = {}) {
            const modal = typeof modalOrId === 'string'
                ? document.getElementById(modalOrId)
                : modalOrId;
            if (!modal) return false;

            const isLicenseModal = modal.classList.contains('license-modal');
            if (isLicenseModal) {
                modal.classList.remove('hidden');
            }

            modal.classList.add('active');
            modal.style.display = 'flex';
            if (modal.dataset.scrollLock !== '1') {
                lockBodyScrollForModal();
                modal.dataset.scrollLock = '1';
            }

            if (options && options.scrollTargetSelector) {
                const scrollTarget = modal.querySelector(options.scrollTargetSelector);
                if (scrollTarget) {
                    scrollTarget.scrollTop = 0;
                }
            }

            requestAnimationFrame(() => {
                focusModalPrimaryControl(modal, options && options.focusSelector ? options.focusSelector : '');
            });

            syncVehicleDetailNestedOverlayState();
            updateAppViewportHeightVar();

            return true;
        }

        function closeStaticOverlayModal(modalOrId) {
            const modal = typeof modalOrId === 'string'
                ? document.getElementById(modalOrId)
                : modalOrId;
            if (!modal) return false;

            const hadLock = modal.dataset.scrollLock === '1';
            const isLicenseModal = modal.classList.contains('license-modal');

            modal.classList.remove('active');
            if (isLicenseModal) {
                modal.classList.add('hidden');
            }
            modal.style.display = 'none';
            modal.dataset.scrollLock = '0';

            if (hadLock) {
                unlockBodyScrollForModal();
            }

            syncVehicleDetailNestedOverlayState();
            updateAppViewportHeightVar();
            return true;
        }

        function loadClientGeoTelemetry() {
            try {
                const raw = sessionStorage.getItem('clientGeoTelemetry');
                if (!raw) return null;
                const parsed = JSON.parse(raw);
                if (!parsed || typeof parsed !== 'object') return null;
                if (typeof parsed.lat !== 'number' || typeof parsed.lon !== 'number') return null;
                return parsed;
            } catch (e) {
                return null;
            }
        }

        function saveClientGeoTelemetry(payload) {
            if (!payload) return;
            clientGeoTelemetry = payload;
            try {
                sessionStorage.setItem('clientGeoTelemetry', JSON.stringify(payload));
            } catch (e) {
                // ignore localStorage errors
            }
        }

        function clearClientGeoTelemetry() {
            clientGeoTelemetry = null;
            try {
                sessionStorage.removeItem('clientGeoTelemetry');
            } catch (e) {
                // ignore localStorage errors
            }
        }

        function getClientGeoTelemetryForHeaders() {
            if (!clientGeoTelemetry) {
                clientGeoTelemetry = loadClientGeoTelemetry();
            }
            if (!clientGeoTelemetry) return null;

            const capturedAtMs = Number(clientGeoTelemetry.capturedAtMs || 0);
            if (!capturedAtMs || (Date.now() - capturedAtMs) > CLIENT_GEO_MAX_AGE_MS) {
                return null;
            }
            return clientGeoTelemetry;
        }

        function appendClientGeoHeaders(headers) {
            if (!headers || typeof headers !== 'object') {
                return false;
            }
            const geo = getClientGeoTelemetryForHeaders();
            if (!geo) {
                captureClientGeolocation(false);
                return false;
            }
            headers['X-Geo-Lat'] = String(geo.lat);
            headers['X-Geo-Lon'] = String(geo.lon);
            if (geo.accuracy !== null && geo.accuracy !== undefined) {
                headers['X-Geo-Accuracy'] = String(geo.accuracy);
            }
            if (geo.capturedAtMs) {
                try {
                    headers['X-Geo-Captured-At'] = new Date(Number(geo.capturedAtMs)).toISOString();
                } catch (e) {
                    // ignore invalid timestamp
                }
            }
            return true;
        }

        function captureClientGeolocation(force = false) {
            const session = AdminBrowserSession.snapshot();
            if (!session.token) return;
            try { AdminBrowserSession.assertCurrent(session); } catch { return; }
            if (typeof navigator === 'undefined' || !navigator.geolocation) return;

            const now = Date.now();
            if (!force && (now - clientGeoLastAttemptAt) < CLIENT_GEO_MIN_RETRY_MS) return;
            clientGeoLastAttemptAt = now;

            navigator.geolocation.getCurrentPosition(
                (position) => {
                    try { AdminBrowserSession.assertCurrent(session); } catch { return; }
                    const coords = position && position.coords ? position.coords : null;
                    if (!coords) return;
                    const lat = Number(coords.latitude);
                    const lon = Number(coords.longitude);
                    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
                    const payload = {
                        lat: Number(lat.toFixed(6)),
                        lon: Number(lon.toFixed(6)),
                        accuracy: Number.isFinite(Number(coords.accuracy)) ? Math.round(Number(coords.accuracy)) : null,
                        capturedAtMs: Date.now(),
                    };
                    saveClientGeoTelemetry(payload);
                },
                () => {
                    // Uživatel nepovolil polohu nebo se nepodařilo načtení.
                },
                {
                    enableHighAccuracy: true,
                    timeout: 7000,
                    maximumAge: 300000,
                }
            );
        }

        function startClientGeoRefresh() {
            if (clientGeoRefreshTimer) {
                clearInterval(clientGeoRefreshTimer);
                clientGeoRefreshTimer = null;
            }
            captureClientGeolocation(true);
            clientGeoRefreshTimer = setInterval(() => {
                captureClientGeolocation(false);
            }, CLIENT_GEO_MIN_RETRY_MS);
        }

        function stopClientGeoRefresh() {
            if (clientGeoRefreshTimer) {
                clearInterval(clientGeoRefreshTimer);
                clientGeoRefreshTimer = null;
            }
        }

        let authStoryTimer = null;

        function activateAuthStorySlide(index) {
            const storyboard = document.querySelector('[data-auth-storyboard]');
            if (!storyboard) return;
            const frames = Array.from(storyboard.querySelectorAll('.auth-story-frame'));
            const steps = Array.from(document.querySelectorAll('.auth-story-step'));
            if (!frames.length) return;

            const safeIndex = Math.max(0, Math.min(index, frames.length - 1));
            frames.forEach((frame, i) => {
                frame.classList.toggle('is-active', i === safeIndex);
            });
            steps.forEach((step, i) => {
                step.classList.toggle('is-active', i === safeIndex);
            });
            storyboard.dataset.storyIndex = String(safeIndex);
        }

        function startAuthStoryAutoplay() {
            const storyboard = document.querySelector('[data-auth-storyboard]');
            if (!storyboard) return;
            const framesCount = storyboard.querySelectorAll('.auth-story-frame').length;
            if (!framesCount || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

            if (authStoryTimer) {
                clearInterval(authStoryTimer);
                authStoryTimer = null;
            }

            authStoryTimer = setInterval(() => {
                const current = Number(storyboard.dataset.storyIndex || '0');
                const next = (current + 1) % framesCount;
                activateAuthStorySlide(next);
            }, 3000);
        }

        function stopAuthStoryAutoplay() {
            if (authStoryTimer) {
                clearInterval(authStoryTimer);
                authStoryTimer = null;
            }
        }

        function initAuthPromoSequence() {
            const storyboard = document.querySelector('[data-auth-storyboard]');
            if (!storyboard) return;

            activateAuthStorySlide(0);
            startAuthStoryAutoplay();

            storyboard.addEventListener('mouseenter', stopAuthStoryAutoplay);
            storyboard.addEventListener('mouseleave', startAuthStoryAutoplay);

            document.querySelectorAll('.auth-story-step').forEach((button) => {
                button.addEventListener('click', () => {
                    const stepIndex = Number(button.dataset.storyStep || '0');
                    activateAuthStorySlide(stepIndex);
                    startAuthStoryAutoplay();
                });
            });
        }

        // Přepsání HTML5 validace na české zprávy
        document.addEventListener('DOMContentLoaded', function() {
            initAppViewportHeightTracking();
            // Přesunout licenční modal pod body (portal), aby byl vždy overlay.
            const mountedLicenseModal = document.getElementById('licenseModal');
            if (mountedLicenseModal && mountedLicenseModal.parentElement !== document.body) {
                document.body.appendChild(mountedLicenseModal);
            }
            ['vehicleDetailModal', 'addServiceRecordModal', 'serviceRecordDetailModal'].forEach((modalId) => {
                const modalEl = document.getElementById(modalId);
                if (modalEl && modalEl.parentElement !== document.body) {
                    document.body.appendChild(modalEl);
                }
            });

            // Při startu zavřít license dropdown/modal a odemknout scroll
            // Zajistit, že modal je skrytý, zejména pokud uživatel není přihlášený
            const lm = document.getElementById('licenseModal');
            if (lm) {
                lm.classList.add('hidden');
                lm.style.display = 'none';
            }
            const ld = document.getElementById('licenseQuickDropdown');
            if (ld) {
                ld.classList.add('hidden');
                ld.style.display = 'none';
            }
            clearBodyScrollLocks();

            // The shared bootstrap verifies the administrator before showing data.

            initAuthPromoSequence();
            document.addEventListener('visibilitychange', () => {
                if (document.hidden) {
                    stopAuthStoryAutoplay();
                } else {
                    startAuthStoryAutoplay();
                }
            });

            // Funkce pro zobrazení chybové zprávy (použije showAlert pokud existuje, jinak alert)
            function showValidationError(message) {
                if (typeof showAlert === 'function') {
                    showAlert(message, 'error');
                } else {
                    // Fallback - zobrazit alert kontejner pokud existuje
                    const container = document.getElementById('alertContainer');
                    if (container) {
                        container.innerHTML = `<div class="alert alert-error">${escapeHtml(message)}</div>`;
                        setTimeout(() => {
                            container.innerHTML = '';
                        }, 5000);
                    } else {
                        alert(message);
                    }
                }
            }

            // Přepsat výchozí HTML5 validaci pro všechny required prvky
            const forms = document.querySelectorAll('form');
            forms.forEach(form => {
                form.addEventListener('invalid', function(e) {
                    e.preventDefault();
                    const element = e.target;

                    // Zobrazit českou chybovou zprávu
                    if (element.validity.valueMissing) {
                        let message = 'Vyplňte prosím toto pole';
                        if (element.tagName === 'TEXTAREA' && element.id && element.id.includes('Description')) {
                            message = 'Vyplňte prosím popis úkonu';
                        } else if (element.tagName === 'INPUT' && element.type === 'date') {
                            message = 'Vyberte prosím datum';
                        } else if (element.tagName === 'SELECT') {
                            message = 'Vyberte prosím možnost';
                        }

                        // Zobrazit alert místo výchozího tooltipu
                        showValidationError(message);
                        element.focus();
                    }
                }, true);

                // Přepsat výchozí submit validaci
                form.addEventListener('submit', function(e) {
                    if (!form.checkValidity()) {
                        e.preventDefault();
                        e.stopPropagation();

                        // Najít první nevalidní prvek
                        const firstInvalid = form.querySelector(':invalid');
                        if (firstInvalid) {
                            firstInvalid.focus();
                            firstInvalid.dispatchEvent(new Event('invalid', { bubbles: true }));
                        }
                    }
                });
            });
        });

        // Helper funkce pro získání location objektu (kompatibilní s Webnode i standardním prostředím)
        function getLocation() {
            try {
                // Zkusit Webnode API (pokud je k dispozici)
                if (typeof wnd !== 'undefined' && wnd.fe && wnd.fe.Location) {
                    return wnd.fe.Location;
                }
            } catch (e) {
                console.warn("[APP] Webnode API není dostupné, používám window.location");
            }
            // Fallback na standardní window.location
            return window.location;
        }

        // API URL - centrální funkce pro získání BASE URL
        function getApiBaseUrl() { return window.location.origin; }

        // Alias pro zpětnou kompatibilitu
        function getApiUrl() {
            return getApiBaseUrl();
        }

        function updateMobileServerStatus(statusClass, text) {
            const mobileBadge = document.getElementById('mobileServerStatus');
            const mobileIndicator = document.getElementById('mobileStatusIndicator');
            const mobileText = document.getElementById('mobileStatusText');
            if (!mobileBadge || !mobileIndicator || !mobileText) return;

            mobileIndicator.classList.remove('status-online', 'status-offline', 'status-checking');
            mobileIndicator.classList.add(statusClass || 'status-checking');
            mobileText.textContent = text || 'Kontroluji...';
        }

        function setMobileNavbarToggleVisualState(isOpen) {
            const menuToggle = document.getElementById('mobileMenuToggle');
            if (!menuToggle) return;

            menuToggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');

            // Neměnit innerHTML během click eventu (na mobilech to může odpojit event.target
            // a outside-click listener by menu ihned zavřel).
            const icon = menuToggle.querySelector('span[aria-hidden="true"]');
            if (icon) {
                icon.textContent = isOpen ? '✕' : '☰';
                return;
            }

            menuToggle.textContent = isOpen ? '✕' : '☰';
        }

        function closeMobileNavbarMenu() {
            const navbar = document.getElementById('mainNavbar');
            if (!navbar) return;

            navbar.classList.remove('mobile-menu-open');
            setMobileNavbarToggleVisualState(false);
        }

        function toggleMobileNavbarMenu() {
            const navbar = document.getElementById('mainNavbar');
            if (!navbar) return;

            const willOpen = !navbar.classList.contains('mobile-menu-open');
            navbar.classList.toggle('mobile-menu-open', willOpen);
            setMobileNavbarToggleVisualState(willOpen);
        }

        // Kontrola stavu serveru
        async function checkServerStatus() {
            const indicator = document.getElementById('statusIndicator');
            const statusText = document.getElementById('statusText');

            if (!indicator || !statusText) return;

            // Pokud API_URL není inicializována, zkusit znovu
            if (!API_URL) {
                API_URL = getApiUrl();
            }

            // Pokud není nastavená API URL, zobrazit varování (jen pro admina)
            if (!API_URL) {
                indicator.className = 'status-offline';
                statusText.textContent = 'API URL není nastavena';
                updateMobileServerStatus('status-offline', 'Server offline');
                // Zobrazit konfigurační panel jen pro admina
                const location = getLocation();
                const urlParams = new URLSearchParams(location.search || '');
                if (urlParams.get('admin') === '1') {
                    showApiUrlConfig();
                }
                return;
            }

            try {
                indicator.className = 'status-checking';
                statusText.textContent = 'Kontroluji...';
                updateMobileServerStatus('status-checking', 'Kontroluji...');



                const headers = {};

                const response = await fetch(`${API_URL}/health`, {
                    method: 'GET',
                    headers: headers,
                    mode: 'cors',
                    cache: 'no-cache'
                });



                if (response.ok) {
                    const data = await response.json();

                    indicator.className = 'status-online';
                    statusText.textContent = 'Server online';
                    updateMobileServerStatus('status-online', 'Server online');
                } else {
                    const errorText = await response.text();
                    console.error("[STATUS] Server error:");
                    throw new Error(`Server neodpovídá (${response.status})`);
                }
            } catch (error) {
                indicator.className = 'status-offline';
                statusText.textContent = 'Server offline';
                updateMobileServerStatus('status-offline', 'Server offline');
                console.error("[STATUS] Server status check failed:");
                console.error("[STATUS] API_URL:");

                // Pokud jsme na toozservis.cz a server neodpovídá, zobrazit konfiguraci jen pro admina
                const location = getLocation();
                const hostname = location.hostname || '';
                if (hostname.includes('toozservis.cz') ||
                    hostname.includes('webnode.com')) {
                    const urlParams = new URLSearchParams(location.search || '');
                    if ((error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) &&
                        urlParams.get('admin') === '1') {
                        showApiUrlConfig();
                    }
                }
            }
        }

        // Zobrazení alertu
        function showAlert(message, type = 'info') {
            const container = document.getElementById('alertContainer');
            container.innerHTML = `<div class="alert alert-${escapeHtml(type)}" data-testid="alert-${escapeHtml(type)}">${escapeHtml(message)}</div>`;
            setTimeout(() => {
                container.innerHTML = '';
            }, 5000);
        }

        function getSystemNotificationStorageKey() {
            const userId = currentUser && currentUser.id ? String(currentUser.id) : 'anonymous';
            return `systemNotificationsSeen:${userId}`;
        }

        function getSeenSystemNotificationIds() {
            try {
                const raw = sessionStorage.getItem(getSystemNotificationStorageKey()) || '[]';
                const parsed = JSON.parse(raw);
                return Array.isArray(parsed) ? parsed.map((id) => Number(id)).filter((id) => Number.isFinite(id)) : [];
            } catch (error) {
                return [];
            }
        }

        function rememberSeenSystemNotificationId(notificationId) {
            const id = Number(notificationId);
            if (!Number.isFinite(id)) return;
            const existing = new Set(getSeenSystemNotificationIds());
            existing.add(id);
            const sliced = Array.from(existing).slice(-200);
            sessionStorage.setItem(getSystemNotificationStorageKey(), JSON.stringify(sliced));
        }

        function mapSystemNotificationSeverityToAlertType(severity) {
            const key = String(severity || 'info').toLowerCase();
            if (key === 'critical') return 'error';
            if (key === 'warning') return 'warning';
            return 'info';
        }

        async function loadSystemNotifications() {
            if (!currentUser || !accessToken) return;
            try {
                const payload = await apiCall('/api/v1/system-notifications?limit=20', 'GET', null, 12000);
                const items = Array.isArray(payload && payload.items) ? payload.items : [];
                const seen = new Set(getSeenSystemNotificationIds());
                for (const item of items) {
                    const id = Number(item && item.id);
                    if (!Number.isFinite(id) || seen.has(id)) {
                        continue;
                    }
                    const title = item.title ? `${item.title}: ` : '';
                    const message = String(item.message || '').trim();
                    if (message) {
                        showAlert(`${title}${message}`, mapSystemNotificationSeverityToAlertType(item.severity));
                    }
                    rememberSeenSystemNotificationId(id);
                }
            } catch (error) {
                console.warn("[SYSTEM_NOTIFICATIONS] Load failed:");
            }
        }

        function stopSystemNotificationsPolling() {
            if (window.__systemNotificationsTimer) {
                clearInterval(window.__systemNotificationsTimer);
                window.__systemNotificationsTimer = null;
            }
        }

        function startSystemNotificationsPolling() {
            stopSystemNotificationsPolling();
            loadSystemNotifications();
            window.__systemNotificationsTimer = setInterval(() => {
                if (!currentUser || !accessToken) return;
                loadSystemNotifications();
            }, 60000);
        }

        // Formátování datumu do CZ (DD. MM. YYYY), fallback na "—"
        function formatDateCZ(value) {
            if (!value) return '—';
            try {
                const d = new Date(value);
                if (!isNaN(d.getTime())) {
                    return d.toLocaleDateString('cs-CZ');
                }
            } catch (e) {
                // ignore
            }
            return typeof value === 'string' && value.trim() ? value : '—';
        }

        function normalizeDateInput(value) {
            if (!value) return '';
            const trimmed = value.trim();
            if (!trimmed) return '';
            if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
                return trimmed;
            }
            const dotMatch = trimmed.match(/^(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})$/);
            if (dotMatch) {
                const [, d, m, y] = dotMatch;
                return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
            }
            const parsed = new Date(trimmed);
            if (!isNaN(parsed.getTime())) {
                const y = parsed.getFullYear();
                const m = String(parsed.getMonth() + 1).padStart(2, '0');
                const d = String(parsed.getDate()).padStart(2, '0');
                return `${y}-${m}-${d}`;
            }
            return '';
        }

        // Zobrazení chyby ve stálém kontejneru pod formulářem (nezaniká automaticky)
        function showFormError(containerId, message) {
            const container = document.getElementById(containerId);
            if (container) {
                container.innerHTML = `<div class="alert alert-error" data-testid="alert-error">${escapeHtml(message)}</div>`;
                // Scrollovat na chybu, aby byla viditelná
                container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            } else {
                // Fallback na standardní alert
                showAlert(message, 'error');
            }
        }

        // Vyčištění chyby ve formuláři
        function clearFormError(containerId) {
            const container = document.getElementById(containerId);
            if (container) {
                container.innerHTML = '';
            }
        }

        // API volání s timeout a jednotným error handlingem
        async function apiCall(endpoint, method = 'GET', data = null, timeoutOrSignal = 30000) {
            // Aktualizovat API_URL při každém volání (pro případ změny)
            API_URL = getApiBaseUrl();

            if (!API_URL) {
                const location = getLocation();
                const urlParams = new URLSearchParams(location.search || '');
                if (urlParams.get('admin') === '1') {
                    showApiUrlConfig();
                }
                throw new Error('API URL není nastavena. Kontaktujte administrátora.');
            }

            const headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Accept-Language': 'cs-CZ,cs;q=0.9,en;q=0.8'
            };

            // Přidat Referer hlavičku pro Cloudflare (pokud je dostupná)
            if (typeof window !== 'undefined' && window.location) {
                headers['Referer'] = window.location.origin + window.location.pathname;
            }

            // Přidat JWT token do headeru (preferovaná metoda)
            if (accessToken) {
                headers['Authorization'] = `Bearer ${accessToken}`;

            }
            appendClientGeoHeaders(headers);

            // Rozpoznat, zda je timeoutOrSignal číslo (timeout) nebo AbortSignal
            let timeout = 30000;
            let signal = null;
            if (typeof timeoutOrSignal === 'number') {
                timeout = timeoutOrSignal;
            } else if (timeoutOrSignal instanceof AbortSignal) {
                signal = timeoutOrSignal;
                timeout = 30000; // Default timeout i při použití signal
            }

            const options = {
                method,
                headers,
                credentials: 'include', // Zahrnout cookies pro Cloudflare
                mode: 'cors',
                cache: 'no-cache'
            };

            if (signal) {
                options.signal = signal;
            }

            if (data) {
                options.body = JSON.stringify(data);
            }

            try {
                const url = `${API_URL}${endpoint}`;


                const response = await AdminBrowserSession.request(url, {...options, timeoutMs: timeout});

                // Debug tracking - uložit request info
                const requestInfo = {
                    method: method,
                    url: url,
                    status: response.status,
                    timestamp: new Date().toISOString()
                };

                // Diagnostics never retain response payloads, tokens or personal data.
                requestInfo.url = new URL(url, window.location.origin).pathname;

                // Přidat do debug logu (max 3)
                debugRequests.unshift(requestInfo);
                if (debugRequests.length > DEBUG_MAX_REQUESTS) {
                    debugRequests.pop();
                }

                // Zkontrolovat Content-Type hlavičku
                const contentType = response.headers.get('content-type');
                const isJson = contentType && contentType.includes('application/json');

                if (response.ok) {
                    if (response.status === 204) return null;
                    if (!isJson) {
                        console.warn("[API] Response není JSON, ale status je OK");
                        const text = await response.text();
                        console.warn("[API] Response text:");
                        throw new Error('Server vrátil neočekávaný formát odpovědi');
                    }
                    const result = await response.json();

                    return result;
                } else {
                    if (response.status === 403) {
                        let message = 'K této operaci nemáte oprávnění.';
                        if (isJson) {
                            const error = await response.json();
                            if (typeof error.detail === 'string') message = error.detail;
                        }
                        throw new Error(message);
                    }

                    // 404 Not Found - poskytnout užitečnější zprávu s detailními informacemi
                    if (response.status === 404) {
                        console.error("Klientskou operaci se nepodařilo dokončit.");
                        console.error("Klientskou operaci se nepodařilo dokončit.");
                        console.error("Klientskou operaci se nepodařilo dokončit.");
                        console.error("Klientskou operaci se nepodařilo dokončit.");

                        let errorMessage = 'Endpoint nebyl nalezen';
                        let responseBody = '';
                        try {
                            if (isJson) {
                                const error = await response.json();
                                responseBody = JSON.stringify(error).substring(0, 200);
                                if (error.detail) {
                                    errorMessage = error.detail;
                                } else if (error.message) {
                                    errorMessage = error.message;
                                }
                            } else {
                                const text = await response.text();
                                responseBody = text.substring(0, 200);
                            }
                        } catch (e) {
                            // Ignorovat chyby při parsování
                        }

                        // Detailní chybová zpráva pro debug
                        const detailedError = `Endpoint nebyl nalezen: ${endpoint}\n\n` +
                            `Volaná URL: ${url}\n` +
                            `API Base URL: ${API_URL}\n` +
                            `Status: 404 Not Found\n` +
                            `Response body: ${responseBody || '[prázdné]'}\n\n` +
                            `Zkontrolujte:\n` +
                            `- Zda backend běží na ${API_URL}\n` +
                            `- Zda router ${endpoint} je zaregistrován\n` +
                            `- Zda je token správně posílán (Authorization header)`;

                        throw new Error(detailedError);
                    }

                    // Cloudflare challenge (403 s HTML)
                    if (response.status === 403 && !isJson) {
                        console.error("[API] Cloudflare challenge detected (403 with HTML)");
                        throw new Error('Cloudflare blokuje požadavek. Zkuste obnovit stránku (F5) a zkusit znovu.');
                    }

                    let errorMessage = 'Chyba při komunikaci s API';
                    let errorData = null;
                    try {
                        if (isJson) {
                            const error = await response.json();
                            errorData = error;

                            // LICENSE_UI_START: Handling LICENSE_QUOTA_EXCEEDED
                            if (error.error && error.error.code === "LICENSE_QUOTA_EXCEEDED") {
                                console.warn("[LICENSE] Quota exceeded:");
                                // Zobrazit banner
                                if (typeof showLicenseQuotaBanner === 'function') {
                                    showLicenseQuotaBanner(error.error);
                                }
                                // Refresh license status
                                if (typeof loadLicenseStatus === 'function') {
                                    loadLicenseStatus();
                                }
                                // Vrátit chybu pro volající funkci
                                errorMessage = error.error.message || 'Limit vozidel překročen';
                            } else {
                                // Zobrazit detailnější chybovou zprávu
                                if (error.detail) {
                                    if (Array.isArray(error.detail)) {
                                        // Pydantic validation errors
                                        errorMessage = error.detail.map(e => `${e.loc?.join('.')}: ${e.msg}`).join(', ');
                                    } else {
                                        errorMessage = error.detail;
                                    }
                                } else if (error.message) {
                                    errorMessage = error.message;
                                } else {
                                    errorMessage = JSON.stringify(error);
                                }
                            }
                        } else {
                            // Pokud není JSON, zkusit přečíst jako text
                            const text = await response.text();
                            if (text.includes('Cloudflare') || text.includes('challenge')) {
                                errorMessage = 'Cloudflare blokuje požadavek. Zkuste obnovit stránku (F5) a zkusit znovu.';
                            } else {
                                errorMessage = `HTTP ${response.status}: ${response.statusText}`;
                            }
                        }
                    } catch (e) {
                        errorMessage = `HTTP ${response.status}: ${response.statusText}`;
                    }
                    throw new Error(errorMessage);
                }
            } catch (error) {
                console.error("Klientskou operaci se nepodařilo dokončit.");

                // Pokud je to network error nebo timeout, poskytnout užitečnější zprávu
                if (error.message === 'Failed to fetch' || error.name === 'TypeError' || error.message.includes('časový limit')) {
                    throw new Error('Nepodařilo se připojit k serveru. Zkontrolujte připojení a zkuste to znovu.');
                }

                // Pokud je to 401/403, už jsme odhlásili uživatele
                if (error.message.includes('relace vypršela')) {
                    throw error;
                }

                throw error;
            }
        }

        async function apiUploadFormData(endpoint, formData, method = 'POST') {
            API_URL = getApiBaseUrl();
            if (!API_URL) {
                throw new Error('API URL není nastavena. Kontaktujte administrátora.');
            }

            const headers = {
                'Accept': 'application/json',
                'Accept-Language': 'cs-CZ,cs;q=0.9,en;q=0.8'
            };

            if (accessToken) {
                headers['Authorization'] = `Bearer ${accessToken}`;
            }
            appendClientGeoHeaders(headers);

            const response = await AdminBrowserSession.request(`${API_URL}${endpoint}`, {
                method,
                headers,
                body: formData,
                credentials: 'include',
                mode: 'cors',
                cache: 'no-cache',
            });

            const contentType = response.headers.get('content-type') || '';
            const isJson = contentType.includes('application/json');

            if (!response.ok) {
                let message = `HTTP ${response.status}`;
                try {
                    if (isJson) {
                        const payload = await response.json();
                        message = payload?.detail || payload?.message || payload?.error?.message || message;
                    } else {
                        const text = await response.text();
                        if (text) {
                            message = text.slice(0, 220);
                        }
                    }
                } catch (e) {
                    // no-op
                }
                throw new Error(message);
            }

            if (isJson) {
                return response.json();
            }
            return {};
        }

        function previewAddVehiclePhoto(fileInput) {
            const previewWrap = document.getElementById('vehiclePhotoPreviewWrap');
            const previewImage = document.getElementById('vehiclePhotoPreview');
            if (!previewWrap || !previewImage) {
                return;
            }

            const file = fileInput && fileInput.files && fileInput.files[0] ? fileInput.files[0] : null;
            if (!file) {
                previewImage.removeAttribute('src');
                previewWrap.classList.add('hidden');
                return;
            }

            const reader = new FileReader();
            reader.onload = () => {
                previewImage.src = String(reader.result || '');
                previewWrap.classList.remove('hidden');
            };
            reader.onerror = () => {
                previewImage.removeAttribute('src');
                previewWrap.classList.add('hidden');
            };
            reader.readAsDataURL(file);
        }

        const vehiclePhotoObjectUrls = new Map();

        function buildVehiclePhotoUrl(vehicleId) {
            if (!vehicleId) return '';
            return `${getApiBaseUrl()}/api/v1/vehicles/${vehicleId}/photo?v=${Date.now()}`;
        }

        function revokeVehiclePhotoObjectUrl(vehicleId) {
            const key = Number(vehicleId);
            const existing = vehiclePhotoObjectUrls.get(key);
            if (existing) {
                try {
                    URL.revokeObjectURL(existing);
                } catch (e) {
                    // ignore revoke errors
                }
                vehiclePhotoObjectUrls.delete(key);
            }
        }

        async function hydrateVehiclePhotoPreview(vehicleId, imgEl) {
            if (!imgEl || !vehicleId) return false;
            const key = Number(vehicleId);
            revokeVehiclePhotoObjectUrl(key);
            imgEl.removeAttribute('src');

            API_URL = getApiBaseUrl();
            if (!API_URL) {
                throw new Error('API URL není nastavena.');
            }

            const headers = {
                'Accept': 'image/*'
            };
            if (accessToken) {
                headers['Authorization'] = `Bearer ${accessToken}`;
            }
            appendClientGeoHeaders(headers);

            const response = await AdminBrowserSession.request(`${API_URL}/api/v1/vehicles/${key}/photo?v=${Date.now()}`, {
                method: 'GET',
                headers,
                credentials: 'include',
                mode: 'cors',
                cache: 'no-store'
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const blob = await response.blob();
            const objectUrl = URL.createObjectURL(blob);
            vehiclePhotoObjectUrls.set(key, objectUrl);
            imgEl.src = objectUrl;
            return true;
        }

        function fileToBase64Payload(file) {
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => {
                    const result = String(reader.result || '');
                    const base64 = result.includes(',') ? result.split(',', 2)[1] : result;
                    if (!base64) {
                        reject(new Error('Soubor se nepodařilo převést.'));
                        return;
                    }
                    resolve(base64);
                };
                reader.onerror = () => reject(new Error('Soubor se nepodařilo načíst.'));
                reader.readAsDataURL(file);
            });
        }

        async function uploadVehiclePhoto(vehicleId, file) {
            if (!vehicleId || !file) {
                throw new Error('Chybí vozidlo nebo soubor.');
            }
            const payload = {
                file_name: file.name || 'vehicle-photo.jpg',
                file_mime_type: file.type || 'image/jpeg',
                file_content_base64: await fileToBase64Payload(file),
            };
            return apiCall(`/api/v1/vehicles/${vehicleId}/photo`, 'POST', payload);
        }

        async function handleVehiclePhotoUpload(vehicleId, inputEl) {
            const file = inputEl && inputEl.files && inputEl.files[0] ? inputEl.files[0] : null;
            if (!file) return;
            try {
                showAlert('Nahrávám fotku vozidla...', 'info');
                await uploadVehiclePhoto(vehicleId, file);
                showAlert('Fotka vozidla byla nahrána.', 'success');
                await showVehicleDetail(vehicleId);
                await loadVehicles();
            } catch (error) {
                showAlert(`Nepodařilo se nahrát fotku: ${error.message}`, 'error');
            } finally {
                if (inputEl) {
                    inputEl.value = '';
                }
            }
        }

        async function deleteVehiclePhoto(vehicleId) {
            if (!vehicleId) return;
            if (!confirm('Opravdu chcete smazat fotku vozidla?')) {
                return;
            }
            try {
                await apiCall(`/api/v1/vehicles/${vehicleId}/photo`, 'DELETE');
                showAlert('Fotka vozidla byla smazána.', 'success');
                await showVehicleDetail(vehicleId);
                await loadVehicles();
            } catch (error) {
                showAlert(`Nepodařilo se smazat fotku: ${error.message}`, 'error');
            }
        }

        function urlBase64ToUint8Array(base64String) {
            if (!base64String) return null;
            const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
            const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
            const rawData = window.atob(base64);
            const outputArray = new Uint8Array(rawData.length);
            for (let i = 0; i < rawData.length; ++i) {
                outputArray[i] = rawData.charCodeAt(i);
            }
            return outputArray;
        }

        function subscriptionToPayload(subscription) {
            if (!subscription) return null;
            const data = subscription.toJSON ? subscription.toJSON() : null;
            if (data && data.endpoint && data.keys && data.keys.p256dh && data.keys.auth) {
                return {
                    endpoint: data.endpoint,
                    keys: {
                        p256dh: data.keys.p256dh,
                        auth: data.keys.auth
                    }
                };
            }

            const p256dh = subscription.getKey ? subscription.getKey('p256dh') : null;
            const auth = subscription.getKey ? subscription.getKey('auth') : null;
            if (!subscription.endpoint || !p256dh || !auth) return null;
            const toBase64 = (buffer) => {
                const binary = String.fromCharCode.apply(null, new Uint8Array(buffer));
                return btoa(binary);
            };
            return {
                endpoint: subscription.endpoint,
                keys: {
                    p256dh: toBase64(p256dh),
                    auth: toBase64(auth)
                }
            };
        }

        async function ensurePushServiceWorkerRegistered() {
            if (!('serviceWorker' in navigator)) {
                throw new Error('Service Worker není v tomto prohlížeči podporován.');
            }
            if (!window.isSecureContext) {
                throw new Error('Push notifikace vyžadují HTTPS nebo localhost.');
            }
            if (pushSwRegistration) return pushSwRegistration;
            pushSwRegistration = await navigator.serviceWorker.register(window.CustomerWeb ? '/web/customer-sw.js' : '/web/sw.js', { scope: '/web/' });
            return pushSwRegistration;
        }

        function getPushClientSupport() {
            const ua = navigator.userAgent || '';
            const isIOS = /iPad|iPhone|iPod/i.test(ua)
                || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
            const isStandalone = Boolean(
                (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches)
                || window.navigator.standalone === true
            );
            const hasNotification = typeof Notification !== 'undefined';
            const hasPushManager = typeof PushManager !== 'undefined';
            const hasServiceWorker = 'serviceWorker' in navigator;
            const isSecureContext = Boolean(window.isSecureContext);
            const iosNeedsStandalone = isIOS && !isStandalone;
            const supported = hasNotification && hasPushManager && hasServiceWorker && isSecureContext && !iosNeedsStandalone;

            return {
                isIOS,
                isStandalone,
                hasNotification,
                hasPushManager,
                hasServiceWorker,
                isSecureContext,
                iosNeedsStandalone,
                supported
            };
        }

        function mapPushFailureReason(reason) {
            switch (reason) {
                case 'ios_home_screen_required':
                    return 'Na iPhonu/iPadu funguje push jen z webu přidaného na plochu (Sdílet -> Přidat na plochu).';
                case 'https_required':
                    return 'Push vyžaduje HTTPS (nebo localhost).';
                case 'permission_denied':
                    return 'Notifikace jsou v prohlížeči zakázané. Povolte je v nastavení Safari.';
                case 'permission_default':
                case 'permission_not_granted':
                    return 'Nejprve povolte notifikace pro tuto aplikaci.';
                case 'unsupported':
                    return 'Tento režim prohlížeče push notifikace nepodporuje.';
                case 'missing_vapid_public_key':
                    return 'Server zatím nemá dostupný VAPID klíč.';
                case 'invalid_subscription_payload':
                    return 'Nepodařilo se vytvořit validní push subskripci.';
                case 'sync_in_progress':
                    return 'Probíhá synchronizace push, zkuste to za chvíli.';
                default:
                    return reason || 'neznámá chyba';
            }
        }

        async function refreshReminderPushStatus() {
            const statusEl = document.getElementById('pushStatusMessage');
            const permissionEl = document.getElementById('pushPermissionBadge');
            const subscriptionEl = document.getElementById('pushSubscriptionBadge');
            const enableBtn = document.getElementById('enablePushBtn');
            const disableBtn = document.getElementById('disablePushBtn');
            const testBtn = document.getElementById('testPushBtn');

            if (!statusEl || !permissionEl || !subscriptionEl) return null;

            let backendStatus = null;
            try {
                backendStatus = await apiCall('/api/v1/push/status', 'GET');
            } catch (error) {
                statusEl.textContent = `Push status: ${error.message || 'neznámá chyba'}`;
                statusEl.style.color = '#ef4444';
                return null;
            }

            const clientSupport = getPushClientSupport();
            const permission = (typeof Notification !== 'undefined') ? Notification.permission : 'unsupported';
            const activeSubscriptions = Number(backendStatus.active_subscriptions || 0);
            const isReady = Boolean(backendStatus.ready);
            let permissionLabel = permission === 'granted'
                ? 'Povoleno'
                : permission === 'denied'
                    ? 'Zakázáno'
                    : permission === 'default'
                        ? 'Neuděleno'
                        : 'Nepodporováno';
            if (clientSupport.iosNeedsStandalone) {
                permissionLabel = 'Jen po přidání na plochu';
            }

            permissionEl.textContent = `Oprávnění: ${permissionLabel}`;
            if (clientSupport.iosNeedsStandalone) {
                permissionEl.style.color = '#f59e0b';
            } else {
                permissionEl.style.color = permission === 'granted' ? '#10b981' : (permission === 'denied' ? '#ef4444' : '#94a3b8');
            }
            subscriptionEl.textContent = activeSubscriptions > 0
                ? `Aktivní zařízení: ${activeSubscriptions}`
                : 'Aktivní zařízení: 0';
            subscriptionEl.style.color = activeSubscriptions > 0 ? '#10b981' : '#94a3b8';

            if (!clientSupport.isSecureContext) {
                statusEl.textContent = 'Push vyžaduje HTTPS (nebo localhost).';
                statusEl.style.color = '#f59e0b';
            } else if (clientSupport.iosNeedsStandalone) {
                statusEl.textContent = 'Safari na iPhonu/iPadu: otevřete aplikaci z ikony na ploše (Sdílet -> Přidat na plochu).';
                statusEl.style.color = '#f59e0b';
            } else if (!clientSupport.hasNotification || !clientSupport.hasPushManager || !clientSupport.hasServiceWorker) {
                statusEl.textContent = 'Tento prohlížeč nebo jeho aktuální režim nepodporuje Web Push.';
                statusEl.style.color = '#f59e0b';
            } else if (!backendStatus.enabled) {
                statusEl.textContent = 'Push je na serveru vypnutý.';
                statusEl.style.color = '#f59e0b';
            } else if (!backendStatus.configured) {
                statusEl.textContent = 'Push není nakonfigurován (chybí VAPID klíče).';
                statusEl.style.color = '#f59e0b';
            } else if (!backendStatus.library_available) {
                statusEl.textContent = 'Push není připraven (chybí pywebpush).';
                statusEl.style.color = '#f59e0b';
            } else if (permission !== 'granted') {
                statusEl.textContent = 'Pro push je potřeba povolit notifikace v prohlížeči.';
                statusEl.style.color = '#94a3b8';
            } else if (activeSubscriptions === 0) {
                statusEl.textContent = 'Push je povolen, ale zařízení zatím není zaregistrované.';
                statusEl.style.color = '#94a3b8';
            } else {
                statusEl.textContent = 'Push notifikace jsou aktivní.';
                statusEl.style.color = '#10b981';
            }

            const canUseClientPush = clientSupport.supported;
            if (enableBtn) enableBtn.disabled = !canUseClientPush || !backendStatus.enabled || !backendStatus.configured;
            if (disableBtn) disableBtn.disabled = !canUseClientPush || activeSubscriptions === 0;
            if (testBtn) testBtn.disabled = !canUseClientPush || !isReady || activeSubscriptions === 0;

            return backendStatus;
        }

        async function ensurePushSubscribed(options = {}) {
            const interactive = Boolean(options && options.interactive);
            const force = Boolean(options && options.force);

            if (pushSubscriptionSyncInProgress) {
                return { ok: false, reason: 'sync_in_progress' };
            }

            pushSubscriptionSyncInProgress = true;
            try {
                const clientSupport = getPushClientSupport();
                if (!clientSupport.isSecureContext) {
                    return { ok: false, reason: 'https_required' };
                }

                if (clientSupport.iosNeedsStandalone) {
                    return { ok: false, reason: 'ios_home_screen_required' };
                }

                if (!clientSupport.hasPushManager || !clientSupport.hasNotification || !clientSupport.hasServiceWorker) {
                    return { ok: false, reason: 'unsupported' };
                }

                if (window.Notification.permission === 'denied') {
                    return { ok: false, reason: 'permission_denied' };
                }

                if (window.Notification.permission !== 'granted') {
                    if (!interactive) {
                        return { ok: false, reason: 'permission_not_granted' };
                    }
                    const permission = await Notification.requestPermission();
                    if (permission !== 'granted') {
                        return { ok: false, reason: `permission_${permission}` };
                    }
                }

                const keyInfo = await apiCall('/api/v1/push/vapid-public-key', 'GET');
                const publicKey = keyInfo && keyInfo.vapid_public_key ? String(keyInfo.vapid_public_key) : '';
                if (!publicKey) {
                    return { ok: false, reason: 'missing_vapid_public_key' };
                }

                const registration = await ensurePushServiceWorkerRegistered();
                let subscription = await registration.pushManager.getSubscription();

                if (force && subscription) {
                    await subscription.unsubscribe();
                    subscription = null;
                }

                if (!subscription) {
                    subscription = await registration.pushManager.subscribe({
                        userVisibleOnly: true,
                        applicationServerKey: urlBase64ToUint8Array(publicKey)
                    });
                }

                const payload = subscriptionToPayload(subscription);
                if (!payload) {
                    return { ok: false, reason: 'invalid_subscription_payload' };
                }

                await apiCall('/api/v1/push/subscribe', 'POST', payload);
                return { ok: true, reason: 'subscribed' };
            } catch (error) {
                return { ok: false, reason: error.message || 'subscribe_failed' };
            } finally {
                pushSubscriptionSyncInProgress = false;
                await refreshReminderPushStatus();
            }
        }

        async function disablePushNotifications() {
            try {
                if ('serviceWorker' in navigator) {
                    const registration = pushSwRegistration || await navigator.serviceWorker.getRegistration('/web/');
                    if (registration) {
                        const subscription = await registration.pushManager.getSubscription();
                        if (subscription) {
                            const payload = subscriptionToPayload(subscription);
                            try {
                                await apiCall('/api/v1/push/unsubscribe', 'POST', payload ? { endpoint: payload.endpoint } : {});
                            } catch (error) {
                                console.warn("[PUSH] Backend unsubscribe warning:");
                            }
                            await subscription.unsubscribe();
                        } else {
                            await apiCall('/api/v1/push/unsubscribe', 'POST', {});
                        }
                    } else {
                        await apiCall('/api/v1/push/unsubscribe', 'POST', {});
                    }
                }
            } catch (error) {
                console.warn("[PUSH] Disable failed:");
            } finally {
                await refreshReminderPushStatus();
            }
        }

        async function sendPushTestNotification() {
            try {
                const response = await apiCall('/api/v1/push/test', 'POST', {
                    title: 'Evidence Vozidel',
                    body: 'Test push notifikace je doručena.'
                });
                const sent = Number(response?.result?.sent || 0);
                if (sent > 0) {
                    showAlert('Test push notifikace byla odeslána.', 'success');
                } else {
                    showAlert('Test push nebyl odeslán. Zkontrolujte oprávnění/subskripci.', 'warning');
                }
            } catch (error) {
                showAlert(`Test push selhal: ${error.message || 'Neznámá chyba'}`, 'error');
            } finally {
                await refreshReminderPushStatus();
            }
        }

        // Nastavení DEV API URL panelu (skrýt v produkci)
        function setupDevApiUrlPanel() {
            const panel = document.getElementById('dev-api-url-panel');
            if (!panel) return;

            if (window.location.hostname === "app.toozservis.cz") {
                // V produkci panel schováme
                panel.style.display = "none";
            } else {
                // V DEV zobrazíme, pokud je potřeba
                panel.style.display = "block";
            }
        }

        // Zobrazení konfigurace API URL
        function showApiUrlConfig() {
            const configPanel = document.getElementById('dev-api-url-panel');
            const input = document.getElementById('apiUrlInput');
            const currentUrl = document.getElementById('currentApiUrl');

            if (configPanel) {
                configPanel.classList.remove('hidden');
                const savedUrl = (typeof SpravaVozidelStorage !== 'undefined')
                    ? SpravaVozidelStorage.getLocal('apiUrl')
                    : localStorage.getItem('toozhub_api_url');
                if (savedUrl) {
                    input.value = savedUrl;
                    currentUrl.textContent = `Aktuální URL: ${savedUrl}`;
                } else {
                    currentUrl.textContent = 'API URL není nastavena (použije se výchozí: http://127.0.0.1:8001)';
                }
            }
        }

        // Skrytí konfigurace API URL
        function hideApiUrlConfig() {
            const configPanel = document.getElementById('dev-api-url-panel');
            if (configPanel) {
                configPanel.classList.add('hidden');
            }
        }

        // Uložení API URL
        function saveApiUrl() {
            const input = document.getElementById('apiUrlInput');
            let url = input.value.trim();

            if (!url) {
                // Pokud je prázdné, smazat uloženou URL (použije se výchozí)
                if (typeof SpravaVozidelStorage !== 'undefined') {
                    SpravaVozidelStorage.removeLocal('apiUrl');
                } else {
                    localStorage.removeItem('toozhub_api_url');
                    localStorage.removeItem('sprava_vozidel_api_url');
                }
                API_URL = getApiBaseUrl();
                showAlert('API URL byla vymazána. Použije se výchozí URL.', 'success');
                setTimeout(() => {
                    checkServerStatus();
                    location.reload(); // Reload pro aktualizaci
                }, 500);
                return;
            }

            // Automaticky přidat https:// pokud chybí (pokud není localhost)
            if (!url.startsWith('http://') && !url.startsWith('https://')) {
                if (url.includes('localhost') || url.includes('127.0.0.1')) {
                    url = 'http://' + url;
                } else {
                    url = 'https://' + url;
                }
            }

            // Validace URL
            try {
                new URL(url);
            } catch (e) {
                showAlert('Neplatná URL. Zadejte prosím platnou URL (např. http://127.0.0.1:8001)', 'error');
                return;
            }

            // Uložit do localStorage (kanonický klíč; legacy se odstraní)
            if (typeof SpravaVozidelStorage !== 'undefined') {
                SpravaVozidelStorage.setLocal('apiUrl', url);
            } else {
                localStorage.setItem('sprava_vozidel_api_url', url);
                localStorage.removeItem('toozhub_api_url');
            }
            API_URL = url;

            // Aktualizovat input pole
            input.value = url;

            // Aktualizovat zobrazení
            const currentUrl = document.getElementById('currentApiUrl');
            currentUrl.textContent = `Aktuální URL: ${url}`;

            showAlert('API URL byla uložena. Kontroluji připojení...', 'success');

            // Zkontrolovat stav serveru a reload pro aktualizaci
            setTimeout(() => {
                checkServerStatus();
                location.reload(); // Reload pro aktualizaci všech API volání
            }, 500);
        }

        function getAuthStorageItem(key) {
            if (key === AUTH_STORAGE_KEYS.token) return AdminBrowserSession.token();
            if (key === AUTH_STORAGE_KEYS.user) return currentUser ? JSON.stringify(currentUser) : null;
            return null;
        }

        function clearAuthStorage() { AdminBrowserSession.end('expired'); }

        function markAuthSessionEstablished() {
            authSessionEstablishedAt = Date.now();
        }

        function clearAuthSessionEstablishedMark() {
            authSessionEstablishedAt = 0;
        }

        function isWithinAuthAutoLogoutGraceWindow() {
            return authSessionEstablishedAt > 0 && (Date.now() - authSessionEstablishedAt) < AUTH_AUTO_LOGOUT_GRACE_MS;
        }

        function saveAuthSession(token, user, persistent = false) {
            AdminBrowserSession.set(token, user?.role);
            accessToken = token; currentUser = user;
            markAuthSessionEstablished();
        }

        function persistCurrentUserToActiveStorage(user) {
            // Personal profiles stay in memory and are always reloaded from the server.
            if (user && typeof user === 'object') currentUser = user;
        }

        async function ensureCurrentUserProfileLoaded(options = {}) {
            const force = !!(options && options.force);
            if (!accessToken) return false;
            if (!force && currentUser && currentUser.email) return true;
            try {
                const me = await apiCall('/user/me', 'GET');
                if (me && typeof me === 'object' && me.email) {
                    currentUser = me;
                    persistCurrentUserToActiveStorage(me);
                    return true;
                }
            } catch (error) {
                console.warn("[AUTH] Nelze načíst /user/me po loginu:");
            }
            return !!(currentUser && currentUser.email);
        }

        function getStaySignedInPreference() { return false; }

        function updateRememberedLoginPreferences() {
            const emailInput = document.getElementById('loginEmail');
            const rememberEmailCheckbox = document.getElementById('rememberLoginEmailCheckbox');
            const staySignedInCheckbox = document.getElementById('staySignedInCheckbox');

            if (rememberEmailCheckbox) {
                const shouldRememberEmail = !!rememberEmailCheckbox.checked;
                localStorage.setItem(AUTH_STORAGE_KEYS.rememberedEmailEnabled, shouldRememberEmail ? 'true' : 'false');
                if (shouldRememberEmail && emailInput && emailInput.value.trim()) {
                    localStorage.setItem(AUTH_STORAGE_KEYS.rememberedEmail, emailInput.value.trim());
                } else if (!shouldRememberEmail) {
                    localStorage.removeItem(AUTH_STORAGE_KEYS.rememberedEmail);
                }
            }

            if (staySignedInCheckbox) {
                localStorage.setItem(
                    AUTH_STORAGE_KEYS.staySignedIn,
                    staySignedInCheckbox.checked ? 'true' : 'false'
                );
            }
        }

        function initRememberedLoginPreferences() {
            const emailInput = document.getElementById('loginEmail');
            const rememberEmailCheckbox = document.getElementById('rememberLoginEmailCheckbox');
            const staySignedInCheckbox = document.getElementById('staySignedInCheckbox');
            const rememberedEmail = localStorage.getItem(AUTH_STORAGE_KEYS.rememberedEmail) || '';
            const rememberedEmailEnabled =
                String(localStorage.getItem(AUTH_STORAGE_KEYS.rememberedEmailEnabled) || '').toLowerCase() === 'true'
                || !!rememberedEmail;

            if (rememberEmailCheckbox) {
                rememberEmailCheckbox.checked = rememberedEmailEnabled;
            }
            if (emailInput && rememberedEmailEnabled && rememberedEmail && !emailInput.value.trim()) {
                emailInput.value = rememberedEmail;
            }
            if (staySignedInCheckbox) {
                staySignedInCheckbox.checked = getStaySignedInPreference();
            }
        }

        function resetTwoFactorChallengeState(options = {}) {
            const keepError = Boolean(options && options.keepError);
            pendingTwoFactorChallenge = null;
            pendingTwoFactorExpiresAt = 0;

            const panel = document.getElementById('loginTwoFactorPanel');
            if (panel) {
                panel.classList.add('hidden');
            }

            const codeInput = document.getElementById('loginTwoFactorCode');
            if (codeInput) {
                codeInput.value = '';
            }

            const loginSubmitBtn = document.getElementById('loginSubmitBtn');
            if (loginSubmitBtn) {
                loginSubmitBtn.disabled = false;
            }

            const registerBtn = document.getElementById('loginShowRegisterBtn');
            if (registerBtn) {
                registerBtn.disabled = false;
            }

            if (!keepError) {
                clearFormError('loginErrorContainer');
            }
        }

        function openTwoFactorChallenge(challengeToken, expiresInSec) {
            pendingTwoFactorChallenge = String(challengeToken || '');
            pendingTwoFactorExpiresAt = Date.now() + (Number(expiresInSec || 0) * 1000);

            const panel = document.getElementById('loginTwoFactorPanel');
            if (panel) {
                panel.classList.remove('hidden');
            }

            const loginSubmitBtn = document.getElementById('loginSubmitBtn');
            if (loginSubmitBtn) {
                loginSubmitBtn.disabled = true;
            }

            const registerBtn = document.getElementById('loginShowRegisterBtn');
            if (registerBtn) {
                registerBtn.disabled = true;
            }

            setTimeout(() => {
                const codeInput = document.getElementById('loginTwoFactorCode');
                if (codeInput) codeInput.focus();
            }, 80);
        }

        function getSelectedLoginMode() {
            return loginMode === 'service' ? 'service' : 'user';
        }

        function getLoginModeHintText(mode) {
            if (mode === 'service') {
                return 'Servisní účet pro práci s klienty a termíny. Každý účet má jednu roli (uživatel nebo servis).';
            }
            return 'Běžný zákaznický účet pro správu vlastních vozidel. Pro servis použijte samostatný servisní účet.';
        }

        function setLoginMode(mode = 'user') {
            const normalizedMode = String(mode || 'user').toLowerCase() === 'service' ? 'service' : 'user';
            loginMode = normalizedMode;

            try {
                localStorage.setItem(AUTH_STORAGE_KEYS.loginMode, normalizedMode);
            } catch (e) {
                // ignore localStorage errors
            }

            const userBtn = document.getElementById('loginModeUserBtn');
            const serviceBtn = document.getElementById('loginModeServiceBtn');
            userBtn?.classList.toggle('active', normalizedMode === 'user');
            serviceBtn?.classList.toggle('active', normalizedMode === 'service');

            const titleEl = document.getElementById('loginTitle');
            if (titleEl) {
                titleEl.textContent = normalizedMode === 'service' ? 'Přihlášení servisu' : 'Přihlášení';
            }

            const submitBtn = document.getElementById('loginSubmitBtn');
            if (submitBtn) {
                submitBtn.textContent = normalizedMode === 'service' ? 'Přihlásit servis' : 'Přihlásit se';
            }

            const hintEl = document.getElementById('loginModeHint');
            if (hintEl) {
                hintEl.textContent = getLoginModeHintText(normalizedMode);
            }
        }

        function getSelectedRegistrationMode() {
            return registrationMode === 'service' ? 'service' : 'user';
        }

        function getRegistrationModeHintText(mode) {
            if (mode === 'service') {
                return 'Servisní účet podléhá schválení developerem. Před aktivací proběhne kontrola údajů a účelu registrace.';
            }
            return 'Registrace uživatele s potvrzením e-mailové adresy.';
        }

        function setRegistrationMode(mode = 'user') {
            const normalizedMode = String(mode || 'user').toLowerCase() === 'service' ? 'service' : 'user';
            registrationMode = normalizedMode;

            const userBtn = document.getElementById('registerModeUserBtn');
            const serviceBtn = document.getElementById('registerModeServiceBtn');
            userBtn?.classList.toggle('active', normalizedMode === 'user');
            serviceBtn?.classList.toggle('active', normalizedMode === 'service');

            const hintEl = document.getElementById('registerModeHint');
            if (hintEl) {
                hintEl.textContent = getRegistrationModeHintText(normalizedMode);
            }

            const icoLabel = document.getElementById('regIcoLabel');
            if (icoLabel) {
                icoLabel.textContent = normalizedMode === 'service'
                    ? 'IČO servisu *:'
                    : 'IČO (volitelně):';
            }

            const nameLabel = document.getElementById('regNameLabel');
            if (nameLabel) {
                nameLabel.textContent = normalizedMode === 'service'
                    ? 'Název servisu *:'
                    : 'Jméno / název:';
            }

            const icoInput = document.getElementById('regIco');
            if (icoInput) {
                icoInput.required = normalizedMode === 'service';
            }

            const extraFields = document.getElementById('serviceRegistrationExtraFields');
            if (extraFields) {
                extraFields.classList.toggle('hidden', normalizedMode !== 'service');
            }

            const registerBtn = document.getElementById('registerSubmitBtn');
            if (registerBtn) {
                registerBtn.textContent = normalizedMode === 'service'
                    ? 'Odeslat žádost o servisní účet'
                    : 'Registrovat';
            }
        }

        function initLoginModeFromState() {
            const location = getLocation();
            const params = new URLSearchParams(location.search || '');
            const modeFromUrl = String(params.get('mode') || params.get('login') || '').toLowerCase();
            if (modeFromUrl === 'service' || modeFromUrl === 'user') {
                setLoginMode(modeFromUrl);
                return;
            }

            const savedMode = String(localStorage.getItem(AUTH_STORAGE_KEYS.loginMode) || '').toLowerCase();
            if (savedMode === 'service' || savedMode === 'user') {
                setLoginMode(savedMode);
                return;
            }

            setLoginMode('user');
        }

        function clearLocalAuthSession() {
            clearAuthStorage();
            currentUser = null;
            accessToken = null;
            clearAuthSessionEstablishedMark();
            resetTwoFactorChallengeState({ keepError: true });
        }

        // Přihlášení - Cloudflare-safe verze
        async function handleLogin(event) {
            event?.preventDefault();
            if (!window.CustomerWeb) { AdminBrowserSession.end('verification'); return; }
            const button = document.querySelector('#loginForm button[type="submit"]');
            if (button) button.disabled = true;
            try {
                const response = await apiCall('/user/login', 'POST', {
                    email: document.getElementById('loginEmail').value.trim(),
                    password: document.getElementById('loginPassword').value
                });
                if (response.two_factor_required) {
                    openTwoFactorChallenge(response.challenge_token, response.challenge_expires_in || 300);
                    return;
                }
                saveAuthSession(response.access_token, response.user);
                updateRememberedLoginPreferences();
                location.reload();
            } catch (error) { showFormError('loginErrorContainer', error.message); }
            finally { if (button) button.disabled = false; }
        }

        // Zajistit globální dostupnost handleLogin
        window.handleLogin = handleLogin;

        async function handleLoginTwoFactor() {
            const challengeToken = String(pendingTwoFactorChallenge || '');
            if (!challengeToken) {
                showFormError('loginErrorContainer', 'Nejprve se přihlaste emailem a heslem.');
                return;
            }
            if (pendingTwoFactorExpiresAt && Date.now() > pendingTwoFactorExpiresAt) {
                resetTwoFactorChallengeState({ keepError: true });
                showFormError('loginErrorContainer', '2FA výzva vypršela. Přihlaste se znovu.');
                return;
            }

            const codeInput = document.getElementById('loginTwoFactorCode');
            const code = codeInput ? String(codeInput.value || '').trim() : '';
            if (!/^\d{6}$/.test(code)) {
                showFormError('loginErrorContainer', 'Zadejte platný 6místný ověřovací kód.');
                return;
            }

            const verifyBtn = document.getElementById('loginTwoFactorVerifyBtn');
            const originalLabel = verifyBtn ? verifyBtn.textContent : 'Ověřit kód';
            if (verifyBtn) {
                verifyBtn.disabled = true;
                verifyBtn.textContent = 'Ověřuji...';
            }

            try {
                const response = await apiCall('/user/login/2fa', 'POST', {
                    challenge_token: challengeToken,
                    code
                });
                if (!response || !response.access_token || !response.user) {
                    throw new Error('2FA ověření vrátilo neúplná data.');
                }

                const staySignedIn = document.getElementById('staySignedInCheckbox')?.checked === true;
                saveAuthSession(response.access_token, response.user, staySignedIn);
                if (window.CustomerWeb) { location.reload(); return; }
                if ((!currentUser || !currentUser.email) && accessToken) {
                    await ensureCurrentUserProfileLoaded({ force: true });
                }
                updateRememberedLoginPreferences();
                resetTwoFactorChallengeState({ keepError: true });

                if (typeof showDashboard === 'function') {
                    showDashboard();
                }

                if (!isAuthenticated()) {
                    throw new Error('2FA ověření proběhlo, ale relace nebyla dokončena. Obnovte stránku a zkuste to znovu.');
                }

                const selectedLoginMode = getSelectedLoginMode();
                const loggedInRole = String(currentUser?.role || 'user').toLowerCase();
                if (typeof switchTab === 'function') {
                    if (loggedInRole === 'service' || (selectedLoginMode === 'service' && (loggedInRole === 'admin' || loggedInRole === 'developer_admin'))) {
                        setTimeout(() => switchTab('serviceWorkspace'), 120);
                    }
                }

                if (typeof loadLicenseStatus === 'function') {
                    await loadLicenseStatus();
                }
                showAlert('Přihlášení úspěšné (2FA).', 'success');
            } catch (error) {
                const errorMessage = error && error.message ? error.message : 'Nepodařilo se ověřit 2FA kód';
                showFormError('loginErrorContainer', errorMessage);
            } finally {
                if (verifyBtn) {
                    verifyBtn.disabled = false;
                    verifyBtn.textContent = originalLabel;
                }
            }
        }

        function cancelLoginTwoFactor() {
            resetTwoFactorChallengeState({ keepError: true });
            showAlert('2FA ověření bylo zrušeno. Můžete se přihlásit znovu.', 'info');
        }

        window.handleLoginTwoFactor = handleLoginTwoFactor;
        window.cancelLoginTwoFactor = cancelLoginTwoFactor;

        // Zobrazení formuláře pro zapomenuté heslo
        function showForgotPasswordForm() {
            const form = document.getElementById('forgotPasswordForm');
            const resetContainer = document.getElementById('resetPasswordContainer');
            if (form) {
                form.classList.remove('hidden');
                form.style.display = 'block';
            }
            if (resetContainer) {
                resetContainer.innerHTML = '';
            }
            // Focus na input
            setTimeout(() => {
                const emailInput = document.getElementById('forgotPasswordEmail');
                if (emailInput) {
                    emailInput.focus();
                    emailInput.select();
                }
            }, 100);
        }

        // Skrytí formuláře pro zapomenuté heslo
        function hideForgotPasswordForm() {
            const form = document.getElementById('forgotPasswordForm');
            const resetContainer = document.getElementById('resetPasswordContainer');
            if (form) {
                form.classList.add('hidden');
                form.style.display = 'none';
            }
            if (resetContainer) {
                resetContainer.innerHTML = '';
            }
            // Vyčistit input
            const emailInput = document.getElementById('forgotPasswordEmail');
            if (emailInput) {
                emailInput.value = '';
            }
        }

        // Zapomenuté heslo - Cloudflare-safe verze
        async function handleForgotPassword() {
            // Vyčistit předchozí zprávy
            const resetContainer = document.getElementById('resetPasswordContainer');
            const emailInput = document.getElementById('forgotPasswordEmail');

            if (resetContainer) {
                resetContainer.innerHTML = '';
            }

            // Získat email z formuláře
            const email = emailInput ? emailInput.value.trim() : '';

            if (!email) {
                showFormError('resetPasswordContainer', 'Zadejte prosím email');
                if (emailInput) {
                    emailInput.focus();
                }
                return;
            }

            // Validace emailu
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (!emailRegex.test(email)) {
                showFormError('resetPasswordContainer', 'Neplatný formát emailu');
                if (emailInput) {
                    emailInput.focus();
                }
                return;
            }

            // Zobrazit načítání
            if (resetContainer) {
                resetContainer.innerHTML = '<div class="alert alert-info">Odesílám reset odkaz na email...</div>';
            }

            // Deaktivovat tlačítko během odesílání
            const form = emailInput?.closest('#forgotPasswordForm');
            const submitBtn = form?.querySelector('button[type="submit"]');
            const originalBtnText = submitBtn?.textContent;
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = 'Odesílám...';
            }

            try {
                // Získat API URL
                const apiUrl = getApiBaseUrl();
                if (!apiUrl) {
                    throw new Error('API URL není nastavena');
                }

                // Cloudflare-safe fetch request
                const response = await fetch(`${apiUrl}/user/forgot-password`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'Accept-Language': 'cs-CZ,cs;q=0.9,en;q=0.8'
                    },
                    credentials: 'include',
                    body: JSON.stringify({ email })
                });

                // Kontrola Content-Type hlavičky
                const contentType = response.headers.get('content-type');
                const isJson = contentType && contentType.includes('application/json');

                // Ošetření Cloudflare challenge (403 s HTML)
                if (response.status === 403 && !isJson) {
                    throw new Error('Bezpečnostní ochrana (Cloudflare) dočasně zablokovala požadavek. Obnovte stránku (F5) a zkuste znovu.');
                }

                // Kontrola, zda je odpověď OK
                if (!response.ok) {
                    let errorMessage = 'Nepodařilo se odeslat reset odkaz';
                    try {
                        if (isJson) {
                            const error = await response.json();
                            errorMessage = error.detail || error.message || errorMessage;
                        } else {
                            errorMessage = `HTTP ${response.status}: ${response.statusText}`;
                        }
                    } catch (e) {
                        errorMessage = `HTTP ${response.status}: ${response.statusText}`;
                    }
                    throw new Error(errorMessage);
                }

                // Parsování JSON odpovědi
                if (!isJson) {
                    throw new Error('Server vrátil neočekávaný formát odpovědi');
                }

                const data = await response.json();

                // Zkontrolovat, zda email byl odeslán
                if (data.email_sent) {
                    // Email byl odeslán
                    if (resetContainer) {
                        resetContainer.innerHTML = `
                            <div class="alert alert-success" style="margin-top: 15px;">
                                <strong>✓ Reset odkaz byl odeslán</strong><br><br>
                                Na email <strong>${escapeHtml(email)}</strong> byl odeslán odkaz pro obnovení hesla.<br>
                                Zkontrolujte prosím svou emailovou schránku (i složku spam).<br><br>
                                <small>Odkaz je platný 24 hodin.</small>
                            </div>
                        `;
                    }
                    // Skrýt formulář po úspěchu
                    hideForgotPasswordForm();
                } else if (data.reset_url) {
                    // Email není nakonfigurován nebo chyba, zobrazit reset URL
                    const resetUrl = data.reset_url;
                    if (resetContainer) {
                        resetContainer.innerHTML = `
                            <div class="alert alert-warning" style="margin-top: 15px; background: rgba(251, 191, 36, 0.15); color: #f59e0b; border: 2px solid rgba(251, 191, 36, 0.5);">
                                <strong>⚠️ Email není nakonfigurován</strong><br><br>
                                Reset odkaz pro testování:<br>
                                <a href="${escapeHtml(safeLegacyURL(resetUrl))}" target="_blank" rel="noopener noreferrer" style="color: #f59e0b; word-break: break-all; text-decoration: underline; font-weight: 600;">${escapeHtml(resetUrl)}</a><br><br>
                                <small>Zkopírujte odkaz a otevřete v prohlížeči, nebo klikněte na odkaz výše.</small>
                                ${data.error_detail ? `<br><br><small style="color: #9ca3af;">Detail: ${escapeHtml(data.error_detail)}</small>` : ''}
                            </div>
                        `;
                    }

                } else if (data.error) {
                    // Chyba při odesílání
                    let errorMsg = data.message || 'Email nebyl odeslán. Zkontrolujte konfiguraci SMTP v logu serveru.';

                    // Pokud je k dispozici reset URL, zobrazit ho také
                    if (data.reset_url) {
                        const resetUrl = data.reset_url;
                        if (resetContainer) {
                            resetContainer.innerHTML = `
                                <div class="alert alert-error" style="margin-top: 15px;">
                                    <strong>❌ Chyba při odesílání emailu:</strong><br>
                                    ${escapeHtml(errorMsg).replace(/\n/g, '<br>')}
                                    <br><br>
                                    <strong>Reset odkaz pro testování:</strong><br>
                                    <a href="${escapeHtml(safeLegacyURL(resetUrl))}" target="_blank" rel="noopener noreferrer" style="color: #ef4444; word-break: break-all; text-decoration: underline; font-weight: 600;">${escapeHtml(resetUrl)}</a>
                                    <br><br>
                                    <small>Zkopírujte odkaz a otevřete v prohlížeči, nebo klikněte na odkaz výše.</small>
                                    ${data.error_detail ? `<br><br><small style="color: #9ca3af;">Detail: ${escapeHtml(data.error_detail)}</small>` : ''}
                                </div>
                            `;
                        }
                    } else {
                        showFormError('resetPasswordContainer', errorMsg + (data.error_detail ? '\n\nDetail: ' + data.error_detail : ''));
                    }
                    console.error("[RESET] Email error:");
                    if (data.error_detail) {
                        console.error("[RESET] Error detail:");
                    }
                } else {
                    // Obecná zpráva (bezpečnostní - neodhalit, zda email existuje)
                    if (resetContainer) {
                        resetContainer.innerHTML = `
                            <div class="alert alert-info" style="margin-top: 15px;">
                                <strong>ℹ️ Požadavek zpracován</strong><br><br>
                                Pokud email existuje, byl odeslán reset odkaz.<br>
                                Zkontrolujte prosím svou emailovou schránku (i složku spam).<br><br>
                                <small>Odkaz je platný 24 hodin.</small>
                            </div>
                        `;
                    }
                    // Skrýt formulář po úspěchu
                    hideForgotPasswordForm();
                }
            } catch (error) {
                console.error("[RESET] Error:");
                const errorMessage = error.message || 'Neznámá chyba';
                showFormError('resetPasswordContainer', 'Nepodařilo se odeslat reset odkaz: ' + errorMessage);
            } finally {
                // Obnovit tlačítko
                if (submitBtn) {
                    submitBtn.disabled = false;
                    if (originalBtnText) {
                        submitBtn.textContent = originalBtnText;
                    }
                }
            }
        }

        // Zajistit globální dostupnost funkcí
        window.handleForgotPassword = handleForgotPassword;
        window.showForgotPasswordForm = showForgotPasswordForm;
        window.hideForgotPasswordForm = hideForgotPasswordForm;

        // ARES lookup s AbortController pro zrušení předchozích requestů
        let aresAbortController = null;
        let aresDebounceTimeout = null;
        let profileAresAbortController = null;
        let profileAresDebounceTimeout = null;

        // Zobrazení chyby pod IČO inputem
        function showAresError(message) {
            const icoInput = document.getElementById('regIco');
            if (!icoInput) return;

            // Odstranit předchozí chybu
            const existingError = icoInput.parentElement.querySelector('.ares-error');
            if (existingError) {
                existingError.remove();
            }

            // Přidat novou chybu
            const errorDiv = document.createElement('div');
            errorDiv.className = 'ares-error';
            errorDiv.style.color = '#dc3545';
            errorDiv.style.fontSize = '0.875rem';
            errorDiv.style.marginTop = '0.25rem';
            errorDiv.textContent = message;
            icoInput.parentElement.appendChild(errorDiv);

            // Automaticky odstranit po 5 sekundách
            setTimeout(() => {
                if (errorDiv.parentElement) {
                    errorDiv.remove();
                }
            }, 5000);
        }

        function clearProfileAresError() {
            const icoInput = document.getElementById('profileIco');
            if (!icoInput) {
                return;
            }
            const container = icoInput.closest('.form-group') || icoInput.parentElement;
            if (!container) {
                return;
            }
            const existingError = container.querySelector('.profile-ares-error');
            if (existingError) {
                existingError.remove();
            }
        }

        function showProfileAresError(message) {
            const icoInput = document.getElementById('profileIco');
            if (!icoInput) {
                return;
            }
            const container = icoInput.closest('.form-group') || icoInput.parentElement;
            if (!container) {
                return;
            }

            clearProfileAresError();

            const errorDiv = document.createElement('div');
            errorDiv.className = 'ares-error profile-ares-error';
            errorDiv.style.color = '#dc3545';
            errorDiv.style.fontSize = '0.875rem';
            errorDiv.style.marginTop = '0.25rem';
            errorDiv.textContent = message;
            container.appendChild(errorDiv);

            setTimeout(() => {
                if (errorDiv.parentElement) {
                    errorDiv.remove();
                }
            }, 7000);
        }

        function formatZipForDisplay(zipValue) {
            if (!zipValue) {
                return '';
            }
            const zipDigits = String(zipValue).replace(/\s+/g, '');
            if (/^\d{5}$/.test(zipDigits)) {
                return `${zipDigits.slice(0, 3)} ${zipDigits.slice(3)}`;
            }
            return String(zipValue);
        }

        function applyProfileAresData(payload) {
            const data = normalizeAresData(payload);
            const fieldMap = [
                ['profileName', data.company_name],
                ['profileDic', data.dic],
                ['profileStreet', data.street],
                ['profileStreetNumber', data.house_number],
                ['profileCity', data.city],
                ['profileZip', formatZipForDisplay(data.zip)]
            ];

            fieldMap.forEach(([fieldId, value]) => {
                const input = document.getElementById(fieldId);
                if (!input || !value) {
                    return;
                }
                input.value = value;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
            });
        }

        async function fetchAresDataNoForcedLogout(ico, abortSignal = null, opts = {}) {
            const shouldLogoutOnAuthError = !!(opts && opts.logoutOnAuthError);
            API_URL = getApiBaseUrl();
            if (!API_URL) {
                throw new Error('API URL není nastavena. Kontaktujte administrátora.');
            }

            const headers = {
                'Accept': 'application/json',
                'Accept-Language': 'cs-CZ,cs;q=0.9,en;q=0.8'
            };

            if (typeof window !== 'undefined' && window.location) {
                headers['Referer'] = window.location.origin + window.location.pathname;
            }

            if (accessToken) {
                headers['Authorization'] = `Bearer ${accessToken}`;
            }
            appendClientGeoHeaders(headers);

            const options = {
                method: 'GET',
                headers,
                credentials: 'include',
                mode: 'cors',
                cache: 'no-cache'
            };
            if (abortSignal) {
                options.signal = abortSignal;
            }

            let response;
            try {
                response = await AdminBrowserSession.request(`${API_URL}/api/v1/ares/${encodeURIComponent(ico)}`, options);
            } catch (error) {
                if (error.name === 'AbortError') {
                    throw error;
                }
                throw new Error('Nepodařilo se připojit k serveru. Zkontrolujte připojení a zkuste to znovu.');
            }

            const contentType = response.headers.get('content-type');
            const isJson = contentType && contentType.includes('application/json');

            if (response.ok) {
                if (!isJson) {
                    throw new Error('Server vrátil neočekávaný formát odpovědi');
                }
                return await response.json();
            }

            let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
            try {
                if (isJson) {
                    const errorData = await response.json();
                    if (errorData?.detail) {
                        if (Array.isArray(errorData.detail)) {
                            errorMessage = errorData.detail.map(e => `${e.loc?.join('.')}: ${e.msg}`).join(', ');
                        } else {
                            errorMessage = errorData.detail;
                        }
                    } else if (errorData?.message) {
                        errorMessage = errorData.message;
                    }
                } else {
                    const text = await response.text();
                    if (text && text.includes('Cloudflare')) {
                        errorMessage = 'Cloudflare blokuje požadavek. Zkuste obnovit stránku (F5) a zkusit znovu.';
                    }
                }
            } catch (parseError) {
                // Ignorovat chyby při parsování odpovědi
            }

            if (response.status === 401 && shouldLogoutOnAuthError) {
                handleLogout();
                throw new Error(errorMessage || 'Vaše relace vypršela. Prosím přihlaste se znovu.');
            }

            throw new Error(errorMessage);
        }

        async function loadProfileAresData(ico) {
            if (window.__licenseFlags && window.__licenseFlags.aresEnabled === false) {
                showProfileAresError('ARES lookup je dostupný od plánu BASIC.');
                return;
            }
            if (!ico) {
                return;
            }

            const icoClean = ico.trim().replace(/[^\d]/g, '');
            if (icoClean.length !== 8 || !/^\d+$/.test(icoClean)) {
                return;
            }

            if (profileAresAbortController) {
                profileAresAbortController.abort();
            }
            profileAresAbortController = new AbortController();

            clearProfileAresError();

            try {
                const data = await fetchAresDataNoForcedLogout(
                    icoClean,
                    profileAresAbortController.signal,
                    { logoutOnAuthError: true }
                );
                applyProfileAresData(data);
            } catch (error) {
                if (error.name === 'AbortError') {
                    return;
                }

                let errorMessage = 'Nepodařilo se načíst data z ARES';
                if (error.message) {
                    if (error.message.includes('404') || error.message.includes('nenalezeno')) {
                        errorMessage = 'IČO nebylo nalezeno v ARES. Zkontrolujte správnost IČO.';
                    } else if (error.message.includes('503') || error.message.includes('unavailable')) {
                        errorMessage = 'ARES je dočasně nedostupný. Zkuste to prosím později.';
                    } else if (error.message.includes('422') || error.message.includes('IČO musí')) {
                        errorMessage = 'Neplatné IČO - musí obsahovat přesně 8 číslic.';
                    } else {
                        errorMessage = error.message;
                    }
                }

                showProfileAresError(errorMessage);
            }
        }

        async function handleProfileAresLookup() {
            const icoInput = document.getElementById('profileIco');
            const lookupButton = document.getElementById('profileAresLookupBtn');

            if (!icoInput) {
                return;
            }

            const icoDigits = (icoInput.value || '').replace(/[^\d]/g, '').slice(0, 8);
            if (icoInput.value !== icoDigits) {
                icoInput.value = icoDigits;
            }

            clearProfileAresError();

            if (!icoDigits) {
                showProfileAresError('Zadejte IČO pro načtení údajů z ARES.');
                icoInput.focus();
                return;
            }

            if (!/^\d{8}$/.test(icoDigits)) {
                showProfileAresError('IČO musí obsahovat přesně 8 číslic.');
                icoInput.focus();
                return;
            }

            const originalText = lookupButton ? lookupButton.textContent : '';
            if (lookupButton) {
                lookupButton.disabled = true;
                lookupButton.textContent = 'Načítám data z ARES...';
            }

            try {
                await loadProfileAresData(icoDigits);
            } finally {
                if (lookupButton) {
                    lookupButton.disabled = false;
                    lookupButton.textContent = originalText || '🔎 Načíst údaje z ARES';
                }
            }
        }

        function initProfileAresAutofill() {
            const icoInput = document.getElementById('profileIco');
            if (!icoInput) {
                return;
            }

            if (icoInput.dataset.profileAresListenerAttached === 'true') {
                return;
            }
            icoInput.dataset.profileAresListenerAttached = 'true';

            icoInput.addEventListener('input', (e) => {
                const rawValue = e.target.value || '';
                const icoDigits = rawValue.replace(/[^\d]/g, '').slice(0, 8);
                if (rawValue !== icoDigits) {
                    e.target.value = icoDigits;
                }

                if (profileAresDebounceTimeout) {
                    clearTimeout(profileAresDebounceTimeout);
                    profileAresDebounceTimeout = null;
                }

                clearProfileAresError();

                if (icoDigits.length === 8) {
                    profileAresDebounceTimeout = setTimeout(() => {
                        loadProfileAresData(icoDigits);
                        profileAresDebounceTimeout = null;
                    }, 500);
                }
            });
        }

        // Načtení dat z ARES (nová verze s GET endpointem)
        async function loadAresData(ico) {
            if (window.__licenseFlags && window.__licenseFlags.aresEnabled === false) {
                showAlert('ARES lookup je dostupný od plánu BASIC.', 'info');
                return;
            }
            if (!ico) {
                return;
            }

            const icoClean = ico.trim().replace(/[\s-]/g, '');

            // Validace IČO
            if (icoClean.length !== 8 || !/^\d+$/.test(icoClean)) {
                return; // Nezobrazovat chybu, jen neprovádět lookup
            }

            // Zrušit předchozí request
            if (aresAbortController) {
                aresAbortController.abort();
            }
            aresAbortController = new AbortController();

            // Odstranit předchozí chybu
            const icoInput = document.getElementById('regIco');
            if (icoInput) {
                const existingError = icoInput.parentElement.querySelector('.ares-error');
                if (existingError) {
                    existingError.remove();
                }
            }

            try {
                // Volat ARES bez vynuceného odhlášení (registrace běží i bez autentizace)
                const data = await fetchAresDataNoForcedLogout(
                    icoClean,
                    aresAbortController.signal,
                    { logoutOnAuthError: false }
                );


                // Nový endpoint vrací přímo AresLookupResponse: {ico, company_name, dic, street, house_number, city, zip, source}

                // Vyplnění polí podle nového formátu
                if (data.company_name) {
                    document.getElementById('regName').value = data.company_name;
                }
                if (data.dic) {
                    document.getElementById('regDic').value = data.dic;
                }
                if (data.street) {
                    document.getElementById('regStreet').value = data.street;
                }
                if (data.house_number) {
                    document.getElementById('regStreetNumber').value = data.house_number;
                }
                if (data.city) {
                    document.getElementById('regCity').value = data.city;
                }
                if (data.zip) {
                    document.getElementById('regZip').value = data.zip;
                }

                // Zobrazit pole s ARES daty po úspěšném načtení
                const aresFields = document.getElementById('aresDataFields');
                if (aresFields) {
                    aresFields.style.display = 'block';
                }

                showAlert('Data z ARES byla úspěšně načtena', 'success');
            } catch (error) {
                console.error("[ARES] Error:");
                let errorMessage = 'Nepodařilo se načíst data z ARES';

                if (error.name === 'AbortError') {
                    // Request byl zrušen, neukazovat chybu
                    return;
                } else if (error.message) {
                    if (error.message.includes('404') || error.message.includes('nenalezeno')) {
                        errorMessage = 'IČO nebylo nalezeno v ARES. Zkontrolujte správnost IČO.';
                    } else if (error.message.includes('503') || error.message.includes('unavailable')) {
                        errorMessage = 'ARES nedostupný. Zkuste to prosím později.';
                    } else if (error.message.includes('422') || error.message.includes('Neplatné')) {
                        errorMessage = 'Neplatné IČO - musí obsahovat přesně 8 číslic.';
                    } else if (error.message.includes('Timeout') || error.message.includes('časový limit')) {
                        errorMessage = 'Timeout při načítání z ARES. Zkuste to prosím znovu.';
                    } else {
                        errorMessage = error.message;
                    }
                }

                showAresError(errorMessage);
            }
        }

        // Pomocná funkce: normalizace různých formátů ARES odpovědi
        function normalizeAresData(payload) {
            if (!payload || typeof payload !== 'object') {
                return {
                    ico: null,
                    company_name: '',
                    dic: '',
                    street: '',
                    house_number: '',
                    city: '',
                    zip: ''
                };
            }

            const sidlo = payload.sidlo || {};
            const houseParts = [];
            if (sidlo.cisloDomovni) houseParts.push(String(sidlo.cisloDomovni));
            if (sidlo.cisloOrientacni) houseParts.push(String(sidlo.cisloOrientacni));
            if (sidlo.cisloOrientacniPismeno) houseParts.push(String(sidlo.cisloOrientacniPismeno));

            return {
                ico: payload.ico || null,
                company_name: payload.company_name || payload.obchodniJmeno || payload.nazev || '',
                dic: payload.dic || '',
                street: payload.street || sidlo.nazevUlice || '',
                house_number: payload.house_number || (houseParts.length ? houseParts.join('/') : ''),
                city: payload.city || sidlo.nazevObce || '',
                zip: payload.zip || (sidlo.psc ? String(sidlo.psc) : '')
            };
        }

        // Registrace
        async function handleRegister() {
            // Vyčistit předchozí chyby
            const errorContainer = document.getElementById('registerErrorContainer');
            if (errorContainer) {
                errorContainer.innerHTML = '';
            }

            const selectedRegistrationMode = getSelectedRegistrationMode();
            const email = document.getElementById('regEmail').value.trim();
            const password = document.getElementById('regPassword').value;
            const passwordConfirm = document.getElementById('regPasswordConfirm').value;
            const ico = document.getElementById('regIco').value.trim();
            const name = document.getElementById('regName').value.trim();
            const dic = document.getElementById('regDic').value.trim();
            const street = document.getElementById('regStreet').value.trim();
            const streetNumber = document.getElementById('regStreetNumber').value.trim();
            const city = document.getElementById('regCity').value.trim();
            const zip = document.getElementById('regZip').value.trim();
            const phone = document.getElementById('regPhone').value.trim();
            const responsiblePerson = (document.getElementById('regResponsiblePerson')?.value || '').trim();
            const registrationPurpose = (document.getElementById('regRegistrationPurpose')?.value || '').trim();

            if (!email || !password) {
                showFormError('registerErrorContainer', 'Vyplňte prosím email a heslo');
                return;
            }

            // Validace emailu
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (!emailRegex.test(email)) {
                showFormError('registerErrorContainer', 'Neplatný formát emailu');
                return;
            }

            // Validace hesla
            if (password.length < 6) {
                showFormError('registerErrorContainer', 'Heslo musí mít alespoň 6 znaků');
                return;
            }

            if (password !== passwordConfirm) {
                showFormError('registerErrorContainer', 'Hesla se neshodují');
                return;
            }

            if (selectedRegistrationMode === 'service') {
                const icoDigits = ico.replace(/[^\d]/g, '');
                if (icoDigits.length !== 8) {
                    showFormError('registerErrorContainer', 'Pro registraci servisu je povinné platné IČO (8 číslic).');
                    return;
                }
                if (!name) {
                    showFormError('registerErrorContainer', 'Vyplňte název servisu.');
                    return;
                }
                if (!responsiblePerson) {
                    showFormError('registerErrorContainer', 'Vyplňte zodpovědnou osobu servisu.');
                    return;
                }
                if (!street || !city || !zip) {
                    showFormError('registerErrorContainer', 'U servisní registrace je povinná kompletní adresa (ulice, město, PSČ).');
                    return;
                }
                if (!phone) {
                    showFormError('registerErrorContainer', 'U servisní registrace je povinný telefon.');
                    return;
                }
                if (!registrationPurpose || registrationPurpose.length < 10) {
                    showFormError('registerErrorContainer', 'Uveďte účel registrace servisu (alespoň 10 znaků).');
                    return;
                }
            }

            try {
                if (selectedRegistrationMode === 'service') {
                    const icoDigits = ico.replace(/[^\d]/g, '');
                    showAlert('Odesílám žádost o servisní účet ke schválení...', 'info');
                    const response = await apiCall('/user/register/service-request', 'POST', {
                        email,
                        password,
                        ico: icoDigits,
                        service_name: name,
                        responsible_person: responsiblePerson,
                        phone,
                        street,
                        street_number: streetNumber || null,
                        city,
                        zip,
                        dic: dic || null,
                        registration_purpose: registrationPurpose
                    });

                    if (errorContainer) {
                        errorContainer.innerHTML = '';
                    }

                    setLoginMode('service');
                    showLogin();
                    const loginEmailInput = document.getElementById('loginEmail');
                    if (loginEmailInput) {
                        loginEmailInput.value = email;
                    }
                    showAlert(
                        response?.message || 'Žádost o servisní účet byla přijata. Po schválení developerem se budete moci přihlásit.',
                        'success'
                    );
                    return;
                }

                showAlert('Registruji uživatele...', 'info');
                const response = await apiCall('/user/register', 'POST', {
                    email,
                    password,
                    ico: ico || null,
                    name: name || null,
                    dic: dic || null,
                    street: street || null,
                    street_number: streetNumber || null,
                    city: city || null,
                    zip: zip || null,
                    phone: phone || null
                });
                if (window.CustomerWeb) { showLogin(); showAlert(response.email_sent ? 'Účet byl vytvořen. Potvrďte e-mail a přihlaste se.' : 'Účet byl vytvořen, potvrzovací e-mail se nepodařilo odeslat. Přihlaste se a požádejte o nový.', 'info'); return; }
                if (response.access_token) {
                    saveAuthSession(response.access_token, response.user, getStaySignedInPreference());
                } else {
                    if (window.CustomerWeb) { showLogin(); showAlert('Účet byl vytvořen. Potvrďte e-mail a přihlaste se.', 'success'); return; }
                    saveAuthSession(null, response, getStaySignedInPreference());
                }
                if (errorContainer) {
                    errorContainer.innerHTML = '';
                }
                let registrationAlertType = 'success';
                let registrationMessage = 'Registrace úspěšná!';
                if (response.email_sent === true || response.registration_email_status === 'sent') {
                    registrationMessage = 'Registrace úspěšná. Potvrzovací e-mail byl odeslán.';
                } else if (response.registration_email_status === 'failed') {
                    registrationAlertType = 'warning';
                    registrationMessage = 'Registrace úspěšná, ale potvrzovací e-mail se nepodařilo odeslat.';
                } else if (response.registration_email_status === 'not_configured') {
                    registrationAlertType = 'info';
                    registrationMessage = 'Registrace úspěšná. E-mailové potvrzení momentálně není aktivní.';
                }
                showDashboard();
                showAlert(registrationMessage, registrationAlertType);
            } catch (error) {
                console.error("Registration error:");
                const errorMessage = error.message || 'Neznámá chyba';
                // Zpracovat specifické chybové zprávy z API
                let displayMessage = 'Nepodařilo se zaregistrovat';
                if (errorMessage.includes('již existuje') || errorMessage.includes('already exists')) {
                    displayMessage = 'Uživatel s tímto emailem již existuje. Použijte jiný email nebo se přihlaste.';
                } else if (errorMessage.includes('IČO') && (errorMessage.includes('registrováno') || errorMessage.includes('registraci'))) {
                    displayMessage = 'Toto IČO už je v systému použité. Pro jedno IČO je povolen jen jeden servisní účet.';
                } else if (errorMessage.includes('čeká na schválení')) {
                    displayMessage = 'Pro tento email už čeká žádost o servisní účet na schválení developera.';
                } else if (errorMessage.includes('servisní registrace už byla schválena')) {
                    displayMessage = 'Servisní registrace byla už schválena. Přihlaste se jako Servis.';
                } else if (errorMessage.includes('Heslo musí mít')) {
                    displayMessage = errorMessage;
                } else {
                    displayMessage = `Nepodařilo se zaregistrovat: ${errorMessage}`;
                }
                showFormError('registerErrorContainer', displayMessage);
            }
        }

        // Odhlášení
        function handleLogout() { void AdminBrowserSession.logout(); }

        // Sledování aktivity pro automatické odhlášení
        let inactivityTimer = null;
        let inactivityTimeout = 15 * 60 * 1000; // 15 minut v milisekundách

        function resetInactivityTimer() {
            // Zrušit stávající timer
            if (inactivityTimer) {
                clearTimeout(inactivityTimer);
            }

            // Pokud je uživatel přihlášen, nastavit nový timer
            if (currentUser && accessToken) {
                inactivityTimer = setTimeout(() => {

                    showAlert('Byl jste automaticky odhlášen kvůli nečinnosti (15 minut).', 'warning');
                    handleLogout();
                }, inactivityTimeout);
            }
        }

        function stopInactivityTimer() {
            if (inactivityTimer) {
                clearTimeout(inactivityTimer);
                inactivityTimer = null;
            }
        }

        function setupActivityTracking() {
            // Eventy pro sledování aktivity
            const activityEvents = [
                'mousedown',
                'mousemove',
                'keypress',
                'scroll',
                'touchstart',
                'click'
            ];

            // Přidat event listenery pro všechny aktivitní eventy
            activityEvents.forEach(event => {
                document.addEventListener(event, resetInactivityTimer, true);
            });

            // Sledovat změny viditelnosti stránky (Page Visibility API)
            document.addEventListener('visibilitychange', () => {
                if (document.hidden) {
                    // Stránka je skrytá - pozastavit timer

                    stopInactivityTimer();
                } else {
                    // Stránka je viditelná - resetovat timer

                    resetInactivityTimer();
                }
            });


        }

        // Jednotná kontrola auth stavu
        function isAuthenticated() {
            return !!(AdminBrowserSession.token() && currentUser && currentUser.email);
        }

        function clearBodyScrollLocks() {
            const floatingModalRoot = document.getElementById(APP_FLOATING_MODAL_ROOT_ID);
            if (floatingModalRoot) {
                floatingModalRoot.dataset.locked = '0';
                floatingModalRoot.remove();
            }
            ['licenseModal', 'vehicleDetailModal', 'addServiceRecordModal', 'serviceRecordDetailModal', 'attachmentPreviewModal'].forEach((modalId) => {
                const modalEl = document.getElementById(modalId);
                if (modalEl) {
                    modalEl.dataset.scrollLock = '0';
                }
            });
            const vehicleModal = document.getElementById('vehicleDetailModal');
            if (vehicleModal) {
                vehicleModal.dataset.nestedModalOpen = '0';
            }
            mobileModalViewportFreezeHeight = 0;
            unlockBodyScrollForModal(true);
            updateAppViewportHeightVar();
        }

        function getStoredLoginModePreference() {
            try {
                const savedMode = String(localStorage.getItem(AUTH_STORAGE_KEYS.loginMode) || '').toLowerCase();
                if (savedMode === 'service') return 'service';
            } catch (e) {
                // ignore storage errors
            }
            return 'user';
        }

        function hasServiceAccessRole() {
            const role = String(currentUser?.role || '').toLowerCase();
            return role === 'service' || role === 'admin' || role === 'developer_admin';
        }

        function getActiveWorkspaceMode() {
            const role = String(currentUser?.role || '').toLowerCase();
            if (role === 'service') {
                return 'service';
            }
            if (role !== 'admin' && role !== 'developer_admin') {
                return 'user';
            }

            const preferredMode = (loginMode === 'service' || loginMode === 'user')
                ? loginMode
                : getStoredLoginModePreference();
            return preferredMode === 'service' ? 'service' : 'user';
        }

        function isServiceWorkspaceRole() {
            return hasServiceAccessRole() && getActiveWorkspaceMode() === 'service';
        }

        function shouldShowServicesDirectoryTab() {
            return getActiveWorkspaceMode() === 'user';
        }

        function setDashboardTabVisibility(tabKey, shouldShow) {
            const btn = document.querySelector(`.tab[data-tab-key="${tabKey}"]`);
            if (!btn) return;
            btn.classList.toggle('hidden', !shouldShow);
        }

        function setDashboardTabLabel(tabKey, label) {
            const btn = document.querySelector(`.tab[data-tab-key="${tabKey}"]`);
            if (!btn || !label) return;
            btn.textContent = label;
        }

        function getFirstVisibleDashboardTabKey() {
            const btn = Array.from(document.querySelectorAll('.tabs .tab[data-tab-key]'))
                .find((item) => !item.classList.contains('hidden'));
            return btn ? String(btn.getAttribute('data-tab-key') || '') : '';
        }

        function ensureActiveVisibleDashboardTab(preferredKey) {
            const activeBtn = document.querySelector('.tabs .tab.active[data-tab-key]');
            const activeHidden = !activeBtn || activeBtn.classList.contains('hidden');
            if (!activeHidden) return;

            const fallbackKey = preferredKey || getFirstVisibleDashboardTabKey();
            if (fallbackKey) {
                switchTab(fallbackKey, { skipUnsavedGuard: true });
            }
        }

        function updateRoleBasedDashboardTabs() {
            loginMode = getStoredLoginModePreference();
            const serviceMode = isServiceWorkspaceRole();
            for (const key of ['customerOverview','customerArchives','customerInvitations']) setDashboardTabVisibility(key, !serviceMode);

            if (serviceMode) {
                // Finální servisní dashboard: 1 Klienti 2 Kalendář 3 Připomínky 4 Přidat vozidlo 5 Nastavení 6 Podpora
                setDashboardTabVisibility('vehicles', false);
                setDashboardTabVisibility('servicesDirectory', false);
                setDashboardTabVisibility('serviceWorkspace', true);
                setDashboardTabVisibility('reservations', true);
                setDashboardTabVisibility('reminders', true);
                setDashboardTabVisibility('addVehicle', true);
                setDashboardTabVisibility('profile', true);
                setDashboardTabVisibility('support', true);

                setDashboardTabLabel('serviceWorkspace', 'Klienti');
                setDashboardTabLabel('reservations', 'Kalendář');
                setDashboardTabLabel('reminders', 'Připomínky');
                setDashboardTabLabel('addVehicle', 'Přidat vozidlo');
                setDashboardTabLabel('profile', 'Nastavení');
                setDashboardTabLabel('support', 'Podpora');

                const vehiclesTab = document.getElementById('vehiclesTab');
                if (vehiclesTab) vehiclesTab.classList.remove('active');
                const servicesDirectoryTab = document.getElementById('servicesDirectoryTab');
                if (servicesDirectoryTab) servicesDirectoryTab.classList.remove('active');

                ensureActiveVisibleDashboardTab('serviceWorkspace');
                return;
            }

            // User / admin-user režim
            setDashboardTabVisibility('vehicles', true);
            setDashboardTabVisibility('addVehicle', true);
            setDashboardTabVisibility('reminders', true);
            setDashboardTabVisibility('reservations', true);
            setDashboardTabVisibility('profile', true);
            setDashboardTabVisibility('support', true);
            setDashboardTabVisibility('serviceWorkspace', false);
            setDashboardTabVisibility('servicesDirectory', shouldShowServicesDirectoryTab());

            setDashboardTabLabel('vehicles', 'Vozidla');
            setDashboardTabLabel('addVehicle', 'Přidat vozidlo');
            setDashboardTabLabel('reminders', 'Připomínky');
            setDashboardTabLabel('reservations', 'Rezervace');
            setDashboardTabLabel('servicesDirectory', 'Servisy');
            setDashboardTabLabel('serviceWorkspace', 'Servis klienti');
            setDashboardTabLabel('profile', 'Nastavení');
            setDashboardTabLabel('support', 'Podpora');

            const serviceTab = document.getElementById('serviceWorkspaceTab');
            if (serviceTab) serviceTab.classList.remove('active');
            ensureActiveVisibleDashboardTab('vehicles');
        }

        function capturePendingServiceInviteTokenFromUrl() {
            try {
                const location = getLocation();
                const params = new URLSearchParams(location.search || '');
                const token = String(params.get('invite_token') || '').trim();
                if (token) {
                    pendingServiceInviteToken = token;
                    localStorage.setItem('pendingServiceInviteToken', token);
                } else {
                    const cached = String(localStorage.getItem('pendingServiceInviteToken') || '').trim();
                    pendingServiceInviteToken = cached || null;
                }
            } catch (e) {
                pendingServiceInviteToken = null;
            }
        }

        function capturePendingReservationClaimTokenFromUrl() {
            try {
                const params = new URLSearchParams(window.location.search || '');
                const token = String(params.get('reservation_claim_token') || '').trim();
                const reservationIdRaw = String(params.get('reservation_id') || '').trim();
                const reservationId = /^\d+$/.test(reservationIdRaw) ? Number(reservationIdRaw) : null;

                if (token) {
                    pendingReservationClaimToken = token;
                    pendingReservationClaimReservationId = reservationId;
                    localStorage.setItem('pendingReservationClaimToken', token);
                    if (reservationId) {
                        localStorage.setItem('pendingReservationClaimReservationId', String(reservationId));
                    } else {
                        localStorage.removeItem('pendingReservationClaimReservationId');
                    }

                    params.delete('reservation_claim_token');
                    params.delete('reservation_id');
                    const cleanQuery = params.toString();
                    const cleanUrl = `${window.location.pathname}${cleanQuery ? `?${cleanQuery}` : ''}${window.location.hash || ''}`;
                    window.history.replaceState({}, document.title, cleanUrl);
                } else {
                    const cachedToken = String(localStorage.getItem('pendingReservationClaimToken') || '').trim();
                    const cachedReservationIdRaw = String(localStorage.getItem('pendingReservationClaimReservationId') || '').trim();
                    pendingReservationClaimToken = cachedToken || null;
                    pendingReservationClaimReservationId = /^\d+$/.test(cachedReservationIdRaw)
                        ? Number(cachedReservationIdRaw)
                        : null;
                }
            } catch (error) {
                pendingReservationClaimToken = null;
                pendingReservationClaimReservationId = null;
            }
        }

        async function acceptPendingServiceInviteToken() {
            if (!pendingServiceInviteToken || !isAuthenticated()) return;
            if (isServiceWorkspaceRole()) return;

            const token = pendingServiceInviteToken;
            pendingServiceInviteToken = null;

            try {
                await apiCall('/api/v1/services/workspace/invitations/accept', 'POST', {
                    token
                });
                localStorage.removeItem('pendingServiceInviteToken');
                showAlert('Pozvánka od servisu byla přijata. Servis nyní uvidí vaše vozidla a historii úkonů.', 'success');
                loadManagedServiceContacts(true);
            } catch (error) {
                console.warn("[SERVICE_INVITE] Nepodařilo se přijmout pozvánku:");
                pendingServiceInviteToken = token;
                localStorage.setItem('pendingServiceInviteToken', token);
            }
        }

        async function acceptPendingReservationClaimToken() {
            if (!pendingReservationClaimToken || !isAuthenticated()) return;
            if (!hasServiceAccessRole()) return;

            const token = pendingReservationClaimToken;
            const reservationId = pendingReservationClaimReservationId;
            pendingReservationClaimToken = null;
            pendingReservationClaimReservationId = null;

            try {
                const result = await apiCall('/api/v1/reservations/claim-link', 'POST', { token });
                localStorage.removeItem('pendingReservationClaimToken');
                localStorage.removeItem('pendingReservationClaimReservationId');
                showAlert(
                    result?.message || 'Klient byl automaticky přiřazen k servisu a rezervace je připravena.',
                    'success'
                );
                if (isServiceReservationsContext()) {
                    loadReservations();
                }
                if (typeof loadServiceWorkspace === 'function') {
                    loadServiceWorkspace();
                }
                if (reservationId && typeof switchTab === 'function') {
                    setTimeout(() => switchTab('reservations'), 120);
                }
            } catch (error) {
                console.warn("[RESERVATION_LINK] Nepodařilo se potvrdit propojení z odkazu:");
                showAlert(
                    `Nepodařilo se potvrdit přiřazení rezervace: ${error?.message || 'Neznámá chyba'}`,
                    'warning'
                );
                pendingReservationClaimToken = token;
                pendingReservationClaimReservationId = reservationId;
                localStorage.setItem('pendingReservationClaimToken', token);
                if (reservationId) {
                    localStorage.setItem('pendingReservationClaimReservationId', String(reservationId));
                }
            }
        }

        // Zobrazení přihlášení (skrýt dashboard)
        function showLogin() {
            if (!window.CustomerWeb) { AdminBrowserSession.end('verification'); return; }
            document.getElementById('adminSessionLoading')?.remove();
            const auth = document.getElementById('authSection');
            auth.classList.remove('hidden'); auth.style.display = '';
            document.getElementById('dashboard').classList.add('hidden');
            document.getElementById('loginForm').classList.remove('hidden');
            document.getElementById('registerForm').classList.add('hidden');
        }

        // Zobrazení dashboardu (skrýt login)
        function showDashboard() {
            document.getElementById('adminSessionLoading')?.remove();
            const dashboardStartTs = performance.now();
            // Kontrola auth stavu
            if (!isAuthenticated()) {
                console.warn("[DASHBOARD] Uživatel není přihlášen - zobrazuji login");
                showLogin();
                return;
            }
            closeMobileNavbarMenu();
            clearBodyScrollLocks();

            const authSection = document.getElementById('authSection');
            const dashboard = document.getElementById('dashboard');
            const userEmailEl = document.getElementById('userEmail');
            const navbar = document.getElementById('mainNavbar');
            const userBadge = document.getElementById('userBadge');
            const logoutBtn = document.getElementById('logout-btn');

            if (!authSection || !dashboard) {
                console.error("[DASHBOARD] authSection nebo dashboard neexistuje!");
                return;
            }

            // Skrýt auth section
            authSection.classList.add('hidden');
            authSection.style.display = 'none';

            // Command Bot DOČASNĚ VYPNUT
            // updateCommandBotVisibility();

            // Zobrazit navbar
            if (navbar) {
                navbar.classList.remove('hidden');
            }

            // Zobrazit dashboard
            dashboard.classList.add('active');
            dashboard.style.display = 'block';

            // Zobrazit badge uživatele a logout button
            if (userEmailEl && currentUser) {
                userEmailEl.textContent = currentUser.email;
                if (userBadge) {
                    userBadge.classList.remove('hidden');
                }
            }
            if (logoutBtn) {
                logoutBtn.classList.remove('hidden');
            }
            updateRoleBasedDashboardTabs();

            // Spustit sledování aktivity při přihlášení
            resetInactivityTimer();
            startClientGeoRefresh();
            startReminderNotificationHeartbeat();
            startSystemNotificationsPolling();

            if (isServiceWorkspaceRole()) {
                if (typeof loadServiceWorkspace === 'function') {
                    loadServiceWorkspace();
                }
            } else {
                loadVehicles(false);
            }


            deferNonCriticalUiTask('system-capabilities', () => loadSystemCapabilities(false));
            deferNonCriticalUiTask('license-ui-init', async () => {
                if (typeof initLicenseDropdownHandlers === 'function') {
                    initLicenseDropdownHandlers();
                }
                if (typeof startLicenseRefresh === 'function') {
                    startLicenseRefresh();
                }
                if (typeof loadLicenseStatus === 'function' && (!licenseLastFetch || (Date.now() - licenseLastFetch > 5000))) {
                    await loadLicenseStatus();
                }
                if (typeof loadComgateLicenseConfig === 'function') {
                    await loadComgateLicenseConfig();
                }
            }, 180);
            deferNonCriticalUiTask('payment-return-info', async () => {
                if (typeof handlePendingPaymentReturnInfo === 'function') {
                    await handlePendingPaymentReturnInfo();
                }
            }, 700);
            deferNonCriticalUiTask('service-add-vehicle-init', () => {
                if (typeof ensureServiceAddVehicleSection === 'function') {
                    ensureServiceAddVehicleSection();
                }
            }, 220);
            deferNonCriticalUiTask('managed-service-contacts', () => loadManagedServiceContacts(false), 260);
            deferNonCriticalUiTask('pending-service-invite', () => acceptPendingServiceInviteToken(), 300);
            deferNonCriticalUiTask('pending-reservation-claim', () => acceptPendingReservationClaimToken(), 340);
            deferNonCriticalUiTask('push-subscription-sync', async () => {
                await ensurePushSubscribed({ interactive: false });
            }, 800);

            if (isServiceWorkspaceRole()) {
                deferNonCriticalUiTask('service-reservations-prefetch', () => loadReservations(false), 200);
                deferNonCriticalUiTask('service-reminders-prefetch', () => loadServiceWorkspaceReminders(false), 240);
            }
        }

        // LICENSE_UI_START: Načtení licenčního statusu a renderování do TopBar
        async function loadLicenseStatus() {
            // Kontrola autentizace - pokud není přihlášený, nezobrazovat licence
            if (!isAuthenticated()) {

                closeLicenseModal();
                return;
            }

            const labelEl = document.getElementById("licenseQuickLabel");
            const currentEl = document.getElementById("licenseQuickCurrent");
            const vehiclesEl = document.getElementById("licenseQuickVehicles");
            const featuresEl = document.getElementById("licenseQuickFeatures");

            if (!labelEl || !currentEl || !vehiclesEl || !featuresEl) {
                console.warn("[LICENSE] license quick elements not found");
                return;
            }

            labelEl.textContent = "Licence: načítám…";
            currentEl.textContent = "Načítám informace o licenci...";
            vehiclesEl.textContent = "";
            featuresEl.innerHTML = "";

            try {
                const apiUrl = getApiBaseUrl();
                const headers = {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'Accept-Language': 'cs-CZ,cs;q=0.9,en;q=0.8'
                };
                if (accessToken) {
                    headers['Authorization'] = `Bearer ${accessToken}`;
                }
                appendClientGeoHeaders(headers);

                const response = await AdminBrowserSession.request(`${apiUrl}/api/v1/license/status`, {
                    method: 'GET',
                    headers,
                    credentials: 'include',
                    mode: 'cors',
                    cache: 'no-cache'
                });

                const contentType = response.headers.get('content-type') || '';
                const isJson = contentType.includes('application/json');

                if (response.status === 401) {
                    labelEl.textContent = "Licence: (nepřihlášen)";
                    currentEl.textContent = "Pro zobrazení licence se přihlaste.";
                    vehiclesEl.textContent = "";
                    featuresEl.innerHTML = "";
                    licenseLastFetch = Date.now();
                    return;
                }

                if (!response.ok) {
                    let detail = '';
                    if (isJson) {
                        try {
                            const errData = await response.json();
                            detail = errData.detail || errData.message || '';
                        } catch (e) {
                            // ignore parse error
                        }
                    }
                    labelEl.textContent = "Licence: chyba";
                    currentEl.textContent = "Nepodařilo se načíst licenci.";
                    vehiclesEl.textContent = detail ? `${response.status} – ${detail}` : `HTTP ${response.status}`;
                    featuresEl.innerHTML = "";
                    licenseLastFetch = Date.now();
                    return;
                }

                const payload = isJson ? await response.json() : null;
                const data = payload && payload.data ? payload.data : (payload || {});
                renderLicenseMenu(data);
                if (typeof applyLicenseToUI === 'function') {
                    applyLicenseToUI(data);
                }
                licenseLastFetch = Date.now();
            } catch (e) {
                console.error("[LICENSE] failed:");
                labelEl.textContent = "Licence: chyba";
                currentEl.textContent = "Nepodařilo se načíst licenci.";
                vehiclesEl.textContent = e.message || String(e);
                featuresEl.innerHTML = "";
                licenseLastFetch = Date.now();
            }
        }

        function isFeatureEnabled(license, key) {
            return !!(license && Object.prototype.hasOwnProperty.call(license, key) ? license[key] : false);
        }

        function applyLicenseToUI(license) {
            if (window.CustomerWeb) document.body.dataset.webPlan = ['admin', 'developer_admin', 'service'].includes(currentUser?.role) ? 'premium' : (license?.plan || 'free');
            const flags = {
                vinEnabled: isFeatureEnabled(license, 'vin_decode_enabled'),
                remindersEnabled: isFeatureEnabled(license, 'reminders_enabled'),
                vehicleHistoryEnabled: isFeatureEnabled(license, 'vehicle_history_enabled'),
                documentsEnabled: isFeatureEnabled(license, 'documents_enabled'),
                costsTrackingEnabled: isFeatureEnabled(license, 'costs_tracking_enabled'),
                statisticsEnabled: isFeatureEnabled(license, 'statistics_enabled'),
                sharingWithServiceEnabled: isFeatureEnabled(license, 'sharing_with_service_enabled'),
                // ARES necháváme funkční pro všechny tarify
                aresEnabled: true,
            };
            if ((license?.plan || '').toLowerCase() === 'free') {
                flags.vinEnabled = false; // ve FREE vždy ruční zadání
            }
            window.__licenseFlags = flags;

            const vinInput = document.getElementById('vehicleVin');
            if (vinInput) {
                vinInput.disabled = false; // VIN lze vždy vyplnit ručně
                vinInput.title = flags.vinEnabled ? '' : 'Automatické načtení VIN je dostupné od plánu BASIC';
                vinInput.placeholder = flags.vinEnabled
                    ? 'Zadejte VIN - automaticky se načtou data'
                    : 'Zadejte VIN (data vyplňte ručně)';
            }
            const vinInfo = document.getElementById('vinSourceText');
            if (vinInfo && !flags.vinEnabled) {
                vinInfo.textContent = 'Automatické VIN dekódování je dostupné od plánu BASIC. Vyplňte údaje ručně.';
            }

            const remindersContainer = document.getElementById('remindersContainer');
            if (remindersContainer && !flags.remindersEnabled) {
                renderRemindersUpsell(remindersContainer);
            }

            // Pokud VIN auto-fill není povolen, upravit placeholdery polí z VIN
            const vinDependentPlaceholders = [
                { id: 'vehicleModel', disabledText: 'Vyplňte ručně (automatické vyplnění v plánu BASIC)', enabledText: 'Načte se z VIN' },
                { id: 'vehicleYear', disabledText: 'Vyplňte ručně (automatické vyplnění v plánu BASIC)', enabledText: 'Načte se z VIN' },
                { id: 'vehicleEngine', disabledText: 'Vyplňte ručně (automatické vyplnění v plánu BASIC)', enabledText: 'Načte se z VIN' },
                { id: 'vehicleTyres', disabledText: 'Vyplňte ručně (automatické vyplnění v plánu BASIC)', enabledText: 'Načte se z VIN' },
                { id: 'vehicleAdditionalNotes', disabledText: 'Vyplňte ručně (automatické vyplnění v plánu BASIC)', enabledText: 'Načte se z VIN' },
                { id: 'vehicleInspectionDate', disabledText: 'Vyplňte ručně (automatické vyplnění v plánu BASIC)', enabledText: 'Načte se z VIN' },
                { id: 'vehicleStkDate', disabledText: 'Vyplňte ručně (automatické vyplnění v plánu BASIC)', enabledText: 'Načte se z VIN' },
            ];
            vinDependentPlaceholders.forEach(field => {
                const el = document.getElementById(field.id);
                if (!el) return;
                el.placeholder = flags.vinEnabled ? field.enabledText : field.disabledText;
            });

            const historySection = document.getElementById('vehicleHistorySection');
            if (historySection) {
                historySection.classList.toggle('feature-disabled', !flags.vehicleHistoryEnabled);
                historySection.title = flags.vehicleHistoryEnabled ? '' : 'Historie vozidla je dostupná od plánu BASIC';
            }

            const documentsSection = document.getElementById('documentsSection');
            if (documentsSection) {
                documentsSection.classList.toggle('feature-disabled', !flags.documentsEnabled);
                documentsSection.title = flags.documentsEnabled ? '' : 'Dokumenty jsou dostupné od plánu BASIC';
            }

            const costsSection = document.getElementById('costsSection');
            if (costsSection) {
                costsSection.classList.toggle('feature-disabled', !flags.costsTrackingEnabled);
                costsSection.title = flags.costsTrackingEnabled ? '' : 'Nákladové sledování je dostupné od plánu PREMIUM';
            }

            const statsSection = document.getElementById('statisticsSection');
            if (statsSection) {
                statsSection.classList.toggle('feature-disabled', !flags.statisticsEnabled);
                statsSection.title = flags.statisticsEnabled ? '' : 'Statistiky jsou dostupné od plánu PREMIUM';
            }

            const sharingInfo = document.getElementById('sharingInfo');
            if (sharingInfo) {
                sharingInfo.textContent = flags.sharingWithServiceEnabled
                    ? 'Sdílení se servisem (brzy) – povoleno'
                    : 'Sdílení se servisem (brzy) – dostupné od plánu PREMIUM';
            }
        }

        function formatPriceFromHalers(value, currency = 'CZK') {
            const amount = Number(value);
            if (!Number.isFinite(amount) || amount <= 0) return 'Na vyžádání';
            const amountCzk = amount / 100;
            const suffix = String(currency || 'CZK').toUpperCase() === 'CZK' ? 'Kč' : String(currency || 'CZK').toUpperCase();
            const whole = Math.abs(amountCzk - Math.round(amountCzk)) < 0.000001;
            return `${amountCzk.toLocaleString('cs-CZ', whole
                ? { minimumFractionDigits: 0, maximumFractionDigits: 0 }
                : { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${suffix}`;
        }

        function normalizeLicensePlanKey(plan) {
            const normalized = String(plan || '').trim().toLowerCase();
            if (normalized === 'basic' || normalized === 'premium' || normalized === 'free') return normalized;
            return 'free';
        }

        function getDefaultComgatePlans() {
            return {
                basic: { monthly: 14900, yearly: 149000 },
                premium: { monthly: 44900, yearly: 449000 },
            };
        }

        function normalizeLicenseBillingPeriod(period) {
            const normalized = String(period || '').trim().toLowerCase();
            return normalized === 'yearly' ? 'yearly' : 'monthly';
        }

        function syncLicenseBillingButtons() {
            const toggle = document.getElementById('licenseBillingToggle');
            if (!toggle) return;
            const period = normalizeLicenseBillingPeriod(selectedLicenseBillingPeriod);
            const buttons = toggle.querySelectorAll('.license-billing-btn');
            buttons.forEach((button) => {
                const buttonPeriod = normalizeLicenseBillingPeriod(button.getAttribute('data-period'));
                const active = buttonPeriod === period;
                button.classList.toggle('active', active);
                button.setAttribute('aria-pressed', active ? 'true' : 'false');
            });
        }

        function setLicenseBillingPeriod(period) {
            selectedLicenseBillingPeriod = normalizeLicenseBillingPeriod(period);
            syncLicenseBillingButtons();
            applyComgateUiConfig(comgateConfigCache);
        }

        function resolveComgatePlanPrice(config, planKey, billingPeriod) {
            const plans = config && typeof config === 'object' ? config.plans : null;
            const planEntry = plans && typeof plans === 'object' ? plans[planKey] : null;
            const defaultPlans = getDefaultComgatePlans();
            const defaultEntry = defaultPlans[planKey] || {};

            // Backward compatibility: starsi API vracelo pouze mesicni cenu jako cislo.
            if (planEntry && typeof planEntry === 'object' && !Array.isArray(planEntry)) {
                const value = Number(planEntry[billingPeriod]);
                if (Number.isFinite(value) && value > 0) return value;
                return Number(defaultEntry[billingPeriod] || NaN);
            }
            if (billingPeriod === 'monthly') {
                const value = Number(planEntry);
                if (Number.isFinite(value) && value > 0) return value;
                return Number(defaultEntry.monthly || NaN);
            }
            return Number(defaultEntry[billingPeriod] || NaN);
        }

        function formatPlanPriceLabel(priceHalers, currency, billingPeriod) {
            if (!Number.isFinite(priceHalers) || priceHalers <= 0) return 'Cena není nastavena';
            const periodLabel = billingPeriod === 'yearly' ? 'rok' : 'měsíc';
            return `${formatPriceFromHalers(priceHalers, currency)} / ${periodLabel}`;
        }

        function updatePaidPlanActionButton(planKey, priceHalers, currency, billingPeriod, paymentEnabled) {
            const card = document.querySelector(`.license-plan-card[data-plan="${planKey}"]`);
            if (!card) return;
            const actionBtn = card.querySelector('.plan-action-btn');
            if (!actionBtn || actionBtn.classList.contains('plan-active')) return;

            const planOrder = { free: 1, basic: 2, premium: 3 };
            const currentOrder = planOrder[normalizeLicensePlanKey(currentLicensePlanForUi)] || 1;
            const targetOrder = planOrder[planKey] || 1;
            const isDowngrade = targetOrder < currentOrder;
            if (isDowngrade) return;

            const hasPrice = Number.isFinite(priceHalers) && priceHalers > 0;
            if (!hasPrice) {
                actionBtn.disabled = true;
                actionBtn.textContent = 'Cena není nastavena';
                actionBtn.title = 'Pro tento plán není nastavená cena.';
                return;
            }

            actionBtn.disabled = false;
            const priceText = formatPriceFromHalers(priceHalers, currency);
            const periodText = billingPeriod === 'yearly' ? 'ročně' : 'měsíčně';
            actionBtn.textContent = `Zaplatit ${priceText}`;
            actionBtn.title = paymentEnabled
                ? `Pokračovat na ${periodText} platbu ${priceText}`
                : `Comgate není aktivní. Po kliknutí uvidíte chybějící nastavení.`;
        }

        function parseCssColorToRgba(value) {
            if (!value) return null;
            const input = String(value).trim();
            const rgbMatch = input.match(/^rgba?\(([^)]+)\)$/i);
            if (rgbMatch) {
                const parts = rgbMatch[1].split(',').map((part) => part.trim());
                if (parts.length >= 3) {
                    const r = Number(parts[0]);
                    const g = Number(parts[1]);
                    const b = Number(parts[2]);
                    const a = parts.length >= 4 ? Number(parts[3]) : 1;
                    if ([r, g, b].every((channel) => Number.isFinite(channel))) {
                        return {
                            r: Math.max(0, Math.min(255, r)),
                            g: Math.max(0, Math.min(255, g)),
                            b: Math.max(0, Math.min(255, b)),
                            a: Number.isFinite(a) ? Math.max(0, Math.min(1, a)) : 1,
                        };
                    }
                }
            }

            const hexMatch = input.match(/^#([0-9a-f]{3,8})$/i);
            if (!hexMatch) return null;
            const hex = hexMatch[1];
            if (hex.length === 3 || hex.length === 4) {
                const r = parseInt(hex[0] + hex[0], 16);
                const g = parseInt(hex[1] + hex[1], 16);
                const b = parseInt(hex[2] + hex[2], 16);
                const a = hex.length === 4 ? parseInt(hex[3] + hex[3], 16) / 255 : 1;
                return { r, g, b, a };
            }
            if (hex.length === 6 || hex.length === 8) {
                const r = parseInt(hex.slice(0, 2), 16);
                const g = parseInt(hex.slice(2, 4), 16);
                const b = parseInt(hex.slice(4, 6), 16);
                const a = hex.length === 8 ? parseInt(hex.slice(6, 8), 16) / 255 : 1;
                return { r, g, b, a };
            }
            return null;
        }

        function getRelativeLuminance(color) {
            if (!color) return 1;
            const toLinear = (channel) => {
                const normalized = channel / 255;
                return normalized <= 0.03928
                    ? normalized / 12.92
                    : Math.pow((normalized + 0.055) / 1.055, 2.4);
            };
            const r = toLinear(color.r);
            const g = toLinear(color.g);
            const b = toLinear(color.b);
            return 0.2126 * r + 0.7152 * g + 0.0722 * b;
        }

        function getEffectiveBackgroundColor(element) {
            let node = element;
            while (node && node instanceof Element) {
                const bg = parseCssColorToRgba(window.getComputedStyle(node).backgroundColor);
                if (bg && bg.a > 0.01) return bg;
                node = node.parentElement;
            }
            const bodyBg = parseCssColorToRgba(window.getComputedStyle(document.body).backgroundColor);
            return bodyBg && bodyBg.a > 0.01 ? bodyBg : { r: 255, g: 255, b: 255, a: 1 };
        }

        function applyPaymentBrandContrast(container) {
            if (!(container instanceof Element)) return;
            const luminance = getRelativeLuminance(getEffectiveBackgroundColor(container));
            const isDarkBackground = luminance < 0.52;
            container.classList.toggle('payment-brand-contrast-dark', isDarkBackground);
            container.classList.toggle('payment-brand-contrast-light', !isDarkBackground);
        }

        function refreshPaymentBrandContrast() {
            applyPaymentBrandContrast(document.getElementById('licenseComgateBrand'));
            applyPaymentBrandContrast(document.querySelector('.payment-legal-left'));
        }

        let paymentBrandContrastRaf = null;
        function schedulePaymentBrandContrastRefresh() {
            if (typeof window === 'undefined') return;
            if (paymentBrandContrastRaf !== null) {
                window.cancelAnimationFrame(paymentBrandContrastRaf);
            }
            paymentBrandContrastRaf = window.requestAnimationFrame(() => {
                paymentBrandContrastRaf = null;
                refreshPaymentBrandContrast();
            });
        }

        function applyComgateUiConfig(config) {
            const providerWrap = document.getElementById('licenseComgateBrand');
            const basicPriceEl = document.getElementById('licensePlanPriceBasic');
            const premiumPriceEl = document.getElementById('licensePlanPricePremium');
            const billingPeriod = normalizeLicenseBillingPeriod(selectedLicenseBillingPeriod);
            syncLicenseBillingButtons();

            const enabled = !!(config && config.enabled);
            const currency = String(config?.currency || 'CZK');
            const basicPrice = resolveComgatePlanPrice(config, 'basic', billingPeriod);
            const premiumPrice = resolveComgatePlanPrice(config, 'premium', billingPeriod);

            if (basicPriceEl) {
                basicPriceEl.textContent = formatPlanPriceLabel(basicPrice, currency, billingPeriod);
            }
            if (premiumPriceEl) {
                premiumPriceEl.textContent = formatPlanPriceLabel(premiumPrice, currency, billingPeriod);
            }
            if (providerWrap) {
                providerWrap.style.opacity = enabled ? '1' : '0.72';
            }

            updatePaidPlanActionButton('basic', basicPrice, currency, billingPeriod, enabled);
            updatePaidPlanActionButton('premium', premiumPrice, currency, billingPeriod, enabled);
            syncLicensePaidPlanConsentState();
            schedulePaymentBrandContrastRefresh();
        }

        async function loadComgateLicenseConfig(force = false) {
            if (!isAuthenticated()) {
                comgateConfigCache = null;
                comgateConfigLoadedAt = 0;
                applyComgateUiConfig(null);
                return null;
            }

            const now = Date.now();
            if (!force && comgateConfigCache && (now - comgateConfigLoadedAt < 120000)) {
                applyComgateUiConfig(comgateConfigCache);
                return comgateConfigCache;
            }

            try {
                const payload = await apiCall('/api/v1/license/comgate/config', 'GET');
                comgateConfigCache = payload && typeof payload === 'object' ? payload : { enabled: false };
            } catch (error) {
                console.warn("[LICENSE] Comgate config load failed:");
                comgateConfigCache = {
                    enabled: false,
                    configured: false,
                    currency: 'CZK',
                    plans: getDefaultComgatePlans(),
                };
            }
            comgateConfigLoadedAt = Date.now();
            applyComgateUiConfig(comgateConfigCache);
            return comgateConfigCache;
        }

        function capturePendingPaymentReturnFromUrl() {
            try {
                const params = new URLSearchParams(window.location.search || '');
                const provider = String(params.get('payment_provider') || '').trim().toLowerCase();
                const status = String(params.get('payment_status') || '').trim().toLowerCase();
                if (provider !== 'comgate' || !status) {
                    return;
                }

                pendingPaymentReturnInfo = {
                    provider,
                    status,
                    plan: String(params.get('plan') || '').trim().toUpperCase(),
                    billingPeriod: normalizeLicenseBillingPeriod(params.get('billing_period') || 'monthly'),
                };
                selectedLicenseBillingPeriod = pendingPaymentReturnInfo.billingPeriod;

                params.delete('payment_provider');
                params.delete('payment_status');
                params.delete('plan');
                params.delete('billing_period');
                const cleanQuery = params.toString();
                const cleanUrl = `${window.location.pathname}${cleanQuery ? `?${cleanQuery}` : ''}${window.location.hash || ''}`;
                window.history.replaceState({}, document.title, cleanUrl);
            } catch (error) {
                console.warn("[LICENSE] Failed to parse payment return URL:");
            }
        }

        async function handlePendingPaymentReturnInfo() {
            if (!pendingPaymentReturnInfo || !isAuthenticated()) return;
            const info = pendingPaymentReturnInfo;
            pendingPaymentReturnInfo = null;
            const billingLabel = info.billingPeriod === 'yearly' ? 'roční' : 'měsíční';
            const planText = info.plan ? ` (${info.plan}, ${billingLabel})` : '';

            if (info.status === 'paid') {
                await loadLicenseStatus();
                await loadComgateLicenseConfig(true);
                const expectedPlan = normalizeLicensePlanKey(info.plan || '');
                if (expectedPlan && expectedPlan !== 'free') {
                    let retries = 0;
                    const maxRetries = 10;
                    const retryDelayMs = 3000;
                    while (normalizeLicensePlanKey(currentLicensePlanForUi || '') !== expectedPlan && retries < maxRetries) {
                        await new Promise((resolve) => setTimeout(resolve, retryDelayMs));
                        await loadLicenseStatus();
                        retries += 1;
                    }
                }
                const subscriptionState = currentLicenseSubscriptionForUi && typeof currentLicenseSubscriptionForUi === 'object'
                    ? currentLicenseSubscriptionForUi
                    : null;
                const statusKey = String(subscriptionState?.status || '').toLowerCase();
                const hasAutoRenew = !!subscriptionState?.auto_renew_enabled;
                const appliedPlan = normalizeLicensePlanKey(currentLicensePlanForUi || '');

                if (expectedPlan && expectedPlan !== 'free' && appliedPlan !== expectedPlan) {
                    showAlert(
                        `Platba byla potvrzena${planText}, ale změna plánu se ještě synchronizuje. Obnovte stránku za chvíli nebo zkontrolujte sekci Licence.`,
                        'warning'
                    );
                    return;
                }

                if (statusKey === 'legacy_manual' || !hasAutoRenew) {
                    showAlert(
                        `Platba přes Comgate byla potvrzena${planText}. Licence je aktivní, ale běží dočasně jako jednorázová platba bez auto-obnovy (recurring karta ještě není plně aktivní).`,
                        'success'
                    );
                } else {
                    showAlert(
                        `Platba přes Comgate byla potvrzena${planText}. Aktivovalo se předplatné s automatickým opakováním podle zvolené fakturace. Správu najdete v sekci Licence.`,
                        'success'
                    );
                }
                return;
            }
            if (info.status === 'pending') {
                showAlert('Platba je zatím ve stavu čekání. Po potvrzení se licence automaticky projeví.', 'info');
                return;
            }
            if (info.status === 'cancelled') {
                showAlert('Platba byla zrušena. Licenci můžete aktivovat znovu.', 'warning');
                return;
            }

            showAlert(`Neznámý stav platby: ${info.status}`, 'warning');
        }

        function resetLicenseLegalConsent() {
            pendingPaidPlanForCheckout = '';
            const termsCheckbox = document.getElementById('licenseAgreeTerms');
            const digitalStartCheckbox = document.getElementById('licenseAgreeDigitalStart');
            if (termsCheckbox) termsCheckbox.checked = false;
            if (digitalStartCheckbox) digitalStartCheckbox.checked = false;
            const consentWrap = document.getElementById('licenseLegalConsentBlock');
            if (consentWrap) {
                consentWrap.classList.add('hidden');
                consentWrap.style.borderColor = '';
                consentWrap.style.boxShadow = '';
            }
            const planInfo = document.getElementById('licenseLegalConsentPlanInfo');
            if (planInfo) {
                planInfo.textContent = 'Vybraný plán: –';
            }
            const consentTitle = document.getElementById('licenseLegalConsentTitle');
            if (consentTitle) {
                consentTitle.textContent = 'Před dokončením platby (Basic/Premium)';
            }
            syncLicensePaidPlanConsentState();
        }

        function formatPaidPlanCheckoutActionLabel(planKey) {
            const normalizedPlan = normalizeLicensePlanKey(planKey);
            if (normalizedPlan !== 'basic' && normalizedPlan !== 'premium') {
                return 'Potvrdit a zaplatit';
            }
            const billingPeriod = normalizeLicenseBillingPeriod(selectedLicenseBillingPeriod);
            const config = comgateConfigCache && typeof comgateConfigCache === 'object' ? comgateConfigCache : null;
            const currency = String(config?.currency || 'CZK');
            const priceHalers = resolveComgatePlanPrice(config, normalizedPlan, billingPeriod);
            const periodLabel = billingPeriod === 'yearly' ? 'ročně' : 'měsíčně';
            if (Number.isFinite(priceHalers) && priceHalers > 0) {
                return `Potvrdit a zaplatit ${formatPriceFromHalers(priceHalers, currency)} (${periodLabel})`;
            }
            return `Potvrdit a pokračovat na platbu (${normalizedPlan.toUpperCase()}, ${periodLabel})`;
        }

        function syncLicensePaidPlanConsentState() {
            const confirmBtn = document.getElementById('licenseConfirmPaidPlanBtn');
            if (!confirmBtn) return;
            const normalizedPlan = normalizeLicensePlanKey(pendingPaidPlanForCheckout || '');
            const hasPendingPaidPlan = normalizedPlan === 'basic' || normalizedPlan === 'premium';
            confirmBtn.disabled = !hasPendingPaidPlan || !hasAcceptedPaidPlanLegalConsent(false);
            confirmBtn.textContent = formatPaidPlanCheckoutActionLabel(normalizedPlan);
        }

        function showLicenseLegalConsentForPaidPlan(planKey) {
            const normalizedPlan = normalizeLicensePlanKey(planKey);
            if (normalizedPlan !== 'basic' && normalizedPlan !== 'premium') {
                return false;
            }
            pendingPaidPlanForCheckout = normalizedPlan;
            const consentWrap = document.getElementById('licenseLegalConsentBlock');
            const planInfo = document.getElementById('licenseLegalConsentPlanInfo');
            const consentTitle = document.getElementById('licenseLegalConsentTitle');
            const billingPeriod = normalizeLicenseBillingPeriod(selectedLicenseBillingPeriod);
            const billingLabel = billingPeriod === 'yearly' ? 'roční' : 'měsíční';

            if (consentTitle) {
                consentTitle.textContent = `Před dokončením platby (${normalizedPlan.toUpperCase()})`;
            }
            if (planInfo) {
                planInfo.textContent = `Vybraný plán: ${normalizedPlan.toUpperCase()} (${billingLabel} fakturace)`;
            }
            if (consentWrap) {
                consentWrap.classList.remove('hidden');
                consentWrap.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
            if (typeof loadComgateLicenseConfig === 'function') {
                loadComgateLicenseConfig().catch((error) => {
                    console.warn("[LICENSE] Comgate config refresh during consent flow failed:");
                });
            }
            syncLicensePaidPlanConsentState();
            return true;
        }

        function hideLicenseLegalConsentForPaidPlan() {
            resetLicenseLegalConsent();
        }

        async function confirmLicensePaidPlanCheckout(button) {
            const planKey = normalizeLicensePlanKey(pendingPaidPlanForCheckout || '');
            if (planKey !== 'basic' && planKey !== 'premium') {
                showAlert('Nejprve vyberte placený plán.', 'warning');
                return;
            }
            if (!hasAcceptedPaidPlanLegalConsent(true)) {
                return;
            }
            await upgradeLicensePlan(planKey, button || null, {
                skipConsentCheck: true,
                deferPaidCheckoutToConsent: false,
            });
        }

        function hasAcceptedPaidPlanLegalConsent(showError = true) {
            const termsCheckbox = document.getElementById('licenseAgreeTerms');
            const digitalStartCheckbox = document.getElementById('licenseAgreeDigitalStart');
            const termsAccepted = !!termsCheckbox?.checked;
            const digitalStartAccepted = !!digitalStartCheckbox?.checked;

            if (termsAccepted && digitalStartAccepted) return true;
            if (!showError) return false;

            const consentWrap = document.getElementById('licenseLegalConsentBlock');
            if (consentWrap) {
                consentWrap.classList.remove('hidden');
                consentWrap.style.borderColor = 'rgba(249, 115, 22, 0.65)';
                consentWrap.style.boxShadow = '0 0 0 2px rgba(249, 115, 22, 0.25)';
                setTimeout(() => {
                    consentWrap.style.borderColor = '';
                    consentWrap.style.boxShadow = '';
                }, 2500);
            }
            showAlert('Zaškrtněte oba souhlasy a potvrďte platbu tlačítkem „Potvrdit a zaplatit“.', 'warning');
            return false;
        }

        function formatSubscriptionDate(value) {
            if (!value) return '-';
            const parsed = new Date(value);
            if (Number.isNaN(parsed.getTime())) return '-';
            return parsed.toLocaleString('cs-CZ', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
            });
        }

        function formatCreditBalanceHalers(value) {
            const raw = Number(value || 0);
            if (!Number.isFinite(raw)) return '0 Kč';
            const sign = raw < 0 ? '-' : '';
            const amountCzk = Math.abs(raw) / 100;
            return `${sign}${amountCzk.toLocaleString('cs-CZ', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} Kč`;
        }

        function getSubscriptionStatusMeta(statusValue) {
            const key = String(statusValue || '').toLowerCase();
            if (key === 'active') return { label: 'Aktivní', color: '#166534', bg: '#dcfce7', border: '#86efac' };
            if (key === 'cancel_at_period_end') return { label: 'Ukončí se v období', color: '#7c2d12', bg: '#ffedd5', border: '#fdba74' };
            if (key === 'grace') return { label: 'Ochranná lhůta', color: '#7f1d1d', bg: '#fee2e2', border: '#fca5a5' };
            if (key === 'legacy_manual') return { label: 'Legacy režim', color: '#1e3a8a', bg: '#dbeafe', border: '#93c5fd' };
            if (key === 'canceled') return { label: 'Ukončeno', color: '#374151', bg: '#f3f4f6', border: '#d1d5db' };
            return { label: 'Neznámý stav', color: '#334155', bg: '#e2e8f0', border: '#cbd5e1' };
        }

        function renderLicenseSubscriptionPanel(subscription, licensePlan) {
            const panel = document.getElementById('licenseSubscriptionPanel');
            const statusBadge = document.getElementById('licenseSubscriptionStatusBadge');
            const summary = document.getElementById('licenseSubscriptionSummary');
            const notice = document.getElementById('licenseSubscriptionNotice');
            const cancelBtn = document.getElementById('licenseSubscriptionCancelBtn');
            const resumeBtn = document.getElementById('licenseSubscriptionResumeBtn');
            const changePlanSelect = document.getElementById('licenseSubscriptionChangePlanSelect');
            const changePlanBtn = document.getElementById('licenseSubscriptionChangePlanBtn');
            if (!panel || !statusBadge || !summary || !notice || !cancelBtn || !resumeBtn || !changePlanSelect || !changePlanBtn) {
                return;
            }

            const normalizedPlan = normalizeLicensePlanKey(licensePlan || 'free');
            const payload = subscription && typeof subscription === 'object' ? subscription : null;
            currentLicenseSubscriptionForUi = payload;
            if (!payload || normalizedPlan === 'free') {
                panel.classList.add('hidden');
                notice.classList.add('hidden');
                notice.classList.remove('notice-warning', 'notice-danger', 'notice-info');
                notice.textContent = '';
                return;
            }

            panel.classList.remove('hidden');
            const meta = getSubscriptionStatusMeta(payload.status);
            statusBadge.textContent = meta.label;
            statusBadge.style.color = meta.color;
            statusBadge.style.background = meta.bg;
            statusBadge.style.borderColor = meta.border;

            const daysToEnd = Number(payload.days_to_end);
            const daysLine = Number.isFinite(daysToEnd)
                ? ` • do konce: ${daysToEnd} dní`
                : '';
            const creditBalance = Number(payload.credit_balance_halers || 0);
            const creditLabel = creditBalance < 0 ? 'Nedoplatek' : 'Kredit';
            summary.innerHTML = `
                <strong>Období do:</strong> ${escapeHtml(formatSubscriptionDate(payload.current_period_end))}${daysLine}<br>
                <strong>Další účtování:</strong> ${escapeHtml(formatSubscriptionDate(payload.next_charge_at))}<br>
                <strong>Auto-obnova:</strong> ${payload.auto_renew_enabled ? 'zapnuto' : 'vypnuto'}<br>
                <strong>Ochranná lhůta do:</strong> ${escapeHtml(formatSubscriptionDate(payload.grace_until))}<br>
                <strong>Naplánovaná změna:</strong> ${escapeHtml(payload.pending_plan_change ? payload.pending_plan_change.toUpperCase() : 'bez změny')}<br>
                <strong>${creditLabel}:</strong> ${escapeHtml(formatCreditBalanceHalers(creditBalance))}
            `;

            const statusKey = String(payload.status || '').toLowerCase();
            const isLegacy = statusKey === 'legacy_manual';
            const canCancel = !isLegacy && payload.auto_renew_enabled && statusKey === 'active';
            const canResume = !isLegacy && !payload.auto_renew_enabled && (statusKey === 'cancel_at_period_end' || statusKey === 'grace');

            cancelBtn.classList.toggle('hidden', !canCancel);
            cancelBtn.disabled = !canCancel;
            resumeBtn.classList.toggle('hidden', !canResume);
            resumeBtn.disabled = !canResume;

            notice.classList.add('hidden');
            notice.classList.remove('notice-warning', 'notice-danger', 'notice-info');
            notice.textContent = '';
            if (statusKey === 'grace') {
                notice.textContent = 'Automatická obnova se nepovedla. Běží ochranná lhůta a plán může být po jejím konci převeden na FREE.';
                notice.classList.remove('hidden');
                notice.classList.add('notice-danger');
            } else if (statusKey === 'cancel_at_period_end') {
                notice.textContent = 'Automatické prodloužení je vypnuté. Plán doběhne do konce období; kdykoli můžete obnovit auto-platby.';
                notice.classList.remove('hidden');
                notice.classList.add('notice-warning');
            } else if (Number.isFinite(daysToEnd) && daysToEnd >= 0 && daysToEnd <= 14) {
                notice.textContent = `Předplatné končí za ${daysToEnd} dní. Zkontrolujte, zda chcete pokračovat, změnit plán nebo předplatné zrušit.`;
                notice.classList.remove('hidden');
                notice.classList.add('notice-info');
            }

            changePlanSelect.disabled = false;
            changePlanBtn.disabled = false;
            changePlanBtn.textContent = isLegacy ? 'Pokračovat na změnu' : 'Naplánovat změnu';
            Array.from(changePlanSelect.options).forEach((option) => {
                const optionPlan = normalizeLicensePlanKey(option.value || '');
                if (!optionPlan) {
                    option.disabled = false;
                    return;
                }
                option.disabled = optionPlan === normalizedPlan;
            });
            if (isLegacy) {
                const pendingPlan = normalizeLicensePlanKey(payload.pending_plan_change || '');
                changePlanSelect.value = pendingPlan && pendingPlan !== normalizedPlan ? pendingPlan : '';
                changePlanSelect.title = 'V legacy režimu se změna placeného plánu provede přes novou platbu.';
                if (!notice.textContent) {
                    notice.textContent = 'Legacy režim: změna plánu se přepočítá podle zbývajícího období (doplatek/přeplatek) a rozdíl se započte do kreditu.';
                    notice.classList.remove('hidden');
                    notice.classList.add('notice-info');
                }
            } else {
                changePlanSelect.title = '';
                const pendingPlan = normalizeLicensePlanKey(payload.pending_plan_change || '');
                changePlanSelect.value = pendingPlan && pendingPlan !== normalizedPlan ? pendingPlan : '';
            }
        }

        async function cancelLicenseSubscription() {
            if (!isAuthenticated()) return;
            if (!window.confirm('Opravdu chcete zrušit automatické prodloužení k datu konce období?')) {
                return;
            }
            try {
                await apiCall('/api/v1/license/subscription/cancel', 'POST');
                showAlert('Automatické prodloužení bylo zrušeno k datu konce období.', 'success');
                await loadLicenseStatus();
            } catch (error) {
                showAlert(`Nepodařilo se zrušit předplatné: ${error.message || error}`, 'error');
            }
        }

        async function resumeLicenseSubscription() {
            if (!isAuthenticated()) return;
            try {
                await apiCall('/api/v1/license/subscription/resume', 'POST');
                showAlert('Automatické prodloužení bylo znovu aktivováno.', 'success');
                await loadLicenseStatus();
            } catch (error) {
                showAlert(`Nepodařilo se obnovit předplatné: ${error.message || error}`, 'error');
            }
        }

        async function scheduleLicenseSubscriptionPlanChange() {
            if (!isAuthenticated()) return;
            const select = document.getElementById('licenseSubscriptionChangePlanSelect');
            if (!select) return;
            const targetPlan = normalizeLicensePlanKey(select.value || '');
            const currentPlan = normalizeLicensePlanKey(currentLicensePlanForUi || '');
            const subscriptionState = currentLicenseSubscriptionForUi && typeof currentLicenseSubscriptionForUi === 'object'
                ? currentLicenseSubscriptionForUi
                : null;
            const statusKey = String(subscriptionState?.status || '').toLowerCase();
            const isLegacy = statusKey === 'legacy_manual';
            if (!targetPlan) {
                showAlert('Nejprve vyberte cílový plán.', 'warning');
                return;
            }
            if (targetPlan === currentPlan) {
                showAlert(`Plán ${targetPlan.toUpperCase()} je už aktivní.`, 'info');
                return;
            }

            if (isLegacy) {
                if (targetPlan === 'free') {
                    if (!window.confirm('Přejít z placeného legacy režimu na FREE hned teď?')) {
                        return;
                    }
                    await upgradeLicensePlan('free', null, { deferPaidCheckoutToConsent: false });
                    select.value = '';
                    return;
                }
                showLicenseLegalConsentForPaidPlan(targetPlan);
                showAlert(`Vybraný plán ${targetPlan.toUpperCase()}. Částka se přepočítá dle zbývajícího období a kreditu. Pak potvrďte „Potvrdit a zaplatit“.`, 'info');
                return;
            }

            if (!window.confirm(`Naplánovat změnu plánu na ${targetPlan.toUpperCase()} od dalšího období?`)) {
                return;
            }
            try {
                await apiCall('/api/v1/license/subscription/change-plan', 'POST', { plan: targetPlan });
                showAlert(`Změna plánu na ${targetPlan.toUpperCase()} byla naplánována od dalšího období.`, 'success');
                select.value = '';
                await loadLicenseStatus();
            } catch (error) {
                showAlert(`Nepodařilo se naplánovat změnu plánu: ${error.message || error}`, 'error');
            }
        }

        function startLicenseRefresh() {
            if (licenseRefreshTimer) return;
            licenseRefreshTimer = setInterval(() => {
                const navbar = document.getElementById('mainNavbar');
                if (accessToken && navbar && !navbar.classList.contains('hidden')) {
                    loadLicenseStatus();
                }
            }, 60000);
        }

        function stopLicenseRefresh() {
            if (licenseRefreshTimer) {
                clearInterval(licenseRefreshTimer);
                licenseRefreshTimer = null;
            }
        }

        async function upgradeLicensePlan(plan, button, options = {}) {
            const planKey = (plan || '').toLowerCase();
            const apiUrl = getApiBaseUrl();
            const skipConsentCheck = !!options?.skipConsentCheck;
            const deferPaidCheckoutToConsent = options?.deferPaidCheckoutToConsent !== false;

            if (!planKey || !["free", "basic", "premium"].includes(planKey)) {
                showAlert("Neplatný plán pro upgrade.", "error");
                return;
            }

            if (!accessToken) {
                showAlert("Musíte být přihlášen(a).", "warning");
                return;
            }

            let originalText = null;
            if (button) {
                originalText = button.textContent;
                button.disabled = true;
                button.textContent = "Probíhá...";
            }

            try {
                const isPaidPlan = planKey === 'basic' || planKey === 'premium';
                const currentPlan = normalizeLicensePlanKey(currentLicensePlanForUi);
                const subscriptionState = currentLicenseSubscriptionForUi && typeof currentLicenseSubscriptionForUi === 'object'
                    ? currentLicenseSubscriptionForUi
                    : null;
                const subscriptionStatus = String(subscriptionState?.status || '').toLowerCase();
                const hasManagedSubscription = !!(subscriptionState && subscriptionStatus && subscriptionStatus !== 'legacy_manual');
                if (isPaidPlan) {
                    // Paid -> paid změna se u aktivního subscription neplatí hned, ale plánuje od dalšího období.
                    if (
                        hasManagedSubscription
                        && currentPlan !== 'free'
                        && currentPlan !== planKey
                    ) {
                        await apiCall('/api/v1/license/subscription/change-plan', 'POST', { plan: planKey });
                        showAlert(`Změna plánu na ${planKey.toUpperCase()} byla naplánována od dalšího období.`, 'success');
                        await loadLicenseStatus();
                        return;
                    }
                    if (currentPlan === planKey) {
                        showAlert(`Plán ${planKey.toUpperCase()} už je aktivní.`, 'info');
                        return;
                    }

                    if (deferPaidCheckoutToConsent && !skipConsentCheck) {
                        showLicenseLegalConsentForPaidPlan(planKey);
                        showAlert(`Vybraný plán ${planKey.toUpperCase()}. Zaškrtněte souhlasy a klikněte na „Potvrdit a zaplatit“.`, 'info');
                        return;
                    }

                    if (!skipConsentCheck && !hasAcceptedPaidPlanLegalConsent(true)) {
                        return;
                    }
                    const comgateConfig = await loadComgateLicenseConfig();
                    const billingPeriod = normalizeLicenseBillingPeriod(selectedLicenseBillingPeriod);
                    const planPrice = resolveComgatePlanPrice(comgateConfig, planKey, billingPeriod);
                    const paymentEnabled = !!(comgateConfig && comgateConfig.enabled);
                    if (!paymentEnabled || !Number.isFinite(planPrice) || planPrice <= 0) {
                        throw new Error(
                            'Online platby zatím nejsou připravené. Dokončete nastavení brány v administraci.'
                        );
                    }
                    if (button) {
                        button.textContent = "Přesměrování na platbu…";
                    }
                    const quote = await apiCall('/api/v1/license/mobile/quote', 'POST', {plan: planKey, billing_period: billingPeriod});
                    const priceText = new Intl.NumberFormat('cs-CZ', {style:'currency', currency:quote.currency}).format(quote.amount_halers / 100);
                    if (!window.confirm(`${quote.test_mode ? 'TESTOVACÍ PLATBA. ' : ''}Objednat ${planKey.toUpperCase()} za ${priceText}? ${quote.recurring ? 'Platba se opakuje podle zvoleného období až do vypnutí prodlužování.' : 'Jednorázová úhrada bez automatického prodlužování.'}`)) return;
                    const key = 'billing-order-' + String(currentUser?.email || '') + '-' + planKey + '-' + billingPeriod;
                    let requestId = sessionStorage.getItem(key);
                    if (!requestId) { requestId = crypto.randomUUID(); sessionStorage.setItem(key, requestId); }
                    const checkoutPayload = await apiCall('/api/v1/license/mobile/checkout', 'POST', {
                        plan: planKey, billing_period: quote.billing_period, request_id: requestId,
                        expected_amount_halers: quote.amount_halers, expected_currency: quote.currency,
                        expected_test_mode: quote.test_mode, contract_version: quote.contract_version,
                        expected_recurring: quote.recurring,
                        accept_terms: !!document.getElementById('licenseAgreeTerms')?.checked,
                        accept_immediate_service: !!document.getElementById('licenseAgreeDigitalStart')?.checked,
                        accept_recurring: quote.recurring && !!document.getElementById('licenseAgreeDigitalStart')?.checked,
                    });
                    sessionStorage.removeItem(key);
                    const requiresPayment = !(checkoutPayload && checkoutPayload.requires_payment === false);
                    if (!requiresPayment) {
                        hideLicenseLegalConsentForPaidPlan();
                        showAlert(
                            checkoutPayload?.message || 'Změna plánu byla provedena bez dodatečné platby (započten kredit/přeplatek).',
                            'success'
                        );
                        await loadLicenseStatus();
                        return;
                    }
                    const redirectUrl = safeLegacyURL(checkoutPayload?.redirect_url);
                    if (!redirectUrl) {
                        throw new Error('Comgate nevrátil přesměrování na platební bránu.');
                    }
                    hideLicenseLegalConsentForPaidPlan();
                    window.location.assign(redirectUrl);
                    return;
                }

                // Paid -> FREE změna: plánuje se k datu konce aktuálního období.
                if (planKey === 'free' && hasManagedSubscription && currentPlan !== 'free') {
                    await apiCall('/api/v1/license/subscription/change-plan', 'POST', { plan: 'free' });
                    showAlert('Přechod na FREE byl naplánován k datu konce aktuálního období.', 'success');
                    await loadLicenseStatus();
                    return;
                }

                const upgradeHeaders = {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Accept-Language': 'cs-CZ,cs;q=0.9,en;q=0.8',
                    'Authorization': `Bearer ${accessToken}`
                };
                appendClientGeoHeaders(upgradeHeaders);

                const response = await AdminBrowserSession.request(`${apiUrl}/api/v1/license/upgrade`, {
                    method: 'POST',
                    headers: upgradeHeaders,
                    credentials: 'include',
                    mode: 'cors',
                    cache: 'no-cache',
                    body: JSON.stringify({ plan: planKey })
                });

                const contentType = response.headers.get('content-type') || '';
                const isJson = contentType.includes('application/json');
                const data = isJson ? await response.json() : null;

                if (response.status === 401) {
                    showAlert("Nejste přihlášen(a). Přihlaste se a zkuste znovu.", "warning");
                    return;
                }

                if (response.status === 403) {
                    showAlert("Nemáte oprávnění k upgradu pro tento účet.", "warning");
                    return;
                }

                if (!response.ok) {
                    const detail = data?.detail || data?.message || `HTTP ${response.status}`;
                    showAlert(`Nepodařilo se změnit licenci: ${detail}`, "error");
                    return;
                }

                const appliedPlan = (data?.plan || data?.data?.plan || planKey).toString().toUpperCase();
                if (appliedPlan !== planKey.toUpperCase()) {
                    showAlert(`Licence nastavena na ${appliedPlan} (požadováno ${planKey.toUpperCase()})`, "warning");
                } else {
                    showAlert(`Licence změněna na ${appliedPlan}`, "success");
                }
                closeLicenseModal();
                await loadLicenseStatus();
            } catch (e) {
                showAlert(`Nepodařilo se změnit licenci: ${e.message || e}`, "error");
            } finally {
                if (button) {
                    button.disabled = false;
                    if (originalText !== null) {
                        button.textContent = originalText;
                    }
                }
            }
        }

        // LICENSE_UI_START: Renderování licence do TopBar menu
        function renderLicenseMenu(license) {
            // Kontrola autentizace - pokud není přihlášený, nezobrazovat licence
            if (!isAuthenticated()) {
                console.warn("[LICENSE] Uživatel není přihlášen - nesmí se zobrazit licence");
                closeLicenseModal();
                return;
            }

            const labelEl = document.getElementById("licenseQuickLabel");
            const currentEl = document.getElementById("licenseQuickCurrent");
            const vehiclesEl = document.getElementById("licenseQuickVehicles");
            const featuresEl = document.getElementById("licenseQuickFeatures");

            if (!labelEl || !currentEl || !vehiclesEl || !featuresEl) {
                return;
            }

            const plan = (license.plan || "UNKNOWN").toString().toUpperCase();
            const tenantCurrent = Number(license.vehicles_current ?? 0);
            const userCurrentRaw = license.vehicles_current_user;
            const hasUserCurrent = userCurrentRaw !== null
                && userCurrentRaw !== undefined
                && !Number.isNaN(Number(userCurrentRaw));
            const userCurrent = hasUserCurrent ? Number(userCurrentRaw) : tenantCurrent;
            const limit = Number(license.vehicles_limit ?? 0);
            const unlimited = !!license.is_unlimited;
            const hasDifferentUserCount = hasUserCurrent && userCurrent !== tenantCurrent;

            labelEl.textContent = `Licence: ${plan}`;
            currentEl.textContent = `Aktuální plán: ${plan}`;

            if (unlimited || limit === 0) {
                if (hasDifferentUserCount) {
                    vehiclesEl.textContent = `Vozidla: Neomezeně (${userCurrent} vaše / ${tenantCurrent} v tenantu)`;
                } else {
                    vehiclesEl.textContent = `Vozidla: Neomezeně (${tenantCurrent} aktuálně)`;
                }
            } else {
                if (hasDifferentUserCount) {
                    vehiclesEl.textContent = `Vozidla: ${tenantCurrent} / ${limit} (vaše: ${userCurrent})`;
                } else {
                    vehiclesEl.textContent = `Vozidla: ${tenantCurrent} / ${limit}`;
                }
            }

            const quickItems = document.querySelectorAll('.license-quick-item');
            quickItems.forEach(item => {
                const itemPlan = (item.getAttribute('data-plan') || '').toUpperCase();
                const flag = item.querySelector('.license-quick-current-flag');
                const upgradeBtn = item.querySelector('.license-quick-upgrade');
                if (itemPlan === plan) {
                    if (flag) flag.classList.remove('hidden');
                    if (upgradeBtn) {
                        upgradeBtn.disabled = true;
                        upgradeBtn.textContent = 'Aktuální';
                    }
                } else {
                    if (flag) flag.classList.add('hidden');
                    if (upgradeBtn) {
                        upgradeBtn.disabled = false;
                        upgradeBtn.textContent = 'Upgradovat';
                    }
                }
            });

            const featureKeys = Object.keys(license || {}).filter(key => key.endsWith('_enabled'));
            if (featureKeys.length === 0) {
                featuresEl.innerHTML = '<div class="license-quick-feature">Funkce: neuvedeno</div>';
            } else {
                featuresEl.innerHTML = featureKeys.map(key => {
                    const enabled = !!license[key];
                    const rawLabel = key.replace('_enabled', '').replace(/_/g, ' ');
                    const label = rawLabel.charAt(0).toUpperCase() + rawLabel.slice(1);
                    const icon = enabled ? '✓' : '✕';
                    const iconClass = enabled ? 'license-quick-flag' : 'license-quick-flag off';
                    const statusText = enabled ? 'Zapnuto' : 'Vypnuto';
                    return `<div class="license-quick-feature"><span class="${iconClass}">${icon}</span><span>${escapeHtml(label)} — ${statusText}</span></div>`;
                }).join('');
            }

            // Aktualizovat modal pouze pokud je uživatel přihlášený
            if (isAuthenticated() && typeof updateLicenseModal === 'function') {
                updateLicenseModal(license);
            }

        }

        function ensureLicenseModalRoot() {
            const modal = document.getElementById("licenseModal");
            if (!modal) return null;

            // Pro jistotu držet modal přímo pod <body>, aby nebyl ovlivněn layoutem tabů.
            if (modal.parentElement !== document.body) {
                document.body.appendChild(modal);
            }

            // Dodatečné runtime jištění pro mobilní browsery.
            modal.style.setProperty('position', 'fixed', 'important');
            modal.style.setProperty('inset', '0', 'important');
            modal.style.setProperty('z-index', '2147483640', 'important');
            return modal;
        }

        // LICENSE_UI_START: Otevření/zavření license modalu
        function openLicensePlans() {
            // Kontrola, jestli je uživatel přihlášený
            if (!isAuthenticated()) {
                console.warn("[LICENSE] Uživatel není přihlášen - zobrazuji přihlašovací okno");
                showLogin();
                return;
            }

            if (typeof loadComgateLicenseConfig === 'function') {
                loadComgateLicenseConfig().catch((error) => {
                    console.warn("[LICENSE] Comgate config refresh failed:");
                });
            }

            const dropdown = document.getElementById('licenseQuickDropdown');
            if (dropdown) {
                dropdown.classList.add('hidden');
            }
            const modal = ensureLicenseModalRoot();
            if (modal) {
                syncLicenseBillingButtons();
                applyComgateUiConfig(comgateConfigCache);
                resetLicenseLegalConsent();
                openStaticOverlayModal(modal, {
                    scrollTargetSelector: '.license-modal-body',
                    focusSelector: '#licenseBillingToggle .license-billing-btn.active',
                });
                return;
            }
            showAlert("Plány nejsou dostupné v této verzi.", "info");
        }

        function openLicenseModal() {
            // Kontrola, jestli je uživatel přihlášený
            if (!isAuthenticated()) {
                console.warn("[LICENSE] Uživatel není přihlášen - zobrazuji přihlašovací okno");
                showLogin();
                return;
            }

            const modal = ensureLicenseModalRoot();
            if (!modal) return;
            syncLicenseBillingButtons();
            applyComgateUiConfig(comgateConfigCache);
            resetLicenseLegalConsent();
            openStaticOverlayModal(modal, {
                scrollTargetSelector: '.license-modal-body',
                focusSelector: '#licenseBillingToggle .license-billing-btn.active',
            });
        }

        function closeLicenseModal() {
            const modal = document.getElementById("licenseModal");
            if (!modal) return;
            closeStaticOverlayModal(modal);
        }

        // LICENSE_UI_START: Aktualizace license modalu
        function updateLicenseModal(license) {
            // Kontrola autentizace - pokud není přihlášený, modal nesmí být viditelný
            if (!isAuthenticated()) {
                console.warn("[LICENSE] Uživatel není přihlášen - modal musí být skrytý");
                closeLicenseModal();
                return;
            }

            const currentBadge = document.getElementById('licenseCurrentBadge');
            const currentDetails = document.getElementById('licenseCurrentDetails');
            const planCards = document.querySelectorAll('.license-plan-card');

            if (!currentBadge || !currentDetails) return;

            const plan = (license.plan || "unknown").toLowerCase();
            const planUpper = plan.toUpperCase();
            currentLicensePlanForUi = normalizeLicensePlanKey(plan);
            currentLicenseSubscriptionForUi = license?.subscription && typeof license.subscription === 'object'
                ? license.subscription
                : null;
            const status = license.status || "unknown";
            const tenantCurrent = Number(license.vehicles_current ?? 0);
            const userCurrentRaw = license.vehicles_current_user;
            const hasUserCurrent = userCurrentRaw !== null
                && userCurrentRaw !== undefined
                && !Number.isNaN(Number(userCurrentRaw));
            const userCurrent = hasUserCurrent ? Number(userCurrentRaw) : tenantCurrent;
            const limit = Number(license.vehicles_limit ?? 0);
            const unlimited = !!license.is_unlimited;
            const hasDifferentUserCount = hasUserCurrent && userCurrent !== tenantCurrent;

            // Aktualizovat badge
            const planBadge = currentBadge.querySelector('.license-plan-badge');
            const statusBadge = currentBadge.querySelector('.license-status-badge');

            if (planBadge) {
                planBadge.textContent = planUpper;
                planBadge.className = `license-plan-badge plan-${plan}`;
            }
            if (statusBadge) {
                statusBadge.textContent = status === 'active' ? 'Aktivní' : status;
                statusBadge.className = `license-status-badge status-${status}`;
            }

            // Aktualizovat detaily (kompaktní režim vedle názvu modalu).
            let vehicleSummary = '';
            if (unlimited || limit === 0) {
                if (hasDifferentUserCount) {
                    vehicleSummary = `Vozidla neomezeně · vaše ${userCurrent} / tenant ${tenantCurrent}`;
                } else {
                    vehicleSummary = `Vozidla neomezeně · evidováno ${tenantCurrent}`;
                }
            } else {
                const remaining = license.vehicles_remaining ?? Math.max(0, limit - tenantCurrent);
                vehicleSummary = `Vozidla ${tenantCurrent}/${limit}`;
                if (hasDifferentUserCount) {
                    vehicleSummary += ` · vaše ${userCurrent}`;
                }
                if (remaining > 0) {
                    vehicleSummary += ` · <span class="license-remaining">zbývá ${escapeHtml(remaining)}</span>`;
                } else {
                    vehicleSummary += ` · <span class="license-limit-reached">limit dosažen</span>`;
                }
            }

            // Feature flags
            const features = [];
            if (license.vin_decode_enabled) features.push('VIN dekódování');
            if (license.ares_enabled) features.push('ARES lookup');
            if (license.reminders_enabled) features.push('Připomínky');

            const detailChunks = [`<span class="license-detail-item">${vehicleSummary}</span>`];
            if (features.length > 0) {
                const visibleFeatures = features.slice(0, 2);
                const extraFeatures = Math.max(0, features.length - visibleFeatures.length);
                const featuresSummary = `${visibleFeatures.join(', ')}${extraFeatures > 0 ? ` +${extraFeatures}` : ''}`;
                detailChunks.push(`<span class="license-detail-item">Funkce: ${escapeHtml(featuresSummary)}</span>`);
            }

            if (currentDetails) {
                currentDetails.innerHTML = detailChunks.join('');
            }

            // Aktualizovat stav tlačítek v plánech
            const planOrder = { free: 1, basic: 2, premium: 3 };
            const currentOrder = planOrder[plan] || 0;

            planCards.forEach(card => {
                const cardPlan = card.getAttribute('data-plan');
                const actionBtn = card.querySelector('.plan-action-btn');
                const cardOrder = planOrder[cardPlan] || 0;
                const isCurrent = cardPlan === plan;

                if (!actionBtn) return;

                if (isCurrent) {
                    card.classList.add('plan-current');
                    actionBtn.disabled = true;
                    actionBtn.classList.remove('plan-upgrade');
                    actionBtn.classList.add('plan-active');
                    actionBtn.textContent = 'Aktuální plán';
                } else {
                    card.classList.remove('plan-current');
                    actionBtn.disabled = false;
                    actionBtn.classList.remove('plan-active');
                    actionBtn.classList.add('plan-upgrade');
                    actionBtn.textContent = cardOrder < currentOrder ? 'Snížit plán' : 'Upgradovat';
                }
            });

            renderLicenseSubscriptionPanel(currentLicenseSubscriptionForUi, currentLicensePlanForUi);

            // Ceny a payment-ready stav se dopočítají podle aktivní konfigurace Comgate.
            applyComgateUiConfig(comgateConfigCache);
        }

        // LICENSE_UI_START: Inicializace event handlerů
        let licenseHandlersInitialized = false;
        function initLicenseDropdownHandlers() {
            if (licenseHandlersInitialized) return;
            licenseHandlersInitialized = true;

            // Kliknutí na tlačítka upgrade v modalu
            document.addEventListener('click', function(e) {
                const cancelSubscriptionBtn = e.target.closest('#licenseSubscriptionCancelBtn');
                if (cancelSubscriptionBtn) {
                    e.preventDefault();
                    e.stopPropagation();
                    cancelLicenseSubscription();
                    return;
                }

                const resumeSubscriptionBtn = e.target.closest('#licenseSubscriptionResumeBtn');
                if (resumeSubscriptionBtn) {
                    e.preventDefault();
                    e.stopPropagation();
                    resumeLicenseSubscription();
                    return;
                }

                const changeSubscriptionBtn = e.target.closest('#licenseSubscriptionChangePlanBtn');
                if (changeSubscriptionBtn) {
                    e.preventDefault();
                    e.stopPropagation();
                    scheduleLicenseSubscriptionPlanChange();
                    return;
                }

                const confirmPaidPlanBtn = e.target.closest('#licenseConfirmPaidPlanBtn');
                if (confirmPaidPlanBtn) {
                    e.preventDefault();
                    e.stopPropagation();
                    confirmLicensePaidPlanCheckout(confirmPaidPlanBtn);
                    return;
                }

                const cancelPaidPlanBtn = e.target.closest('#licenseCancelPaidPlanBtn');
                if (cancelPaidPlanBtn) {
                    e.preventDefault();
                    e.stopPropagation();
                    hideLicenseLegalConsentForPaidPlan();
                    showAlert('Výběr placeného plánu byl zrušen.', 'info');
                    return;
                }

                const billingBtn = e.target.closest('.license-billing-btn');
                if (billingBtn) {
                    e.preventDefault();
                    e.stopPropagation();
                    setLicenseBillingPeriod(billingBtn.getAttribute('data-period') || 'monthly');
                    return;
                }

                const upgradeBtn = e.target.closest('.plan-action-btn.plan-upgrade');
                if (upgradeBtn) {
                    e.stopPropagation();
                    const planCard = upgradeBtn.closest('.license-plan-card');
                    const plan = planCard?.getAttribute('data-plan');
                    if (plan) {
                        upgradeLicensePlan(plan, upgradeBtn);
                    } else {
                        showAlert("Nepodařilo se zjistit plán k upgradu.", "error");
                    }
                }
            });

            const termsCheckbox = document.getElementById('licenseAgreeTerms');
            const digitalStartCheckbox = document.getElementById('licenseAgreeDigitalStart');
            if (termsCheckbox) {
                termsCheckbox.addEventListener('change', syncLicensePaidPlanConsentState);
            }
            if (digitalStartCheckbox) {
                digitalStartCheckbox.addEventListener('change', syncLicensePaidPlanConsentState);
            }

            // Zavřít modal při kliknutí na overlay nebo ESC
            document.addEventListener('keydown', function(e) {
                if (e.key === 'Escape') {
                    closeLicenseModal();
                }
            });
        }

        // LICENSE_UI_START: Debug panel update - DEAKTIVOVÁNO (panel je skrytý)
        function updateLicenseDebugPanel() {
            // Debug panel je skrytý - funkce deaktivována
            return;
        }

        // LICENSE_UI_START: Vykreslení licenčního badge
        function renderLicenseBadge(license) {
            const badge = document.getElementById('licenseBadge');
            const planEl = document.getElementById('licensePlan');
            const vehiclesEl = document.getElementById('licenseVehicles');
            const remainingEl = document.getElementById('licenseRemaining');
            const upgradeBtn = document.getElementById('licenseUpgradeBtn');

            if (!badge || !planEl || !vehiclesEl || !remainingEl) {
                console.warn("[LICENSE] License badge elements not found");
                return;
            }

            // Barvy podle plánu
            const planColors = {
                'free': { bg: '#f1f5f9', border: '#e2e8f0', text: '#64748b' },
                'basic': { bg: '#eff6ff', border: '#bfdbfe', text: '#1e40af' },
                'premium': { bg: '#fef3c7', border: '#fde68a', text: '#92400e' }
            };

            const colors = planColors[license.plan] || planColors.free;
            badge.style.background = colors.bg;
            badge.style.borderColor = colors.border;

            // Plan text
            const planText = license.plan.toUpperCase();
            const statusText = license.status === 'active' ? 'active' : license.status;
            planEl.textContent = `Licence: ${planText} (${statusText})`;
            planEl.style.color = colors.text;

            // Vehicles text
            const tenantCurrent = Number(license.vehicles_current ?? 0);
            const userCurrentRaw = license.vehicles_current_user;
            const hasUserCurrent = userCurrentRaw !== null
                && userCurrentRaw !== undefined
                && !Number.isNaN(Number(userCurrentRaw));
            const userCurrent = hasUserCurrent ? Number(userCurrentRaw) : tenantCurrent;
            const hasDifferentUserCount = hasUserCurrent && userCurrent !== tenantCurrent;

            if (license.is_unlimited) {
                if (hasDifferentUserCount) {
                    vehiclesEl.textContent = `Vozidla: ${userCurrent} vaše / ${tenantCurrent} tenant`;
                } else {
                    vehiclesEl.textContent = `Vozidla: ${tenantCurrent}/∞`;
                }
            } else {
                if (hasDifferentUserCount) {
                    vehiclesEl.textContent = `Vozidla: ${tenantCurrent}/${license.vehicles_limit} (vaše: ${userCurrent})`;
                } else {
                    vehiclesEl.textContent = `Vozidla: ${tenantCurrent}/${license.vehicles_limit}`;
                }
            }

            // Remaining text
            if (license.is_unlimited) {
                remainingEl.textContent = '';
            } else {
                const remaining = license.vehicles_remaining || 0;
                if (remaining > 0) {
                    remainingEl.textContent = `• Zbývá: ${remaining}`;
                } else {
                    remainingEl.textContent = '• Limit dosažen';
                    remainingEl.style.color = '#dc2626';
                }
            }

            // Upgrade button (zobrazit pokud není premium)
            if (upgradeBtn) {
                if (license.plan !== 'premium') {
                    upgradeBtn.style.display = 'inline-block';
                } else {
                    upgradeBtn.style.display = 'none';
                }
            }

            // Zobrazit badge
            badge.style.display = 'block';
        }

        // LICENSE_UI_START: Zobrazení banneru při překročení limitu
        function showLicenseQuotaBanner(error) {
            const details = error.details || {};
            const plan = details.plan || 'free';
            const current = details.current || 0;
            const limit = details.limit || 1;

            const message = `Limit vozidel překročen (${current}/${limit}). Zvažte upgrade licence.`;

            if (typeof showAlert === 'function') {
                showAlert(message, 'error');
            } else {
                // Fallback - vytvořit banner
                const banner = document.createElement('div');
                banner.style.cssText = 'position: fixed; top: 20px; right: 20px; background: #fee2e2; border: 1px solid #fecaca; color: #991b1b; padding: 16px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); z-index: 10000; max-width: 400px;';
                banner.innerHTML = `
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <div>
                            <strong>Limit vozidel překročen</strong>
                            <p style="margin: 8px 0 0 0; font-size: 0.9em;">${escapeHtml(message)}</p>
                        </div>
                        <button ${legacyActionAttributes("click", "remove_9744c335")} style="background: none; border: none; font-size: 20px; cursor: pointer; color: #991b1b; padding: 0; margin-left: 12px;">×</button>
                    </div>
                `;
                document.body.appendChild(banner);

                // Auto-remove po 10 sekundách
                setTimeout(() => {
                    if (banner.parentElement) {
                        banner.remove();
                    }
                }, 10000);
            }
        }

        // LICENSE_UI_START: Upgrade modal (placeholder)
        function showUpgradeModal() {
            if (typeof showAlert === 'function') {
                showAlert('Kontaktujte TooZServis pro změnu licence.', 'info');
            } else {
                alert('Kontaktujte TooZServis pro změnu licence.');
            }
        }
        // LICENSE_UI_END

        // Pomocná funkce pro zobrazení chyby s retry tlačítkem
        function showErrorWithRetry(containerId, errorMessage, retryFunction) {
            const container = document.getElementById(containerId);
            if (!container) return;
            const box = document.createElement('div');
            box.className = 'alert alert-error';
            const text = document.createElement('p');
            text.textContent = 'Chyba: ' + String(errorMessage || '');
            const retry = document.createElement('button');
            retry.className = 'btn'; retry.type = 'button'; retry.textContent = 'Zkusit znovu';
            retry.addEventListener('click', retryFunction);
            box.append(text, retry); container.replaceChildren(box);
        }

        // UI preference keys: sprava_vozidel_* (legacy toozhub_* čte SpravaVozidelStorage)
        const UI_SECTION_CACHE_TTL_MS = 60 * 1000;
        let reminderNotificationHeartbeatTimer = null;
        const vehiclesUiState = {
            loadedAt: 0,
            loadingPromise: null,
            ownerKey: ''
        };
        const remindersUiState = {
            items: [],
            filteredItems: [],
            loadedAt: 0,
            loadingPromise: null,
            ownerKey: ''
        };

        function getUiCacheOwnerKey() {
            if (!isAuthenticated()) return 'anonymous';
            return `${currentUser?.id || 0}:${currentUser?.email || ''}:${currentUser?.role || ''}`;
        }

        function isUiSectionCacheFresh(state, ttlMs = UI_SECTION_CACHE_TTL_MS) {
            const loadedAt = Number(state?.loadedAt || 0);
            return loadedAt > 0
                && state?.ownerKey === getUiCacheOwnerKey()
                && (Date.now() - loadedAt) < ttlMs;
        }

        function markUiSectionLoaded(state) {
            state.loadedAt = Date.now();
            state.ownerKey = getUiCacheOwnerKey();
        }

        function deferNonCriticalUiTask(label, task, delayMs = 0) {
            const run = () => {
                const start = performance.now();
                Promise.resolve()
                    .then(task)
                    .catch((error) => {
                        console.warn("Klientskou operaci se nepodařilo dokončit.");
                    })
                    .finally(() => {
                        const duration = Math.round(performance.now() - start);

                    });
            };

            if (delayMs > 0) {
                window.setTimeout(run, delayMs);
                return;
            }

            if (typeof window.requestIdleCallback === 'function') {
                window.requestIdleCallback(run, { timeout: 1200 });
                return;
            }

            window.setTimeout(run, 32);
        }

        function getDefaultVehicleViewMode() {
            try {
                if (window.matchMedia && window.matchMedia('(max-width: 768px)').matches) {
                    return 'list';
                }
            } catch (e) {
                // ignore matchMedia issues and fallback below
            }
            return 'grid';
        }

        function getVehicleViewMode() {
            const mode = (typeof SpravaVozidelStorage !== 'undefined'
                ? SpravaVozidelStorage.getLocal('vehicleViewMode')
                : localStorage.getItem('toozhub_vehicle_view_mode')) || getDefaultVehicleViewMode();
            if (mode === 'grid' || mode === 'list' || mode === 'compact') {
                return mode;
            }
            return getDefaultVehicleViewMode();
        }

        function getVehicleStkStatusMeta(stkDateValue) {
            if (!(stkDateValue instanceof Date) || Number.isNaN(stkDateValue.getTime())) {
                return { className: 'stk-unknown', label: 'Platnost STK neznámá' };
            }

            const today = new Date();
            today.setHours(0, 0, 0, 0);

            const validUntil = new Date(stkDateValue.getTime());
            validUntil.setHours(0, 0, 0, 0);

            const diffDays = Math.ceil((validUntil.getTime() - today.getTime()) / 86400000);
            if (diffDays < 0) {
                return { className: 'stk-expired', label: 'Prošlá STK' };
            }
            if (diffDays <= 60) {
                const daysWord = diffDays === 1 ? 'den' : ((diffDays >= 2 && diffDays <= 4) ? 'dny' : 'dní');
                const verb = (diffDays >= 2 && diffDays <= 4) ? 'zbývají' : 'zbývá';
                return {
                    className: 'stk-soon',
                    label: `STK brzy - ${verb} ${diffDays} ${daysWord}`,
                    daysRemaining: diffDays
                };
            }
            return { className: 'stk-ok', label: 'STK OK' };
        }

        function applyVehicleViewModeUI() {
            const selectedMode = getVehicleViewMode();
            document.querySelectorAll('.vehicle-view-btn').forEach((button) => {
                const isActive = button.getAttribute('data-view') === selectedMode;
                button.classList.toggle('active', isActive);
                button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
            });

            const modeNote = document.getElementById('vehicleViewModeNote');
            if (modeNote) {
                const modeDescriptions = {
                    grid: 'Mřížka: barevné karty s SPZ, STK a motorem pro detailní přehled.',
                    list: 'Seznam: rychlé řádky Název + SPZ s barevným stavem STK.',
                    compact: 'Kompaktní: čisté karty s SPZ, značkou/model a STK pro rychlé ovládání.'
                };
                modeNote.textContent = modeDescriptions[selectedMode] || '';
            }

            const wrapper = document.querySelector('#vehiclesContainer .vehicle-view');
            if (wrapper) {
                wrapper.classList.remove('vehicle-view-grid', 'vehicle-view-list', 'vehicle-view-compact');
                wrapper.classList.add(`vehicle-view-${selectedMode}`);
            }
        }

        function setVehicleView(mode) {
            if (!['grid', 'list', 'compact'].includes(mode)) {
                return;
            }

            const currentMode = getVehicleViewMode();
            if (currentMode === mode) {
                return;
            }

            if (typeof SpravaVozidelStorage !== 'undefined') {
                SpravaVozidelStorage.setLocal('vehicleViewMode', mode);
            } else {
                localStorage.setItem('sprava_vozidel_vehicle_view_mode', mode);
                localStorage.removeItem('toozhub_vehicle_view_mode');
            }
            // Re-render je nutný, protože každý režim má odlišné HTML karty.
            // Pouhé přepnutí CSS třídy nestačí (hlavně mezi compact a list/grid).
            applyVehicleViewModeUI();
            loadVehicles(false);
        }

        function getDefaultReminderViewMode() {
            try {
                if (window.matchMedia && window.matchMedia('(max-width: 768px)').matches) {
                    return 'compact';
                }
            } catch (e) {
                // ignore matchMedia issues and fallback below
            }
            return 'grid';
        }

        function getReminderViewMode() {
            const mode = (typeof SpravaVozidelStorage !== 'undefined'
                ? SpravaVozidelStorage.getLocal('reminderViewMode')
                : localStorage.getItem('toozhub_reminder_view_mode')) || getDefaultReminderViewMode();
            if (mode === 'grid' || mode === 'list' || mode === 'compact' || mode === 'calendar') {
                return mode;
            }
            return getDefaultReminderViewMode();
        }

        function getReminderFilterMode() {
            const mode = String((typeof SpravaVozidelStorage !== 'undefined'
                ? SpravaVozidelStorage.getLocal('reminderFilterMode')
                : localStorage.getItem('toozhub_reminder_filter_mode')) || 'active').toLowerCase();
            if (mode === 'all' || mode === 'active' || mode === 'expired' || mode === 'completed') {
                return mode;
            }
            return 'active';
        }

        function setReminderFilter(mode) {
            const normalized = String(mode || '').toLowerCase();
            if (!['all', 'active', 'expired', 'completed'].includes(normalized)) {
                return;
            }
            if (normalized === getReminderFilterMode()) return;
            if (typeof SpravaVozidelStorage !== 'undefined') {
                SpravaVozidelStorage.setLocal('reminderFilterMode', normalized);
            } else {
                localStorage.setItem('sprava_vozidel_reminder_filter_mode', normalized);
                localStorage.removeItem('toozhub_reminder_filter_mode');
            }
            loadReminders(false);
        }

        function getReminderCalendarMonthDate() {
            const stored = String((typeof SpravaVozidelStorage !== 'undefined'
                ? SpravaVozidelStorage.getLocal('reminderCalendarMonth')
                : localStorage.getItem('toozhub_reminder_calendar_month')) || '').trim();
            const match = stored.match(/^(\d{4})-(\d{2})$/);
            if (match) {
                const year = Number(match[1]);
                const month = Number(match[2]);
                if (Number.isFinite(year) && Number.isFinite(month) && month >= 1 && month <= 12) {
                    return new Date(year, month - 1, 1);
                }
            }
            const now = new Date();
            return new Date(now.getFullYear(), now.getMonth(), 1);
        }

        function persistReminderCalendarMonth(dateObj) {
            if (!(dateObj instanceof Date) || Number.isNaN(dateObj.getTime())) return;
            const year = dateObj.getFullYear();
            const month = String(dateObj.getMonth() + 1).padStart(2, '0');
            if (typeof SpravaVozidelStorage !== 'undefined') {
                SpravaVozidelStorage.setLocal('reminderCalendarMonth', `${year}-${month}`);
            } else {
                localStorage.setItem('sprava_vozidel_reminder_calendar_month', `${year}-${month}`);
                localStorage.removeItem('toozhub_reminder_calendar_month');
            }
        }

        function shiftReminderCalendarMonth(deltaMonths) {
            const base = getReminderCalendarMonthDate();
            base.setMonth(base.getMonth() + Number(deltaMonths || 0));
            base.setDate(1);
            persistReminderCalendarMonth(base);
            loadReminders(false);
        }

        function parseReminderDateValue(rawValue, endOfDay = false) {
            if (!rawValue) return null;
            if (rawValue instanceof Date && !Number.isNaN(rawValue.getTime())) {
                return new Date(rawValue.getTime());
            }
            if (typeof rawValue === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(rawValue)) {
                const parsed = new Date(`${rawValue}T${endOfDay ? '23:59:59' : '00:00:00'}`);
                return Number.isNaN(parsed.getTime()) ? null : parsed;
            }
            const parsed = new Date(rawValue);
            return Number.isNaN(parsed.getTime()) ? null : parsed;
        }

        function getReminderReferenceDate(reminder) {
            const notifyAtDate = parseReminderDateValue(reminder?.notify_at, false);
            if (notifyAtDate) return notifyAtDate;
            return parseReminderDateValue(reminder?.due_date, true);
        }

        function getReminderStatusMeta(reminder) {
            if (reminder?.is_completed === true) {
                return {
                    key: 'completed',
                    label: 'Dokončeno',
                    className: 'completed',
                    accent: '#10b981',
                    daysTo: null,
                };
            }

            const reference = getReminderReferenceDate(reminder);
            if (!reference) {
                return {
                    key: 'active',
                    label: 'Aktivní',
                    className: 'active',
                    accent: '#2563eb',
                    daysTo: null,
                };
            }

            const now = new Date();
            const diffMs = reference.getTime() - now.getTime();
            const daysTo = Math.ceil(diffMs / 86400000);

            if (diffMs < 0) {
                return {
                    key: 'expired',
                    label: 'Propadlé',
                    className: 'expired',
                    accent: '#dc2626',
                    daysTo,
                };
            }

            return {
                key: 'active',
                label: 'Aktivní',
                className: 'active',
                accent: '#2563eb',
                daysTo,
            };
        }

        function getReminderTypePresentation(type) {
            const key = String(type || '').toUpperCase();
            if (key === 'STK') {
                return {
                    label: 'STK',
                    color: '#ef4444',
                    icon: '<span class="reminder-type-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M3 13l2-5h14l2 5"></path><path d="M5 13h14v6H5z"></path><circle cx="8" cy="17" r="1.5"></circle><circle cx="16" cy="17" r="1.5"></circle></svg></span>',
                };
            }
            if (key === 'OLEJ') {
                return {
                    label: 'OLEJ',
                    color: '#f59e0b',
                    icon: '<span class="reminder-type-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 3c3 4 5 6.7 5 10a5 5 0 1 1-10 0c0-3.3 2-6 5-10z"></path></svg></span>',
                };
            }
            if (key === 'VLASTNI') {
                return {
                    label: 'VLASTNÍ',
                    color: '#8b5cf6',
                    icon: '<span class="reminder-type-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M4 4h12l4 4v12H4z"></path><path d="M16 4v4h4"></path><path d="M8 13h8"></path><path d="M8 17h5"></path></svg></span>',
                };
            }
            return {
                label: key || 'OBECNÁ',
                color: '#6366f1',
                icon: '<span class="reminder-type-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M14.7 6.3l3 3"></path><path d="M3 21l4-1 10-10-3-3L4 17l-1 4z"></path></svg></span>',
            };
        }

        function getReminderMethodText(reminder) {
            const method = typeof reminder?.notification_method === 'string'
                ? reminder.notification_method.toLowerCase()
                : '';
            if (method === 'email') return 'E-mail';
            if (method === 'both') return 'Aplikace + e-mail';
            if (method === 'app') return 'Aplikace (push / fallback e-mail)';
            return 'Globální pravidlo';
        }

        function formatReminderDateShort(rawValue, withTime = false) {
            const parsed = parseReminderDateValue(rawValue, false);
            if (!parsed) return '—';
            if (withTime) {
                return `${parsed.toLocaleDateString('cs-CZ')} ${parsed.toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' })}`;
            }
            return parsed.toLocaleDateString('cs-CZ');
        }

        function reminderMatchesFilter(reminder, filterMode) {
            if (filterMode === 'all') return true;
            const status = getReminderStatusMeta(reminder).key;
            if (filterMode === 'completed') return status === 'completed';
            if (filterMode === 'expired') return status === 'expired';
            if (filterMode === 'active') return status === 'active';
            return true;
        }

        function getReminderFilterCounts(reminders) {
            const counts = { all: reminders.length, active: 0, expired: 0, completed: 0 };
            reminders.forEach((reminder) => {
                const key = getReminderStatusMeta(reminder).key;
                if (key === 'active') counts.active += 1;
                else if (key === 'expired') counts.expired += 1;
                else if (key === 'completed') counts.completed += 1;
            });
            return counts;
        }

        function reminderDaysMetaLabel(daysTo) {
            if (!Number.isFinite(daysTo)) return '';
            if (daysTo < 0) {
                const abs = Math.abs(daysTo);
                const word = abs === 1 ? 'dnem' : (abs >= 2 && abs <= 4 ? 'dny' : 'dny');
                return `po termínu ${abs} ${word}`;
            }
            if (daysTo === 0) return 'termín dnes';
            if (daysTo === 1) return 'termín zítra';
            const word = daysTo >= 2 && daysTo <= 4 ? 'dny' : 'dní';
            return `za ${daysTo} ${word}`;
        }

        function applyReminderViewModeUI() {
            const selectedMode = getReminderViewMode();
            document.querySelectorAll('.reminder-view-btn').forEach((button) => {
                const isActive = button.getAttribute('data-view') === selectedMode;
                button.classList.toggle('active', isActive);
                button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
            });

            const modeNote = document.getElementById('reminderViewModeNote');
            if (modeNote) {
                const modeDescriptions = {
                    grid: 'Mřížka: standardní karty připomínek pro detailní přehled.',
                    list: 'Seznam: 1 karta na řádek, rychlé porovnání více položek.',
                    compact: 'Kompaktní: zhuštěné karty, detail otevřete kliknutím.',
                    calendar: 'Kalendář: termíny připomínek po dnech v měsíčním přehledu.'
                };
                modeNote.textContent = modeDescriptions[selectedMode] || '';
            }

            const wrapper = document.querySelector('#remindersContainer .reminders-grid');
            if (wrapper) {
                wrapper.classList.remove('reminder-view-grid', 'reminder-view-list', 'reminder-view-compact');
                if (selectedMode !== 'calendar') {
                    wrapper.classList.add(`reminder-view-${selectedMode}`);
                }
            }
        }

        function setReminderView(mode) {
            if (!['grid', 'list', 'compact', 'calendar'].includes(mode)) {
                return;
            }

            const currentMode = getReminderViewMode();
            if (currentMode === mode) {
                return;
            }

            if (typeof SpravaVozidelStorage !== 'undefined') {
                SpravaVozidelStorage.setLocal('reminderViewMode', mode);
            } else {
                localStorage.setItem('sprava_vozidel_reminder_view_mode', mode);
                localStorage.removeItem('toozhub_reminder_view_mode');
            }
            loadReminders(false);
        }

        async function openVehicleFromShortcut(vehicleId, source = '') {
            const normalizedId = Number(vehicleId);
            if (!Number.isFinite(normalizedId) || normalizedId <= 0) {
                showAlert('Vybrané vozidlo není dostupné.', 'error');
                return;
            }

            try {
                if (!isServiceWorkspaceRole()) {
                    switchTab('vehicles');
                    await new Promise((resolve) => setTimeout(resolve, 40));
                }
                await showVehicleDetail(normalizedId);
            } catch (error) {
                console.error("Klientskou operaci se nepodařilo dokončit.");
                showAlert('Nepodařilo se otevřít detail vozidla.', 'error');
            }
        }

        // Načtení vozidel
        async function loadVehicles(force = true) {
            const renderStartTs = performance.now();
            const container = document.getElementById('vehiclesContainer');
            if (!container) {
                console.error("[VEHICLES] Container not found - dashboard možná není zobrazen");
                return;
            }

            // Kontrola auth stavu
            if (!isAuthenticated()) {
                console.warn("[VEHICLES] Uživatel není přihlášen");
                return;
            }

            const cacheOwnerKey = getUiCacheOwnerKey();
            if (!force
                && isUiSectionCacheFresh(vehiclesUiState)
                && container.dataset.renderedFor === cacheOwnerKey
                && container.innerHTML.trim()) {
                applyVehicleViewModeUI();
                return;
            }

            container.innerHTML = '<div class="loading">Načítám vozidla...</div>';





            try {
                const vehicles = await apiCall('/api/v1/vehicles', 'GET');



                if (!vehicles || vehicles.length === 0) {
                    container.innerHTML = '<p>Zatím nemáte žádná vozidla. Přidejte první vozidlo pomocí tlačítka "Přidat vozidlo".</p>';
                    applyVehicleViewModeUI();
                    return;
                }

                const viewMode = getVehicleViewMode();
                let html = `<div class="cards-grid vehicle-view vehicle-view-${escapeHtml(viewMode)}">`;
                vehicles.forEach(vehicle => {
                    // Only the dedicated expiry field is authoritative; notes may be historical.
                    const inspectionDate = inspectionDateOnly(vehicle.stk_valid_until);
                    const stkDateValue = inspectionDate ? new Date(inspectionDate + 'T12:00:00') : null;
                    const stkText = stkDateValue ? stkDateValue.toLocaleDateString('cs-CZ') : 'Nezadáno';

                    // Formátování motoru - obsah, kód motoru místo "nm"
                    let engineText = 'Nezadáno';
                    if (vehicle.engine) {
                        engineText = vehicle.engine;

                        // Pokusit najít kód motoru z poznámek a nahradit "/ nm" za "/ [kód motoru]"
                        let engineCode = null;

                        // 1. Zkusit najít v poznámkách - hledat pouze specifické formáty kódu motoru
                        if (vehicle.notes) {
                            const notesText = vehicle.notes;

                            // Nejdřív zkusit najít ve formátu "Typ: X, CFGB" (kde X je typ motoru a CFGB je kód)
                            const typePattern = /Typ:\s*([^,\n]+),\s*([A-Z0-9]{4,6})/i;
                            const typeMatch = notesText.match(typePattern);
                            if (typeMatch && typeMatch[2]) {
                                const code = typeMatch[2].trim();
                                    // Ověřit, že to vypadá jako kód motoru (3-6 znaků pro Peugeot/Citroen/Fiat)
                                    if (/^[A-Z0-9]{3,6}$/.test(code)) {
                                        const knownModels = ['SUPERB', 'V50', 'BOXER', 'PASSAT', 'OCTAVIA', 'MW75', 'TRANSPORTER'];
                                        if (!knownModels.includes(code)) {
                                            engineCode = code;
                                        }
                                    }
                            }

                            // Pokud nenašli, zkusit další formáty
                            if (!engineCode) {
                                const engineCodePatterns = [
                                    /Typ motoru:.*?,\s*([A-Z0-9]{4,6})/i,  // "Typ motoru: 2 NM, CFGB"
                                    /Kód motoru:\s*([A-Z0-9]{4,6})/i,  // "Kód motoru: CFGB"
                                    /Motor kód:\s*([A-Z0-9]{4,6})/i,  // "Motor kód: CFGB"
                                ];

                                for (const pattern of engineCodePatterns) {
                                    const match = notesText.match(pattern);
                                    if (match && match[1]) {
                                        const code = match[1].trim();
                                        // Podporovat 3-6 znaků pro různé značky (Peugeot/Citroen/Fiat mají kratší kódy)
                                        if (/^[A-Z0-9]{3,6}$/.test(code)) {
                                            const knownModels = ['SUPERB', 'V50', 'BOXER', 'PASSAT', 'OCTAVIA', 'MW75', 'TRANSPORTER'];
                                            if (!knownModels.includes(code)) {
                                                engineCode = code;
                                                break;
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // 2. Zkusit najít kód motoru přímo v engine poli pouze pokud je to skutečně kód motoru
                        // (nikoli model vozidla - např. "SUPERB" není kód motoru)
                        if (!engineCode && engineText.includes(',')) {
                            const parts = engineText.split(',');
                            if (parts.length > 1) {
                                const lastPart = parts[parts.length - 1].trim();
                                // Ověřit, že to vypadá jako kód motoru (3-6 znaků pro různé značky)
                                if (/^[A-Z0-9]{3,6}$/.test(lastPart)) {
                                    // Vyloučit známé modely
                                    const knownModels = ['SUPERB', 'V50', 'BOXER', 'PASSAT', 'OCTAVIA', 'TRANSPORTER'];
                                    if (!knownModels.includes(lastPart)) {
                                        engineCode = lastPart;
                                    }
                                }
                            }
                        }

                        // 3. Zkontrolovat, jestli už není kód motoru na konci engineText (po čárce)
                        let existingCodeAtEnd = null;
                        if (engineText.includes(',')) {
                            const parts = engineText.split(',');
                            if (parts.length > 1) {
                                const lastPart = parts[parts.length - 1].trim();
                                // Pokud vypadá jako kód motoru (3-6 velkých písmen/čísel)
                                if (/^[A-Z0-9]{3,6}$/.test(lastPart)) {
                                    const knownModels = ['SUPERB', 'V50', 'BOXER', 'PASSAT', 'OCTAVIA', 'TRANSPORTER'];
                                    if (!knownModels.includes(lastPart)) {
                                        existingCodeAtEnd = lastPart;
                                    }
                                }
                            }
                        }

                        // 4. Pokud máme kód motoru (z poznámek nebo z engine pole), použít ho
                        const finalEngineCode = engineCode || existingCodeAtEnd;

                        if (finalEngineCode) {
                            // Nejdřív odstranit "/ nm"
                            engineText = engineText.replace(/\s*\/\s*nm\s*$/i, '');
                            engineText = engineText.replace(/\s*\/\s*nm\s*/i, '');

                            // Odstranit kód motoru na konci (pokud tam už je po čárce) - escape regex znaků
                            const escapedCode = finalEngineCode.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                            engineText = engineText.replace(new RegExp(`,\\s*${escapedCode}\\s*$`, 'i'), '');

                            // Odstranit mezery na konci
                            engineText = engineText.trim();

                            // Přidat kód motoru za poslední "/" (pouze jednou)
                            if (!engineText.endsWith(finalEngineCode)) {
                                engineText = engineText + ' / ' + finalEngineCode;
                            }
                        } else {
                            // Pokud není kód motoru, odstranit "/ nm" úplně
                            engineText = engineText.replace(/\s*\/\s*nm\s*$/i, '');
                            engineText = engineText.replace(/\s*\/\s*nm\s*/i, '');
                            // Odstranit případné zbylé čárky na konci
                            engineText = engineText.replace(/,\s*$/, '');
                        }
                    }

                    // Formátování názvu s rokem výroby
                    const vehicleName = vehicle.nickname || 'Bez názvu';
                    const vehicleYear = vehicle.year || null;
                    const titleDisplay = vehicleYear ? `${vehicleName} (${vehicleYear})` : vehicleName;
                    const plateDisplay = vehicle.plate || 'Nezadáno';
                    const stkStatus = getVehicleStkStatusMeta(stkDateValue);
                    const brandModelDisplay = [vehicle.brand, vehicle.model].filter(Boolean).join(' ') || 'Nezadáno';
                    const compactStkBadgeLabel = (() => {
                        if (stkStatus.className !== 'stk-soon') return stkStatus.label;
                        const days = Number(stkStatus.daysRemaining);
                        if (Number.isNaN(days)) return 'STK brzy';
                        const daysWord = days === 1 ? 'den' : ((days >= 2 && days <= 4) ? 'dny' : 'dní');
                        return `STK za ${days} ${daysWord}`;
                    })();

                    if (viewMode === 'compact') {
                        html += `
                            <div class="card vehicle-card vehicle-card-compact ${escapeHtml(stkStatus.className)}" ${legacyActionAttributes("click", "showVehicleDetail_8ee4a012", vehicle.id)} style="cursor: pointer;" data-testid="vehicle-card" data-vehicle-id="${escapeHtml(vehicle.id)}">
                                <div class="card-header">
                                    <div class="compact-head-main">
                                        <h3 class="card-title">🚗 ${escapeHtml(titleDisplay)}</h3>
                                        <p class="compact-subtitle">${escapeHtml(brandModelDisplay)}</p>
                                    </div>
                                    <span class="view-stk-badge ${escapeHtml(stkStatus.className)}">${escapeHtml(compactStkBadgeLabel)}</span>
                                </div>
                                <div class="card-body compact-card-body">
                                    <div class="compact-meta-row compact-meta-row-primary">
                                        <div class="card-field compact-field compact-field-plate">
                                            <span class="card-label">SPZ</span>
                                            <span class="card-value">${escapeHtml(plateDisplay)}</span>
                                        </div>
                                        <div class="card-field compact-field">
                                            <span class="card-label">STK do</span>
                                            <span class="card-value">${escapeHtml(stkText)}</span>
                                        </div>
                                    </div>
                                </div>
                                <div class="card-actions">
                                    <button class="btn-edit" ${legacyActionAttributes("click", "stopPropagation_ae1e895d", vehicle.id)}>✏️ Upravit</button>
                                    <button class="btn-danger" ${legacyActionAttributes("click", "stopPropagation_00b7832c", vehicle.id)}>🗑️ Smazat</button>
                                </div>
                            </div>
                        `;
                    } else {
                        html += `
                            <div class="card vehicle-card ${escapeHtml(stkStatus.className)}" ${legacyActionAttributes("click", "showVehicleDetail_8ee4a012", vehicle.id)} style="cursor: pointer;" data-testid="vehicle-card" data-vehicle-id="${escapeHtml(vehicle.id)}">
                                <div class="card-header">
                                    <h3 class="card-title">${escapeHtml(titleDisplay)}</h3>
                                    <span class="view-stk-badge ${escapeHtml(stkStatus.className)}">${escapeHtml(stkStatus.label)}</span>
                                </div>
                                <div class="card-body">
                                    <div class="card-field">
                                        <span class="card-label">SPZ</span>
                                        <span class="card-value">${escapeHtml(plateDisplay)}</span>
                                    </div>
                                    <div class="card-field">
                                        <span class="card-label">Platnost STK</span>
                                        <span class="card-value card-value-stk">${escapeHtml(stkText)}</span>
                                    </div>
                                    <div class="card-field">
                                        <span class="card-label">Motor</span>
                                        <span class="card-value">${escapeHtml(engineText)}</span>
                                    </div>
                                </div>
                            </div>
                        `;
                    }
                });
                html += '</div>';
                container.innerHTML = html;
                container.dataset.renderedFor = cacheOwnerKey;
                markUiSectionLoaded(vehiclesUiState);
                applyVehicleViewModeUI();

            } catch (error) {
                vehiclesUiState.loadedAt = 0;
                console.error("[VEHICLES] Error loading vehicles:");
                let errorMessage = error.message || 'Neznámá chyba';

                // Zlepšit chybové zprávy s detailními informacemi pro debug
                const apiUrl = getApiBaseUrl();
                const endpoint = '/api/v1/vehicles';
                const fullUrl = `${apiUrl}${endpoint}`;

                if (errorMessage.includes('404') || errorMessage.includes('Not Found')) {
                    if (errorMessage.includes('Uživatel nenalezen')) {
                        errorMessage = 'Vaše relace vypršela. Prosím přihlaste se znovu.';
                    } else {
                        // Detailní chybová zpráva pro debug
                        errorMessage = `Endpoint vozidel nebyl nalezen.\n\n` +
                            `Volaná URL: ${fullUrl}\n` +
                            `Status: 404 Not Found\n` +
                            `Zkontrolujte:\n` +
                            `- Zda backend běží na ${apiUrl}\n` +
                            `- Zda je token správně posílán v Authorization headeru\n` +
                            `- Zda router /api/v1/vehicles je zaregistrován`;
                        console.error("[VEHICLES] Debug info:");
                    }
                } else if (errorMessage.includes('401') || errorMessage.includes('Unauthorized')) {
                    errorMessage = 'Vaše relace vypršela. Prosím přihlaste se znovu.';
                } else if (errorMessage.includes('Timeout') || errorMessage.includes('časový limit')) {
                    errorMessage = `Timeout při načítání vozidel.\n\nVolaná URL: ${fullUrl}\nZkuste to prosím znovu.`;
                } else if (errorMessage.includes('Failed to fetch') || errorMessage.includes('připojit k serveru')) {
                    errorMessage = `Nepodařilo se připojit k serveru.\n\nVolaná URL: ${fullUrl}\nZkontrolujte připojení.`;
                }

                showErrorWithRetry('vehiclesContainer', `Nepodařilo se načíst vozidla: ${errorMessage}`, loadVehicles);
            }
        }

        // VIN lookup s AbortController pro zrušení předchozích requestů
        let vinAbortController = null;
        let vinDebounceTimeout = null;
        let vinLastFetched = '';

        // Zobrazení chyby pod VIN inputem
        function showVinError(message) {
            const vinInput = document.getElementById('vehicleVin');
            if (!vinInput) return;

            // Odstranit předchozí chybu
            const existingError = vinInput.parentElement.querySelector('.vin-error');
            if (existingError) {
                existingError.remove();
            }

            // Přidat novou chybu
            const errorDiv = document.createElement('div');
            errorDiv.className = 'vin-error';
            errorDiv.style.color = '#dc3545';
            errorDiv.style.fontSize = '0.875rem';
            errorDiv.style.marginTop = '0.25rem';
            errorDiv.textContent = message;
            vinInput.parentElement.appendChild(errorDiv);

            // Automaticky odstranit po 5 sekundách
            setTimeout(() => {
                if (errorDiv.parentElement) {
                    errorDiv.remove();
                }
            }, 5000);
        }

        // Načtení dat z VIN (nová verze s GET endpointem)
        async function loadVinData(vin) {
            if (window.__licenseFlags && window.__licenseFlags.vinEnabled === false) {
                showAlert('VIN dekódování je dostupné od plánu BASIC.', 'info');
                return;
            }



            if (!vin) {

                return;
            }

            const vinClean = vin.trim().toUpperCase().replace(/[\s-]/g, '');


            // Validace VIN
            if (vinClean.length !== 17) {

                return; // Nezobrazovat chybu, jen neprovádět lookup
            }

            // Validace alfanumerických znaků
            if (!/^[A-HJ-NPR-Z0-9]{17}$/.test(vinClean)) {
                console.error("[VIN] Invalid VIN format - contains I, O, or Q");
                showVinError('VIN obsahuje nepovolené znaky (I, O, Q nejsou povoleny)');
                return;
            }

            // Zrušit předchozí request
            if (vinAbortController) {

                vinAbortController.abort();
            }
            vinAbortController = new AbortController();

            // Odstranit předchozí chybu
            const vinInput = document.getElementById('vehicleVin');
            if (vinInput) {
                const existingError = vinInput.parentElement.querySelector('.vin-error');
                if (existingError) {
                    existingError.remove();
                }
            }

            try {
                // Získat API base URL pro logování
                const apiBaseUrl = getApiBaseUrl();
                const endpoint = '/api/vehicles/decode-vin';
                const fullUrl = `${apiBaseUrl}${endpoint}`;




                // Volat decoder endpoint pro kompletní data
                const response = await apiCall(endpoint, 'POST', { vin: vinClean }, vinAbortController.signal);



                // Zkontrolovat, zda je response úspěšný
                if (!response.success || !response.data) {
                    const errorMsg = response.errors && response.errors.length > 0
                        ? response.errors.join(', ')
                        : 'Nepodařilo se získat data o vozidle';
                    throw new Error(errorMsg);
                }

                // Použít data z decoder response
                const data = response.data;


                // Robustní setter pro inputy
                function setValueIfExists(id, value, options = {}) {
                    const el = document.getElementById(id);
                    if (!el) {
                        if (options.logMissing) {
                            console.warn("Klientskou operaci se nepodařilo dokončit.");
                        }
                        return false;
                    }
                    if (value === null || value === undefined || value === "") {
                        return false;
                    }
                    // Pro textarea a input
                    if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
                        el.value = value;
                        // Dispatch events pro triggerování validace/change handlerů
                        el.dispatchEvent(new Event("input", { bubbles: true }));
                        el.dispatchEvent(new Event("change", { bubbles: true }));
                    }
                    return true;
                }

                // Normalizace fuel_type
                function normalizeFuelType(fuelType) {
                    if (!fuelType) return fuelType;
                    const fuelMap = {
                        'nm': 'Nafta',
                        'bm': 'Benzín',
                        'el': 'Elektro',
                        'hy': 'Hybrid',
                        'lpg': 'LPG',
                        'cng': 'CNG'
                    };
                    return fuelMap[fuelType.toLowerCase()] || fuelType;
                }

                // Očištění type_label (odstranit leading " / ")
                function cleanTypeLabel(s) {
                    if (!s) return s;
                    return s.replace(/^\s*\/\s*/, "").trim();
                }

                // Vyplnění všech polí formuláře
                const brandInput = document.getElementById('vehicleBrand');
                const typeInput = document.getElementById('vehicleType');
                const engineCodeInput = document.getElementById('vehicleEngineCode');
                const maxPowerInput = document.getElementById('vehicleMaxPower');
                const tyresInput = document.getElementById('vehicleTyres');
                const additionalNotesInput = document.getElementById('vehicleAdditionalNotes');
                const inspectionDateInput = document.getElementById('vehicleInspectionDate');
                const modelInput = document.getElementById('vehicleModel');
                const yearInput = document.getElementById('vehicleYear');
                const engineInput = document.getElementById('vehicleEngine');
                const plateInput = document.getElementById('vehiclePlate');
                const nameInput = document.getElementById('vehicleName');
                const notesInput = document.getElementById('vehicleNotes');

                let filledFields = [];
                let filledIds = [];

                // SPZ (NEPŘEPISOVAT pokud uživatel něco napsal)
                if (data.plate) {
                    const currentPlate = plateInput ? plateInput.value.trim() : '';
                    const userPlate = currentPlate && currentPlate.length > 0 && currentPlate !== '1A2 3456';
                    if (!userPlate && setValueIfExists('vehiclePlate', data.plate)) {
                        filledFields.push('SPZ: ' + data.plate);
                        filledIds.push('vehiclePlate');

                    } else if (userPlate) {

                    }
                }

                // Značka (make) -> vehicleBrand (hidden)
                if (setValueIfExists('vehicleBrand', data.make)) {
                    filledFields.push('značka: ' + data.make);
                    filledIds.push('vehicleBrand');

                }

                // Model -> vehicleModel
                if (setValueIfExists('vehicleModel', data.model)) {
                    filledFields.push('model: ' + data.model);
                    filledIds.push('vehicleModel');

                }

                // Název vozidla (make + model) -> vehicleName
                if (nameInput) {
                    let nameValue = '';
                    if (data.make && data.model) {
                        nameValue = `${data.make} ${data.model}`;
                    } else if (data.make) {
                        nameValue = data.make;
                    }
                    if (nameValue && setValueIfExists('vehicleName', nameValue)) {
                        filledFields.push('název: ' + nameValue);
                        filledIds.push('vehicleName');

                    }
                }

                // Rok (production_year) -> vehicleYear
                const year = data.production_year || data.model_year;
                if (year && setValueIfExists('vehicleYear', year.toString())) {
                    filledFields.push('rok: ' + year);
                    filledIds.push('vehicleYear');

                }

                // Motor - použít engine_code jako primární, pak sestavit z dalších údajů -> vehicleEngine
                if (engineInput) {
                    let engineValue = '';
                    // Primární: engine_code
                    if (data.engine_code) {
                        engineValue = data.engine_code;
                    }
                    // Sekundární: sestavit z displacement, power, fuel
                    if (!engineValue && (data.engine_displacement_cc || data.engine_power_kw || data.fuel_type)) {
                        const parts = [];
                        if (data.engine_displacement_cc) {
                            parts.push(`${data.engine_displacement_cc} cm³`);
                        }
                        if (data.engine_power_kw) {
                            parts.push(`${data.engine_power_kw} kW`);
                        }
                        if (data.fuel_type) {
                            parts.push(normalizeFuelType(data.fuel_type));
                        }
                        if (parts.length > 0) {
                            engineValue = parts.join(' / ');
                        }
                    }
                    if (engineValue && setValueIfExists('vehicleEngine', engineValue)) {
                        filledFields.push('motor: ' + engineValue);
                        filledIds.push('vehicleEngine');

                    }
                }

                // Typ vozidla (type_label očištěný) -> vehicleType (hidden)
                const vehicleType = cleanTypeLabel(data.type_label || data.body_type);
                if (vehicleType && setValueIfExists('vehicleType', vehicleType)) {
                    filledFields.push('typ: ' + vehicleType);
                    filledIds.push('vehicleType');

                }

                // Kód motoru (engine_code) -> vehicleEngineCode (hidden)
                if (setValueIfExists('vehicleEngineCode', data.engine_code)) {
                    filledFields.push('kód motoru: ' + data.engine_code);
                    filledIds.push('vehicleEngineCode');

                }

                // Max. výkon (engine_power_kw) -> vehicleMaxPower (hidden)
                if (data.engine_power_kw && setValueIfExists('vehicleMaxPower', data.engine_power_kw.toString())) {
                    filledFields.push('max. výkon: ' + data.engine_power_kw + ' kW');
                    filledIds.push('vehicleMaxPower');

                }

                // Kola a pneumatiky (wheels_and_tyres nebo tyres array)
                if (tyresInput) {
                    if (data.wheels_and_tyres) {
                        tyresInput.value = data.wheels_and_tyres;
                        filledFields.push('kola a pneumatiky');

                    } else if (data.tyres && Array.isArray(data.tyres) && data.tyres.length > 0) {
                        tyresInput.value = data.tyres.join('\n');
                        filledFields.push('pneumatiky');

                    } else if (data.tyres_raw) {
                        tyresInput.value = data.tyres_raw;
                        filledFields.push('pneumatiky (raw)');

                    }
                }

                // Další záznamy (extra_records)
                if (additionalNotesInput && data.extra_records) {
                    additionalNotesInput.value = data.extra_records;
                    filledFields.push('další záznamy');

                }

                // Technická prohlídka do (tech_inspection_valid_to) -> vehicleStkDate (required) + info pole
                const stkDateRaw = data.tech_inspection_valid_to || data.stk_valid_until;
                const normalizedStk = normalizeDateInput(stkDateRaw || '');
                if (normalizedStk && setValueIfExists('vehicleStkDate', normalizedStk, { logMissing: true })) {
                    filledFields.push('STK platnost do: ' + (stkDateRaw || normalizedStk));
                    filledIds.push('vehicleStkDate');

                }
                // Ponechat textové pole pro informativní účely (bez požadavku na formát)
                if (stkDateRaw && setValueIfExists('vehicleInspectionDate', stkDateRaw)) {
                    filledIds.push('vehicleInspectionDate');

                }

                // Poznámky - sestavit z emisní normy a dalších údajů -> vehicleNotes
                if (notesInput) {
                    let notes = [];
                    if (data.emission_standard) {
                        notes.push(`Emisní norma: ${data.emission_standard}`);
                    }
                    if (data.curb_weight_kg) {
                        notes.push(`Pohotovostní hmotnost: ${data.curb_weight_kg} kg`);
                    }
                    if (data.gross_weight_kg) {
                        notes.push(`Celková hmotnost: ${data.gross_weight_kg} kg`);
                    }
                    if (data.seats) {
                        notes.push(`Počet míst: ${data.seats}`);
                    }

                    // Přidat informaci o zdroji dat do poznámek (POVINNÉ)
                    if (data.source_priority && data.source_priority.length > 0) {
                        const sourceInfo = `Dekódováno z: ${data.source_priority.join(', ')}`;
                        notes.push(sourceInfo);

                    }

                    if (notes.length > 0) {
                        const currentNotes = notesInput.value.trim();
                        const newNotes = notes.join('\n');
                        if (currentNotes) {
                            notesInput.value = currentNotes + '\n\n' + newNotes;
                        } else {
                            notesInput.value = newNotes;
                        }
                        notesInput.dispatchEvent(new Event("input", { bubbles: true }));
                        notesInput.dispatchEvent(new Event("change", { bubbles: true }));
                        filledFields.push('poznámky');
                        filledIds.push('vehicleNotes');

                    }
                }







                // Zobrazit úspěšnou zprávu
                if (filledFields.length > 0) {
                    showAlert(`Data z VIN načtena: ${filledFields.join(', ')}`, 'success');
                } else {
                    showVinError('VIN dekodér nevrátil žádná data');
                }
            } catch (error) {
                console.error("[VIN] ========================================");
                console.error("[VIN] ERROR occurred:");
                console.error("[VIN] Error name:");
                console.error("[VIN] Error message:");
                console.error("[VIN] Error stack:");

                let errorMsg = error.message || 'Neznámá chyba';

                // Zlepšit chybové zprávy
                if (error.name === 'AbortError') {
                    // Request byl zrušen, neukazovat chybu

                    return;
                } else if (errorMsg.includes('404') || errorMsg.includes('Not Found')) {
                    console.error("[VIN] 404 - Endpoint not found");
                    errorMsg = 'VIN dekodér není dostupný. Zkontrolujte připojení k serveru.';
                } else if (errorMsg.includes('422') || errorMsg.includes('Unprocessable')) {
                    console.error("[VIN] 422 - Invalid VIN format");
                    errorMsg = 'Neplatný VIN kód. Zkontrolujte správnost VIN (17 znaků, bez I, O, Q).';
                } else if (errorMsg.includes('Timeout') || errorMsg.includes('časový limit')) {
                    console.error("[VIN] Timeout - Request took too long");
                    errorMsg = 'Timeout při načítání dat z VIN. Zkuste to prosím znovu.';
                } else if (errorMsg.includes('500') || errorMsg.includes('Server')) {
                    console.error("[VIN] 500 - Server error");
                    errorMsg = 'Chyba serveru při dekódování VIN. Zkuste to prosím později.';
                } else if (errorMsg.includes('CORS') || errorMsg.includes('CORS')) {
                    console.error("[VIN] CORS error - Cross-origin request blocked");
                    errorMsg = 'CORS chyba - zkontrolujte konfiguraci serveru.';
                } else if (errorMsg.includes('Network') || errorMsg.includes('Failed to fetch')) {
                    console.error("[VIN] Network error - Cannot reach server");
                    errorMsg = 'Nelze se připojit k serveru. Zkontrolujte připojení k internetu.';
                }

                console.error("[VIN] Final error message:");
                showVinError('VIN se nepodařilo načíst: ' + errorMsg);
            }
        }

        function setFieldError(inputId, errorId, message) {
            const input = document.getElementById(inputId);
            const errorEl = errorId ? document.getElementById(errorId) : null;
            if (input) {
                input.classList.add('input-error');
            }
            if (errorEl) {
                errorEl.textContent = message || '';
            }
        }

        function clearFieldError(inputId, errorId) {
            const input = document.getElementById(inputId);
            const errorEl = errorId ? document.getElementById(errorId) : null;
            if (input) {
                input.classList.remove('input-error');
            }
            if (errorEl) {
                errorEl.textContent = '';
            }
        }

        function buildServiceAddVehicleSectionHtml() {
            return `
                <div class="service-add-vehicle-shell">
                    <h2>Přidat vozidlo klientovi</h2>
                    <p class="form-hint" style="margin-top:-2px; margin-bottom:12px;">
                        Vozidlo se uloží pod vybraného klienta a servis k němu získá správu.
                    </p>
                    <div class="form-compact">
                        <div class="form-group full-width">
                            <label for="serviceAddVehicleCustomer">Klient *</label>
                            <select id="serviceAddVehicleCustomer"></select>
                        </div>
                        <div class="form-group">
                            <label for="serviceAddVehicleNickname">Název vozidla *</label>
                            <input type="text" id="serviceAddVehicleNickname" placeholder="např. Octavia firemní">
                        </div>
                        <div class="form-group">
                            <label for="serviceAddVehiclePlate">SPZ *</label>
                            <input type="text" id="serviceAddVehiclePlate" placeholder="1A2 3456">
                        </div>
                        <div class="form-group">
                            <label for="serviceAddVehicleVin">VIN</label>
                            <input type="text" id="serviceAddVehicleVin" maxlength="17" placeholder="17 znaků">
                        </div>
                        <div class="form-group">
                            <label for="serviceAddVehicleBrand">Značka</label>
                            <input type="text" id="serviceAddVehicleBrand" placeholder="Škoda">
                        </div>
                        <div class="form-group">
                            <label for="serviceAddVehicleModel">Model</label>
                            <input type="text" id="serviceAddVehicleModel" placeholder="Octavia">
                        </div>
                        <div class="form-group">
                            <label for="serviceAddVehicleYear">Rok</label>
                            <input type="number" id="serviceAddVehicleYear" min="1900" max="2100" placeholder="2020">
                        </div>
                        <div class="form-group">
                            <label for="serviceAddVehicleEngine">Motor</label>
                            <input type="text" id="serviceAddVehicleEngine" placeholder="2.0 TDI">
                        </div>
                        <div class="form-group">
                            <label for="serviceAddVehicleStk">Platnost STK (pokud ji znáte)</label>
                            <input type="date" id="serviceAddVehicleStk">
                        </div>
                        <div class="form-group full-width">
                            <label for="serviceAddVehicleNotes">Poznámka</label>
                            <textarea id="serviceAddVehicleNotes" rows="3" placeholder="Poznámka servisu ke klientskému vozidlu"></textarea>
                        </div>
                    </div>
                    <div class="add-vehicle-button-group">
                        <button class="btn btn-primary" type="button" ${legacyActionAttributes("click", "handleServiceAddVehicleSubmit_ce285c5f")}>Přidat vozidlo klientovi</button>
                        <button class="btn btn-secondary" type="button" ${legacyActionAttributes("click", "resetServiceAddVehicleForm_e1b0258c")}>Vyčistit</button>
                    </div>
                    <div id="serviceAddVehicleStatus" class="form-hint" style="margin-top:8px;"></div>
                </div>
            `;
        }

        async function loadServiceAddVehicleCustomers(selectedCustomerId = null) {
            const customerSelect = document.getElementById('serviceAddVehicleCustomer');
            if (!customerSelect) return;

            let customers = Array.isArray(serviceWorkspaceState.customers) ? serviceWorkspaceState.customers : [];
            if (!customers.length) {
                try {
                    const response = await apiCall('/api/v1/services/workspace/customers', 'GET');
                    customers = Array.isArray(response) ? response : [];
                    serviceWorkspaceState.customers = customers;
                } catch (error) {
                    console.error("[SERVICE_ADD_VEHICLE] Nepodařilo se načíst klienty:");
                    customerSelect.innerHTML = '<option value="">Klienti se nepodařilo načíst</option>';
                    return;
                }
            }

            const options = ['<option value="">Vyberte klienta...</option>'].concat(
                customers.map((customer) => {
                    const customerId = Number(customer?.customer_id || 0);
                    const label = `${customer?.name || customer?.email || `Klient #${customerId}`} (${customer?.email || '-'})`;
                    return `<option value="${customerId}">${escapeHtml(label)}</option>`;
                })
            );
            customerSelect.innerHTML = options.join('');

            const preferred = Number(selectedCustomerId || serviceWorkspaceState.selectedCustomerId || 0);
            if (preferred > 0) {
                customerSelect.value = String(preferred);
            }
        }

        function resetServiceAddVehicleForm() {
            const ids = [
                'serviceAddVehicleCustomer',
                'serviceAddVehicleNickname',
                'serviceAddVehiclePlate',
                'serviceAddVehicleVin',
                'serviceAddVehicleBrand',
                'serviceAddVehicleModel',
                'serviceAddVehicleYear',
                'serviceAddVehicleEngine',
                'serviceAddVehicleStk',
                'serviceAddVehicleNotes'
            ];
            ids.forEach((id) => {
                const field = document.getElementById(id);
                if (field) field.value = '';
            });
            const status = document.getElementById('serviceAddVehicleStatus');
            if (status) status.textContent = '';
        }

        async function ensureServiceAddVehicleSection(forceRender = false) {
            const addVehicleTab = document.getElementById('addVehicleTab');
            if (!addVehicleTab) return;

            let section = document.getElementById('serviceAddVehicleSection');
            if (!section) {
                section = document.createElement('div');
                section.id = 'serviceAddVehicleSection';
                section.classList.add('hidden');
                addVehicleTab.prepend(section);
            }

            const isServiceMode = isServiceWorkspaceRole();
            const defaultChildren = Array.from(addVehicleTab.children).filter((child) => child.id !== 'serviceAddVehicleSection');
            if (isServiceMode) {
                section.classList.remove('hidden');
                defaultChildren.forEach((child) => child.classList.add('hidden'));
                if (forceRender || !serviceAddVehicleState.initialized) {
                    section.innerHTML = buildServiceAddVehicleSectionHtml();
                    serviceAddVehicleState.initialized = true;
                }
                await loadServiceAddVehicleCustomers();
                return;
            }

            section.classList.add('hidden');
            defaultChildren.forEach((child) => child.classList.remove('hidden'));
        }

        async function openServiceAddVehicleForCustomer(customerId) {
            const customerIdNum = Number(customerId || 0);
            if (!customerIdNum) {
                switchTab('addVehicle');
                return;
            }
            serviceWorkspaceState.selectedCustomerId = customerIdNum;
            switchTab('addVehicle');
            await ensureServiceAddVehicleSection(true);
            const customerSelect = document.getElementById('serviceAddVehicleCustomer');
            if (customerSelect) {
                customerSelect.value = String(customerIdNum);
            }
        }

        async function handleServiceAddVehicleSubmit() {
            if (!isServiceWorkspaceRole()) {
                showAlert('Tato sekce je dostupná pouze pro servisní účet.', 'error');
                return;
            }
            if (serviceAddVehicleState.submitting) {
                return;
            }

            const customerId = Number(document.getElementById('serviceAddVehicleCustomer')?.value || 0);
            const nickname = String(document.getElementById('serviceAddVehicleNickname')?.value || '').trim();
            const plate = String(document.getElementById('serviceAddVehiclePlate')?.value || '').trim();
            const vin = String(document.getElementById('serviceAddVehicleVin')?.value || '').trim().toUpperCase();
            const brand = String(document.getElementById('serviceAddVehicleBrand')?.value || '').trim();
            const model = String(document.getElementById('serviceAddVehicleModel')?.value || '').trim();
            const yearRaw = Number(document.getElementById('serviceAddVehicleYear')?.value || 0);
            const engine = String(document.getElementById('serviceAddVehicleEngine')?.value || '').trim();
            const stk = String(document.getElementById('serviceAddVehicleStk')?.value || '').trim();
            const notes = String(document.getElementById('serviceAddVehicleNotes')?.value || '').trim();

            if (!customerId) {
                showAlert('Vyberte klienta.', 'error');
                return;
            }
            if (!nickname || nickname.length < 2) {
                showAlert('Vyplňte název vozidla (min. 2 znaky).', 'error');
                return;
            }
            if (!plate) {
                showAlert('Vyplňte SPZ.', 'error');
                return;
            }
            if (stk && !inspectionDateOnly(stk)) {
                showAlert('Datum STK není platné.', 'error');
                return;
            }

            const payload = {
                nickname,
                plate,
                vin: vin || null,
                brand: brand || null,
                model: model || null,
                year: Number.isFinite(yearRaw) && yearRaw > 0 ? yearRaw : null,
                engine: engine || null,
                notes: notes || null,
                stk_valid_until: stk || null,
                tyres_info: null
            };

            serviceAddVehicleState.submitting = true;
            const statusEl = document.getElementById('serviceAddVehicleStatus');
            if (statusEl) statusEl.textContent = 'Ukládám vozidlo klientovi...';

            try {
                const response = await apiCall(`/api/v1/services/workspace/customers/${customerId}/vehicles`, 'POST', payload);
                showAlert(response?.message || 'Vozidlo bylo úspěšně přidáno.', 'success');
                if (statusEl) statusEl.textContent = response?.message || 'Vozidlo bylo přidáno.';
                resetServiceAddVehicleForm();
                await Promise.all([
                    loadServiceWorkspace(),
                    loadServicesDirectory(true)
                ]);
                switchTab('serviceWorkspace');
            } catch (error) {
                console.error("[SERVICE_ADD_VEHICLE] Chyba při ukládání:");
                const message = `Nepodařilo se přidat vozidlo: ${error?.message || 'Neznámá chyba'}`;
                showAlert(message, 'error');
                if (statusEl) statusEl.textContent = message;
            } finally {
                serviceAddVehicleState.submitting = false;
            }
        }

        // Přidání vozidla
        async function handleAddVehicle() {



            const vin = document.getElementById('vehicleVin').value.trim();
            const plateInput = document.getElementById('vehiclePlate');
            const nameInput = document.getElementById('vehicleName');
            const stkInput = document.getElementById('vehicleStkDate');
            const plate = plateInput ? plateInput.value.trim() : '';
            const name = nameInput ? nameInput.value.trim() : '';
            const brand = document.getElementById('vehicleBrand').value.trim();
            const vehicleType = document.getElementById('vehicleType')?.value.trim() || '';
            const engineCode = document.getElementById('vehicleEngineCode')?.value.trim() || '';
            const maxPower = document.getElementById('vehicleMaxPower')?.value.trim() || '';
            const tyres = document.getElementById('vehicleTyres')?.value.trim() || '';
            const additionalNotes = document.getElementById('vehicleAdditionalNotes')?.value.trim() || '';
            const inspectionDate = document.getElementById('vehicleInspectionDate')?.value.trim() || '';
            const photoInput = document.getElementById('vehiclePhotoInput');
            const vehiclePhotoFile = photoInput && photoInput.files && photoInput.files[0] ? photoInput.files[0] : null;
            const model = document.getElementById('vehicleModel').value.trim();
            const yearText = document.getElementById('vehicleYear').value.trim();
            const engine = document.getElementById('vehicleEngine').value.trim();
            const notes = document.getElementById('vehicleNotes').value.trim();
            const stkRaw = stkInput ? stkInput.value.trim() : '';
            const stkDate = inspectionDateOnly(normalizeDateInput(stkRaw));

            // Vyčistit předchozí chyby
            clearFieldError('vehicleName', 'vehicleNameError');
            clearFieldError('vehiclePlate', 'vehiclePlateError');
            clearFieldError('vehicleStkDate', 'vehicleStkError');

            let hasError = false;
            if (!name || name.length < 2) {
                setFieldError('vehicleName', 'vehicleNameError', 'Zadejte název vozidla (min. 2 znaky)');
                hasError = true;
            }
            if (!plate) {
                setFieldError('vehiclePlate', 'vehiclePlateError', 'Zadejte SPZ vozidla');
                hasError = true;
            }
            if (stkRaw && !stkDate) {
                setFieldError('vehicleStkDate', 'vehicleStkError', 'Datum STK není platné (RRRR-MM-DD)');
                hasError = true;
            }

            if (hasError) {
                showAlert('Zkontrolujte název vozidla, SPZ a případné zadané datum STK.', 'error');
                return;
            }

            // Parsování roku
            let year = null;
            if (yearText) {
                const parsedYear = parseInt(yearText);
                if (!isNaN(parsedYear)) {
                    year = parsedYear;
                }
            }

            // Sestavit poznámky - zahrnout všechny extrahované údaje
            let fullNotes = notes;
            if (tyres) {
                fullNotes += (fullNotes ? '\n\n' : '') + 'Kola a pneumatiky:\n' + tyres;
            }
            if (additionalNotes) {
                fullNotes += (fullNotes ? '\n\n' : '') + 'Další záznamy:\n' + additionalNotes;
            }
            // STK platnost se už neukládá do poznámek, ukládá se přímo do stk_valid_until
            // if (inspectionDate) {
            //     fullNotes += (fullNotes ? '\n\n' : '') + 'Technická prohlídka do: ' + inspectionDate;
            // }
            if (vehicleType) {
                fullNotes += (fullNotes ? '\n\n' : '') + 'Typ: ' + vehicleType;
            }
            if (maxPower) {
                fullNotes += (fullNotes ? '\n\n' : '') + 'Max. výkon: ' + maxPower;
            }

            const vehicleData = {
                vin: vin || null,
                plate,
                nickname: name,
                brand: brand || null,
                model: model || null,
                year: year,
                engine: engine || null,
                engine_code: engineCode || null,
                tyres_info: tyres || null,
                notes: fullNotes || null,
                stk_valid_until: stkDate || null,
                insurance_provider: null,
                insurance_valid_until: null,
                ...(window.CustomerFeatures?.extraVehicleData(vin) || {})
            };



            try {
                showAlert('Přidávám vozidlo...', 'info');

                const vehicle = await apiCall('/api/v1/vehicles', 'POST', vehicleData);
                window.CustomerFeatures?.clearDraft();


                if (vehiclePhotoFile && vehicle && vehicle.id) {
                    try {
                        await uploadVehiclePhoto(vehicle.id, vehiclePhotoFile);
                    } catch (photoError) {
                        console.error("[ADD VEHICLE] Upload photo failed:");
                        showAlert(`Vozidlo bylo přidáno, ale fotka se nenahrála: ${photoError.message}`, 'error');
                    }
                }

                showAlert('Vozidlo bylo úspěšně přidáno!', 'success');

                // Vyčistit formulář
                document.getElementById('vehicleVin').value = '';
                document.getElementById('vehiclePlate').value = '';
                document.getElementById('vehicleName').value = '';
                document.getElementById('vehicleBrand').value = '';
                document.getElementById('vehicleType').value = '';
                document.getElementById('vehicleEngineCode').value = '';
                document.getElementById('vehicleMaxPower').value = '';
                document.getElementById('vehicleTyres').value = '';
                document.getElementById('vehicleAdditionalNotes').value = '';
                document.getElementById('vehicleStkDate').value = '';
                document.getElementById('vehicleInspectionDate').value = '';
                document.getElementById('vehicleModel').value = '';
                document.getElementById('vehicleYear').value = '';
                document.getElementById('vehicleEngine').value = '';
                document.getElementById('vehicleNotes').value = '';
                if (photoInput) {
                    photoInput.value = '';
                }
                const photoPreviewWrap = document.getElementById('vehiclePhotoPreviewWrap');
                const photoPreview = document.getElementById('vehiclePhotoPreview');
                if (photoPreviewWrap) photoPreviewWrap.classList.add('hidden');
                if (photoPreview) photoPreview.removeAttribute('src');
                clearFieldError('vehicleName', 'vehicleNameError');
                clearFieldError('vehiclePlate', 'vehiclePlateError');
                clearFieldError('vehicleStkDate', 'vehicleStkError');

                // Skrýt informační box o zdrojích
                const sourceInfoBox = document.getElementById('vinSourceInfo');
                if (sourceInfoBox) {
                    sourceInfoBox.style.display = 'none';
                }

                // Načíst aktualizovaný seznam vozidel
                await loadVehicles();

                // Přepnout na záložku s vozidly
                switchTab('vehicles');

                // Pokud je zobrazen detail vozidla, aktualizovat ho
                if (currentVehicleId) {
                    await showVehicleDetail(currentVehicleId);
                }
            } catch (error) {
                console.error("[ADD VEHICLE] Error:");
                const errMsg = error?.message || 'Neznámá chyba';
                const errLower = errMsg.toLowerCase();
                if (errLower.includes('stk')) {
                    setFieldError('vehicleStkDate', 'vehicleStkError', 'Zadejte platnost STK');
                }
                if (errLower.includes('název vozidla') || errLower.includes('nickname')) {
                    setFieldError('vehicleName', 'vehicleNameError', 'Zadejte název vozidla (min. 2 znaky)');
                }
                if (errLower.includes('spz') || errLower.includes('plate')) {
                    setFieldError('vehiclePlate', 'vehiclePlateError', 'Zadejte SPZ vozidla');
                }
                showAlert('Nepodařilo se přidat vozidlo: ' + errMsg, 'error');
            }
        }

        // Proměnná pro aktuální zobrazené vozidlo
        let currentVehicleId = null;
        let expandedVehicleId = null;

        // Rozbalení/sbalení detailu vozidla v kartě
        async function toggleVehicleDetail(vehicleId) {
            const detailPanel = document.getElementById(`vehicle-detail-${vehicleId}`);
            const header = detailPanel?.previousElementSibling;

            if (!detailPanel || !header) return;

            const isExpanded = detailPanel.classList.contains('expanded');

            if (isExpanded) {
                // Sbalit
                detailPanel.classList.remove('expanded');
                header.classList.remove('expanded');
                expandedVehicleId = null;
            } else {
                // Sbalit ostatní panely
                if (expandedVehicleId && expandedVehicleId !== vehicleId) {
                    const otherPanel = document.getElementById(`vehicle-detail-${expandedVehicleId}`);
                    const otherHeader = otherPanel?.previousElementSibling;
                    if (otherPanel) otherPanel.classList.remove('expanded');
                    if (otherHeader) otherHeader.classList.remove('expanded');
                }

                // Rozbalit tento panel
                detailPanel.classList.add('expanded');
                header.classList.add('expanded');
                expandedVehicleId = vehicleId;
                currentVehicleId = vehicleId;

                // Načíst data vozidla, pokud ještě nejsou načtena
                const infoContainer = document.getElementById(`vehicle-info-${vehicleId}`);
                if (infoContainer && infoContainer.innerHTML.includes('Načítám')) {
                    await loadVehicleDetailInline(vehicleId);
                }
            }
        }

        // Načtení detailu vozidla do rozbalovacího panelu
        async function loadVehicleDetailInline(vehicleId) {
            const infoContainer = document.getElementById(`vehicle-info-${vehicleId}`);
            const servicesContainer = document.getElementById(`service-records-${vehicleId}`);

            if (!infoContainer) return;

            try {
                // Načíst data vozidla
                const vehicle = await apiCall(`/api/v1/vehicles/${vehicleId}`, 'GET');

                // Uložit aktuální vozidlo pro editaci
                window.currentVehicle = vehicle;

                // Zobrazit data vozidla - minimalistický design s možností editace
                infoContainer.innerHTML = `
                    <div class="vehicle-info-list">
                        <!-- Název - editovatelné -->
                        <div class="vehicle-info-row editable" data-field="nickname" data-vehicle-id="${escapeHtml(vehicleId)}">
                            <span class="vehicle-info-label">Název</span>
                            <div class="vehicle-info-edit" style="display: none;">
                                <input type="text" id="edit-nickname-${escapeHtml(vehicleId)}" value="${escapeHtml(vehicle.nickname || '')}" placeholder="Název vozidla">
                                <div class="vehicle-info-actions">
                                    <button class="vehicle-info-btn save" ${legacyActionAttributes("click", "saveVehicleFieldInline_b9b42868", vehicleId)}>Uložit</button>
                                    <button class="vehicle-info-btn cancel" ${legacyActionAttributes("click", "cancelEditInline_6b16e294", vehicleId)}>Zrušit</button>
                                </div>
                            </div>
                            <div class="vehicle-info-display" style="display: flex; align-items: center; justify-content: space-between; flex: 1; gap: 12px;">
                                <span class="vehicle-info-value ${!vehicle.nickname ? 'empty' : ''}">${escapeHtml(vehicle.nickname || 'Nezadáno')}</span>
                                <button class="vehicle-info-btn" ${legacyActionAttributes("click", "startEditInline_78e44df3", vehicleId)} title="Upravit název">✏️</button>
                            </div>
                        </div>

                        <!-- SPZ - editovatelné -->
                        <div class="vehicle-info-row editable" data-field="plate" data-vehicle-id="${escapeHtml(vehicleId)}">
                            <span class="vehicle-info-label">SPZ</span>
                            <div class="vehicle-info-edit" style="display: none;">
                                <input type="text" id="edit-plate-${escapeHtml(vehicleId)}" value="${escapeHtml(vehicle.plate || '')}" placeholder="SPZ">
                                <div class="vehicle-info-actions">
                                    <button class="vehicle-info-btn save" ${legacyActionAttributes("click", "saveVehicleFieldInline_e2d47f23", vehicleId)}>Uložit</button>
                                    <button class="vehicle-info-btn cancel" ${legacyActionAttributes("click", "cancelEditInline_6a45c869", vehicleId)}>Zrušit</button>
                                </div>
                            </div>
                            <div class="vehicle-info-display" style="display: flex; align-items: center; justify-content: space-between; flex: 1; gap: 12px;">
                                <span class="vehicle-info-value ${!vehicle.plate ? 'empty' : ''}">${escapeHtml(vehicle.plate || 'Nezadáno')}</span>
                                <button class="vehicle-info-btn" ${legacyActionAttributes("click", "startEditInline_3a976e52", vehicleId)} title="Upravit SPZ">✏️</button>
                            </div>
                        </div>

                        <!-- VIN - pouze zobrazení -->
                        <div class="vehicle-info-row">
                            <span class="vehicle-info-label">VIN</span>
                            <span class="vehicle-info-value ${!vehicle.vin ? 'empty' : ''}" style="font-family: monospace; font-size: 14px; text-align: right;">${escapeHtml(vehicle.vin || 'Nezadáno')}</span>
                        </div>

                        ${vehicle.brand ? `
                        <div class="vehicle-info-row">
                            <span class="vehicle-info-label">Značka</span>
                            <span class="vehicle-info-value" style="text-align: right;">${escapeHtml(vehicle.brand)}</span>
                        </div>
                        ` : ''}

                        ${vehicle.model ? `
                        <div class="vehicle-info-row">
                            <span class="vehicle-info-label">Model</span>
                            <span class="vehicle-info-value" style="text-align: right;">${escapeHtml(vehicle.model)}</span>
                        </div>
                        ` : ''}

                                ${vehicle.year ? `
                                <div class="vehicle-info-row">
                                    <span class="vehicle-info-label">Rok výroby</span>
                                    <span class="vehicle-info-value" style="text-align: right;">${escapeHtml(vehicle.year)}</span>
                                </div>
                                ` : ''}

                                ${vehicle.engine ? `
                                <div class="vehicle-info-row">
                                    <span class="vehicle-info-label">Motor</span>
                                    <span class="vehicle-info-value" style="text-align: right;">${escapeHtml(vehicle.engine)}</span>
                                </div>
                                ` : ''}

                                <div class="vehicle-info-row">
                                    <span class="vehicle-info-label">Platnost STK</span>
                                    <span class="vehicle-info-value" style="text-align: right;">${escapeHtml(formatDateCZ(vehicle.stk_valid_until))}</span>
                                </div>

                                <!-- Poznámky - editovatelné -->
                                <div class="vehicle-info-row editable" data-field="notes" data-vehicle-id="${escapeHtml(vehicleId)}">
                            <span class="vehicle-info-label">Poznámky</span>
                            <div class="vehicle-info-edit" style="display: none; flex-direction: column; gap: 8px; flex: 1;">
                                <textarea id="edit-notes-${escapeHtml(vehicleId)}" placeholder="Poznámky k vozidlu" rows="4">${escapeHtml(vehicle.notes || '')}</textarea>
                                <div class="vehicle-info-actions">
                                    <button class="vehicle-info-btn save" ${legacyActionAttributes("click", "saveVehicleFieldInline_42078fb0", vehicleId)}>Uložit</button>
                                    <button class="vehicle-info-btn cancel" ${legacyActionAttributes("click", "cancelEditInline_bd54022a", vehicleId)}>Zrušit</button>
                                </div>
                            </div>
                            <div class="vehicle-info-display" style="display: flex; align-items: flex-start; justify-content: space-between; flex: 1; gap: 12px;">
                                <span class="vehicle-info-value ${!vehicle.notes ? 'empty' : ''}" style="white-space: pre-wrap; line-height: 1.6; text-align: left;">${escapeHtml(vehicle.notes || 'Nezadáno')}</span>
                                <button class="vehicle-info-btn" ${legacyActionAttributes("click", "startEditInline_9c9fa615", vehicleId)} style="flex-shrink: 0;" title="Upravit poznámky">✏️</button>
                            </div>
                        </div>

                        <div class="vehicle-info-row">
                            <span class="vehicle-info-label">Přidáno</span>
                            <span class="vehicle-info-value" style="text-align: right;">${escapeHtml(new Date(vehicle.created_at).toLocaleDateString('cs-CZ'))}</span>
                        </div>
                    </div>
                `;

                // Načíst servisní záznamy
                await loadServiceRecordsInline(vehicleId);

            } catch (error) {
                console.error("Error loading vehicle detail:");
                infoContainer.innerHTML = `<p class="alert alert-error">Chyba při načítání detailu vozidla: ${escapeHtml(error.message)}</p>`;
            }
        }

        // Zobrazení detailu vozidla v modal okně
        // Smazání vozidla
        async function deleteVehicle(vehicleId) {
            if (!vehicleId) {
                showAlert('Chyba: Vozidlo není vybráno', 'error');
                return;
            }

            // Potvrzení smazání
            const vehicle = await apiCall(`/api/v1/vehicles/${vehicleId}`, 'GET');
            const vehicleName = vehicle.nickname || vehicle.brand || 'Vozidlo';

            if (!confirm(`Opravdu chcete smazat vozidlo "${vehicleName}"?\n\nTato akce je nevratná a smaže také všechny servisní záznamy a připomínky spojené s tímto vozidlem.`)) {
                return;
            }

            try {
                showAlert('Mažu vozidlo...', 'info');
                await apiCall(`/api/v1/vehicles/${vehicleId}`, 'DELETE');
                showAlert('Vozidlo bylo úspěšně smazáno', 'success');

                // Zavřít detail vozidla
                closeVehicleModal();
                const detail = document.getElementById('vehicleDetail');
                if (detail) {
                    detail.classList.remove('active');
                }
                currentVehicleId = null;

                // Načíst aktualizovaný seznam vozidel
                await loadVehicles();

                // Přepnout na záložku s vozidly
                switchTab('vehicles');
            } catch (error) {
                console.error("Error deleting vehicle:");
                showAlert('Nepodařilo se smazat vozidlo: ' + (error.message || 'Neznámá chyba'), 'error');
            }
        }

        async function showVehicleDetail(vehicleId) {
            currentVehicleId = vehicleId;

            const modal = document.getElementById('vehicleDetailModal');
            const modalBody = document.getElementById('vehicleModalBody');
            const modalTitle = document.getElementById('vehicleModalTitle');

            if (!modal || !modalBody) return;

            // Zobrazit modal
            openStaticOverlayModal(modal, {
                scrollTargetSelector: '.vehicle-modal-body',
            });

            // Zobrazit loading
            modalBody.innerHTML = '<div class="loading">Načítám...</div>';
            modalTitle.textContent = 'Detail vozidla';

            try {
                // Načíst data vozidla
                const vehicle = await apiCall(`/api/v1/vehicles/${vehicleId}`, 'GET');

                // Uložit aktuální vozidlo pro editaci
                window.currentVehicle = vehicle;

                // Aktualizovat název v hlavičce modalu
                modalTitle.textContent = vehicle.nickname || 'Detail vozidla';
                const vehicleBrandModel = [vehicle.brand, vehicle.model].filter(Boolean).join(' ') || 'Nezadáno';
                const vehiclePlate = vehicle.plate || 'Nezadáno';
                const vehicleStkDate = formatDateCZ(vehicle.stk_valid_until);
                const isServiceMode = isServiceWorkspaceRole();
                const serviceQuickActionsHtml = isServiceMode ? `
                    <div class="service-workspace-customer-actions" style="margin: 0 0 12px;">
                        <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "openServiceReservationComposer_e4398f77", Number(vehicleId))}>
                            Nová rezervace
                        </button>
                        <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "openServiceReminderComposer_0a77658d", Number(vehicleId))}>
                            Nová připomínka
                        </button>
                    </div>
                ` : '';
                const deleteVehicleButtonHtml = isServiceMode ? '' : `
                    <button ${legacyActionAttributes("click", "deleteVehicle_624fafe1", vehicleId)} class="vehicle-service-btn delete">
                        🗑️ Smazat
                    </button>
                `;

                // Zobrazit data vozidla - minimalistický design s možností editace
                modalBody.innerHTML = `
                    <div class="vehicle-modal-content-grid">
                        <div class="vehicle-modal-section vehicle-modal-section-info">
                            <h3>Data vozidla</h3>
                            <div class="vehicle-mobile-summary">
                                <div class="vehicle-mobile-chip">
                                    <span class="chip-label">SPZ</span>
                                    <span class="chip-value">${escapeHtml(vehiclePlate)}</span>
                                </div>
                                <div class="vehicle-mobile-chip">
                                    <span class="chip-label">Model</span>
                                    <span class="chip-value">${escapeHtml(vehicleBrandModel)}</span>
                                </div>
                                <div class="vehicle-mobile-chip">
                                    <span class="chip-label">STK</span>
                                    <span class="chip-value">${escapeHtml(vehicleStkDate)}</span>
                                </div>
                            </div>
                            <div class="vehicle-info-row">
                                <span class="vehicle-info-label">Fotka vozidla</span>
                                <div style="display:flex; flex-direction:column; align-items:flex-end; gap:8px; width:100%;">
                                    ${vehicle.photo_path ? `
                                        <div class="vehicle-photo-preview-wrap" style="max-width: 210px; width: 100%;">
                                            <img id="vehicle-photo-preview-modal-${escapeHtml(vehicleId)}" alt="Fotka vozidla ${escapeHtml(vehicle.nickname || '')}" loading="lazy">
                                        </div>
                                    ` : '<span class="vehicle-info-value empty">Bez fotky</span>'}
                                    <div class="vehicle-photo-actions" style="justify-content:flex-end;">
                                        <input
                                            type="file"
                                            id="vehicle-photo-upload-${escapeHtml(vehicleId)}"
                                            accept="image/*"
                                            style="display:none;"
                                            ${legacyActionAttributes("change", "handleVehiclePhotoUpload_4167fc86", vehicleId)}
                                        >
                                        <button
                                            type="button"
                                            class="btn-secondary"
                                            ${legacyActionAttributes("click", "getElementById_a0ecb1b8", vehicleId)}
                                        >
                                            📷 Nahrát z galerie
                                        </button>
                                        ${vehicle.photo_path ? `
                                            <button type="button" class="btn-danger" ${legacyActionAttributes("click", "deleteVehiclePhoto_0ab86de5", vehicleId)}>
                                                🗑️ Smazat fotku
                                            </button>
                                        ` : ''}
                                    </div>
                                </div>
                            </div>
                            <div class="vehicle-info-list">
                                <!-- Název - editovatelné -->
                                <div class="vehicle-info-row editable" data-field="nickname" data-vehicle-id="${escapeHtml(vehicleId)}">
                                    <span class="vehicle-info-label">Název</span>
                                    <div class="vehicle-info-edit" style="display: none;">
                                        <input type="text" id="edit-nickname-modal-${escapeHtml(vehicleId)}" value="${escapeHtml(vehicle.nickname || '')}" placeholder="Název vozidla">
                                        <div class="vehicle-info-actions">
                                            <button class="vehicle-info-btn save" ${legacyActionAttributes("click", "saveVehicleFieldModal_ac7bea60", vehicleId)}>Uložit</button>
                                            <button class="vehicle-info-btn cancel" ${legacyActionAttributes("click", "cancelEditModal_f36251c7", vehicleId)}>Zrušit</button>
                                        </div>
                                    </div>
                                    <div class="vehicle-info-display" style="display: flex; align-items: center; justify-content: space-between; flex: 1; gap: 12px; width: 100%;">
                                        <span class="vehicle-info-value ${!vehicle.nickname ? 'empty' : ''}" style="flex: 1; min-width: 0;">${escapeHtml(vehicle.nickname || 'Nezadáno')}</span>
                                        <button class="vehicle-info-btn" ${legacyActionAttributes("click", "startEditModal_c9c8fba8", vehicleId)} title="Upravit název" style="flex-shrink: 0;">✏️</button>
                                    </div>
                                </div>

                                <!-- SPZ - editovatelné -->
                                <div class="vehicle-info-row editable" data-field="plate" data-vehicle-id="${escapeHtml(vehicleId)}">
                                    <span class="vehicle-info-label">SPZ</span>
                                    <div class="vehicle-info-edit" style="display: none;">
                                        <input type="text" id="edit-plate-modal-${escapeHtml(vehicleId)}" value="${escapeHtml(vehicle.plate || '')}" placeholder="SPZ">
                                        <div class="vehicle-info-actions">
                                            <button class="vehicle-info-btn save" ${legacyActionAttributes("click", "saveVehicleFieldModal_744cb514", vehicleId)}>Uložit</button>
                                            <button class="vehicle-info-btn cancel" ${legacyActionAttributes("click", "cancelEditModal_865ff583", vehicleId)}>Zrušit</button>
                                        </div>
                                    </div>
                                    <div class="vehicle-info-display" style="display: flex; align-items: center; justify-content: space-between; flex: 1; gap: 12px; width: 100%;">
                                        <span class="vehicle-info-value ${!vehicle.plate ? 'empty' : ''}" style="flex: 1; min-width: 0;">${escapeHtml(vehicle.plate || 'Nezadáno')}</span>
                                        <button class="vehicle-info-btn" ${legacyActionAttributes("click", "startEditModal_4f44e6af", vehicleId)} title="Upravit SPZ" style="flex-shrink: 0;">✏️</button>
                                    </div>
                                </div>

                                <!-- VIN - pouze zobrazení -->
                                <div class="vehicle-info-row">
                                    <span class="vehicle-info-label">VIN</span>
                                    <span class="vehicle-info-value vehicle-vin-value ${!vehicle.vin ? 'empty' : ''}">${escapeHtml(vehicle.vin || 'Nezadáno')}</span>
                                </div>

                                ${vehicle.brand ? `
                                <div class="vehicle-info-row">
                                    <span class="vehicle-info-label">Značka</span>
                                    <span class="vehicle-info-value">${escapeHtml(vehicle.brand)}</span>
                                </div>
                                ` : ''}

                                ${vehicle.model ? `
                                <div class="vehicle-info-row">
                                    <span class="vehicle-info-label">Model</span>
                                    <span class="vehicle-info-value">${escapeHtml(vehicle.model)}</span>
                                </div>
                                ` : ''}

                                ${vehicle.year ? `
                                <div class="vehicle-info-row">
                                    <span class="vehicle-info-label">Rok výroby</span>
                                    <span class="vehicle-info-value">${escapeHtml(vehicle.year)}</span>
                                </div>
                                ` : ''}

                                ${vehicle.engine ? `
                                <div class="vehicle-info-row">
                                    <span class="vehicle-info-label">Motor</span>
                                    <span class="vehicle-info-value">${escapeHtml(vehicle.engine)}</span>
                                </div>
                                ` : ''}

                                <div class="vehicle-info-row">
                                    <span class="vehicle-info-label">Platnost STK</span>
                                    <span class="vehicle-info-value">${escapeHtml(vehicleStkDate)}</span>
                                </div>

                                <!-- Poznámky - editovatelné -->
                                <div class="vehicle-info-row editable" data-field="notes" data-vehicle-id="${escapeHtml(vehicleId)}">
                                    <span class="vehicle-info-label">Poznámky</span>
                                    <div class="vehicle-info-edit" style="display: none; flex-direction: column; gap: 8px; flex: 1;">
                                        <textarea id="edit-notes-modal-${escapeHtml(vehicleId)}" placeholder="Poznámky k vozidlu" rows="4">${escapeHtml(vehicle.notes || '')}</textarea>
                                        <div class="vehicle-info-actions">
                                            <button class="vehicle-info-btn save" ${legacyActionAttributes("click", "saveVehicleFieldModal_56abb99a", vehicleId)}>Uložit</button>
                                            <button class="vehicle-info-btn cancel" ${legacyActionAttributes("click", "cancelEditModal_05232943", vehicleId)}>Zrušit</button>
                                        </div>
                                    </div>
                                    <div class="vehicle-info-display" style="display: flex; align-items: flex-start; justify-content: space-between; flex: 1; gap: 12px; width: 100%;">
                                        <span class="vehicle-info-value ${!vehicle.notes ? 'empty' : ''}" style="white-space: pre-wrap; line-height: 1.6; text-align: left; flex: 1; min-width: 0;">${escapeHtml(vehicle.notes || 'Nezadáno')}</span>
                                        <button class="vehicle-info-btn" ${legacyActionAttributes("click", "startEditModal_e8e688b9", vehicleId)} style="flex-shrink: 0;" title="Upravit poznámky">✏️</button>
                                    </div>
                                </div>

                                <div class="vehicle-info-row">
                                    <span class="vehicle-info-label">Přidáno</span>
                                    <span class="vehicle-info-value">${escapeHtml(new Date(vehicle.created_at).toLocaleDateString('cs-CZ'))}</span>
                                </div>
                            </div>
                        </div>

                        <div class="vehicle-modal-section vehicle-modal-section-service">
                            <div class="vehicle-service-header">
                                <h3>Servisní úkony</h3>
                                <div class="vehicle-service-actions">
                                    <button ${legacyActionAttributes("click", "generateServiceRecordsPDF_0c66ea62", vehicleId)} class="vehicle-service-btn pdf">
                                        📄 PDF
                                    </button>
                                    <button ${legacyActionAttributes("click", "openAddServiceRecordModal_384438cb", vehicleId)} class="vehicle-service-btn add">
                                        + Přidat záznam
                                    </button>
                                    ${deleteVehicleButtonHtml}
                                </div>
                            </div>
                            ${serviceQuickActionsHtml}

                            <!-- AI záznamy (vytvořené asistentem) - dlaždice -->
                            <div id="ai-service-records-modal-${escapeHtml(vehicleId)}" class="ai-service-records-list" style="margin-bottom: 20px;"></div>
                            <!-- Běžné servisní záznamy - dlaždice -->
                            <div id="service-records-modal-${escapeHtml(vehicleId)}" class="service-records-grid"></div>
                            <div id="tachometer-history-modal-${escapeHtml(vehicleId)}" class="vehicle-tachometer-history-shell"></div>
                        </div>
                    </div>
                `;

                // Načíst náhled fotky přes autorizovaný fetch (img tag neposílá Authorization header)
                if (vehicle.photo_path) {
                    const modalPhoto = document.getElementById(`vehicle-photo-preview-modal-${vehicleId}`);
                    if (modalPhoto) {
                        try {
                            await hydrateVehiclePhotoPreview(vehicleId, modalPhoto);
                        } catch (photoError) {
                            console.warn("[VEHICLE] Nepodařilo se načíst náhled fotky:");
                        }
                    }
                } else {
                    revokeVehiclePhotoObjectUrl(vehicleId);
                }

                // Načíst servisní záznamy
                await loadServiceRecordsModal(vehicleId);
                await loadVehicleTachometerHistorySection(vehicleId);
                window.CustomerFeatures?.vehicleLoaded(vehicle);

            } catch (error) {
                console.error("Error loading vehicle detail:");
                modalBody.innerHTML = `<p class="alert alert-error">Chyba při načítání detailu vozidla: ${escapeHtml(error.message)}</p>`;
            }
        }

        // Zavření modal okna
        function closeVehicleModal() {
            const modal = document.getElementById('vehicleDetailModal');
            if (modal) {
                closeStaticOverlayModal(modal);
                modal.dataset.nestedModalOpen = '0';
                if (currentVehicleId) {
                    revokeVehiclePhotoObjectUrl(currentVehicleId);
                }
                currentVehicleId = null;
            }
        }

        // Zavření modalu pomocí ESC klávesy
        document.addEventListener('keydown', function(event) {
            if (event.key === 'Escape') {
                const floatingModalRoot = document.getElementById(APP_FLOATING_MODAL_ROOT_ID);
                if (floatingModalRoot) {
                    const hasReservationModal = !!floatingModalRoot.querySelector('.reservation-create')
                        || !!floatingModalRoot.querySelector('.reservation-detail-modal');
                    const hasReminderModal = !!floatingModalRoot.querySelector('.reminder-create')
                        || !!floatingModalRoot.querySelector('.reminder-detail-modal');
                    unmountFloatingModal();
                    if (hasReservationModal) {
                        loadReservations();
                    } else if (hasReminderModal) {
                        loadReminders();
                    }
                    return;
                }
                const vehicleModal = document.getElementById('vehicleDetailModal');
                const addServiceModal = document.getElementById('addServiceRecordModal');
                const detailServiceModal = document.getElementById('serviceRecordDetailModal');
                const attachmentPreviewModal = document.getElementById('attachmentPreviewModal');
                if (attachmentPreviewModal && attachmentPreviewModal.style.display === 'flex') {
                    closeAttachmentPreviewModal();
                } else if (detailServiceModal && detailServiceModal.style.display === 'flex') {
                    closeServiceRecordDetailModal();
                } else if (addServiceModal && addServiceModal.style.display === 'flex') {
                    closeAddServiceRecordModal();
                } else if (vehicleModal && vehicleModal.style.display === 'flex') {
                    closeVehicleModal();
                }
            }
        });

        async function uploadServiceRecordAttachment(vehicleId, file) {
            if (!vehicleId || !file) {
                throw new Error('Chybí vozidlo nebo soubor.');
            }
            const payload = {
                file_name: file.name || 'doklad.pdf',
                file_mime_type: file.type || 'application/octet-stream',
                file_content_base64: await fileToBase64Payload(file),
            };
            return apiCall(`/api/v1/vehicles/${vehicleId}/records/attachments/upload`, 'POST', payload);
        }

        async function fetchServiceRecordAttachmentBlob(relativeUrl) {
            const normalizedUrl = String(relativeUrl || '').trim();
            if (!normalizedUrl) {
                throw new Error('Příloha nemá platný odkaz.');
            }

            const token = AdminBrowserSession.token();
            if (!token) {
                throw new Error('Pro otevření přílohy musíte být přihlášeni.');
            }

            const headers = {
                'Accept': 'application/pdf,application/octet-stream,image/*,*/*',
                'Authorization': `Bearer ${token}`,
            };
            appendClientGeoHeaders(headers);
            API_URL = getApiBaseUrl();
            const response = await AdminBrowserSession.request(`${API_URL}${normalizedUrl}`, {
                method: 'GET',
                headers,
                credentials: 'include',
                mode: 'cors',
                cache: 'no-cache',
            });

            if (!response.ok) {
                let errorText = `HTTP ${response.status}`;
                try {
                    const body = await response.text();
                    if (body) errorText = body;
                } catch (e) {
                    // ignore parse issue
                }
                throw new Error(errorText);
            }

            const blob = await response.blob();
            if (!blob || blob.size === 0) {
                throw new Error('Soubor je prázdný.');
            }
            return blob;
        }

        function formatRecordMoney(value, currency = 'CZK') {
            const amount = Number(value);
            if (!Number.isFinite(amount)) return '—';
            const normalizedCurrency = String(currency || 'CZK').toUpperCase();
            const suffix = normalizedCurrency === 'CZK' ? 'Kč' : normalizedCurrency;
            return `${amount.toLocaleString('cs-CZ', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${suffix}`;
        }

        function formatRecordQuantity(value) {
            if (value === null || value === undefined || value === '') return '—';
            const parsed = Number(value);
            if (!Number.isFinite(parsed)) return escapeHtml(String(value));
            return parsed.toLocaleString('cs-CZ', { maximumFractionDigits: 3 });
        }

        function normalizeServiceLink(rawValue) {
            const value = String(rawValue || '').trim();
            if (!value) return '';
            const lower = value.toLowerCase();
            if (lower.startsWith('https://') || lower.startsWith('http://') || lower.startsWith('mailto:')) {
                return value;
            }
            if (/^[a-z0-9][a-z0-9.-]+\.[a-z]{2,}(?:\/.*)?$/i.test(value)) {
                return `https://${value}`;
            }
            return '';
        }

        const SERVICE_REPORT_META_KIND = 'service_report_meta';
        const serviceReportEditorState = {};
        const serviceRecordEditContext = {};

        function roundTo2(value) {
            const parsed = Number(value);
            if (!Number.isFinite(parsed)) return 0;
            return Math.round(parsed * 100) / 100;
        }

        function parseOptionalNumber(rawValue) {
            if (rawValue === null || rawValue === undefined) return null;
            const normalized = String(rawValue).replace(/\s/g, '').replace(',', '.');
            if (!normalized) return null;
            const parsed = Number(normalized);
            return Number.isFinite(parsed) ? parsed : null;
        }

        function normalizeReportItem(rawItem, fallbackCurrency = 'CZK') {
            const source = rawItem && typeof rawItem === 'object' ? rawItem : {};
            const name = String(source.name || '').trim();
            const quantity = parseOptionalNumber(source.quantity);
            const unitPrice = parseOptionalNumber(source.unit_price);
            let totalPrice = parseOptionalNumber(source.total_price);
            if (totalPrice === null && quantity !== null && unitPrice !== null) {
                totalPrice = roundTo2(quantity * unitPrice);
            }
            const unit = String(source.unit || '').trim();
            return {
                name,
                quantity,
                unit,
                unit_price: unitPrice,
                total_price: totalPrice,
                currency: String(source.currency || fallbackCurrency || 'CZK').toUpperCase(),
            };
        }

        function isLaborServiceReportItem(item) {
            const unit = String(item?.unit || '').trim().toLowerCase();
            if (['h', 'hod', 'hod.', 'hodina', 'hodiny', 'hr', 'nh'].includes(unit)) return true;

            const name = String(item?.name || '').trim().toLowerCase();
            if (!name) return false;
            const laborKeywords = [
                'práce', 'prace', 'servisní práce', 'servisni prace', 'hodinová sazba', 'hodinova sazba',
                'diagnost', 'montáž', 'montaz', 'demontáž', 'demontaz', 'oprava', 'seřízení', 'serizeni'
            ];
            return laborKeywords.some((keyword) => name.includes(keyword));
        }

        function deriveLaborMaterialBreakdownFromItems(items) {
            const source = Array.isArray(items) ? items : [];
            let laborTotal = 0;
            let materialsTotal = 0;
            let laborHours = 0;
            let laborHourRate = null;
            let hasLabor = false;
            let hasMaterials = false;

            source.forEach((item) => {
                const normalized = normalizeReportItem(item, item?.currency || 'CZK');
                const total = parseOptionalNumber(normalized.total_price);
                if (!Number.isFinite(total) || total <= 0) return;

                const qty = parseOptionalNumber(normalized.quantity);
                const unitPrice = parseOptionalNumber(normalized.unit_price);
                if (isLaborServiceReportItem(normalized)) {
                    hasLabor = true;
                    laborTotal += Number(total);

                    const unit = String(normalized.unit || '').trim().toLowerCase();
                    if (Number.isFinite(qty) && qty > 0 && ['h', 'hod', 'hod.', 'hodina', 'hodiny', 'hr', 'nh'].includes(unit)) {
                        laborHours += Number(qty);
                        if (laborHourRate === null && Number.isFinite(unitPrice) && unitPrice > 0) {
                            laborHourRate = Number(unitPrice);
                        } else if (laborHourRate === null) {
                            laborHourRate = Number(total) / Number(qty);
                        }
                    } else if (laborHourRate === null && Number.isFinite(unitPrice) && unitPrice > 0) {
                        laborHourRate = Number(unitPrice);
                    }
                } else {
                    hasMaterials = true;
                    materialsTotal += Number(total);
                }
            });

            return {
                labor_total: hasLabor ? roundTo2(laborTotal) : null,
                materials_total: hasMaterials ? roundTo2(materialsTotal) : null,
                labor_hours: laborHours > 0 ? roundTo2(laborHours) : null,
                labor_hour_rate: Number.isFinite(laborHourRate) && laborHourRate > 0 ? roundTo2(laborHourRate) : null,
            };
        }

        function sanitizeServiceReportPayload(rawPayload) {
            const raw = rawPayload && typeof rawPayload === 'object' ? rawPayload : {};
            const currency = String(raw.currency || 'CZK').toUpperCase();
            const items = Array.isArray(raw.items)
                ? raw.items.map((item) => normalizeReportItem(item, currency)).filter((item) => item.name)
                : [];

            const report = {
                source_type: String(raw.source_type || 'manual').trim().toLowerCase() || 'manual',
                document_number: String(raw.document_number || '').trim() || null,
                supplier_name: String(raw.supplier_name || '').trim() || null,
                supplier_email: String(raw.supplier_email || '').trim() || null,
                supplier_website: String(raw.supplier_website || '').trim() || null,
                service_link: normalizeServiceLink(raw.service_link || raw.supplier_website || ''),
                customer_name: String(raw.customer_name || '').trim() || null,
                service_summary: String(raw.service_summary || '').trim() || null,
                issue_description: String(raw.issue_description || '').trim() || null,
                technician_name: String(raw.technician_name || '').trim() || null,
                technician_initials: String(raw.technician_initials || '').trim() || null,
                issue_date: String(raw.issue_date || '').trim() || null,
                due_date: String(raw.due_date || '').trim() || null,
                currency,
                labor_hours: parseOptionalNumber(raw.labor_hours),
                labor_hour_rate: parseOptionalNumber(raw.labor_hour_rate),
                labor_total: parseOptionalNumber(raw.labor_total),
                materials_total: parseOptionalNumber(raw.materials_total),
                subtotal_without_vat: parseOptionalNumber(raw.subtotal_without_vat),
                vat_rate: parseOptionalNumber(raw.vat_rate),
                vat_amount: parseOptionalNumber(raw.vat_amount),
                total_with_vat: parseOptionalNumber(raw.total_with_vat),
                items,
            };

            if (!report.service_link && report.supplier_email) {
                report.service_link = `mailto:${report.supplier_email}`;
            }
            if (!report.technician_initials && report.technician_name) {
                const initials = String(report.technician_name)
                    .split(/[\s-]+/)
                    .filter(Boolean)
                    .slice(0, 3)
                    .map((part) => part[0]?.toUpperCase() || '')
                    .join('');
                report.technician_initials = initials || null;
            }

            const inferred = deriveLaborMaterialBreakdownFromItems(items);
            if (report.labor_total === null && inferred.labor_total !== null) {
                report.labor_total = inferred.labor_total;
            }
            if (report.materials_total === null && inferred.materials_total !== null) {
                report.materials_total = inferred.materials_total;
            }
            if (report.labor_hours === null && inferred.labor_hours !== null) {
                report.labor_hours = inferred.labor_hours;
            }
            if (report.labor_hour_rate === null && inferred.labor_hour_rate !== null) {
                report.labor_hour_rate = inferred.labor_hour_rate;
            }

            if (report.subtotal_without_vat === null) {
                const subtotal = roundTo2((report.materials_total || 0) + (report.labor_total || 0));
                report.subtotal_without_vat = subtotal > 0 ? subtotal : null;
            }
            if (report.vat_amount === null && report.total_with_vat !== null && report.subtotal_without_vat !== null) {
                const computedVat = roundTo2(report.total_with_vat - report.subtotal_without_vat);
                if (computedVat >= 0.01) {
                    report.vat_amount = computedVat;
                }
            }
            if (report.total_with_vat === null) {
                const total = roundTo2((report.subtotal_without_vat || 0) + (report.vat_amount || 0));
                report.total_with_vat = total > 0 ? total : null;
            }
            return report;
        }

        function buildFallbackServiceReport(record) {
            const category = String(record?.category || 'JINE').trim();
            const categoryInfo = SERVICE_CATEGORIES.find((item) => item.value === category);
            const summary = String(record?.description || '').trim();
            const note = String(record?.note || '').trim();
            return sanitizeServiceReportPayload({
                source_type: 'manual',
                service_summary: summary || (categoryInfo ? categoryInfo.label : null),
                issue_description: note || null,
                currency: 'CZK',
                materials_total: parseOptionalNumber(record?.price),
                total_with_vat: parseOptionalNumber(record?.price),
                items: [],
            });
        }

        function extractServiceReportFromAttachments(recordAttachments, fallbackRecord = null) {
            const list = Array.isArray(recordAttachments) ? recordAttachments : [];
            let fallbackSummary = null;
            for (const attachment of list) {
                if (attachment && attachment.parsed_summary && typeof attachment.parsed_summary === 'object') {
                    if (!fallbackSummary) {
                        fallbackSummary = attachment.parsed_summary;
                    }
                    if (!isParsedSummaryLikelyInvalid(attachment.parsed_summary)) {
                        return sanitizeServiceReportPayload(attachment.parsed_summary);
                    }
                }
            }
            if (fallbackSummary) {
                return sanitizeServiceReportPayload(fallbackSummary);
            }
            return buildFallbackServiceReport(fallbackRecord || {});
        }

        function getServiceReportState(prefix) {
            if (!serviceReportEditorState[prefix]) {
                serviceReportEditorState[prefix] = sanitizeServiceReportPayload({});
            }
            return serviceReportEditorState[prefix];
        }

        function ensureServiceReportItems(prefix) {
            const report = getServiceReportState(prefix);
            if (!Array.isArray(report.items)) report.items = [];
            if (report.items.length === 0) {
                report.items.push(normalizeReportItem({ name: '', quantity: null, unit: '', unit_price: null, total_price: null }, report.currency));
            }
            return report;
        }

        function refreshServiceReportComputedValues(prefix) {
            const report = ensureServiceReportItems(prefix);
            report.items = report.items.map((item) => {
                const normalized = normalizeReportItem(item, report.currency);
                if (normalized.total_price === null && normalized.quantity !== null && normalized.unit_price !== null) {
                    normalized.total_price = roundTo2(normalized.quantity * normalized.unit_price);
                }
                return normalized;
            });

            const inferred = deriveLaborMaterialBreakdownFromItems(report.items);
            report.materials_total = inferred.materials_total;
            if (report.labor_hours === null && inferred.labor_hours !== null) {
                report.labor_hours = inferred.labor_hours;
            }
            if (report.labor_hour_rate === null && inferred.labor_hour_rate !== null) {
                report.labor_hour_rate = inferred.labor_hour_rate;
            }

            if (report.labor_hours !== null && report.labor_hour_rate !== null) {
                report.labor_total = roundTo2(report.labor_hours * report.labor_hour_rate);
            } else if (inferred.labor_total !== null) {
                report.labor_total = inferred.labor_total;
            } else if (report.labor_total !== null) {
                report.labor_total = roundTo2(report.labor_total);
            } else {
                report.labor_total = null;
            }

            const subtotal = roundTo2((report.materials_total || 0) + (report.labor_total || 0));
            report.subtotal_without_vat = subtotal > 0 ? subtotal : null;

            if (report.vat_rate !== null && subtotal > 0) {
                report.vat_amount = roundTo2(subtotal * (report.vat_rate / 100));
            } else if (report.vat_amount !== null) {
                report.vat_amount = roundTo2(report.vat_amount);
            }

            const total = roundTo2((report.subtotal_without_vat || 0) + (report.vat_amount || 0));
            report.total_with_vat = total > 0 ? total : null;

            const totalLabelEl = document.getElementById(`serviceReportTotalLabel-${prefix}`);
            if (totalLabelEl) {
                totalLabelEl.textContent = formatRecordMoney(report.total_with_vat, report.currency);
            }
            const subtotalLabelEl = document.getElementById(`serviceReportSubtotalLabel-${prefix}`);
            if (subtotalLabelEl) {
                subtotalLabelEl.textContent = formatRecordMoney(report.subtotal_without_vat, report.currency);
            }
            const laborLabelEl = document.getElementById(`serviceReportLaborLabel-${prefix}`);
            if (laborLabelEl) {
                laborLabelEl.textContent = formatRecordMoney(report.labor_total, report.currency);
            }
            const materialsLabelEl = document.getElementById(`serviceReportMaterialsLabel-${prefix}`);
            if (materialsLabelEl) {
                materialsLabelEl.textContent = formatRecordMoney(report.materials_total, report.currency);
            }
            const vatLabelEl = document.getElementById(`serviceReportVatLabel-${prefix}`);
            if (vatLabelEl) {
                vatLabelEl.textContent = formatRecordMoney(report.vat_amount, report.currency);
            }
        }

        function renderServiceReportEditor(prefix) {
            const container = document.getElementById(`serviceReportEditor-${prefix}`);
            if (!container) return;
            const report = ensureServiceReportItems(prefix);
            const rowsHtml = report.items.map((item, index) => `
                <tr>
                    <td><input type="text" id="${escapeHtml(prefix)}-item-name-${escapeHtml(index)}" value="${escapeHtml(String(item.name || ''))}" placeholder="Název práce / dílu" ${legacyActionAttributes("input", "updateServiceReportItemField_9e0f4764", prefix, index)}></td>
                    <td class="col-qty"><input type="number" id="${escapeHtml(prefix)}-item-qty-${escapeHtml(index)}" value="${escapeHtml(item.quantity !== null ? String(item.quantity) : '')}" min="0" step="0.001" ${legacyActionAttributes("input", "updateServiceReportItemField_ad8afce2", prefix, index)}></td>
                    <td class="col-unit"><input type="text" id="${escapeHtml(prefix)}-item-unit-${escapeHtml(index)}" value="${escapeHtml(String(item.unit || ''))}" placeholder="ks/h" ${legacyActionAttributes("input", "updateServiceReportItemField_a414fc26", prefix, index)}></td>
                    <td class="col-price"><input type="number" id="${escapeHtml(prefix)}-item-price-${escapeHtml(index)}" value="${escapeHtml(item.unit_price !== null ? String(item.unit_price) : '')}" min="0" step="0.01" ${legacyActionAttributes("input", "updateServiceReportItemField_59aa0f06", prefix, index)}></td>
                    <td class="col-total"><input type="number" id="${escapeHtml(prefix)}-item-total-${escapeHtml(index)}" value="${escapeHtml(item.total_price !== null ? String(item.total_price) : '')}" min="0" step="0.01" ${legacyActionAttributes("input", "updateServiceReportItemField_ccaec052", prefix, index)}></td>
                    <td style="white-space:nowrap;"><button type="button" class="btn btn-secondary" style="padding:6px 8px;" ${legacyActionAttributes("click", "removeServiceReportItemRow_c34afc59", prefix, index)}>✕</button></td>
                </tr>
            `).join('');

            container.innerHTML = `
                <div class="record-document-summary" style="margin-top:10px;">
                    <div style="color:#c7d2fe; font-size:12px; margin-bottom:6px;"><strong>Strukturovaná servisní zpráva</strong></div>
                    <div class="form-row" style="display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px; margin-bottom:10px;">
                        <div><label style="font-size:12px;color:#94a3b8;">Dodavatel / servis</label><input type="text" id="${escapeHtml(prefix)}-supplier-name" value="${escapeHtml(String(report.supplier_name || ''))}" ${legacyActionAttributes("input", "updateServiceReportField_ecbeffe9", prefix)}></div>
                        <div><label style="font-size:12px;color:#94a3b8;">Kontakt</label><input type="text" id="${escapeHtml(prefix)}-supplier-email" value="${escapeHtml(String(report.supplier_email || ''))}" ${legacyActionAttributes("input", "updateServiceReportField_1172f6b4", prefix)}></div>
                        <div><label style="font-size:12px;color:#94a3b8;">Technik / iniciály</label><input type="text" id="${escapeHtml(prefix)}-technician-name" value="${escapeHtml(String(report.technician_name || ''))}" ${legacyActionAttributes("input", "updateServiceReportField_542de729", prefix)}></div>
                        <div><label style="font-size:12px;color:#94a3b8;">Měna</label><input type="text" id="${escapeHtml(prefix)}-currency" value="${escapeHtml(String(report.currency || 'CZK'))}" ${legacyActionAttributes("input", "updateServiceReportField_a2c2ac4e", prefix)}></div>
                        <div><label style="font-size:12px;color:#94a3b8;">Rozsah prací</label><input type="text" id="${escapeHtml(prefix)}-service-summary" value="${escapeHtml(String(report.service_summary || ''))}" ${legacyActionAttributes("input", "updateServiceReportField_da3733a5", prefix)}></div>
                        <div><label style="font-size:12px;color:#94a3b8;">Popis závady</label><input type="text" id="${escapeHtml(prefix)}-issue-description" value="${escapeHtml(String(report.issue_description || ''))}" ${legacyActionAttributes("input", "updateServiceReportField_5c514df8", prefix)}></div>
                    </div>
                    <div class="record-items-table-wrap">
                        <table class="record-items-table">
                            <thead>
                                <tr>
                                    <th style="width:40%;">Položka</th>
                                    <th style="width:10%;">Počet</th>
                                    <th style="width:10%;">Jedn.</th>
                                    <th class="col-price" style="width:16%;">Cena/ks</th>
                                    <th class="col-total" style="width:16%;">Celkem</th>
                                    <th style="width:8%;"></th>
                                </tr>
                            </thead>
                            <tbody>${rowsHtml}</tbody>
                        </table>
                    </div>
                    <div style="margin-top:8px; display:flex; justify-content:flex-start;">
                        <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "addServiceReportItemRow_64949d99", prefix)}>+ Přidat položku</button>
                    </div>
                    <div class="form-row" style="display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; margin-top:12px;">
                        <div><label style="font-size:12px;color:#94a3b8;">Hodiny práce</label><input type="number" min="0" step="0.01" value="${escapeHtml(report.labor_hours !== null ? String(report.labor_hours) : '')}" ${legacyActionAttributes("input", "updateServiceReportField_7880e478", prefix)}></div>
                        <div><label style="font-size:12px;color:#94a3b8;">Sazba práce / hod</label><input type="number" min="0" step="0.01" value="${escapeHtml(report.labor_hour_rate !== null ? String(report.labor_hour_rate) : '')}" ${legacyActionAttributes("input", "updateServiceReportField_cd16696a", prefix)}></div>
                        <div><label style="font-size:12px;color:#94a3b8;">DPH %</label><input type="number" min="0" step="0.01" value="${escapeHtml(report.vat_rate !== null ? String(report.vat_rate) : '')}" ${legacyActionAttributes("input", "updateServiceReportField_f9802feb", prefix)}></div>
                    </div>
                    <div class="record-items-footer" style="margin-top:10px; justify-content:flex-start; gap:24px; flex-wrap:wrap;">
                        <span>Materiál: <strong id="serviceReportMaterialsLabel-${escapeHtml(prefix)}">—</strong></span>
                        <span>Práce: <strong id="serviceReportLaborLabel-${escapeHtml(prefix)}">—</strong></span>
                        <span>Základ: <strong id="serviceReportSubtotalLabel-${escapeHtml(prefix)}">—</strong></span>
                        <span>DPH: <strong id="serviceReportVatLabel-${escapeHtml(prefix)}">—</strong></span>
                        <span>Celkem: <strong id="serviceReportTotalLabel-${escapeHtml(prefix)}">—</strong></span>
                    </div>
                </div>
            `;
            refreshServiceReportComputedValues(prefix);
        }

        function initializeServiceReportEditor(prefix, initialReport) {
            serviceReportEditorState[prefix] = sanitizeServiceReportPayload(initialReport || {});
            renderServiceReportEditor(prefix);
        }

        function updateServiceReportField(prefix, field, value) {
            const report = getServiceReportState(prefix);
            if (field === 'currency') {
                report.currency = String(value || 'CZK').trim().toUpperCase() || 'CZK';
            } else if (['labor_hours', 'labor_hour_rate', 'vat_rate'].includes(field)) {
                report[field] = parseOptionalNumber(value);
            } else {
                report[field] = String(value || '').trim() || null;
                if (field === 'supplier_email' && report[field] && !report.service_link) {
                    report.service_link = `mailto:${report[field]}`;
                }
                if (field === 'technician_name') {
                    const initials = String(report[field] || '')
                        .split(/[\s-]+/)
                        .filter(Boolean)
                        .slice(0, 3)
                        .map((part) => part[0]?.toUpperCase() || '')
                        .join('');
                    report.technician_initials = initials || null;
                }
            }
            refreshServiceReportComputedValues(prefix);
        }

        function updateServiceReportItemField(prefix, index, field, value) {
            const report = ensureServiceReportItems(prefix);
            if (!report.items[index]) return;
            if (field === 'name' || field === 'unit') {
                report.items[index][field] = String(value || '').trim();
            } else {
                report.items[index][field] = parseOptionalNumber(value);
            }
            if (field === 'quantity' || field === 'unit_price') {
                const qty = parseOptionalNumber(report.items[index].quantity);
                const unitPrice = parseOptionalNumber(report.items[index].unit_price);
                if (qty !== null && unitPrice !== null) {
                    report.items[index].total_price = roundTo2(qty * unitPrice);
                    const totalInput = document.getElementById(`${prefix}-item-total-${index}`);
                    if (totalInput) totalInput.value = String(report.items[index].total_price);
                }
            } else if (field === 'total_price') {
                const qty = parseOptionalNumber(report.items[index].quantity);
                const totalPrice = parseOptionalNumber(report.items[index].total_price);
                if (qty !== null && qty > 0 && totalPrice !== null) {
                    report.items[index].unit_price = roundTo2(totalPrice / qty);
                    const unitPriceInput = document.getElementById(`${prefix}-item-price-${index}`);
                    if (unitPriceInput) unitPriceInput.value = String(report.items[index].unit_price);
                }
            }
            refreshServiceReportComputedValues(prefix);
        }

        function addServiceReportItemRow(prefix) {
            const report = ensureServiceReportItems(prefix);
            report.items.push(normalizeReportItem({ name: '', quantity: null, unit: '', unit_price: null, total_price: null }, report.currency));
            renderServiceReportEditor(prefix);
        }

        function removeServiceReportItemRow(prefix, index) {
            const report = ensureServiceReportItems(prefix);
            if (report.items.length <= 1) {
                report.items[0] = normalizeReportItem({ name: '', quantity: null, unit: '', unit_price: null, total_price: null }, report.currency);
            } else {
                report.items.splice(index, 1);
            }
            renderServiceReportEditor(prefix);
        }

        function getServiceReportEditorValue(prefix) {
            return sanitizeServiceReportPayload(getServiceReportState(prefix));
        }

        function isParsedSummaryLikelyInvalid(summary) {
            if (!summary || typeof summary !== 'object') return false;
            const items = Array.isArray(summary.items) ? summary.items : [];
            if (items.length === 0) return false;

            const suspiciousPatterns = [
                /\b\d{1,5}\s*\/\s*\d{1,5}[a-z]?\b/i, // adresa typu 2351/19a
                /\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b.*\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b/i, // řádek s více daty
                /^(celkov[aá]\s+částka|celkova\s+castka|celkem|zbýv[aá]\s+uhradit|zbyva\s+uhradit|uhrazeno)\b/i, // souhrnné řádky
            ];

            return items.some(item => {
                const name = String(item?.name || '').trim();
                if (!name) return false;
                return suspiciousPatterns.some(pattern => pattern.test(name));
            });
        }

        async function tryBuildParsedSummaryFromAttachment(vehicleId, attachment) {
            if (!attachment || !attachment.download_url) return null;
            try {
                const blob = await fetchServiceRecordAttachmentBlob(attachment.download_url);
                const payload = {
                    source_type: String(attachment.source_type || 'invoice').trim().toLowerCase() || 'invoice',
                    file_name: attachment.file_name || 'doklad',
                    file_mime_type: blob.type || attachment.mime_type || 'application/octet-stream',
                    file_content_base64: await fileToBase64Payload(blob),
                };
                const result = await apiCall(`/api/v1/vehicles/${vehicleId}/records/document-prefill`, 'POST', payload);
                const summary = result?.prefill?.service_report;
                return summary && typeof summary === 'object' ? summary : null;
            } catch (error) {
                console.warn("Nepodařilo se dopočítat položky z přílohy:");
                return null;
            }
        }

        let activeAttachmentPreviewUrl = null;

        function closeAttachmentPreviewModal() {
            const modal = document.getElementById('attachmentPreviewModal');
            const frame = document.getElementById('attachmentPreviewFrame');
            if (frame) {
                frame.removeAttribute('src');
            }
            if (modal) {
                closeStaticOverlayModal(modal);
            }
            if (activeAttachmentPreviewUrl) {
                URL.revokeObjectURL(activeAttachmentPreviewUrl);
                activeAttachmentPreviewUrl = null;
            }
        }

        function openAttachmentPreviewModal(blobUrl, titleText = 'Náhled dokladu') {
            let modal = document.getElementById('attachmentPreviewModal');
            if (!modal) {
                modal = document.createElement('div');
                modal.id = 'attachmentPreviewModal';
                modal.className = 'vehicle-modal app-modal-drawer';
                modal.style.display = 'none';
                modal.innerHTML = `
                    <div class="vehicle-modal-content" style="max-width: 1100px; width: 94vw; max-height: 94vh; overflow: hidden; display: flex; flex-direction: column;">
                        <div class="vehicle-modal-header" style="display:flex; align-items:center; justify-content:space-between; gap: 12px;">
                            <h2 id="attachmentPreviewTitle" style="margin:0; font-size: 22px;">Náhled dokladu</h2>
                            <button type="button" class="vehicle-modal-close" ${legacyActionAttributes("click", "closeAttachmentPreviewModal_75e4c0dd")}>&times;</button>
                        </div>
                        <div style="flex: 1; padding: 0 20px 20px; min-height: 60vh;">
                            <iframe
                                id="attachmentPreviewFrame"
                                title="Náhled přílohy"
                                sandbox=""
                                style="width: 100%; height: 100%; min-height: 62vh; border: 1px solid rgba(148, 163, 184, 0.3); border-radius: 8px; background: #0f172a;"
                            ></iframe>
                        </div>
                        <div style="padding: 0 20px 20px; display:flex; justify-content:flex-end;">
                            <button type="button" class="btn" style="background:#6b7280; color:#fff; border:none; border-radius:8px; padding:10px 16px;" ${legacyActionAttributes("click", "closeAttachmentPreviewModal_75e4c0dd")}>Zavřít</button>
                        </div>
                    </div>
                `;
                document.body.appendChild(modal);
            }

            const title = document.getElementById('attachmentPreviewTitle');
            if (title) {
                title.textContent = titleText || 'Náhled dokladu';
            }
            const frame = document.getElementById('attachmentPreviewFrame');
            if (frame) {
                frame.src = blobUrl;
            }
            openStaticOverlayModal(modal, {
                focusSelector: '.vehicle-modal-close',
            });
        }

        function decodePreviewHint(value) {
            try {
                return decodeURIComponent(String(value || ''));
            } catch (error) {
                return String(value || '');
            }
        }

        function looksLikePdfByHint(fileName, relativeUrl) {
            const nameHint = decodePreviewHint(fileName).trim().toLowerCase();
            const urlHint = decodePreviewHint(relativeUrl).trim().toLowerCase();
            return nameHint.includes('.pdf') || urlHint.includes('.pdf');
        }

        async function hasPdfMagicHeader(blob) {
            try {
                const header = await blob.slice(0, 5).text();
                return header === '%PDF-';
            } catch (error) {
                return false;
            }
        }

        async function openServiceRecordAttachmentPreview(encodedDownloadUrl, encodedFileName = '') {
            const relativeUrl = decodePreviewHint(encodedDownloadUrl).trim();
            if (!relativeUrl) {
                showAlert('Příloha nemá platný odkaz.', 'error');
                return;
            }
            const fileName = decodePreviewHint(encodedFileName).trim() || 'priloha';
            const likelyPdf = looksLikePdfByHint(fileName, relativeUrl);
            // Otevřít tab hned při kliknutí (pro pravděpodobné PDF), aby popup neblokoval prohlížeč.
            const previewWindow = likelyPdf ? window.open('', '_blank') : null;
            try {
                const blob = await fetchServiceRecordAttachmentBlob(relativeUrl);
                const blobType = String(blob?.type || '').toLowerCase();
                const isPdf = likelyPdf || blobType.includes('pdf') || await hasPdfMagicHeader(blob);
                const blobUrl = URL.createObjectURL(blob);

                if (isPdf) {
                    closeAttachmentPreviewModal();
                    if (previewWindow && !previewWindow.closed) {
                        previewWindow.opener = null;
                        previewWindow.location.replace(blobUrl);
                    } else {
                        const opened = window.open(blobUrl, '_blank');
                        if (!opened) {
                            URL.revokeObjectURL(blobUrl);
                            throw new Error('Prohlížeč zablokoval náhled v nové kartě. Povolte vyskakovací okna pro tento web.');
                        }
                        opened.opener = null;
                    }
                    // URL ponechat chvíli živé kvůli načtení PDF vieweru v nové kartě.
                    setTimeout(() => URL.revokeObjectURL(blobUrl), 120_000);
                    return;
                }

                if (previewWindow && !previewWindow.closed) {
                    previewWindow.close();
                }
                if (activeAttachmentPreviewUrl) {
                    URL.revokeObjectURL(activeAttachmentPreviewUrl);
                }
                activeAttachmentPreviewUrl = blobUrl;
                openAttachmentPreviewModal(blobUrl, `Náhled: ${fileName}`);
            } catch (error) {
                if (previewWindow) {
                    previewWindow.close();
                }
                console.error("Error opening service attachment preview:");
                showAlert('Nepodařilo se otevřít přílohu: ' + (error?.message || 'Neznámá chyba'), 'error');
            }
        }

        function parseServiceRecordAttachments(vehicleId, attachmentsRaw) {
            if (!attachmentsRaw) {
                return [];
            }
            try {
                const parsed = typeof attachmentsRaw === 'string' ? JSON.parse(attachmentsRaw) : attachmentsRaw;
                if (!Array.isArray(parsed)) {
                    return [];
                }
                return parsed
                    .filter(item => item && typeof item === 'object')
                    .map(item => ({
                        kind: item.kind || '',
                        file_name: item.file_name || 'Příloha',
                        file_size: Number(item.file_size) || null,
                        mime_type: item.mime_type || '',
                        source_type: item.source_type || '',
                        storage_key: item.storage_key || '',
                        path: item.path || '',
                        download_url: item.download_url || (item.storage_key ? `/api/v1/vehicles/${vehicleId}/records/attachments/download?key=${encodeURIComponent(item.storage_key)}` : ''),
                        can_preview: Boolean(item.download_url || item.storage_key),
                        parsed_summary: item.parsed_summary && typeof item.parsed_summary === 'object'
                            ? sanitizeServiceReportPayload(item.parsed_summary)
                            : null,
                    }))
                    .filter(item => Boolean(item.kind || item.parsed_summary || item.download_url));
            } catch (error) {
                console.warn("Nepodařilo se zpracovat přílohy servisního záznamu:");
                return [];
            }
        }

        function formatAttachmentSize(bytes) {
            const value = Number(bytes);
            if (!Number.isFinite(value) || value <= 0) return '';
            if (value < 1024) return `${value} B`;
            if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
            return `${(value / (1024 * 1024)).toFixed(1)} MB`;
        }

        // Seznam dostupných kategorií servisních záznamů
        const SERVICE_CATEGORIES = [
            { value: 'OLEJ', label: 'Olej', icon: '🛢️' },
            { value: 'BRZDY', label: 'Brzdy', icon: '🛑' },
            { value: 'PNEU', label: 'Pneumatiky', icon: '⭕' },
            { value: 'STK', label: 'STK', icon: '✅' },
            { value: 'DIAGNOSTIKA', label: 'Diagnostika', icon: '🔧' },
            { value: 'FILTRY', label: 'Filtry', icon: '🔍' },
            { value: 'CHLADICI', label: 'Chladicí systém', icon: '❄️' },
            { value: 'VYFUK', label: 'Výfuk', icon: '💨' },
            { value: 'OSVETLENI', label: 'Osvětlení', icon: '💡' },
            { value: 'KAROSERIE', label: 'Karoserie', icon: '🚗' },
            { value: 'INTERIER', label: 'Interiér', icon: '🪑' },
            { value: 'ELEKTRIKA', label: 'Elektrika', icon: '⚡' },
            { value: 'KLIMATIZACE', label: 'Klimatizace', icon: '🌡️' },
            { value: 'PREVENTIVNI', label: 'Preventivní', icon: '🛡️' },
            { value: 'OPRAVA', label: 'Oprava', icon: '🔨' },
            { value: 'JINE', label: 'Jiné', icon: '📋' }
        ];
        let addServiceRecordDocumentPrefill = null;

        function toDateTimeLocalString(value) {
            const date = new Date(value);
            if (Number.isNaN(date.getTime())) {
                return '';
            }
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            const hours = String(date.getHours()).padStart(2, '0');
            const minutes = String(date.getMinutes()).padStart(2, '0');
            return `${year}-${month}-${day}T${hours}:${minutes}`;
        }

        function setAddServiceRecordAnalysisStatus(messageHtml = '', tone = 'info') {
            const statusEl = document.getElementById('serviceAttachmentAnalysisStatus-add');
            if (!statusEl) return;
            if (!messageHtml) {
                statusEl.innerHTML = '';
                statusEl.style.display = 'none';
                return;
            }
            const toneMap = {
                info: { bg: 'rgba(59, 130, 246, 0.12)', border: 'rgba(59, 130, 246, 0.35)', text: '#bfdbfe' },
                success: { bg: 'rgba(16, 185, 129, 0.12)', border: 'rgba(16, 185, 129, 0.35)', text: '#86efac' },
                warning: { bg: 'rgba(245, 158, 11, 0.14)', border: 'rgba(245, 158, 11, 0.35)', text: '#fcd34d' },
                error: { bg: 'rgba(239, 68, 68, 0.12)', border: 'rgba(239, 68, 68, 0.35)', text: '#fca5a5' },
            };
            const style = toneMap[tone] || toneMap.info;
            statusEl.style.display = 'block';
            statusEl.style.marginTop = '10px';
            statusEl.style.padding = '10px 12px';
            statusEl.style.borderRadius = '8px';
            statusEl.style.border = `1px solid ${style.border}`;
            statusEl.style.background = style.bg;
            statusEl.style.color = style.text;
            statusEl.style.fontSize = '12px';
            statusEl.style.lineHeight = '1.45';
            statusEl.innerHTML = messageHtml;
        }

        function applyAddServiceRecordPrefill(prefillPayload) {
            const prefill = prefillPayload && typeof prefillPayload === 'object' ? prefillPayload : {};
            const categoryValue = String(prefill.category || '').trim().toUpperCase();
            if (categoryValue && !document.getElementById('serviceCategory-add')?.value) {
                const categoryInfo = SERVICE_CATEGORIES.find(cat => cat.value === categoryValue);
                if (categoryInfo) {
                    selectCategory(categoryInfo.value, categoryInfo.label, categoryInfo.icon, 'add');
                }
            }

            const dateEl = document.getElementById('serviceDate-add');
            if (dateEl && prefill.performed_at) {
                dateEl.value = toDateTimeLocalString(prefill.performed_at);
            }

            const descriptionEl = document.getElementById('serviceDescription-add');
            if (descriptionEl && prefill.description && !String(descriptionEl.value || '').trim()) {
                descriptionEl.value = String(prefill.description || '');
            }

            const mileageEl = document.getElementById('serviceMileage-add');
            const mileage = Number(prefill.mileage);
            if (mileageEl && Number.isFinite(mileage) && mileage >= 0 && !String(mileageEl.value || '').trim()) {
                mileageEl.value = String(Math.trunc(mileage));
            }

            const priceEl = document.getElementById('servicePrice-add');
            const price = Number(prefill.price);
            if (priceEl && Number.isFinite(price) && price >= 0 && !String(priceEl.value || '').trim()) {
                priceEl.value = String(price);
            }

            const noteEl = document.getElementById('serviceNote-add');
            if (noteEl && prefill.note && !String(noteEl.value || '').trim()) {
                noteEl.value = String(prefill.note || '');
            }

            if (prefill.service_report && typeof prefill.service_report === 'object') {
                initializeServiceReportEditor('add', prefill.service_report);
            }
        }

        function renderAddServiceRecordParsedSummary(prefillPayload, parseConfidence, processingStatus) {
            const prefill = prefillPayload && typeof prefillPayload === 'object' ? prefillPayload : {};
            const report = prefill.service_report && typeof prefill.service_report === 'object'
                ? prefill.service_report
                : {};
            const items = Array.isArray(report.items) ? report.items : [];
            const itemLines = items.slice(0, 4).map(item => {
                const name = escapeHtml(String(item?.name || 'Položka'));
                const total = Number(item?.total_price);
                const currency = String(item?.currency || report.currency || 'CZK').toUpperCase();
                const totalLabel = Number.isFinite(total)
                    ? `${total.toLocaleString('cs-CZ', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency === 'CZK' ? 'Kč' : currency}`
                    : 'bez ceny';
                return `<li style="margin: 0 0 3px 0;">${name} <span style="opacity:0.8;">(${escapeHtml(totalLabel)})</span></li>`;
            }).join('');
            const confidence = Number(parseConfidence);
            const confidenceLabel = Number.isFinite(confidence) ? `${Math.round(confidence * 100)} %` : 'n/a';
            const supplier = escapeHtml(String(report.supplier_name || 'Neuvedeno'));
            const supplierEmailRaw = String(report.supplier_email || '').trim();
            const supplierEmail = supplierEmailRaw ? escapeHtml(supplierEmailRaw) : '';
            const serviceSummaryRaw = String(report.service_summary || '').trim();
            const serviceSummary = serviceSummaryRaw ? escapeHtml(serviceSummaryRaw) : '';
            const technicianNameRaw = String(report.technician_name || '').trim();
            const technicianInitialsRaw = String(report.technician_initials || '').trim();
            const technicianLabel = technicianNameRaw
                ? `${escapeHtml(technicianNameRaw)}${technicianInitialsRaw ? ` (${escapeHtml(technicianInitialsRaw)})` : ''}`
                : '';
            const serviceLinkValue = normalizeServiceLink(
                report.service_link || report.supplier_website || (supplierEmailRaw ? `mailto:${supplierEmailRaw}` : '')
            );
            const serviceLinkHtml = serviceLinkValue
                ? `<a href="${escapeHtml(safeLegacyURL(serviceLinkValue, true))}" target="_blank" rel="noopener noreferrer" style="color:#c7d2fe; text-decoration:underline;">Otevřít servis</a>`
                : '';
            const customer = escapeHtml(String(report.customer_name || 'Neuvedeno'));
            const docNumber = escapeHtml(String(report.document_number || 'Neuvedeno'));
            const total = Number(prefill.price ?? report.total_with_vat);
            const totalLabel = Number.isFinite(total)
                ? `${total.toLocaleString('cs-CZ', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} Kč`
                : 'Neuvedeno';
            const tone = processingStatus === 'failed'
                ? 'error'
                : (processingStatus === 'needs_review' ? 'warning' : 'success');

            setAddServiceRecordAnalysisStatus(
                `
                <div><strong>Doklad načten.</strong> Přesnost: ${escapeHtml(confidenceLabel)}.</div>
                <div style="margin-top:4px;">Dodavatel: <strong>${supplier}</strong></div>
                ${supplierEmail ? `<div>Kontakt: <strong>${supplierEmail}</strong></div>` : ''}
                ${serviceLinkHtml ? `<div>Servis: ${serviceLinkHtml}</div>` : ''}
                <div>Odběratel: <strong>${customer}</strong></div>
                <div>Číslo dokladu: <strong>${docNumber}</strong></div>
                ${serviceSummary ? `<div>Popis prací: <strong>${serviceSummary}</strong></div>` : ''}
                ${technicianLabel ? `<div>Technik: <strong>${technicianLabel}</strong></div>` : ''}
                <div>Celkem: <strong>${escapeHtml(totalLabel)}</strong></div>
                ${itemLines ? `<div style="margin-top:6px;">Položky:</div><ul style="margin:4px 0 0 18px; padding:0;">${itemLines}</ul>` : ''}
                `,
                tone
            );
        }

        async function handleAddServiceAttachmentSelection(event) {
            const fileInput = event && event.target ? event.target : document.getElementById('serviceAttachmentFile-add');
            const file = fileInput && fileInput.files && fileInput.files[0] ? fileInput.files[0] : null;
            addServiceRecordDocumentPrefill = null;
            if (!file) {
                setAddServiceRecordAnalysisStatus('');
                return;
            }

            const modal = document.getElementById('addServiceRecordModal');
            const vehicleIdRaw = modal ? modal.getAttribute('data-vehicle-id') : null;
            const vehicleSelect = document.getElementById('serviceVehicle-add');
            let vehicleId = vehicleIdRaw ? parseInt(vehicleIdRaw, 10) : null;
            if ((!vehicleId || Number.isNaN(vehicleId)) && vehicleSelect) {
                const selectedVehicleId = parseInt(vehicleSelect.value, 10);
                if (!Number.isNaN(selectedVehicleId)) {
                    vehicleId = selectedVehicleId;
                }
            }
            if (!vehicleId || Number.isNaN(vehicleId)) {
                setAddServiceRecordAnalysisStatus('Vyberte nejprve vozidlo, potom nahrajte doklad.', 'warning');
                return;
            }

            const autofillCheckbox = document.getElementById('serviceAttachmentAutofill-add');
            if (!autofillCheckbox || !autofillCheckbox.checked) {
                setAddServiceRecordAnalysisStatus('Automatické předvyplnění je vypnuté. Zapněte volbu pod nahraným dokladem.', 'info');
                return;
            }

            const category = String(document.getElementById('serviceCategory-add')?.value || '').trim();
            const dateInput = String(document.getElementById('serviceDate-add')?.value || '').trim();
            const description = String(document.getElementById('serviceDescription-add')?.value || '').trim();
            const mileageRaw = String(document.getElementById('serviceMileage-add')?.value || '').trim();
            const priceRaw = String(document.getElementById('servicePrice-add')?.value || '').trim();
            const note = String(document.getElementById('serviceNote-add')?.value || '').trim();
            const sourceType = String(document.getElementById('serviceAttachmentSourceType-add')?.value || 'invoice').trim().toLowerCase();

            let fallbackMileage = null;
            if (mileageRaw) {
                const parsedMileage = Number(mileageRaw);
                if (Number.isInteger(parsedMileage) && parsedMileage >= 0) {
                    fallbackMileage = parsedMileage;
                }
            }
            let fallbackPrice = null;
            if (priceRaw) {
                const parsedPrice = Number(String(priceRaw).replace(',', '.'));
                if (Number.isFinite(parsedPrice) && parsedPrice >= 0) {
                    fallbackPrice = parsedPrice;
                }
            }

            let fallbackPerformedAt = null;
            if (dateInput) {
                const dateCandidate = new Date(dateInput);
                if (!Number.isNaN(dateCandidate.getTime())) {
                    fallbackPerformedAt = dateCandidate.toISOString();
                }
            }

            try {
                setAddServiceRecordAnalysisStatus('Analyzuji doklad a předvyplňuji formulář...', 'info');
                const payload = {
                    source_type: sourceType,
                    file_name: file.name || 'doklad',
                    file_mime_type: file.type || 'application/octet-stream',
                    file_content_base64: await fileToBase64Payload(file),
                    manual_note: note || null,
                    fallback_category: category || null,
                    fallback_mileage: fallbackMileage,
                    fallback_performed_at: fallbackPerformedAt,
                    fallback_description: description || null,
                    fallback_price: fallbackPrice,
                };
                const result = await apiCall(`/api/v1/vehicles/${vehicleId}/records/document-prefill`, 'POST', payload);
                addServiceRecordDocumentPrefill = result;
                applyAddServiceRecordPrefill(result?.prefill || {});
                renderAddServiceRecordParsedSummary(result?.prefill || {}, result?.parse_confidence, result?.processing_status);
            } catch (error) {
                console.error("Error prefill from document:");
                addServiceRecordDocumentPrefill = null;
                setAddServiceRecordAnalysisStatus(
                    'Nepodařilo se vytěžit data z dokladu: ' + escapeHtml(String(error?.message || 'Neznámá chyba')),
                    'error'
                );
            }
        }

        // Otevření modalu pro přidání servisního záznamu
        async function openAddServiceRecordModal(vehicleId = null) {
            const modal = document.getElementById('addServiceRecordModal');
            const modalBody = document.getElementById('addServiceRecordModalBody');

            if (!modal || !modalBody) return;

            // Resetovat modal (pokud byl použit pro editaci)
            resetAddServiceRecordModal();

            const modalTitle = modal.querySelector('.vehicle-modal-header h2');
            const parsedVehicleId = Number.parseInt(vehicleId, 10);
            const hasPreselectedVehicle = Number.isInteger(parsedVehicleId) && parsedVehicleId > 0;

            if (hasPreselectedVehicle) {
                modal.setAttribute('data-vehicle-id', String(parsedVehicleId));
            } else {
                modal.removeAttribute('data-vehicle-id');
            }

            let availableVehicles = [];
            if (!hasPreselectedVehicle) {
                try {
                    availableVehicles = await apiCall('/api/v1/vehicles', 'GET');
                } catch (error) {
                    console.error("Error loading vehicles for quick service record:");
                    showAlert('Nepodařilo se načíst seznam vozidel pro rychlé přidání záznamu.', 'error');
                    return;
                }

                if (!Array.isArray(availableVehicles) || availableVehicles.length === 0) {
                    showAlert('Nejdříve přidejte alespoň jedno vozidlo.', 'info');
                    return;
                }
            }

            // Zobrazit modal
            openStaticOverlayModal(modal, {
                scrollTargetSelector: '.vehicle-modal-body',
            });

            if (modalTitle) {
                modalTitle.textContent = hasPreselectedVehicle
                    ? 'Přidat servisní záznam'
                    : 'Rychlé přidání servisního záznamu';
            }

            const vehicleSelectorHtml = hasPreselectedVehicle
                ? ''
                : `
                    <div class="form-group">
                        <label for="serviceVehicle-add" style="display: block; margin-bottom: 8px; color: #cbd5e1; font-size: 14px; font-weight: 500;">Vozidlo *</label>
                        <select id="serviceVehicle-add" required style="width: 100%; padding: 10px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 6px; color: #f1f5f9; font-size: 14px;">
                            ${availableVehicles.map(v => `
                                <option value="${escapeHtml(v.id)}">
                                    ${(escapeHtml(v.nickname || 'Bez názvu'))} - ${(escapeHtml(v.plate || 'Bez SPZ'))}
                                </option>
                            `).join('')}
                        </select>
                    </div>
                `;

            // Vytvořit formulář s výběrem kategorie
            modalBody.innerHTML = `
                <form id="addServiceRecordForm" ${legacyActionAttributes("submit", "handleAddServiceRecordSubmit_ecdf7283")} style="display: flex; flex-direction: column; gap: 16px;">
                    ${vehicleSelectorHtml}

                    <!-- Výběr kategorie -->
                    <div class="form-group">
                        <label style="display: block; margin-bottom: 8px; color: #cbd5e1; font-size: 14px; font-weight: 500;">Kategorie *</label>
                            <div class="category-selector">
                                <button type="button" class="category-selector-button" id="category-selector-btn-add" ${legacyActionAttributes("click", "toggleCategoryDropdown_2fcbf668")}>
                                    <span id="category-selected-text-add">Vyberte kategorii</span>
                                    <span style="font-size: 12px;">▼</span>
                                </button>
                                <div class="category-dropdown" id="category-dropdown-add">
                                    ${SERVICE_CATEGORIES.map(cat => `
                                        <div class="category-option" ${legacyActionAttributes("click", "selectCategory_d858679f", cat.value, cat.label, cat.icon)}>
                                            <span style="margin-right: 8px;">${escapeHtml(cat.icon)}</span>
                                            ${escapeHtml(cat.label)}
                                        </div>
                                    `).join('')}
                                </div>
                                <input type="hidden" id="serviceCategory-add">
                            </div>
                    </div>

                    <!-- Datum -->
                    <div class="form-group">
                        <label for="serviceDate-add" style="display: block; margin-bottom: 8px; color: #cbd5e1; font-size: 14px; font-weight: 500;">Datum *</label>
                        <input type="datetime-local" id="serviceDate-add" style="width: 100%; padding: 10px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 6px; color: #f1f5f9; font-size: 14px;">
                    </div>

                    <!-- Popis -->
                    <div class="form-group">
                        <label for="serviceDescription-add" style="display: block; margin-bottom: 8px; color: #cbd5e1; font-size: 14px; font-weight: 500;">Popis úkonu *</label>
                        <textarea id="serviceDescription-add" rows="3" placeholder="Např. Výměna oleje, kontrola brzd..." title="Vyplňte prosím popis úkonu" style="width: 100%; padding: 10px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 6px; color: #f1f5f9; font-size: 14px; font-family: inherit; resize: vertical;"></textarea>
                    </div>

                    <!-- Nájezd a cena -->
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                        <div class="form-group">
                            <label for="serviceMileage-add" style="display: block; margin-bottom: 8px; color: #cbd5e1; font-size: 14px; font-weight: 500;">Nájezd (km)</label>
                            <input type="number" id="serviceMileage-add" min="0" step="1" inputmode="numeric" style="width: 100%; padding: 10px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 6px; color: #f1f5f9; font-size: 14px;">
                        </div>
                        <div class="form-group">
                            <label for="servicePrice-add" style="display: block; margin-bottom: 8px; color: #cbd5e1; font-size: 14px; font-weight: 500;">Cena (Kč) *</label>
                            <input type="number" id="servicePrice-add" min="0" step="0.01" inputmode="decimal" style="width: 100%; padding: 10px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 6px; color: #f1f5f9; font-size: 14px;">
                        </div>
                    </div>

                    <!-- Poznámka -->
                    <div class="form-group">
                        <label for="serviceNote-add" style="display: block; margin-bottom: 8px; color: #cbd5e1; font-size: 14px; font-weight: 500;">Poznámka</label>
                        <textarea id="serviceNote-add" rows="4" placeholder="Servisní zpráva, doplňující informace..." style="width: 100%; padding: 10px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 6px; color: #f1f5f9; font-size: 14px; font-family: inherit; resize: vertical;"></textarea>
                    </div>

                    <div id="serviceReportEditor-add"></div>

                    <div class="form-group">
                        <label for="serviceAttachmentSourceType-add" style="display: block; margin-bottom: 8px; color: #cbd5e1; font-size: 14px; font-weight: 500;">Typ dokladu pro automatické vytěžení</label>
                        <select id="serviceAttachmentSourceType-add" style="width: 100%; padding: 10px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 6px; color: #f1f5f9; font-size: 14px; margin-bottom: 10px;">
                            <option value="invoice">Faktura</option>
                            <option value="delivery_note">Dodací list</option>
                            <option value="work_order">Zakázkový list</option>
                            <option value="receipt">Účtenka</option>
                            <option value="manual">Ruční zápis</option>
                        </select>

                        <label for="serviceAttachmentFile-add" style="display: block; margin-bottom: 8px; color: #cbd5e1; font-size: 14px; font-weight: 500;">Doklad k záznamu (volitelné)</label>
                        <input type="file" id="serviceAttachmentFile-add" accept=".pdf,.txt,.csv,.json,.xml,image/*" ${legacyActionAttributes("change", "handleAddServiceAttachmentSelection_7214fe63")} style="width: 100%; padding: 10px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 6px; color: #f1f5f9; font-size: 14px;">
                        <label style="display:flex; align-items:flex-start; gap:8px; margin-top:10px; color:#cbd5e1; font-size:13px; line-height:1.35;">
                            <input type="checkbox" id="serviceAttachmentAutofill-add" checked style="margin-top:2px;">
                            <span>Po nahrání dokladu automaticky předvyplnit servisní zprávu (kdo komu fakturoval, položky, datum, cena a případně km).</span>
                        </label>
                        <div id="serviceAttachmentAnalysisStatus-add" style="display:none;"></div>
                        <div style="margin-top: 6px; color: #94a3b8; font-size: 12px;">Podporované: PDF, obrázky a textové doklady (max 15 MB).</div>
                    </div>

                    <div id="addServiceRecordFormError" style="min-height: 20px;"></div>

                    <!-- Tlačítka -->
                    <div style="display: flex; gap: 10px; margin-top: 8px;">
                        <button type="submit" id="addServiceRecordSubmitBtn" class="btn" style="flex: 1; padding: 12px; background: #6366f1; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500;">Přidat záznam</button>
                        <button type="button" ${legacyActionAttributes("click", "closeAddServiceRecordModal_d539d5f4")} class="btn" style="padding: 12px 20px; background: #6c757d; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px;">Zrušit</button>
                    </div>
                </form>
            `;

            // Nastavit aktuální datum a čas jako výchozí
            const now = new Date();
            const year = now.getFullYear();
            const month = String(now.getMonth() + 1).padStart(2, '0');
            const day = String(now.getDate()).padStart(2, '0');
            const hours = String(now.getHours()).padStart(2, '0');
            const minutes = String(now.getMinutes()).padStart(2, '0');
            const dateTimeLocal = `${year}-${month}-${day}T${hours}:${minutes}`;
            document.getElementById('serviceDate-add').value = dateTimeLocal;
            addServiceRecordDocumentPrefill = null;
            setAddServiceRecordAnalysisStatus('');
            initializeServiceReportEditor('add', sanitizeServiceReportPayload({
                source_type: 'manual',
                currency: 'CZK',
                items: [],
            }));

            const autofillToggle = document.getElementById('serviceAttachmentAutofill-add');
            const sourceTypeSelect = document.getElementById('serviceAttachmentSourceType-add');
            const fileInput = document.getElementById('serviceAttachmentFile-add');
            const vehicleSelectEl = document.getElementById('serviceVehicle-add');
            if (autofillToggle) {
                autofillToggle.addEventListener('change', () => {
                    addServiceRecordDocumentPrefill = null;
                    if (autofillToggle.checked && fileInput && fileInput.files && fileInput.files[0]) {
                        handleAddServiceAttachmentSelection({ target: fileInput });
                    } else if (!autofillToggle.checked) {
                        setAddServiceRecordAnalysisStatus('Automatické předvyplnění je vypnuté.', 'info');
                    } else {
                        setAddServiceRecordAnalysisStatus('');
                    }
                });
            }
            if (sourceTypeSelect) {
                sourceTypeSelect.addEventListener('change', () => {
                    addServiceRecordDocumentPrefill = null;
                    if (fileInput && fileInput.files && fileInput.files[0] && autofillToggle && autofillToggle.checked) {
                        handleAddServiceAttachmentSelection({ target: fileInput });
                    }
                });
            }
            if (vehicleSelectEl) {
                vehicleSelectEl.addEventListener('change', () => {
                    addServiceRecordDocumentPrefill = null;
                    if (fileInput && fileInput.files && fileInput.files[0] && autofillToggle && autofillToggle.checked) {
                        handleAddServiceAttachmentSelection({ target: fileInput });
                    }
                });
            }

            requestAnimationFrame(() => {
                const firstField = hasPreselectedVehicle
                    ? document.getElementById('category-selector-btn-add')
                    : document.getElementById('serviceVehicle-add');
                if (firstField && typeof firstField.focus === 'function') {
                    firstField.focus({ preventScroll: true });
                }
            });
        }

        // Zavření modalu pro přidání servisního záznamu
        function closeAddServiceRecordModal() {
            const modal = document.getElementById('addServiceRecordModal');
            if (modal) {
                closeStaticOverlayModal(modal);
                // Resetovat modal
                resetAddServiceRecordModal();
            }
        }

        // Rozbalení/sbalení dropdownu pro výběr kategorie
        function toggleCategoryDropdown(id) {
            const dropdown = document.getElementById(`category-dropdown-${id}`);
            const button = document.getElementById(`category-selector-btn-${id}`);

            if (!dropdown || !button) return;

            const isOpen = dropdown.classList.contains('open');

            // Zavřít všechny ostatní dropdowny
            document.querySelectorAll('.category-dropdown.open').forEach(dd => {
                if (dd.id !== `category-dropdown-${id}`) {
                    dd.classList.remove('open');
                    dd.previousElementSibling?.classList.remove('open');
                }
            });

            if (isOpen) {
                dropdown.classList.remove('open');
                button.classList.remove('open');
            } else {
                dropdown.classList.add('open');
                button.classList.add('open');
            }
        }

        // Výběr kategorie
        function selectCategory(value, label, icon, id) {
            const hiddenInput = document.getElementById(`serviceCategory-${id}`);
            const selectedText = document.getElementById(`category-selected-text-${id}`);
            const dropdown = document.getElementById(`category-dropdown-${id}`);
            const button = document.getElementById(`category-selector-btn-${id}`);

            if (hiddenInput) hiddenInput.value = value;
            if (selectedText) selectedText.textContent = `${icon} ${label}`;

            // Označit vybranou možnost
            dropdown.querySelectorAll('.category-option').forEach(opt => {
                opt.classList.remove('selected');
                if (opt.textContent.includes(label)) {
                    opt.classList.add('selected');
                }
            });

            // Zavřít dropdown
            dropdown.classList.remove('open');
            button.classList.remove('open');
        }

        // Zavření dropdownu při kliknutí mimo
        document.addEventListener('click', function(event) {
            if (!event.target.closest('.category-selector')) {
                document.querySelectorAll('.category-dropdown.open').forEach(dd => {
                    dd.classList.remove('open');
                    dd.previousElementSibling?.classList.remove('open');
                });
            }
        });

        // Odeslání formuláře pro přidání servisního záznamu
        async function handleAddServiceRecordSubmit(event) {
            event.preventDefault();

            const modal = document.getElementById('addServiceRecordModal');
            const vehicleIdRaw = modal ? modal.getAttribute('data-vehicle-id') : null;
            const vehicleSelect = document.getElementById('serviceVehicle-add');
            let vehicleId = vehicleIdRaw ? parseInt(vehicleIdRaw, 10) : null;
            if ((!vehicleId || Number.isNaN(vehicleId)) && vehicleSelect) {
                const selectedVehicleId = parseInt(vehicleSelect.value, 10);
                if (!Number.isNaN(selectedVehicleId)) {
                    vehicleId = selectedVehicleId;
                }
            }
            if (!vehicleId || Number.isNaN(vehicleId)) {
                showFormError('addServiceRecordFormError', 'Vyberte prosím vozidlo, ke kterému chcete záznam přidat.');
                return false;
            }

            clearFormError('addServiceRecordFormError');

            const categoryInput = document.getElementById('serviceCategory-add');
            const dateElement = document.getElementById('serviceDate-add');
            const descriptionElement = document.getElementById('serviceDescription-add');
            const mileageElement = document.getElementById('serviceMileage-add');
            const priceElement = document.getElementById('servicePrice-add');
            const noteElement = document.getElementById('serviceNote-add');
            const attachmentElement = document.getElementById('serviceAttachmentFile-add');
            const attachmentSourceTypeElement = document.getElementById('serviceAttachmentSourceType-add');
            const attachmentAutofillElement = document.getElementById('serviceAttachmentAutofill-add');
            const submitButton = document.getElementById('addServiceRecordSubmitBtn');

            if (!categoryInput || !dateElement || !descriptionElement || !mileageElement || !priceElement || !noteElement) {
                showFormError('addServiceRecordFormError', 'Formulář není správně načten. Zavřete ho a otevřete znovu.');
                return false;
            }

            const sourceType = String(attachmentSourceTypeElement?.value || 'invoice').trim().toLowerCase();
            const attachmentFile = attachmentElement && attachmentElement.files && attachmentElement.files[0]
                ? attachmentElement.files[0]
                : null;
            const shouldAnalyzeDocument = Boolean(
                attachmentFile && attachmentAutofillElement && attachmentAutofillElement.checked
            );

            if (shouldAnalyzeDocument && !addServiceRecordDocumentPrefill && attachmentElement) {
                await handleAddServiceAttachmentSelection({ target: attachmentElement });
            }

            const category = (categoryInput.value || '').trim();
            const dateInput = (dateElement.value || '').trim();
            const descriptionInputValue = (descriptionElement.value || '').trim();
            const mileageRaw = (mileageElement.value || '').trim();
            const priceRaw = (priceElement.value || '').trim();
            const note = (noteElement.value || '').trim();
            const reportData = getServiceReportEditorValue('add');
            const prefillDescription = String(addServiceRecordDocumentPrefill?.prefill?.description || '').trim();
            const description = descriptionInputValue
                || String(reportData.issue_description || '').trim()
                || String(reportData.service_summary || '').trim()
                || prefillDescription;

            let mileageValue = null;
            if (mileageRaw) {
                const parsedMileage = Number(mileageRaw);
                if (!Number.isInteger(parsedMileage) || parsedMileage < 0) {
                    showFormError('addServiceRecordFormError', 'Nájezd musí být celé číslo 0 nebo vyšší.');
                    return false;
                }
                mileageValue = parsedMileage;
            }

            let priceValue = null;
            if (priceRaw) {
                const parsedPrice = Number(String(priceRaw).replace(',', '.'));
                if (!Number.isFinite(parsedPrice) || parsedPrice < 0) {
                    showFormError('addServiceRecordFormError', 'Cena musí být číslo 0 nebo vyšší.');
                    return false;
                }
                priceValue = parsedPrice;
            }
            if (priceValue === null) {
                const prefillPrice = parseOptionalNumber(addServiceRecordDocumentPrefill?.prefill?.price);
                const reportTotal = parseOptionalNumber(reportData.total_with_vat);
                priceValue = reportTotal ?? prefillPrice;
                if (priceValue !== null && priceElement) {
                    priceElement.value = String(priceValue);
                }
            }

            let parsedDate = null;
            if (dateInput) {
                const dateCandidate = new Date(dateInput);
                if (Number.isNaN(dateCandidate.getTime())) {
                    showFormError('addServiceRecordFormError', 'Datum má neplatný formát.');
                    return false;
                }
                parsedDate = dateCandidate;
            }

            if (!category) {
                showFormError('addServiceRecordFormError', 'Vyberte prosím kategorii.');
                return false;
            }
            if (!parsedDate) {
                showFormError('addServiceRecordFormError', 'Vyplňte prosím datum servisního úkonu.');
                return false;
            }
            if (!description) {
                showFormError('addServiceRecordFormError', 'Popis úkonu je povinný.');
                return false;
            }
            if (priceValue === null) {
                showFormError('addServiceRecordFormError', 'Cena je povinná.');
                return false;
            }

            const originalButtonText = submitButton ? submitButton.textContent : '';
            if (submitButton) {
                submitButton.disabled = true;
                submitButton.textContent = 'Ukládám...';
            }

            try {
                if (!reportData.service_summary) {
                    reportData.service_summary = description;
                }
                if (!reportData.total_with_vat && Number.isFinite(priceValue)) {
                    reportData.total_with_vat = roundTo2(priceValue);
                }
                const attachmentsPayload = [
                    {
                        kind: SERVICE_REPORT_META_KIND,
                        parsed_summary: reportData,
                    },
                ];
                const recordData = {
                    performed_at: parsedDate.toISOString(),
                    mileage: mileageValue,
                    description,
                    price: priceValue,
                    note: note || null,
                    category
                };

                if (attachmentFile) {
                    showAlert('Nahrávám doklad...', 'info');
                    const uploadedAttachment = await uploadServiceRecordAttachment(vehicleId, attachmentFile);
                    const attachmentPayload = {
                        kind: 'user_document',
                        file_name: uploadedAttachment.file_name,
                        mime_type: uploadedAttachment.mime_type,
                        file_size: uploadedAttachment.file_size,
                        storage_key: uploadedAttachment.storage_key,
                        download_url: uploadedAttachment.download_url,
                        source_type: sourceType,
                        parsed_summary: reportData,
                    };
                    attachmentsPayload.push(attachmentPayload);
                }
                if (currentLicensePlanForUi !== 'free' || ['admin', 'developer_admin', 'service'].includes(currentUser?.role)) recordData.attachments = JSON.stringify(attachmentsPayload);

                showAlert('Přidávám servisní úkon...', 'info');
                await apiCall(`/api/v1/vehicles/${vehicleId}/records`, 'POST', recordData);

                showAlert('Servisní úkon byl úspěšně přidán!', 'success');

                closeAddServiceRecordModal();
                await loadVehicles();
                if (currentVehicleId === vehicleId) {
                    await loadServiceRecordsModal(vehicleId);
                }
            } catch (error) {
                console.error("Error adding service record:");
                const message = error && error.message ? error.message : 'Neznámá chyba';
                showFormError('addServiceRecordFormError', 'Nepodařilo se přidat servisní úkon: ' + message);
            } finally {
                if (submitButton) {
                    submitButton.disabled = false;
                    submitButton.textContent = originalButtonText || 'Přidat záznam';
                }
            }

            return false;
        }

        // Funkce pro editaci v modalu
        function startEditModal(field, vehicleId) {
            const row = document.querySelector(`.vehicle-info-row[data-field="${field}"][data-vehicle-id="${vehicleId}"]`);
            if (!row) return;

            const display = row.querySelector('.vehicle-info-display');
            const edit = row.querySelector('.vehicle-info-edit');

            if (display && edit) {
                display.style.display = 'none';
                edit.style.display = 'flex';

                // Focus na input
                const input = edit.querySelector('input, textarea');
                if (input) {
                    input.focus();
                    input.select();
                }
            }
        }

        function cancelEditModal(field, vehicleId) {
            const row = document.querySelector(`.vehicle-info-row[data-field="${field}"][data-vehicle-id="${vehicleId}"]`);
            if (!row) return;

            const display = row.querySelector('.vehicle-info-display');
            const edit = row.querySelector('.vehicle-info-edit');

            if (display && edit) {
                edit.style.display = 'none';
                display.style.display = 'flex';

                // Obnovit původní hodnotu
                const input = edit.querySelector('input, textarea');
                if (input && window.currentVehicle) {
                    input.value = window.currentVehicle[field] || '';
                }
            }
        }

        async function saveVehicleFieldModal(field, vehicleId) {
            if (!vehicleId || !window.currentVehicle) {
                showAlert('Chyba: Vozidlo není načteno', 'error');
                return;
            }

            const row = document.querySelector(`.vehicle-info-row[data-field="${field}"][data-vehicle-id="${vehicleId}"]`);
            if (!row) return;

            const input = row.querySelector('input, textarea');
            if (!input) return;

            const newValue = input.value.trim();

            // Validace
            if (field === 'plate' && !newValue) {
                showAlert('SPZ je povinné pole', 'error');
                return;
            }

            try {
                // Příprava dat pro aktualizaci
                const updateData = {};

                if (field === 'nickname') {
                    updateData.nickname = newValue || null;
                } else if (field === 'plate') {
                    updateData.plate = newValue;
                } else if (field === 'notes') {
                    updateData.notes = newValue || null;
                } else {
                    showAlert('Neznámé pole pro úpravu', 'error');
                    return;
                }

                showAlert('Ukládám změny...', 'info');

                // Volání API
                const updatedVehicle = await apiCall(`/api/v1/vehicles/${vehicleId}`, 'PUT', updateData);

                // Aktualizovat lokální data
                window.currentVehicle[field] = newValue;

                // Aktualizovat zobrazení
                const display = row.querySelector('.vehicle-info-display');
                const valueSpan = display.querySelector('.vehicle-info-value');
                if (valueSpan) {
                    valueSpan.textContent = newValue || 'Nezadáno';
                    valueSpan.classList.toggle('empty', !newValue);
                }

                // Skrýt editaci
                const edit = row.querySelector('.vehicle-info-edit');
                if (edit) edit.style.display = 'none';
                if (display) display.style.display = 'flex';

                showAlert('Změny byly úspěšně uloženy!', 'success');

                // Aktualizovat název v hlavičce modalu
                if (field === 'nickname') {
                    document.getElementById('vehicleModalTitle').textContent = newValue || 'Detail vozidla';
                }

                // Obnovit seznam vozidel, aby se aktualizoval název v kartě
                await loadVehicles();

            } catch (error) {
                console.error("Error updating vehicle:");
                showAlert('Nepodařilo se uložit změny: ' + (error.message || 'Neznámá chyba'), 'error');
            }
        }

        // Načtení servisních záznamů do modalu
        async function loadServiceRecordsModal(vehicleId) {
            const container = document.getElementById(`service-records-modal-${vehicleId}`);
            const aiContainer = document.getElementById(`ai-service-records-modal-${vehicleId}`);

            if (!container) return;

            if (aiContainer) aiContainer.innerHTML = '<div class="loading">Načítám AI záznamy...</div>';
            container.innerHTML = '<div class="loading">Načítám servisní záznamy...</div>';

            try {
                const records = await apiCall(`/api/v1/vehicles/${vehicleId}/records`, 'GET');

                if (!records || records.length === 0) {
                    if (aiContainer) aiContainer.innerHTML = '';
                    container.innerHTML = '<p style="color: #cbd5e1; font-size: 14px;">Zatím nejsou žádné servisní záznamy. Klikněte na tlačítko "Přidat záznam" pro vytvoření prvního záznamu.</p>';
                    return;
                }

                // Rozdělit záznamy na AI a běžné
                const aiRecords = records.filter(r => r.created_by_ai === true);
                const normalRecords = records.filter(r => !r.created_by_ai || r.created_by_ai === false);

                const formatTile = (record, isAi = false) => {
                    const category = record.category || 'JINE';
                    const categoryInfo = SERVICE_CATEGORIES.find(c => c.value === category) || SERVICE_CATEGORIES.find(c => c.value === 'JINE');
                    const categoryIcon = categoryInfo ? categoryInfo.icon : '📋';
                    const categoryLabel = categoryInfo ? categoryInfo.label : category;

                    const hasMileage = record.mileage !== null && record.mileage !== undefined && record.mileage !== '';
                    const mileageNumber = Number(record.mileage);
                    const mileageLabel = (hasMileage && Number.isFinite(mileageNumber))
                        ? `${mileageNumber.toLocaleString('cs-CZ')} km`
                        : '—';

                    const hasPrice = record.price !== null && record.price !== undefined && record.price !== '';
                    const priceNumber = Number(record.price);
                    const priceLabel = (hasPrice && Number.isFinite(priceNumber))
                        ? `${priceNumber.toLocaleString('cs-CZ')} Kč`
                        : '—';

                    const dateLabel = formatDateCZ(record.performed_at);
                    const description = escapeHtml(record.description || 'Bez popisu');
                    const categoryText = escapeHtml(`${categoryIcon} ${categoryLabel}`);

                    return `
                        <div class="service-record-tile ${isAi ? 'ai-tile' : ''}" ${legacyActionAttributes("click", "showServiceRecordDetail_941afdd3", record.id, vehicleId)} title="Klikněte pro detail">
                            ${isAi ? '<span class="tile-ai-badge">🤖</span>' : ''}
                            <div class="tile-category">${categoryText}</div>
                            <div class="tile-description">${description}</div>
                            <div class="tile-metrics">
                                <div class="tile-metric">
                                    <span class="tile-metric-label">Datum</span>
                                    <span class="tile-metric-value">${escapeHtml(dateLabel)}</span>
                                </div>
                                <div class="tile-metric">
                                    <span class="tile-metric-label">Km</span>
                                    <span class="tile-metric-value">${escapeHtml(mileageLabel)}</span>
                                </div>
                                <div class="tile-metric tile-metric-price">
                                    <span class="tile-metric-label">Cena</span>
                                    <span class="tile-metric-value">${escapeHtml(priceLabel)}</span>
                                </div>
                            </div>
                        </div>
                    `;
                };

                // Zobrazit AI záznamy jako dlaždice v samostatné sekci
                if (aiContainer) {
                    if (aiRecords.length > 0) {
                        let aiHtml = '<h4 style="margin: 0 0 12px 0; color: #cbd5e1; font-size: 14px; font-weight: 600; display: flex; align-items: center; gap: 8px;"><span>🤖</span> Záznamy vytvořené AI asistentem</h4><div class="service-records-grid">';
                        aiRecords.forEach(record => {
                            aiHtml += formatTile(record, true);
                        });
                        aiHtml += '</div>';
                        aiContainer.innerHTML = aiHtml;
                    } else {
                        aiContainer.innerHTML = '';
                    }
                }

                // Zobrazit běžné záznamy jako dlaždice
                if (normalRecords.length > 0) {
                    let html = '';
                    normalRecords.forEach(record => {
                        html += formatTile(record);
                    });
                    container.innerHTML = html;
                } else {
                    // Pokud jsou jen AI záznamy, zobrazit prázdnou zprávu
                    if (aiRecords.length > 0) {
                        container.innerHTML = '<p style="color: #cbd5e1; font-size: 14px; grid-column: 1 / -1;">Zatím nejsou žádné běžné servisní záznamy.</p>';
                    } else {
                        container.innerHTML = '<p style="color: #cbd5e1; font-size: 14px; grid-column: 1 / -1;">Zatím nejsou žádné servisní záznamy. Klikněte na tlačítko "Přidat záznam" pro vytvoření prvního záznamu.</p>';
                    }
                }
            } catch (error) {
                console.error("Error loading service records:");
                if (aiContainer) aiContainer.innerHTML = '';
                container.innerHTML = `<p class="alert alert-error">Chyba při načítání servisních záznamů: ${escapeHtml(error.message)}</p>`;
            }
        }

        async function loadVehicleTachometerHistorySection(vehicleId) {
            const container = document.getElementById(`tachometer-history-modal-${vehicleId}`);
            if (!container) return;

            container.innerHTML = '<div class="loading">Načítám historii STK / tachometru...</div>';

            try {
                const history = await apiCall(`/api/v1/vehicles/${vehicleId}/tachometer/history`, 'GET');
                const items = Array.isArray(history) ? history : [];

                if (items.length === 0) {
                    container.innerHTML = `
                        <div class="vehicle-tachometer-empty">
                            Historie STK / tachometru zatím není k dispozici.
                        </div>
                    `;
                    return;
                }

                const latest = items[0] || {};
                const latestDate = latest.check_date ? formatDateCZ(latest.check_date) : 'Bez data';
                const latestMileage = Number.isFinite(Number(latest.mileage_km))
                    ? `${Number(latest.mileage_km).toLocaleString('cs-CZ')} km`
                    : 'Bez km';

                container.innerHTML = `
                    <details class="vehicle-tachometer-accordion">
                        <summary>
                            <div>
                                <div class="vehicle-tachometer-summary-title">Historie STK / tachometru</div>
                                <div class="vehicle-tachometer-summary-subtitle">Sekundární importovaná evidence z kontrolatachometru.cz</div>
                            </div>
                            <div class="vehicle-tachometer-summary-badges">
                                <span class="vehicle-tachometer-badge">${escapeHtml(items.length)} záznamů</span>
                                <span class="vehicle-tachometer-badge">${escapeHtml(latestMileage)}</span>
                                <span class="vehicle-tachometer-badge">${escapeHtml(latestDate)}</span>
                            </div>
                        </summary>
                        <div class="vehicle-tachometer-list">
                            ${items.map((item, index) => renderVehicleTachometerHistoryRow(item, index)).join('')}
                        </div>
                    </details>
                `;
            } catch (error) {
                console.error("Error loading tachometer history:");
                container.innerHTML = `
                    <div class="vehicle-tachometer-error">
                        ${currentLicensePlanForUi === 'free' ? 'Historie STK je dostupná v tarifu Basic nebo Premium.' : 'Historii STK se nepodařilo načíst.'}
                    </div>
                `;
            }
        }

        function renderVehicleTachometerHistoryRow(item, index) {
            const entry = item && typeof item === 'object' ? item : {};
            const documents = Array.isArray(entry.documents) ? entry.documents : [];
            const availableDocuments = documents.filter((doc) => doc && doc.available);
            const dateLabel = entry.check_date ? formatDateCZ(entry.check_date) : 'Bez data';
            const mileageLabel = Number.isFinite(Number(entry.mileage_km))
                ? `${Number(entry.mileage_km).toLocaleString('cs-CZ')} km`
                : 'Bez km';
            const summary = String(entry.summary || '').trim();
            const protocol = String(entry.protocol_number || '').trim();
            const inspectionType = String(entry.inspection_type || '').trim();
            const source = String(entry.source || '').trim() || 'kontrolatachometru.cz';
            const status = String(entry.status || '').trim() || 'imported';
            const documentsCount = Number.isFinite(Number(entry.documents_count)) ? Number(entry.documents_count) : availableDocuments.length;

            const documentsHtml = (documents.length > 0 ? documents : [null]).map((document, docIndex) => {
                const doc = document && typeof document === 'object' ? document : null;
                const title = doc && doc.title ? String(doc.title) : (protocol ? `Protokol ${protocol}` : `Dokument ${docIndex + 1}`);
                const reason = doc && doc.reason ? String(doc.reason) : 'Dokument není dostupný v uložených datech.';
                const openMode = doc && doc.open_mode ? String(doc.open_mode) : 'unavailable';
                const externalUrl = doc && doc.external_url ? String(doc.external_url) : '';
                const internalProxyUrl = doc && doc.internal_proxy_url ? String(doc.internal_proxy_url) : '';
                const href = safeLegacyURL(openMode === 'external_url' ? externalUrl : internalProxyUrl);

                if (doc && doc.available && href) {
                    return `
                        <a class="vehicle-tachometer-document-link" href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">
                            Otevřít protokol: ${escapeHtml(title)}
                        </a>
                    `;
                }

                return `
                    <div class="vehicle-tachometer-document-unavailable">
                        ${escapeHtml(title)}
                        <small>${escapeHtml(reason || 'Dokument není dostupný')}</small>
                    </div>
                `;
            }).join('');

            return `
                <details class="vehicle-tachometer-row" ${index === 0 ? 'open' : ''}>
                    <summary>
                        <div>
                            <div class="vehicle-tachometer-row-title">${escapeHtml(mileageLabel)}</div>
                            <div class="vehicle-tachometer-row-subtitle">${escapeHtml(dateLabel)}</div>
                            <div class="vehicle-tachometer-row-meta">${escapeHtml(summary || inspectionType || source)}</div>
                        </div>
                        <div class="vehicle-tachometer-row-action">
                            Zobrazit detail kontroly
                            <div class="vehicle-tachometer-row-meta">${escapeHtml(documentsCount > 0 ? `${documentsCount} dokumentů` : 'Bez dokumentu')}</div>
                        </div>
                    </summary>
                    <div class="vehicle-tachometer-detail">
                        <div class="vehicle-tachometer-detail-grid">
                            ${renderVehicleTachometerDetailCard('Datum kontroly', dateLabel)}
                            ${renderVehicleTachometerDetailCard('KM', mileageLabel)}
                            ${renderVehicleTachometerDetailCard('Typ kontroly', inspectionType || 'Neuvedeno')}
                            ${renderVehicleTachometerDetailCard('Protokol', protocol || 'Neuveden')}
                            ${renderVehicleTachometerDetailCard('Zdroj', source)}
                            ${renderVehicleTachometerDetailCard('Stav', status)}
                        </div>
                        <div class="vehicle-tachometer-summary-box">
                            <strong>Stručný výsledek</strong>
                            ${escapeHtml(summary || 'K detailu kontroly nemáme uložený rozšířený výsledek. K dispozici je pouze importovaná evidence z portálu.')}
                        </div>
                        <div class="vehicle-tachometer-documents">
                            <div class="vehicle-tachometer-row-title" style="font-size:13px;">Protokoly a dokumenty</div>
                            ${documentsHtml}
                        </div>
                    </div>
                </details>
            `;
        }

        function renderVehicleTachometerDetailCard(label, value) {
            return `
                <div class="vehicle-tachometer-detail-card">
                    <strong>${escapeHtml(label)}</strong>
                    <span>${escapeHtml(value || 'Neuvedeno')}</span>
                </div>
            `;
        }

        // Zobrazení/skrytí formuláře pro přidání servisního záznamu
        function toggleAddServiceForm(vehicleId) {
            const formContainer = document.getElementById(`add-service-form-container-${vehicleId}`);
            const btnText = document.getElementById(`add-service-btn-text-${vehicleId}`);

            if (!formContainer) return;

            if (formContainer.style.display === 'none' || !formContainer.style.display) {
                // Zobrazit formulář
                formContainer.style.display = 'block';
                if (btnText) btnText.textContent = '✕ Zrušit';
            } else {
                // Skrýt formulář
                formContainer.style.display = 'none';
                if (btnText) btnText.textContent = '+ Přidat záznam';

                // Vyčistit formulář
                const dateInput = document.getElementById(`serviceDate-modal-${vehicleId}`);
                const mileageInput = document.getElementById(`serviceMileage-modal-${vehicleId}`);
                const descriptionInput = document.getElementById(`serviceDescription-modal-${vehicleId}`);
                const priceInput = document.getElementById(`servicePrice-modal-${vehicleId}`);
                const noteInput = document.getElementById(`serviceNote-modal-${vehicleId}`);

                if (dateInput) dateInput.value = '';
                if (mileageInput) mileageInput.value = '';
                if (descriptionInput) descriptionInput.value = '';
                if (priceInput) priceInput.value = '';
                if (noteInput) noteInput.value = '';
            }
        }

        // Zobrazení detailu servisního záznamu
        async function showServiceRecordDetail(recordId, vehicleId) {
            const modal = document.getElementById('serviceRecordDetailModal');
            const modalBody = document.getElementById('serviceRecordDetailModalBody');

            if (!modal || !modalBody) return;

            // Zobrazit modal s loading
            openStaticOverlayModal(modal, {
                scrollTargetSelector: '.vehicle-modal-body',
            });
            modalBody.innerHTML = '<div class="loading">Načítám...</div>';

            try {
                const record = await apiCall(`/api/v1/vehicles/${vehicleId}/records/${recordId}`, 'GET');
                const date = new Date(record.performed_at);

                // Najít kategorii
                const category = record.category || 'JINE';
                const categoryInfo = SERVICE_CATEGORIES.find(c => c.value === category) || SERVICE_CATEGORIES.find(c => c.value === 'JINE');
                const categoryIcon = categoryInfo ? categoryInfo.icon : '📋';
                const categoryLabel = categoryInfo ? categoryInfo.label : category;
                const recordAttachments = parseServiceRecordAttachments(vehicleId, record.attachments);
                const mileageValue = Number(record.mileage);
                const hasMileage = Number.isFinite(mileageValue) && mileageValue >= 0;
                const priceValue = Number(record.price);
                const hasPrice = Number.isFinite(priceValue) && priceValue >= 0;
                let parsedSummary = (recordAttachments.find(att => att.parsed_summary)?.parsed_summary) || null;
                if (parsedSummary && typeof parsedSummary === 'object') {
                    parsedSummary = sanitizeServiceReportPayload(parsedSummary);
                }
                if (!parsedSummary || isParsedSummaryLikelyInvalid(parsedSummary)) {
                    const attachmentForRebuild = recordAttachments.find(att => att.can_preview && att.download_url) || recordAttachments[0];
                    const recalculatedSummary = await tryBuildParsedSummaryFromAttachment(vehicleId, attachmentForRebuild);
                    if (recalculatedSummary) {
                        parsedSummary = sanitizeServiceReportPayload(recalculatedSummary);
                    }
                }
                const parsedSummaryItems = Array.isArray(parsedSummary?.items) ? parsedSummary.items : [];
                const parsedSummaryCurrency = String(parsedSummary?.currency || 'CZK').toUpperCase();
                const parsedSummaryRowsHtml = parsedSummaryItems.length > 0
                    ? parsedSummaryItems.slice(0, 20).map(item => {
                        const itemName = escapeHtml(String(item?.name || 'Položka'));
                        const itemQuantity = formatRecordQuantity(item?.quantity);
                        const itemUnit = escapeHtml(String(item?.unit || '—'));
                        const itemUnitPrice = formatRecordMoney(item?.unit_price, item?.currency || parsedSummaryCurrency);
                        const itemTotalPrice = formatRecordMoney(item?.total_price, item?.currency || parsedSummaryCurrency);
                        return `
                            <tr>
                                <td>${itemName}</td>
                                <td class="col-qty">${escapeHtml(itemQuantity)}</td>
                                <td class="col-unit">${itemUnit}</td>
                                <td class="col-price">${escapeHtml(itemUnitPrice)}</td>
                                <td class="col-total">${escapeHtml(itemTotalPrice)}</td>
                            </tr>
                        `;
                    }).join('')
                    : '';
                const parsedSummaryTableHtml = parsedSummaryRowsHtml
                    ? `
                        <div class="record-items-table-wrap">
                            <table class="record-items-table">
                                <thead>
                                    <tr>
                                        <th style="width:44%;">Položka</th>
                                        <th style="width:11%;">Počet</th>
                                        <th style="width:11%;">Jedn.</th>
                                        <th class="col-price" style="width:17%;">Cena/ks</th>
                                        <th class="col-total" style="width:17%;">Celkem</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${parsedSummaryRowsHtml}
                                </tbody>
                            </table>
                        </div>
                    `
                    : '';
                const parsedSummaryTotal = formatRecordMoney(parsedSummary?.total_with_vat, parsedSummaryCurrency);
                const parsedServiceLink = normalizeServiceLink(
                    parsedSummary?.service_link
                    || parsedSummary?.supplier_website
                    || (parsedSummary?.supplier_email ? `mailto:${parsedSummary.supplier_email}` : '')
                );
                const parsedTechnician = String(parsedSummary?.technician_name || '').trim();
                const parsedTechnicianInitials = String(parsedSummary?.technician_initials || '').trim();
                const parsedSummaryHtml = parsedSummary
                    ? `
                        <div class="record-document-summary">
                            <div style="color: #c7d2fe; font-size: 12px; margin-bottom: 2px;"><strong>Servisní zpráva z dokladu</strong></div>
                            <div class="record-document-summary-meta">
                                ${parsedSummary?.supplier_name ? `<div>Dodavatel: <strong>${escapeHtml(String(parsedSummary.supplier_name))}</strong></div>` : ''}
                                ${parsedSummary?.supplier_email ? `<div>Kontakt: <strong>${escapeHtml(String(parsedSummary.supplier_email))}</strong></div>` : ''}
                                ${parsedServiceLink ? `<div>Servis: <a href="${escapeHtml(safeLegacyURL(parsedServiceLink, true))}" target="_blank" rel="noopener noreferrer" style="color:#c7d2fe; text-decoration:underline;">Otevřít profil / kontakt</a></div>` : ''}
                                ${parsedSummary?.customer_name ? `<div>Odběratel: <strong>${escapeHtml(String(parsedSummary.customer_name))}</strong></div>` : ''}
                                ${parsedSummary?.document_number ? `<div>Doklad: <strong>${escapeHtml(String(parsedSummary.document_number))}</strong></div>` : ''}
                                ${parsedSummary?.service_summary ? `<div>Popis prací: <strong>${escapeHtml(String(parsedSummary.service_summary))}</strong></div>` : ''}
                                ${parsedSummary?.issue_description ? `<div>Popis závady: <strong>${escapeHtml(String(parsedSummary.issue_description))}</strong></div>` : ''}
                                ${parsedTechnician ? `<div>Technik: <strong>${escapeHtml(parsedTechnician)}${parsedTechnicianInitials ? ` (${escapeHtml(parsedTechnicianInitials)})` : ''}</strong></div>` : ''}
                                ${parsedSummary?.labor_hours ? `<div>Hodiny práce: <strong>${escapeHtml(String(parsedSummary.labor_hours))}</strong></div>` : ''}
                                ${parsedSummary?.labor_hour_rate ? `<div>Sazba práce: <strong>${escapeHtml(formatRecordMoney(parsedSummary.labor_hour_rate, parsedSummaryCurrency))}</strong></div>` : ''}
                            </div>
                            ${parsedSummaryTableHtml}
                            ${(parsedSummaryRowsHtml || parsedSummary?.labor_total || parsedSummary?.materials_total || parsedSummary?.vat_amount) ? `
                                <div class="record-items-footer">
                                    <span>Materiál: ${escapeHtml(formatRecordMoney(parsedSummary?.materials_total, parsedSummaryCurrency))}</span>
                                    <span>Práce: ${escapeHtml(formatRecordMoney(parsedSummary?.labor_total, parsedSummaryCurrency))}</span>
                                    <span>DPH: ${escapeHtml(formatRecordMoney(parsedSummary?.vat_amount, parsedSummaryCurrency))}</span>
                                    <span>Celkem: ${escapeHtml(parsedSummaryTotal)}</span>
                                </div>
                            ` : ''}
                        </div>
                    `
                    : '';
                const noteText = String(record.note || '').trim();
                const generatedReportNote = /^(servisn[ií]\s+zpr[aá]va|zdroj\s*:)/i.test(noteText);
                let noteToRender = noteText;
                if (parsedSummary && generatedReportNote) {
                    const manualNoteMatch = noteText.match(/(?:^|\n)Pozn[aá]mka:\s*(.+)$/i);
                    noteToRender = manualNoteMatch ? manualNoteMatch[1].trim() : '';
                }
                const previewAttachments = recordAttachments.filter((att) => att.can_preview && att.download_url);
                const attachmentsHtml = previewAttachments.length > 0
                    ? `
                        <div class="record-attachments-block">
                            <div style="color: #94a3b8; font-size: 12px; margin-bottom: 4px;">Přílohy / doklady</div>
                            <div class="record-attachments-list">
                                ${previewAttachments.map((att, idx) => `
                                    <button
                                        type="button"
                                        class="record-attachments-item"
                                        ${legacyActionAttributes("click", "openServiceRecordAttachmentPreview_641bbe9b", encodeURIComponent(att.download_url || ''), encodeURIComponent(att.file_name || `Příloha ${idx + 1}`))}
                                    >
                                        📎 ${escapeHtml(att.file_name || `Příloha ${idx + 1}`)}
                                        ${att.file_size ? `<span style="opacity:0.75;">(${escapeHtml(formatAttachmentSize(att.file_size))})</span>` : ''}
                                    </button>
                                `).join('')}
                            </div>
                        </div>
                    `
                    : '';

                let detailHtml = `
                    <div style="padding: 20px;">
                        <h3 style="margin: 0 0 20px 0; color: #e2e8f0; font-size: 18px; display: flex; align-items: center; gap: 8px;">
                            ${escapeHtml(categoryIcon)} ${escapeHtml(categoryLabel)}
                        </h3>
                        <div style="display: flex; flex-direction: column; gap: 12px;">
                            <div>
                                <div style="color: #94a3b8; font-size: 12px; margin-bottom: 4px;">Popis</div>
                                <div style="color: #e2e8f0; font-size: 14px;">${escapeHtml(String(record.description || 'Nezadáno'))}</div>
                            </div>
                            <div>
                                <div style="color: #94a3b8; font-size: 12px; margin-bottom: 4px;">Datum</div>
                                <div style="color: #e2e8f0; font-size: 14px;">${escapeHtml(date.toLocaleDateString('cs-CZ'))} ${escapeHtml(date.toLocaleTimeString('cs-CZ', {hour: '2-digit', minute: '2-digit'}))}</div>
                            </div>
                            <div>
                                <div style="color: #94a3b8; font-size: 12px; margin-bottom: 4px;">Nájezd</div>
                                <div style="color: #e2e8f0; font-size: 14px;">${escapeHtml(hasMileage ? `${mileageValue.toLocaleString('cs-CZ')} km` : 'Neuvedeno')}</div>
                            </div>
                            <div>
                                <div style="color: #94a3b8; font-size: 12px; margin-bottom: 4px;">Cena</div>
                                <div style="color: #6366f1; font-size: 16px; font-weight: 600;">${escapeHtml(hasPrice ? `${priceValue.toLocaleString('cs-CZ')} Kč` : 'Neuvedeno')}</div>
                            </div>
                            ${noteToRender ? `
                            <div>
                                <div style="color: #94a3b8; font-size: 12px; margin-bottom: 4px;">Poznámka</div>
                                <div style="color: #e2e8f0; font-size: 14px; white-space: pre-line;">${escapeHtml(String(noteToRender || ''))}</div>
                            </div>
                            ` : ''}
                            ${parsedSummaryHtml}
                            ${attachmentsHtml}
                            ${record.created_by_ai ? `
                            <div style="margin-top: 12px; padding: 12px; background: rgba(99, 102, 241, 0.15); border-radius: 8px; border-left: 3px solid #6366f1;">
                                <div style="color: #94a3b8; font-size: 11px; font-style: italic;">🤖 Záznam vytvořený AI asistentem</div>
                            </div>
                            ` : ''}
                        </div>
                        <div style="display: flex; gap: 10px; margin-top: 20px; flex-direction: column;">
                            <button ${legacyActionAttributes("click", "openEditServiceRecordModal_544ccd45", recordId, vehicleId)} class="btn" style="width: 100%; padding: 10px; background: #6366f1; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px;">✏️ Upravit</button>
                            <button ${legacyActionAttributes("click", "deleteServiceRecordFromDetail_4ad93f83", recordId, vehicleId)} class="btn" style="width: 100%; padding: 10px; background: #dc3545; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px;">🗑️ Smazat</button>
                            <button ${legacyActionAttributes("click", "closeServiceRecordDetailModal_f01a2a03")} class="btn" style="width: 100%; padding: 10px; background: #6c757d; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px;">Zavřít</button>
                        </div>
                    </div>
                `;

                // Zobrazit v modalu pro detail záznamu
                if (modal && modalBody) {
                    modal.setAttribute('data-vehicle-id', vehicleId);
                    modal.setAttribute('data-record-id', recordId);
                    modal.classList.add('active');
                    modalBody.innerHTML = detailHtml;
                }
            } catch (error) {
                console.error("Error loading service record detail:");
                showAlert('Nepodařilo se načíst detail záznamu: ' + error.message, 'error');
            }
        }

        function closeServiceRecordDetailModal() {
            const modal = document.getElementById('serviceRecordDetailModal');
            if (modal) {
                closeStaticOverlayModal(modal);
            }
        }

        // Generování PDF s historií servisních záznamů - globální funkce
        window.generateServiceRecordsPDF = async function(vehicleId) {
            if (window.CustomerFeatures) {
                try { return await window.CustomerFeatures.downloadPDF(vehicleId); }
                catch (error) { if (error.name !== 'AbortError') showAlert(error.message, 'error'); return; }
            }





            if (!vehicleId || vehicleId === 'undefined' || vehicleId === 'null') {
                console.error("[PDF] Chybí nebo neplatné vehicleId!");
                showAlert('Chyba: Chybí ID vozidla', 'error');
                return;
            }

            // Převést na číslo, pokud je to string
            const vehicleIdNum = parseInt(vehicleId);
            if (isNaN(vehicleIdNum)) {
                console.error("[PDF] vehicleId není číslo:");
                showAlert('Chyba: Neplatné ID vozidla', 'error');
                return;
            }

            try {

                showAlert('Generuji PDF...', 'info');

                // Aktualizovat API_URL (stejně jako v apiCall)
                API_URL = getApiBaseUrl();

                if (!API_URL) {
                    throw new Error('API URL není nastavena. Kontaktujte administrátora.');
                }

                // Získat token pro autentizaci (stejně jako v apiCall)
                const token = AdminBrowserSession.token();
                if (!token) {
                    showAlert('Musíte být přihlášeni', 'error');
                    return;
                }

                const url = `${API_URL}/api/v1/vehicles/${vehicleIdNum}/pdf`;


                const pdfHeaders = {
                    'Authorization': `Bearer ${token}`
                };
                appendClientGeoHeaders(pdfHeaders);

                // Zavolat API endpoint pro generování PDF
                const response = await AdminBrowserSession.request(url, {
                    method: 'GET',
                    headers: pdfHeaders
                });



                if (!response.ok) {
                    // Zkusit získat chybovou zprávu
                    let errorMessage = `Chyba při generování PDF (HTTP ${response.status})`;
                    try {
                        const contentType = response.headers.get('content-type');


                        // Zkusit získat text response (response lze přečíst jen jednou)
                        const responseText = await response.text();


                        if (contentType && contentType.includes('application/json')) {
                            try {
                                const error = JSON.parse(responseText);


                                // FastAPI vrací chyby v různých formátech
                                if (Array.isArray(error.detail)) {
                                    // Validation error - seznam chyb
                                    const errors = error.detail.map(e => {
                                        if (typeof e === 'object' && e.loc && e.msg) {
                                            return `${e.loc.join('.')}: ${e.msg}`;
                                        }
                                        return String(e);
                                    }).join(', ');
                                    errorMessage = `Validační chyba: ${errors}`;
                                } else if (error.detail) {
                                    errorMessage = String(error.detail);
                                } else if (error.message) {
                                    errorMessage = String(error.message);
                                } else {
                                    errorMessage = JSON.stringify(error);
                                }
                            } catch (parseError) {
                                console.error("[PDF] Chyba při parsování JSON:");
                                errorMessage = responseText || errorMessage;
                            }
                        } else {
                            if (responseText && responseText.length < 500) {
                                errorMessage = responseText;
                            }
                        }
                    } catch (e) {
                        console.error("[PDF] Chyba při parsování error response:");
                        errorMessage = `HTTP ${response.status}: ${response.statusText}`;
                    }
                    throw new Error(errorMessage);
                }

                // Zkontrolovat content-type
                const contentType = response.headers.get('content-type');


                if (!contentType || !contentType.includes('application/pdf')) {
                    console.warn("[PDF] Neočekávaný content-type:");
                }

                // Získat PDF jako blob
                const blob = await response.blob();


                if (blob.size === 0) {
                    throw new Error('PDF soubor je prázdný');
                }

                // Vytvořit URL pro stažení
                const blobUrl = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = blobUrl;
                a.style.display = 'none';

                // Název souboru z response headers nebo default
                const contentDisposition = response.headers.get('content-disposition');
                let filename = 'servisni_zaznamy.pdf';
                if (contentDisposition) {
                    const filenameMatch = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/i);
                    if (filenameMatch && filenameMatch[1]) {
                        filename = filenameMatch[1].replace(/['"]/g, '');
                    }
                }

                a.download = filename;
                document.body.appendChild(a);
                a.click();

                // Vyčkat chvíli před odstraněním
                setTimeout(() => {
                    document.body.removeChild(a);
                    window.URL.revokeObjectURL(blobUrl);
                }, 100);


                showAlert('PDF bylo úspěšně vygenerováno a staženo!', 'success');
            } catch (error) {
                console.error("[PDF] Chyba při generování PDF:");
                console.error("[PDF] Error stack:");
                showAlert('Nepodařilo se vygenerovat PDF: ' + (error.message || error), 'error');
            }
        };

        // Také jako normální funkce pro kompatibilitu
        function generateServiceRecordsPDF(vehicleId) {
            return window.generateServiceRecordsPDF(vehicleId);
        }

        // Funkce pro resetování modalu po zavření (aby se při dalším otevření zobrazil správný formulář)
        function resetAddServiceRecordModal() {
            const modal = document.getElementById('addServiceRecordModal');
            addServiceRecordDocumentPrefill = null;
            setAddServiceRecordAnalysisStatus('');
            delete serviceReportEditorState.add;
            if (modal) {
                const recordId = modal.getAttribute('data-record-id');
                if (recordId) {
                    delete serviceReportEditorState[`edit-${recordId}`];
                    delete serviceRecordEditContext[recordId];
                }
                const modalHeader = modal.querySelector('.vehicle-modal-header h2');
                if (modalHeader) modalHeader.textContent = 'Přidat servisní záznam';
                modal.removeAttribute('data-record-id');
                modal.removeAttribute('data-vehicle-id');
            }
        }

        // Otevření modalu pro editaci servisního záznamu
        async function openEditServiceRecordModal(recordId, vehicleId) {
            try {
                // Načíst záznam
                const record = await apiCall(`/api/v1/vehicles/${vehicleId}/records/${recordId}`, 'GET');

                // Zavřít detail modal
                closeServiceRecordDetailModal();

                // Otevřít modal pro editaci (použijeme stejný modal jako pro přidání)
                const modal = document.getElementById('addServiceRecordModal');
                const modalBody = document.getElementById('addServiceRecordModalBody');

                if (!modal || !modalBody) return;

                modal.setAttribute('data-vehicle-id', vehicleId);
                modal.setAttribute('data-record-id', recordId);
                openStaticOverlayModal(modal, {
                    scrollTargetSelector: '.vehicle-modal-body',
                });

                // Najít kategorii
                const category = record.category || 'JINE';
                const categoryInfo = SERVICE_CATEGORIES.find(c => c.value === category) || SERVICE_CATEGORIES.find(c => c.value === 'JINE');
                const categoryIcon = categoryInfo ? categoryInfo.icon : '📋';
                const categoryLabel = categoryInfo ? categoryInfo.label : category;
                const recordAttachments = parseServiceRecordAttachments(vehicleId, record.attachments);
                const reportPayload = extractServiceReportFromAttachments(recordAttachments, record);
                serviceRecordEditContext[recordId] = {
                    attachments: recordAttachments,
                };

                // Formátovat datum pro datetime-local input
                const date = new Date(record.performed_at);
                const year = date.getFullYear();
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const day = String(date.getDate()).padStart(2, '0');
                const hours = String(date.getHours()).padStart(2, '0');
                const minutes = String(date.getMinutes()).padStart(2, '0');
                const dateTimeLocal = `${year}-${month}-${day}T${hours}:${minutes}`;
                const fileAttachments = recordAttachments.filter((att) => att.can_preview && att.download_url);
                const fileAttachmentsHtml = fileAttachments.length
                    ? `
                        <div class="record-attachments-block">
                            <div style="color: #94a3b8; font-size: 12px; margin-bottom: 4px;">Připojené doklady</div>
                            <div class="record-attachments-list">
                                ${fileAttachments.map((att, idx) => `
                                    <button
                                        type="button"
                                        class="record-attachments-item"
                                        ${legacyActionAttributes("click", "openServiceRecordAttachmentPreview_641bbe9b", encodeURIComponent(att.download_url || ''), encodeURIComponent(att.file_name || `Příloha ${idx + 1}`))}
                                    >
                                        📎 ${escapeHtml(att.file_name || `Příloha ${idx + 1}`)}
                                        ${att.file_size ? `<span style="opacity:0.75;">(${escapeHtml(formatAttachmentSize(att.file_size))})</span>` : ''}
                                    </button>
                                `).join('')}
                            </div>
                        </div>
                    `
                    : '';

                // Vytvořit formulář pro editaci
                modalBody.innerHTML = `
                    <form ${legacyActionAttributes("submit", "handleEditServiceRecordSubmit_229cc8e0", recordId, vehicleId)} style="display: flex; flex-direction: column; gap: 16px;">
                        <!-- Výběr kategorie -->
                        <div class="form-group">
                            <label style="display: block; margin-bottom: 8px; color: #cbd5e1; font-size: 14px; font-weight: 500;">Kategorie *</label>
                            <div class="category-selector">
                                <button type="button" class="category-selector-button" id="category-selector-btn-edit-${escapeHtml(recordId)}" ${legacyActionAttributes("click", "toggleCategoryDropdown_713f9a7a", recordId)}>
                                    <span id="category-selected-text-edit-${escapeHtml(recordId)}">${escapeHtml(categoryIcon)} ${escapeHtml(categoryLabel)}</span>
                                    <span style="font-size: 12px;">▼</span>
                                </button>
                                <div class="category-dropdown" id="category-dropdown-edit-${escapeHtml(recordId)}">
                                    ${SERVICE_CATEGORIES.map(cat => `
                                        <div class="category-option ${cat.value === category ? 'selected' : ''}" ${legacyActionAttributes("click", "selectCategory_66b8da76", cat.value, cat.label, cat.icon, recordId)}>
                                            <span style="margin-right: 8px;">${escapeHtml(cat.icon)}</span>
                                            ${escapeHtml(cat.label)}
                                        </div>
                                    `).join('')}
                                </div>
                                <input type="hidden" id="serviceCategory-edit-${escapeHtml(recordId)}" value="${escapeHtml(category)}" required>
                            </div>
                        </div>

                        <!-- Datum -->
                        <div class="form-group">
                            <label for="serviceDate-edit-${escapeHtml(recordId)}" style="display: block; margin-bottom: 8px; color: #cbd5e1; font-size: 14px; font-weight: 500;">Datum *</label>
                            <input type="datetime-local" id="serviceDate-edit-${escapeHtml(recordId)}" value="${escapeHtml(dateTimeLocal)}" required style="width: 100%; padding: 10px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 6px; color: #f1f5f9; font-size: 14px;">
                        </div>

                        <!-- Popis -->
                        <div class="form-group">
                            <label for="serviceDescription-edit-${escapeHtml(recordId)}" style="display: block; margin-bottom: 8px; color: #cbd5e1; font-size: 14px; font-weight: 500;">Popis úkonu *</label>
                            <textarea id="serviceDescription-edit-${escapeHtml(recordId)}" rows="3" placeholder="Např. Výměna oleje, kontrola brzd..." required minlength="3" title="Vyplňte prosím popis úkonu" style="width: 100%; padding: 10px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 6px; color: #f1f5f9; font-size: 14px; font-family: inherit; resize: vertical;">${escapeHtml(record.description || '')}</textarea>
                        </div>

                        <!-- Nájezd a cena -->
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                            <div class="form-group">
                                <label for="serviceMileage-edit-${escapeHtml(recordId)}" style="display: block; margin-bottom: 8px; color: #cbd5e1; font-size: 14px; font-weight: 500;">Nájezd (km) *</label>
                                <input type="number" id="serviceMileage-edit-${escapeHtml(recordId)}" value="${escapeHtml(record.mileage || '')}" required min="0" step="1" inputmode="numeric" style="width: 100%; padding: 10px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 6px; color: #f1f5f9; font-size: 14px;">
                            </div>
                            <div class="form-group">
                                <label for="servicePrice-edit-${escapeHtml(recordId)}" style="display: block; margin-bottom: 8px; color: #cbd5e1; font-size: 14px; font-weight: 500;">Cena (Kč) *</label>
                                <input type="number" id="servicePrice-edit-${escapeHtml(recordId)}" value="${escapeHtml(record.price || '')}" required min="0" step="0.01" inputmode="decimal" style="width: 100%; padding: 10px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 6px; color: #f1f5f9; font-size: 14px;">
                            </div>
                        </div>

                        <!-- Poznámka -->
                        <div class="form-group">
                            <label for="serviceNote-edit-${escapeHtml(recordId)}" style="display: block; margin-bottom: 8px; color: #cbd5e1; font-size: 14px; font-weight: 500;">Poznámka</label>
                            <textarea id="serviceNote-edit-${escapeHtml(recordId)}" rows="4" placeholder="Dodatečné informace..." style="width: 100%; padding: 10px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 6px; color: #f1f5f9; font-size: 14px; font-family: inherit; resize: vertical;">${escapeHtml(record.note || '')}</textarea>
                        </div>

                        <div id="serviceReportEditor-edit-${escapeHtml(recordId)}"></div>
                        ${fileAttachmentsHtml}

                        <!-- Tlačítka -->
                        <div style="display: flex; gap: 10px; margin-top: 8px;">
                            <button type="submit" class="btn" style="flex: 1; padding: 12px; background: #6366f1; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500;">Uložit změny</button>
                            <button type="button" ${legacyActionAttributes("click", "closeAddServiceRecordModal_d539d5f4")} class="btn" style="padding: 12px 20px; background: #6c757d; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px;">Zrušit</button>
                        </div>
                    </form>
                `;

                // Aktualizovat header
                const modalHeader = modal.querySelector('.vehicle-modal-header h2');
                if (modalHeader) modalHeader.textContent = 'Upravit servisní záznam';
                initializeServiceReportEditor(`edit-${recordId}`, reportPayload);
            } catch (error) {
                console.error("Error loading service record for edit:");
                showAlert('Nepodařilo se načíst záznam pro úpravu: ' + error.message, 'error');
            }
        }

        // Odeslání formuláře pro editaci servisního záznamu
        async function handleEditServiceRecordSubmit(event, recordId, vehicleId) {
            event.preventDefault();

            const category = document.getElementById(`serviceCategory-edit-${recordId}`).value;
            const dateInput = document.getElementById(`serviceDate-edit-${recordId}`).value;
            const descriptionInputValue = document.getElementById(`serviceDescription-edit-${recordId}`).value.trim();
            const mileage = document.getElementById(`serviceMileage-edit-${recordId}`).value.trim();
            const price = document.getElementById(`servicePrice-edit-${recordId}`).value.trim();
            const note = document.getElementById(`serviceNote-edit-${recordId}`).value;
            const reportData = getServiceReportEditorValue(`edit-${recordId}`);
            const description = descriptionInputValue
                || String(reportData.issue_description || '').trim()
                || String(reportData.service_summary || '').trim();

            if (!category) {
                showAlert('Vyberte prosím kategorii', 'error');
                return;
            }

            if (!dateInput || !description) {
                showAlert('Vyplňte prosím datum a popis úkonu', 'error');
                return;
            }

            if (!mileage) {
                showAlert('Vyplňte prosím nájezd', 'error');
                return;
            }

            const mileageValue = Number(mileage);
            if (!Number.isInteger(mileageValue) || mileageValue < 0) {
                showAlert('Nájezd musí být celé číslo 0 nebo vyšší', 'error');
                return;
            }

            let priceValue = null;
            if (price) {
                const parsedPrice = Number(String(price).replace(',', '.'));
                if (Number.isFinite(parsedPrice) && parsedPrice >= 0) {
                    priceValue = parsedPrice;
                }
            }
            if (priceValue === null) {
                priceValue = parseOptionalNumber(reportData.total_with_vat);
                const priceInputEl = document.getElementById(`servicePrice-edit-${recordId}`);
                if (priceInputEl && priceValue !== null) {
                    priceInputEl.value = String(priceValue);
                }
            }
            if (!Number.isFinite(priceValue) || priceValue < 0) {
                showAlert('Cena musí být číslo 0 nebo vyšší', 'error');
                return;
            }

            const parsedDate = new Date(dateInput);
            if (Number.isNaN(parsedDate.getTime())) {
                showAlert('Datum má neplatný formát', 'error');
                return;
            }

            try {
                if (!reportData.service_summary) {
                    reportData.service_summary = description;
                }
                reportData.total_with_vat = roundTo2(priceValue);

                const existingAttachmentsRaw = Array.isArray(serviceRecordEditContext[recordId]?.attachments)
                    ? serviceRecordEditContext[recordId].attachments
                    : [];
                const sanitizedAttachments = existingAttachmentsRaw
                    .filter((item) => item && typeof item === 'object' && item.kind !== SERVICE_REPORT_META_KIND)
                    .map((item) => {
                        const clone = {
                            kind: item.kind || 'user_document',
                            file_name: item.file_name || 'Příloha',
                            mime_type: item.mime_type || '',
                            file_size: Number(item.file_size) || null,
                            storage_key: item.storage_key || '',
                            path: item.path || '',
                            download_url: item.download_url || '',
                            source_type: item.source_type || reportData.source_type || 'manual',
                        };
                        if (clone.kind === 'user_document' || clone.kind === 'service_document') {
                            clone.parsed_summary = reportData;
                        } else if (item.parsed_summary && typeof item.parsed_summary === 'object') {
                            clone.parsed_summary = item.parsed_summary;
                        }
                        return clone;
                    });
                sanitizedAttachments.unshift({
                    kind: SERVICE_REPORT_META_KIND,
                    source_type: reportData.source_type || 'manual',
                    parsed_summary: reportData,
                });

                const updateData = {
                    performed_at: parsedDate.toISOString(),
                    mileage: mileageValue,
                    description: description,
                    price: priceValue,
                    note: note || null,
                    category: category,
                    attachments: JSON.stringify(sanitizedAttachments),
                };

                if (currentLicensePlanForUi === 'free' && !['admin', 'developer_admin', 'service'].includes(currentUser?.role)) delete updateData.attachments;
                showAlert('Ukládám změny...', 'info');
                await apiCall(`/api/v1/vehicles/${vehicleId}/records/${recordId}`, 'PUT', updateData);

                showAlert('Záznam byl úspěšně upraven!', 'success');
                delete serviceRecordEditContext[recordId];

                // Zavřít modal
                closeAddServiceRecordModal();

                // Načíst aktualizované záznamy
                await loadServiceRecordsModal(vehicleId);
            } catch (error) {
                console.error("Error updating service record:");
                showAlert('Nepodařilo se upravit záznam: ' + error.message, 'error');
            }
        }

        // Přidání servisního úkonu z modalu
        async function handleAddServiceModal(event, vehicleId) {
            event.preventDefault();

            const dateInput = document.getElementById(`serviceDate-modal-${vehicleId}`).value;
            const mileage = document.getElementById(`serviceMileage-modal-${vehicleId}`).value.trim();
            const description = document.getElementById(`serviceDescription-modal-${vehicleId}`).value.trim();
            const price = document.getElementById(`servicePrice-modal-${vehicleId}`).value.trim();
            const note = document.getElementById(`serviceNote-modal-${vehicleId}`).value;

            if (!dateInput || !description || !mileage || !price) {
                showAlert('Vyplňte prosím datum, popis, nájezd a cenu', 'error');
                return;
            }

            const mileageValue = Number(mileage);
            if (!Number.isInteger(mileageValue) || mileageValue < 0) {
                showAlert('Nájezd musí být celé číslo 0 nebo vyšší', 'error');
                return;
            }

            const priceValue = Number(String(price).replace(',', '.'));
            if (!Number.isFinite(priceValue) || priceValue < 0) {
                showAlert('Cena musí být číslo 0 nebo vyšší', 'error');
                return;
            }

            const parsedDate = new Date(dateInput);
            if (Number.isNaN(parsedDate.getTime())) {
                showAlert('Datum má neplatný formát', 'error');
                return;
            }

            try {
                const recordData = {
                    performed_at: parsedDate.toISOString(),
                    mileage: mileageValue,
                    description: description,
                    price: priceValue,
                    note: note || null,
                    category: 'JINE'
                };

                showAlert('Přidávám servisní úkon...', 'info');
                await apiCall(`/api/v1/vehicles/${vehicleId}/records`, 'POST', recordData);

                showAlert('Servisní úkon byl úspěšně přidán!', 'success');

                // Vyčistit formulář
                document.getElementById(`serviceDate-modal-${vehicleId}`).value = '';
                document.getElementById(`serviceMileage-modal-${vehicleId}`).value = '';
                document.getElementById(`serviceDescription-modal-${vehicleId}`).value = '';
                document.getElementById(`servicePrice-modal-${vehicleId}`).value = '';
                document.getElementById(`serviceNote-modal-${vehicleId}`).value = '';

                // Skrýt formulář
                toggleAddServiceForm(vehicleId);

                // Načíst aktualizované servisní záznamy
                await loadServiceRecordsModal(vehicleId);
            } catch (error) {
                console.error("Error adding service record:");
                showAlert('Nepodařilo se přidat servisní úkon: ' + error.message, 'error');
            }
        }

        function confirmServiceRecordDeletion() {
            const firstConfirm = confirm(
                'Opravdu chcete smazat tento servisní záznam?\n\nTato akce je nevratná.'
            );
            if (!firstConfirm) {
                return false;
            }

            const typedValue = prompt('Pro potvrzení napište slovo: smazat', '');
            if (typedValue === null) {
                return false;
            }

            if (typedValue.trim().toLowerCase() !== 'smazat') {
                showAlert('Mazání zrušeno: potvrzovací slovo není správné.', 'error');
                return false;
            }

            return true;
        }

        async function deleteServiceRecordFromDetail(recordId, vehicleId) {
            if (!confirmServiceRecordDeletion()) {
                return;
            }

            try {
                showAlert('Mažu servisní záznam...', 'info');
                await apiCall(`/api/v1/vehicles/${vehicleId}/records/${recordId}`, 'DELETE');
                closeServiceRecordDetailModal();
                showAlert('Servisní záznam byl úspěšně smazán!', 'success');
                await loadServiceRecordsModal(vehicleId);
            } catch (error) {
                console.error("Error deleting service record from detail:");
                showAlert('Nepodařilo se smazat servisní záznam: ' + error.message, 'error');
            }
        }

        // Smazání servisního záznamu z modalu
        async function deleteServiceRecordModal(recordId, vehicleId) {
            if (!confirmServiceRecordDeletion()) {
                return;
            }

            try {
                showAlert('Mažu servisní záznam...', 'info');
                await apiCall(`/api/v1/vehicles/${vehicleId}/records/${recordId}`, 'DELETE');
                showAlert('Servisní záznam byl úspěšně smazán!', 'success');

                // Načíst aktualizované servisní záznamy
                await loadServiceRecordsModal(vehicleId);
            } catch (error) {
                console.error("Error deleting service record:");
                showAlert('Nepodařilo se smazat servisní záznam: ' + error.message, 'error');
            }
        }

        // Funkce pro inline editaci vozidla v rozbalovacím panelu
        function startEditInline(field, vehicleId) {
            const row = document.querySelector(`.vehicle-info-row[data-field="${field}"][data-vehicle-id="${vehicleId}"]`);
            if (!row) return;

            const display = row.querySelector('.vehicle-info-display');
            const edit = row.querySelector('.vehicle-info-edit');

            if (display && edit) {
                display.style.display = 'none';
                edit.style.display = 'flex';

                // Focus na input
                const input = edit.querySelector('input, textarea');
                if (input) {
                    input.focus();
                    input.select();
                }
            }
        }

        function cancelEditInline(field, vehicleId) {
            const row = document.querySelector(`.vehicle-info-row[data-field="${field}"][data-vehicle-id="${vehicleId}"]`);
            if (!row) return;

            const display = row.querySelector('.vehicle-info-display');
            const edit = row.querySelector('.vehicle-info-edit');

            if (display && edit) {
                edit.style.display = 'none';
                display.style.display = 'flex';

                // Obnovit původní hodnotu
                const input = edit.querySelector('input, textarea');
                if (input && window.currentVehicle) {
                    input.value = window.currentVehicle[field] || '';
                }
            }
        }

        async function saveVehicleFieldInline(field, vehicleId) {
            if (!vehicleId || !window.currentVehicle) {
                showAlert('Chyba: Vozidlo není načteno', 'error');
                return;
            }

            const row = document.querySelector(`.vehicle-info-row[data-field="${field}"][data-vehicle-id="${vehicleId}"]`);
            if (!row) return;

            const input = row.querySelector('input, textarea');
            if (!input) return;

            const newValue = input.value.trim();

            // Validace
            if (field === 'plate' && !newValue) {
                showAlert('SPZ je povinné pole', 'error');
                return;
            }

            try {
                // Příprava dat pro aktualizaci - API očekává přesné názvy polí
                const updateData = {};

                if (field === 'nickname') {
                    updateData.nickname = newValue || null;
                } else if (field === 'plate') {
                    updateData.plate = newValue;
                } else if (field === 'notes') {
                    updateData.notes = newValue || null;
                } else {
                    showAlert('Neznámé pole pro úpravu', 'error');
                    return;
                }

                showAlert('Ukládám změny...', 'info');

                // Volání API
                const updatedVehicle = await apiCall(`/api/v1/vehicles/${vehicleId}`, 'PUT', updateData);

                // Aktualizovat lokální data
                window.currentVehicle[field] = newValue;

                // Aktualizovat zobrazení
                const display = row.querySelector('.vehicle-info-display');
                const valueSpan = display.querySelector('.vehicle-info-value');
                if (valueSpan) {
                    valueSpan.textContent = newValue || 'Nezadáno';
                    valueSpan.classList.toggle('empty', !newValue);
                }

                // Skrýt editaci
                const edit = row.querySelector('.vehicle-info-edit');
                if (edit) edit.style.display = 'none';
                if (display) display.style.display = 'flex';

                showAlert('Změny byly úspěšně uloženy!', 'success');

                // Aktualizovat název v hlavičce karty, pokud se změnil nickname
                if (field === 'nickname') {
                    const card = document.querySelector(`[data-vehicle-id="${vehicleId}"]`);
                    const title = card?.querySelector('.card-title');
                    if (title) {
                        title.textContent = newValue || 'Bez názvu';
                    }
                }

                // Obnovit seznam vozidel, aby se aktualizoval název v kartě
                await loadVehicles();

            } catch (error) {
                console.error("Error updating vehicle:");
                showAlert('Nepodařilo se uložit změny: ' + (error.message || 'Neznámá chyba'), 'error');
            }
        }

        // Načtení servisních záznamů do rozbalovacího panelu
        async function loadServiceRecordsInline(vehicleId) {
            const container = document.getElementById(`service-records-${vehicleId}`);
            if (!container) return;

            container.innerHTML = '<div class="loading">Načítám servisní záznamy...</div>';

            try {
                const records = await apiCall(`/api/v1/vehicles/${vehicleId}/records`, 'GET');

                if (!records || records.length === 0) {
                    container.innerHTML = '<p style="color: #94a3b8; font-size: 14px;">Zatím nejsou žádné servisní záznamy. Přidejte první pomocí formuláře níže.</p>';
                    return;
                }

                let html = '<div class="reminders-section">';
                records.forEach(record => {
                    const date = new Date(record.performed_at);
                    html += `
                        <div class="service-record-item" style="margin-bottom: 12px; padding: 12px; background: rgba(15, 23, 42, 0.4); border-radius: 8px; border-left: 3px solid #6366f1;">
                            <h5 style="margin: 0 0 8px 0; color: #e2e8f0; font-size: 15px;">${escapeHtml(record.description)}</h5>
                            <div style="color: #94a3b8; font-size: 13px; margin-bottom: 8px;">${escapeHtml(date.toLocaleDateString('cs-CZ'))} ${escapeHtml(date.toLocaleTimeString('cs-CZ', {hour: '2-digit', minute: '2-digit'}))}</div>
                            <div style="color: #cbd5e1; font-size: 13px;">
                                ${record.mileage ? `<div><strong>Nájezd:</strong> ${escapeHtml(record.mileage.toLocaleString('cs-CZ'))} km</div>` : ''}
                                ${record.note ? `<div><strong>Kategorie:</strong> ${escapeHtml(record.note)}</div>` : ''}
                                ${record.price ? `<div style="margin-top: 8px; color: #6366f1; font-weight: 600;"><strong>Cena:</strong> ${escapeHtml(record.price.toLocaleString('cs-CZ'))} Kč</div>` : ''}
                            </div>
                            <button ${legacyActionAttributes("click", "deleteServiceRecordInline_6d69444e", record.id, vehicleId)} style="margin-top: 10px; background: #dc3545; color: white; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px;">Smazat</button>
                        </div>
                    `;
                });
                container.innerHTML = html;
            } catch (error) {
                console.error("Error loading service records:");
                container.innerHTML = `<p class="alert alert-error">Chyba při načítání servisních záznamů: ${escapeHtml(error.message)}</p>`;
            }
        }

        // Přidání servisního úkonu z inline formuláře
        async function handleAddServiceInline(event, vehicleId) {
            event.preventDefault();

            const dateInput = document.getElementById(`serviceDate-${vehicleId}`).value;
            const mileage = document.getElementById(`serviceMileage-${vehicleId}`).value.trim();
            const description = document.getElementById(`serviceDescription-${vehicleId}`).value.trim();
            const price = document.getElementById(`servicePrice-${vehicleId}`).value.trim();
            const note = document.getElementById(`serviceNote-${vehicleId}`).value;

            if (!dateInput || !description || !mileage || !price) {
                showAlert('Vyplňte prosím datum, popis, nájezd a cenu', 'error');
                return;
            }

            const mileageValue = Number(mileage);
            if (!Number.isInteger(mileageValue) || mileageValue < 0) {
                showAlert('Nájezd musí být celé číslo 0 nebo vyšší', 'error');
                return;
            }

            const priceValue = Number(String(price).replace(',', '.'));
            if (!Number.isFinite(priceValue) || priceValue < 0) {
                showAlert('Cena musí být číslo 0 nebo vyšší', 'error');
                return;
            }

            const parsedDate = new Date(dateInput);
            if (Number.isNaN(parsedDate.getTime())) {
                showAlert('Datum má neplatný formát', 'error');
                return;
            }

            try {
                const recordData = {
                    performed_at: parsedDate.toISOString(),
                    mileage: mileageValue,
                    description: description,
                    price: priceValue,
                    note: note || null,
                    category: 'JINE'
                };

                showAlert('Přidávám servisní úkon...', 'info');
                await apiCall(`/api/v1/vehicles/${vehicleId}/records`, 'POST', recordData);

                showAlert('Servisní úkon byl úspěšně přidán!', 'success');

                // Vyčistit formulář
                document.getElementById(`serviceDate-${vehicleId}`).value = '';
                document.getElementById(`serviceMileage-${vehicleId}`).value = '';
                document.getElementById(`serviceDescription-${vehicleId}`).value = '';
                document.getElementById(`servicePrice-${vehicleId}`).value = '';
                document.getElementById(`serviceNote-${vehicleId}`).value = '';

                // Načíst aktualizované servisní záznamy
                await loadServiceRecordsInline(vehicleId);
            } catch (error) {
                console.error("Error adding service record:");
                showAlert('Nepodařilo se přidat servisní úkon: ' + error.message, 'error');
            }
        }

        // Smazání servisního záznamu z inline panelu
        async function deleteServiceRecordInline(recordId, vehicleId) {
            if (!confirmServiceRecordDeletion()) {
                return;
            }

            try {
                showAlert('Mažu servisní záznam...', 'info');
                await apiCall(`/api/v1/vehicles/${vehicleId}/records/${recordId}`, 'DELETE');
                showAlert('Servisní záznam byl úspěšně smazán!', 'success');

                // Načíst aktualizované servisní záznamy
                await loadServiceRecordsInline(vehicleId);
            } catch (error) {
                console.error("Error deleting service record:");
                showAlert('Nepodařilo se smazat servisní záznam: ' + error.message, 'error');
            }
        }

        // Funkce pro editaci vozidla (zachováno pro zpětnou kompatibilitu)
        function startEdit(field) {
            if (currentVehicleId) {
                startEditInline(field, currentVehicleId);
            }
        }

        function cancelEdit(field) {
            if (currentVehicleId) {
                cancelEditInline(field, currentVehicleId);
            }
        }

        async function saveVehicleField(field) {
            if (currentVehicleId) {
                await saveVehicleFieldInline(field, currentVehicleId);
            }
        }

        // Zobrazení seznamu vozidel
        function showVehiclesList() {
            document.getElementById('vehiclesList').style.display = 'block';
            document.getElementById('vehicleDetail').classList.remove('active');
            currentVehicleId = null;
        }

        // Načtení servisních záznamů
        async function loadServiceRecords(vehicleId) {
            const container = document.getElementById('serviceRecordsList');
            container.innerHTML = '<div class="loading">Načítám servisní záznamy...</div>';

            try {
                const records = await apiCall(`/api/v1/vehicles/${vehicleId}/records`, 'GET');

                if (!records || records.length === 0) {
                    container.innerHTML = '<p>Zatím nejsou žádné servisní záznamy. Přidejte první pomocí formuláře níže.</p>';
                    return;
                }

                let html = '';
                records.forEach(record => {
                    const date = new Date(record.performed_at);
                    html += `
                        <div class="service-record-item">
                            <h4>${escapeHtml(record.description)}</h4>
                            <div class="record-date">${escapeHtml(date.toLocaleDateString('cs-CZ'))} ${escapeHtml(date.toLocaleTimeString('cs-CZ', {hour: '2-digit', minute: '2-digit'}))}</div>
                            <div class="record-details">
                                ${record.mileage ? `<p><strong>Nájezd:</strong> ${escapeHtml(record.mileage.toLocaleString('cs-CZ'))} km</p>` : ''}
                                ${record.note ? `<p><strong>Kategorie:</strong> ${escapeHtml(record.note)}</p>` : ''}
                            </div>
                            ${record.price ? `<div class="record-price">Cena: ${escapeHtml(record.price.toLocaleString('cs-CZ'))} Kč</div>` : ''}
                            <button ${legacyActionAttributes("click", "deleteServiceRecord_08dc47d2", record.id)} style="margin-top: 10px; background: #dc3545; color: white; border: none; padding: 5px 10px; border-radius: 3px; cursor: pointer;">Smazat</button>
                        </div>
                    `;
                });
                container.innerHTML = html;
            } catch (error) {
                console.error("Error loading service records:");
                container.innerHTML = `<p class="alert alert-error">Chyba při načítání servisních záznamů: ${escapeHtml(error.message)}</p>`;
            }
        }

        // Přidání servisního úkonu
        async function handleAddService(event) {
            event.preventDefault();

            if (!currentVehicleId) {
                showAlert('Chyba: Vozidlo není vybráno', 'error');
                return;
            }

            const dateInput = document.getElementById('serviceDate').value;
            const mileage = document.getElementById('serviceMileage').value.trim();
            const description = document.getElementById('serviceDescription').value.trim();
            const price = document.getElementById('servicePrice').value.trim();
            const note = document.getElementById('serviceNote').value;

            if (!dateInput || !description || !mileage || !price) {
                showAlert('Vyplňte prosím datum, popis, nájezd a cenu', 'error');
                return;
            }

            const mileageValue = Number(mileage);
            if (!Number.isInteger(mileageValue) || mileageValue < 0) {
                showAlert('Nájezd musí být celé číslo 0 nebo vyšší', 'error');
                return;
            }

            const priceValue = Number(String(price).replace(',', '.'));
            if (!Number.isFinite(priceValue) || priceValue < 0) {
                showAlert('Cena musí být číslo 0 nebo vyšší', 'error');
                return;
            }

            const parsedDate = new Date(dateInput);
            if (Number.isNaN(parsedDate.getTime())) {
                showAlert('Datum má neplatný formát', 'error');
                return;
            }

            try {
                const recordData = {
                    performed_at: parsedDate.toISOString(),
                    mileage: mileageValue,
                    description: description,
                    price: priceValue,
                    note: note || null,
                    category: 'JINE'
                };

                showAlert('Přidávám servisní úkon...', 'info');
                await apiCall(`/api/v1/vehicles/${currentVehicleId}/records`, 'POST', recordData);

                showAlert('Servisní úkon byl úspěšně přidán!', 'success');

                // Vyčistit formulář
                document.getElementById('serviceDate').value = '';
                document.getElementById('serviceMileage').value = '';
                document.getElementById('serviceDescription').value = '';
                document.getElementById('servicePrice').value = '';
                document.getElementById('serviceNote').value = '';

                // Načíst aktualizované servisní záznamy
                await loadServiceRecords(currentVehicleId);
            } catch (error) {
                console.error("Error adding service record:");
                showAlert('Nepodařilo se přidat servisní úkon: ' + error.message, 'error');
            }
        }

        // Smazání servisního záznamu
        async function deleteServiceRecord(recordId) {
            if (!confirmServiceRecordDeletion()) {
                return;
            }

            try {
                if (!currentVehicleId) {
                    showAlert('Chyba: Nelze smazat záznam - vozidlo není vybráno', 'error');
                    return;
                }
                await apiCall(`/api/v1/vehicles/${currentVehicleId}/records/${recordId}`, 'DELETE');
                showAlert('Servisní záznam byl smazán', 'success');

                // Načíst aktualizované servisní záznamy (inline i starý způsob)
                if (currentVehicleId) {
                    if (document.getElementById(`service-records-${currentVehicleId}`)) {
                        await loadServiceRecordsInline(currentVehicleId);
                    } else {
                        await loadServiceRecords(currentVehicleId);
                    }
                }
            } catch (error) {
                console.error("Error deleting service record:");
                showAlert('Nepodařilo se smazat servisní záznam: ' + error.message, 'error');
            }
        }

        // Přepínání tabů
        function switchTab(tab, options = {}) {
            const moduleKey = getCapabilityModuleForTab(tab);
            const moduleReport = moduleCapabilities[moduleKey];
            if (moduleReport && moduleReport.available === false) {
                showAlert(
                    'Tato sekce je dočasně nedostupná, dokud neproběhnou migrace databáze. '
                    + formatCapabilityHint(moduleReport),
                    'warning'
                );
                return;
            }

            const activeTabButton = document.querySelector('.tab.active[data-tab-key]');
            const activeTabKey = activeTabButton ? activeTabButton.getAttribute('data-tab-key') : '';
            const shouldGuardUnsavedDraft = !options.skipUnsavedGuard
                && activeTabKey === 'addVehicle'
                && tab !== 'addVehicle'
                && hasUnsavedAddVehicleDraft();

            if (shouldGuardUnsavedDraft) {
                const shouldLeaveDirtyDraft = window.confirm(
                    'Máte rozpracované přidání vozidla. Přechodem na jinou sekci se neuložené změny zahodí. Pokračovat?'
                );
                if (!shouldLeaveDirtyDraft) {
                    return;
                }
            }

            closeMobileNavbarMenu();
            clearBodyScrollLocks();
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));

            const tabMap = {
                vehicles: 'vehiclesTab',
                addVehicle: 'addVehicleTab',
                reminders: 'remindersTab',
                reservations: 'reservationsTab',
                servicesDirectory: 'servicesDirectoryTab',
                serviceWorkspace: 'serviceWorkspaceTab',
                profile: 'profileTab',
                support: 'supportTab'
            };

            const targetContentId = tabMap[tab] || (window.CustomerFeatures && ['customerOverview', 'customerArchives', 'customerInvitations'].includes(tab) ? tab + 'Tab' : null);
            const targetContent = targetContentId ? document.getElementById(targetContentId) : null;
            if (targetContent) {
                targetContent.classList.add('active');
            }

            const targetButton = document.querySelector(`.tab[data-tab-key="${tab}"]`);
            if (targetButton) {
                targetButton.classList.add('active');
            }

            window.CustomerFeatures?.load(tab);
            if (tab === 'vehicles') {
                applyVehicleViewModeUI();
                loadVehicles(false);
            } else if (tab === 'addVehicle') {
                if (typeof ensureServiceAddVehicleSection === 'function') {
                    ensureServiceAddVehicleSection(true);
                }
            } else if (tab === 'reminders') {
                loadReminders(false);
            } else if (tab === 'reservations') {
                loadReservations(false);
            } else if (tab === 'servicesDirectory') {
                loadServicesDirectory();
            } else if (tab === 'serviceWorkspace') {
                loadServiceWorkspace();
            } else if (tab === 'profile') {
                loadProfile(false);
            } else if (tab === 'support') {
                loadSupportPanel(false);
            }
        }

        function hasUnsavedAddVehicleDraft() {
            const addVehicleTab = document.getElementById('addVehicleTab');
            if (!addVehicleTab) return false;
            if (!addVehicleTab.classList.contains('active')) return false;

            if (isServiceWorkspaceRole()) {
                const serviceSelectors = [
                    '#serviceAddVehicleCustomer',
                    '#serviceAddVehicleNickname',
                    '#serviceAddVehiclePlate',
                    '#serviceAddVehicleVin',
                    '#serviceAddVehicleBrand',
                    '#serviceAddVehicleModel',
                    '#serviceAddVehicleYear',
                    '#serviceAddVehicleEngine',
                    '#serviceAddVehicleStk',
                    '#serviceAddVehicleNotes'
                ];
                for (const selector of serviceSelectors) {
                    const field = addVehicleTab.querySelector(selector);
                    if (!field) continue;
                    const value = String(field.value || '').trim();
                    if (value) return true;
                }
                return false;
            }

            const selectors = [
                '#vehicleName',
                '#vehiclePlate',
                '#vehicleModel',
                '#vehicleYear',
                '#vehicleEngine',
                '#vehicleStkDate',
                '#vehicleTyres',
                '#vehicleAdditionalNotes',
                '#vehicleInspectionDate',
                '#vehicleNotes',
                '#vehiclePhotoInput'
            ];

            for (const selector of selectors) {
                const field = addVehicleTab.querySelector(selector);
                if (!field) continue;
                if (field.type === 'file') {
                    if (field.files && field.files.length > 0) return true;
                    continue;
                }
                const value = String(field.value || '').trim();
                if (value) return true;
            }
            return false;
        }

        function confirmExternalWebSectionNavigation() {
            if (!hasUnsavedAddVehicleDraft()) return true;
            return window.confirm(
                'Máte rozpracované přidání vozidla. Otevřením sekce webu se změny v aplikaci neuloží. Pokračovat?'
            );
        }

        function resetManagedServiceContactsFooter() {
            managedServiceContactsState.loadedAt = 0;
            managedServiceContactsState.items = [];
            managedServiceContactsState.loadingPromise = null;
            renderManagedServiceContactsFooter([]);
        }

        async function disconnectManagedServiceContact(serviceId) {
            const serviceIdNum = Number(serviceId || 0);
            if (!serviceIdNum) {
                showAlert('Neplatné ID servisu.', 'error');
                return;
            }
            const confirmDisconnect = confirm(
                'Opravdu chcete tento servis odpojit?\n\n' +
                'Servis ztratí přístup ke všem vašim vozidlům a bude odebrán z aktivních kontaktů.'
            );
            if (!confirmDisconnect) return;

            try {
                const response = await apiCall(`/api/v1/services/my-contacts/${serviceIdNum}`, 'DELETE');
                showAlert(response?.message || 'Servis byl odpojen.', 'success');
                await Promise.all([
                    loadManagedServiceContacts(true),
                    loadServicesDirectory(true)
                ]);
            } catch (error) {
                console.error("[SERVICE_CONTACTS] Odpojení servisu selhalo:");
                showAlert(`Nepodařilo se odpojit servis: ${error?.message || 'Neznámá chyba'}`, 'error');
            }
        }

        function openManagedServiceVehicleAccess(serviceId) {
            const serviceIdNum = Number(serviceId || 0);
            if (!serviceIdNum) {
                showAlert('Neplatné ID servisu.', 'error');
                return;
            }
            pendingServicesDirectoryFocusServiceId = serviceIdNum;
            switchTab('servicesDirectory');
            loadServicesDirectory(true);
        }

        function getPhoneHrefValue(rawValue) {
            const cleaned = String(rawValue || '').replace(/[^\d+]/g, '');
            return cleaned || '';
        }

        function renderManagedServiceContactsFooter(contacts) {
            const block = document.getElementById('managedServiceContactsBlock');
            const list = document.getElementById('managedServiceContactsList');
            if (!block || !list) return;

            const items = Array.isArray(contacts) ? contacts : [];
            const isUserContext = isAuthenticated() && getActiveWorkspaceMode() === 'user';
            if (!isUserContext || !items.length) {
                block.classList.add('hidden');
                list.innerHTML = '';
                return;
            }

            const cardsHtml = items.map((service) => {
                const name = escapeHtml(service?.name || service?.email || 'Servis');
                const emailRaw = String(service?.email || '').trim();
                const phoneRaw = String(service?.phone || '').trim();
                const emailHtml = emailRaw
                    ? `<a href="mailto:${escapeHtml(encodeURIComponent(emailRaw))}">${escapeHtml(emailRaw)}</a>`
                    : 'Není uveden';
                const phoneHref = getPhoneHrefValue(phoneRaw);
                const phoneHtml = phoneHref
                    ? `<a href="tel:${escapeHtml(phoneHref)}">${escapeHtml(phoneRaw)}</a>`
                    : (phoneRaw ? escapeHtml(phoneRaw) : 'Není uveden');
                const addressHtml = escapeHtml(service?.address || service?.city || 'Adresa není uvedena');
                const icoRaw = String(service?.ico || '').trim();
                const icoHtml = icoRaw ? escapeHtml(icoRaw) : 'Není uvedeno';

                return `
                    <article class="managed-service-contact-card">
                        <p class="managed-service-contact-name">${name}</p>
                        <p class="managed-service-contact-line"><strong>Email:</strong> ${emailHtml}</p>
                        <p class="managed-service-contact-line"><strong>Telefon:</strong> ${phoneHtml}</p>
                        <p class="managed-service-contact-line"><strong>Adresa:</strong> ${addressHtml}</p>
                        <p class="managed-service-contact-line"><strong>IČO:</strong> ${icoHtml}</p>
                        <div class="managed-service-contact-actions">
                            <button
                                type="button"
                                class="btn btn-secondary"
                                ${legacyActionAttributes("click", "openManagedServiceVehicleAccess_d8cf6829", Number(service?.id || 0))}
                            >
                                Evidence Vozidel
                            </button>
                            <button
                                type="button"
                                class="btn btn-danger managed-service-contact-disconnect-btn"
                                ${legacyActionAttributes("click", "disconnectManagedServiceContact_96e47cfb", Number(service?.id || 0))}
                            >
                                Odpojit servis
                            </button>
                        </div>
                    </article>
                `;
            }).join('');

            list.innerHTML = cardsHtml;
            block.classList.remove('hidden');
        }

        async function loadManagedServiceContacts(force = false) {
            if (!isAuthenticated() || getActiveWorkspaceMode() !== 'user') {
                renderManagedServiceContactsFooter([]);
                return;
            }

            const cacheAge = Date.now() - Number(managedServiceContactsState.loadedAt || 0);
            if (!force && managedServiceContactsState.items.length && cacheAge < 2 * 60 * 1000) {
                renderManagedServiceContactsFooter(managedServiceContactsState.items);
                return;
            }
            if (!force && managedServiceContactsState.loadingPromise) {
                return managedServiceContactsState.loadingPromise;
            }

            managedServiceContactsState.loadingPromise = (async () => {
                try {
                    const payload = await apiCall('/api/v1/services/my-contacts', 'GET');
                    const contacts = Array.isArray(payload?.services)
                        ? payload.services
                        : (Array.isArray(payload) ? payload : []);
                    managedServiceContactsState.items = contacts;
                    managedServiceContactsState.loadedAt = Date.now();
                    renderManagedServiceContactsFooter(contacts);
                } catch (error) {
                    console.warn("[SERVICE_CONTACTS] Nepodařilo se načíst kontakty servisů:");
                    managedServiceContactsState.items = [];
                    managedServiceContactsState.loadedAt = 0;
                    renderManagedServiceContactsFooter([]);
                } finally {
                    managedServiceContactsState.loadingPromise = null;
                }
            })();

            return managedServiceContactsState.loadingPromise;
        }

        // Zobrazení registrace
        function showRegister() {
            document.getElementById('loginForm').classList.add('hidden');
            document.getElementById('registerForm').classList.remove('hidden');
            setRegistrationMode(getSelectedLoginMode());
            // Vyčistit chyby při přepnutí
            clearFormError('loginErrorContainer');
            clearFormError('registerErrorContainer');
        }

        // Kontrola přihlášení při načtení stránky
        window.addEventListener('DOMContentLoaded', async () => {
            AdminBrowserSession.protect(clearLegacySessionData);
            API_URL = getApiBaseUrl();
            document.getElementById('configButton')?.classList.add('hidden');
            accessToken = AdminBrowserSession.token();
            if (!accessToken && window.CustomerWeb) { showLogin(); initLoginModeFromState(); initRememberedLoginPreferences(); return; }
            if (!accessToken) return;
            try {
                await AdminBrowserSession.verify();
                const profile = await apiCall('/user/me', 'GET');
                if (!window.CustomerWeb && !['admin', 'developer_admin'].includes(profile?.role)) throw new Error('Přístup je určen administrátorům.');
                currentUser = profile;
                if (window.CustomerWeb && await showCustomerEmailVerification()) return;
                markAuthSessionEstablished();
                capturePendingPaymentReturnFromUrl();
                setupActivityTracking();
                serverStatusCheckInterval = setInterval(checkServerStatus, 30000);
                void checkServerStatus();
                showDashboard();
            } catch {
                AdminBrowserSession.end('verification');
                return;
            }

            document.addEventListener('click', (event) => {
                const navbar = document.getElementById('mainNavbar');
                if (!navbar || !navbar.classList.contains('mobile-menu-open')) return;
                if (window.matchMedia && !window.matchMedia('(max-width: 768px)').matches) return;
                const eventPath = typeof event.composedPath === 'function' ? event.composedPath() : [];
                const clickedInsideNavbar = eventPath.includes(navbar) || navbar.contains(event.target);
                if (!clickedInsideNavbar) {
                    closeMobileNavbarMenu();
                }
            });

            document.addEventListener('click', (event) => {
                const externalSectionLink = event.target.closest('a.external-web-section-link');
                if (!externalSectionLink) return;
                if (confirmExternalWebSectionNavigation()) return;

                event.preventDefault();
                event.stopPropagation();
                showAlert('Přechod na web byl zrušen. Nejprve uložte nebo vyčistěte rozpracované vozidlo.', 'warning');
            });

            let resizeDebounceTimer = null;
            window.addEventListener('resize', () => {
                if (resizeDebounceTimer) {
                    clearTimeout(resizeDebounceTimer);
                }
                resizeDebounceTimer = setTimeout(() => {
                    if (!window.matchMedia || !window.matchMedia('(max-width: 768px)').matches) {
                        closeMobileNavbarMenu();
                    }
                }, 120);
            });

            if ('serviceWorker' in navigator) {
                navigator.serviceWorker.addEventListener('message', (event) => {
                    const payload = event && event.data ? event.data : null;
                    // Kanonický typ + legacy (starý service worker) – deprecated odstraní fáze 3
                    const _pushClickTypes = ['SPRAVA_VOZIDEL_NOTIFICATION_CLICK', 'TOOZHUB_NOTIFICATION_CLICK'];
                    if (!payload || !_pushClickTypes.includes(payload.type) || !payload.url) return;
                    try {
                        const parsed = new URL(payload.url, window.location.origin);
                        const tab = parsed.searchParams.get('tab');
                        if (tab && typeof switchTab === 'function' && isAuthenticated()) {
                            switchTab(tab);
                        }
                    } catch (error) {
                        // ignore malformed URL
                    }
                });
            }

            // Zastavit timer při zavření stránky
            window.addEventListener('beforeunload', (event) => {
                stopInactivityTimer();
                stopClientGeoRefresh();
                stopReminderNotificationHeartbeat();
                if (hasUnsavedAddVehicleDraft()) {
                    event.preventDefault();
                    event.returnValue = '';
                }
            });

            // Event listener pro Enter klávesu v login formuláři
            const loginEmailInput = document.getElementById('loginEmail');
            const loginPasswordInput = document.getElementById('loginPassword');
            const loginTwoFactorInput = document.getElementById('loginTwoFactorCode');
            const rememberLoginEmailCheckbox = document.getElementById('rememberLoginEmailCheckbox');
            const staySignedInCheckbox = document.getElementById('staySignedInCheckbox');

            if (loginEmailInput) {
                loginEmailInput.addEventListener('keypress', function(e) {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        if (typeof handleLogin === 'function') {
                            handleLogin();
                        }
                    }
                });
            }

            if (loginPasswordInput) {
                loginPasswordInput.addEventListener('keypress', function(e) {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        if (typeof handleLogin === 'function') {
                            handleLogin();
                        }
                    }
                });
            }

            if (loginTwoFactorInput) {
                loginTwoFactorInput.addEventListener('keypress', function(e) {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        if (typeof handleLoginTwoFactor === 'function') {
                            handleLoginTwoFactor();
                        }
                    }
                });
            }

            if (rememberLoginEmailCheckbox) {
                rememberLoginEmailCheckbox.addEventListener('change', updateRememberedLoginPreferences);
            }
            if (staySignedInCheckbox) {
                staySignedInCheckbox.addEventListener('change', updateRememberedLoginPreferences);
            }

            // Automatické načtení ARES při zadání 8 číslic IČO (s debounce)
            const icoInput = document.getElementById('regIco');
            if (icoInput) {
                icoInput.addEventListener('input', (e) => {
                    const rawValue = String(e.target.value || '');
                    const ico = rawValue.replace(/[^\d]/g, '').slice(0, 8);
                    if (rawValue !== ico) {
                        e.target.value = ico;
                    }

                    // Zrušit předchozí debounce
                    if (aresDebounceTimeout) {
                        clearTimeout(aresDebounceTimeout);
                        aresDebounceTimeout = null;
                    }

                    // Odstranit předchozí chybu
                    const existingError = icoInput.parentElement.querySelector('.ares-error');
                    if (existingError) {
                        existingError.remove();
                    }

                    // Spustit lookup pouze když je 8 číslic
                    if (ico.length === 8 && /^\d+$/.test(ico)) {
                        aresDebounceTimeout = setTimeout(() => {
                            loadAresData(ico);
                            aresDebounceTimeout = null;
                        }, 500);
                    }
                });
            }

            // Automatické dekódování VIN při zadání 17 znaků (s debounce)
            const vinInput = document.getElementById('vehicleVin');
            if (vinInput) {
                vinInput.addEventListener('input', (e) => {
                    const vin = e.target.value.trim().toUpperCase().replace(/[\s-]/g, '');
                    e.target.value = vin;

                    // Zrušit předchozí debounce
                    if (vinDebounceTimeout) {
                        clearTimeout(vinDebounceTimeout);
                        vinDebounceTimeout = null;
                    }

                    // Odstranit předchozí chybu
                    const existingError = vinInput.parentElement.querySelector('.vin-error');
                    if (existingError) {
                        existingError.remove();
                    }

                    // Spustit lookup pouze když je 17 znaků a validní VIN
                    if (vin.length === 17 && /^[A-HJ-NPR-Z0-9]{17}$/.test(vin)) {
                        vinDebounceTimeout = setTimeout(() => {
                            loadVinData(vin);
                            vinDebounceTimeout = null;
                        }, 500);
                    }
                });
            }
        });

        const REMINDER_NOTIFICATION_CHECK_INTERVAL_MS = 10 * 60 * 1000;

        async function triggerReminderNotificationCheck(force = false) {
            try {
                const now = Date.now();
                const lastRaw = (typeof SpravaVozidelStorage !== 'undefined'
                    ? SpravaVozidelStorage.getLocal('reminderNotificationCheckAt')
                    : localStorage.getItem('toozhub_reminder_notification_check_at'));
                const last = lastRaw ? Number.parseInt(lastRaw, 10) : 0;
                const shouldSkip = !force
                    && Number.isFinite(last)
                    && last > 0
                    && (now - last) < REMINDER_NOTIFICATION_CHECK_INTERVAL_MS;

                if (shouldSkip) {
                    return;
                }

                await apiCall('/api/v1/reminders/check-and-send-notifications', 'POST', {});
                if (typeof SpravaVozidelStorage !== 'undefined') {
                    SpravaVozidelStorage.setLocal('reminderNotificationCheckAt', String(now));
                } else {
                    localStorage.setItem('sprava_vozidel_reminder_notification_check_at', String(now));
                    localStorage.removeItem('toozhub_reminder_notification_check_at');
                }
            } catch (error) {
                console.warn("[REMINDERS] Notification check skipped:");
            }
        }

        function startReminderNotificationHeartbeat() {
            const role = String(currentUser?.role || '').toLowerCase();
            if (role && role !== 'user') return;
            if (reminderNotificationHeartbeatTimer) return;
            triggerReminderNotificationCheck();
            reminderNotificationHeartbeatTimer = setInterval(() => {
                if (!isAuthenticated()) return;
                const activeRole = String(currentUser?.role || '').toLowerCase();
                if (activeRole && activeRole !== 'user') return;
                triggerReminderNotificationCheck();
            }, 5 * 60 * 1000);
        }

        function stopReminderNotificationHeartbeat() {
            if (!reminderNotificationHeartbeatTimer) return;
            clearInterval(reminderNotificationHeartbeatTimer);
            reminderNotificationHeartbeatTimer = null;
        }

        function buildReminderFilterBarHtml(counts, selectedFilter) {
            const items = [
                { key: 'active', label: 'Aktivní', count: counts.active },
                { key: 'expired', label: 'Propadlé', count: counts.expired },
                { key: 'completed', label: 'Dokončené', count: counts.completed },
                { key: 'all', label: 'Vše', count: counts.all },
            ];
            return `
                <div class="reminder-filter-bar" role="group" aria-label="Filtr připomínek">
                    ${items.map((item) => `
                        <button
                            type="button"
                            class="reminder-filter-btn ${selectedFilter === item.key ? 'active' : ''}"
                            ${legacyActionAttributes("click", "setReminderFilter_8a7c9d6c", item.key)}
                            aria-pressed="${selectedFilter === item.key ? 'true' : 'false'}"
                        >
                            ${escapeHtml(item.label)} <span>${escapeHtml(item.count)}</span>
                        </button>
                    `).join('')}
                </div>
            `;
        }

        function getReminderPrimaryDateLabel(reminder) {
            if (reminder?.notify_at) {
                return {
                    label: 'Notifikace',
                    value: formatReminderDateShort(reminder.notify_at, true),
                };
            }
            if (reminder?.due_date) {
                return {
                    label: 'Termín',
                    value: formatReminderDateShort(reminder.due_date, false),
                };
            }
            return {
                label: 'Termín',
                value: 'Není nastaven',
            };
        }

        function buildReminderCardMinimalHtml(reminder, index) {
            const typeMeta = getReminderTypePresentation(reminder?.type);
            const statusMeta = getReminderStatusMeta(reminder);
            const primaryDate = getReminderPrimaryDateLabel(reminder);
            const modeBadge = reminder?.is_manual === true
                ? '<span class="badge reminder-status-badge reminder-status-badge-manual">VÝJIMKA</span>'
                : '<span class="badge reminder-status-badge reminder-status-badge-auto">CENTRÁLNÍ</span>';
            const statusLabel = reminderDaysMetaLabel(statusMeta.daysTo);
            const statusChip = `<span class="reminder-status-chip ${escapeHtml(statusMeta.className)}">${escapeHtml(statusMeta.label)}</span>`;

            return `
                <article
                    class="card reminder-card reminder-card-minimal"
                    style="border-left: 4px solid ${escapeHtml(typeMeta.color)};"
                    ${legacyActionAttributes("click", "openReminderDetailModalByIndex_76ed8689", index)}
                    role="button"
                    tabindex="0"
                    ${legacyActionAttributes("keydown", "preventDefault_f85ab9e5", index)}
                >
                    <div class="card-header">
                        <div style="display:flex; align-items:center; gap:8px; min-width:0;">
                            ${typeMeta.icon}
                            <h3 class="card-title" style="color:${escapeHtml(typeMeta.color)}; font-size:15px; margin:0;">${escapeHtml(typeMeta.label)}</h3>
                        </div>
                        <div class="reminder-card-controls">
                            ${modeBadge}
                            ${statusChip}
                        </div>
                    </div>
                    <div class="card-body reminder-card-minimal-body">
                        <div class="card-field reminder-field-vehicle">
                            <span class="card-label">Vozidlo</span>
                            <span class="card-value">${escapeHtml(reminder?.vehicle_name || 'Obecná připomínka')}</span>
                        </div>
                        <div class="card-field reminder-field-due-date">
                            <span class="card-label">${escapeHtml(primaryDate.label)}</span>
                            <span class="card-value">${escapeHtml(primaryDate.value)}</span>
                        </div>
                        <div class="card-field reminder-field-text">
                            <span class="card-label">Popis</span>
                            <span class="card-value">${escapeHtml(reminder?.text || '-')}</span>
                        </div>
                    </div>
                    <div class="card-actions reminder-card-minimal-actions">
                        <span class="reminder-card-mini-meta">${escapeHtml(statusLabel || '')}</span>
                        <button type="button" class="btn btn-secondary reminder-card-detail-btn" ${legacyActionAttributes("click", "stopPropagation_f6bcd6dc", index)}>Detail</button>
                    </div>
                </article>
            `;
        }

        function reminderDateKeyFromDate(dateObj) {
            if (!(dateObj instanceof Date) || Number.isNaN(dateObj.getTime())) return '';
            const y = dateObj.getFullYear();
            const m = String(dateObj.getMonth() + 1).padStart(2, '0');
            const d = String(dateObj.getDate()).padStart(2, '0');
            return `${y}-${m}-${d}`;
        }

        function buildReminderCalendarHtml(reminders) {
            const monthDate = getReminderCalendarMonthDate();
            persistReminderCalendarMonth(monthDate);
            const today = new Date();
            today.setHours(0, 0, 0, 0);

            const monthLabel = monthDate.toLocaleDateString('cs-CZ', { month: 'long', year: 'numeric' });
            const year = monthDate.getFullYear();
            const month = monthDate.getMonth();
            const daysInMonth = new Date(year, month + 1, 0).getDate();
            const firstWeekDayMonday = (new Date(year, month, 1).getDay() + 6) % 7;
            const eventsByDay = new Map();

            reminders.forEach((reminder, idx) => {
                const ref = getReminderReferenceDate(reminder);
                if (!ref) return;
                if (ref.getFullYear() !== year || ref.getMonth() !== month) return;
                const day = ref.getDate();
                const bucket = eventsByDay.get(day) || [];
                bucket.push({ reminder, index: idx });
                eventsByDay.set(day, bucket);
            });

            const weekDays = ['Po', 'Út', 'St', 'Čt', 'Pá', 'So', 'Ne'];
            let cellsHtml = '';

            for (let i = 0; i < firstWeekDayMonday; i += 1) {
                cellsHtml += '<div class="reminder-calendar-cell is-empty"></div>';
            }

            for (let day = 1; day <= daysInMonth; day += 1) {
                const dayDate = new Date(year, month, day);
                const dayKey = reminderDateKeyFromDate(dayDate);
                const isToday = dayDate.getTime() === today.getTime();
                const dayEvents = eventsByDay.get(day) || [];

                const eventsHtml = dayEvents.slice(0, 3).map((item) => {
                    const typeMeta = getReminderTypePresentation(item.reminder?.type);
                    const statusMeta = getReminderStatusMeta(item.reminder);
                    return `
                        <button
                            type="button"
                            class="reminder-calendar-event ${escapeHtml(statusMeta.className)}"
                            title="${escapeHtml(item.reminder?.text || '')}"
                            ${legacyActionAttributes("click", "openReminderDetailModalByIndex_76ed8689", item.index)}
                        >
                            ${escapeHtml(typeMeta.label)} · ${escapeHtml(item.reminder?.vehicle_name || 'Obecná')}
                        </button>
                    `;
                }).join('');

                const moreCount = dayEvents.length > 3
                    ? `<span class="reminder-calendar-more">+${dayEvents.length - 3} další</span>`
                    : '';

                cellsHtml += `
                    <div class="reminder-calendar-cell ${isToday ? 'is-today' : ''}" data-day="${escapeHtml(dayKey)}">
                        <div class="reminder-calendar-day-head">
                            <span class="reminder-calendar-day-num">${day}</span>
                        </div>
                        <div class="reminder-calendar-events">
                            ${eventsHtml || '<span class="reminder-calendar-empty-day">—</span>'}
                            ${moreCount}
                        </div>
                    </div>
                `;
            }

            return `
                <div class="reminder-calendar-shell">
                    <div class="reminder-calendar-toolbar">
                        <button type="button" class="btn btn-secondary reminder-calendar-nav-btn" ${legacyActionAttributes("click", "shiftReminderCalendarMonth_1001e74b")}>◀</button>
                        <strong>${escapeHtml(monthLabel)}</strong>
                        <button type="button" class="btn btn-secondary reminder-calendar-nav-btn" ${legacyActionAttributes("click", "shiftReminderCalendarMonth_98aac5ae")}>▶</button>
                    </div>
                    <div class="reminder-calendar-weekdays">
                        ${weekDays.map((label) => `<span>${escapeHtml(label)}</span>`).join('')}
                    </div>
                    <div class="reminder-calendar-grid">
                        ${cellsHtml}
                    </div>
                </div>
            `;
        }

        function closeReminderDetailModal() {
            unmountFloatingModal();
        }

        function getReminderByIndex(index) {
            const idx = Number(index);
            if (!Number.isFinite(idx) || idx < 0) return null;
            return remindersUiState.filteredItems[idx] || null;
        }

        async function openReminderScheduleFromDetail(index) {
            const reminder = getReminderByIndex(index);
            if (!reminder || !reminder.id || reminder.is_manual !== true) return;
            closeReminderDetailModal();
            await showReminderScheduleForm(reminder.id);
        }

        async function openReminderEditFromDetail(index) {
            const reminder = getReminderByIndex(index);
            if (!reminder || !reminder.id) return;
            closeReminderDetailModal();
            await editReminder(reminder.id);
        }

        async function deleteReminderFromDetail(index) {
            const reminder = getReminderByIndex(index);
            if (!reminder || !reminder.id) return;
            closeReminderDetailModal();
            await deleteReminder(reminder.id);
        }

        function openReminderVehicleFromDetail(index) {
            const reminder = getReminderByIndex(index);
            if (!reminder || !reminder.vehicle_id) return;
            closeReminderDetailModal();
            openVehicleFromShortcut(reminder.vehicle_id, 'reminder-detail');
        }

        function openReminderDetailModalByIndex(index) {
            const reminder = getReminderByIndex(index);
            if (!reminder) {
                showAlert('Detail připomínky není dostupný.', 'error');
                return;
            }

            const typeMeta = getReminderTypePresentation(reminder.type);
            const statusMeta = getReminderStatusMeta(reminder);
            const primaryDate = getReminderPrimaryDateLabel(reminder);
            const notifyAtValue = reminder.notify_at ? formatReminderDateShort(reminder.notify_at, true) : 'Není nastaveno';
            const dueDateValue = reminder.due_date ? formatReminderDateShort(reminder.due_date, false) : 'Není nastaven';
            const methodValue = getReminderMethodText(reminder);
            const modeValue = reminder.is_manual === true ? 'Výjimka (vlastní)' : 'Centrální pravidlo';

            const actionButtons = reminder.is_manual === true && reminder.id
                ? `
                    <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "openReminderScheduleFromDetail_00360b1a", index)}>Nastavit upozornění</button>
                    <button type="button" class="btn btn-primary" ${legacyActionAttributes("click", "openReminderEditFromDetail_43a18932", index)}>Upravit</button>
                    <button type="button" class="btn btn-danger" ${legacyActionAttributes("click", "deleteReminderFromDetail_ca5065e7", index)}>Smazat</button>
                `
                : '';

            const vehicleAction = reminder.vehicle_id
                ? `<button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "openReminderVehicleFromDetail_509daa1f", index)}>Otevřít vozidlo</button>`
                : '';

            const modalHtml = `
                <div class="reminder-modal-overlay" ${legacyActionAttributes("click", "closeReminderDetailModal_adb51a2a")}>
                    <div class="reminder-modal reminder-detail-modal">
                        <div class="reminder-modal-head">
                            <div class="reminder-modal-heading">
                                <span class="reminder-modal-icon" aria-hidden="true">${typeMeta.icon}</span>
                                <div>
                                    <p class="reminder-modal-kicker">Připomínky</p>
                                    <h2 class="modal-title">${escapeHtml(typeMeta.label)} - detail</h2>
                                </div>
                            </div>
                            <button type="button" class="reminder-modal-close" aria-label="Zavřít okno" ${legacyActionAttributes("click", "closeReminderDetailModal_55e91aa3")}>×</button>
                        </div>
                        <div class="reminder-detail-grid">
                            <div class="card-field"><span class="card-label">Stav</span><span class="card-value"><span class="reminder-status-chip ${escapeHtml(statusMeta.className)}">${escapeHtml(statusMeta.label)}</span></span></div>
                            <div class="card-field"><span class="card-label">Režim</span><span class="card-value">${escapeHtml(modeValue)}</span></div>
                            <div class="card-field"><span class="card-label">Vozidlo</span><span class="card-value">${escapeHtml(reminder.vehicle_name || 'Obecná připomínka')}</span></div>
                            <div class="card-field"><span class="card-label">${escapeHtml(primaryDate.label)}</span><span class="card-value">${escapeHtml(primaryDate.value)}</span></div>
                            <div class="card-field"><span class="card-label">Datum termínu</span><span class="card-value">${escapeHtml(dueDateValue)}</span></div>
                            <div class="card-field"><span class="card-label">Přesná notifikace</span><span class="card-value">${escapeHtml(notifyAtValue)}</span></div>
                            <div class="card-field"><span class="card-label">Kanál upozornění</span><span class="card-value">${escapeHtml(methodValue)}</span></div>
                            <div class="card-field"><span class="card-label">Popis</span><span class="card-value">${escapeHtml(reminder.text || '')}</span></div>
                        </div>
                        <div class="form-actions reminder-detail-actions">
                            ${vehicleAction}
                            ${actionButtons}
                            <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "closeReminderDetailModal_55e91aa3")}>Zavřít</button>
                        </div>
                    </div>
                </div>
            `;

            mountFloatingModal(modalHtml);
        }

        function getServiceReminderStatusKey(reminder) {
            if (reminder?.is_completed) return 'COMPLETED';
            const dueDateRaw = String(reminder?.due_date || '').trim();
            if (!dueDateRaw) return 'ACTIVE';
            const dueDate = new Date(dueDateRaw);
            if (Number.isNaN(dueDate.getTime())) return 'ACTIVE';
            dueDate.setHours(0, 0, 0, 0);
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            return dueDate < today ? 'OVERDUE' : 'ACTIVE';
        }

        function getServiceReminderTypeLabel(typeRaw) {
            const key = String(typeRaw || '').trim().toUpperCase();
            const map = {
                STK: 'STK',
                OLEJ: 'Výměna oleje',
                SERVIS: 'Servisní interval',
                PNEU: 'Pneumatiky',
                PNEUMATIKY: 'Pneumatiky',
                VLASTNI: 'Vlastní',
                CUSTOM: 'Vlastní',
            };
            return map[key] || key || 'Připomínka';
        }

        function formatReminderDateTimeCompact(value) {
            if (!value) return '-';
            const parsed = new Date(value);
            if (Number.isNaN(parsed.getTime())) return '-';
            return parsed.toLocaleString('cs-CZ', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        }

        function getServiceReminderFilteredItems() {
            const statusFilter = String(serviceWorkspaceRemindersState.statusFilter || 'ACTIVE').toUpperCase();
            const customerFilter = String(serviceWorkspaceRemindersState.customerFilter || 'ALL');
            const query = String(serviceWorkspaceRemindersState.query || '').trim().toLowerCase();
            return (Array.isArray(serviceWorkspaceRemindersState.items) ? serviceWorkspaceRemindersState.items : [])
                .filter((item) => {
                    const statusKey = getServiceReminderStatusKey(item);
                    if (statusFilter !== 'ALL' && statusKey !== statusFilter) {
                        return false;
                    }
                    if (customerFilter !== 'ALL' && String(item?.customer_id || '') !== customerFilter) {
                        return false;
                    }
                    if (!query) return true;
                    const haystack = [
                        item?.type,
                        item?.text,
                        item?.customer_name,
                        item?.customer_email,
                        item?.vehicle_label,
                    ].filter(Boolean).join(' ').toLowerCase();
                    return haystack.includes(query);
                })
                .sort((a, b) => {
                    const aStatus = getServiceReminderStatusKey(a);
                    const bStatus = getServiceReminderStatusKey(b);
                    const rank = { OVERDUE: 0, ACTIVE: 1, COMPLETED: 2 };
                    if (rank[aStatus] !== rank[bStatus]) {
                        return (rank[aStatus] ?? 99) - (rank[bStatus] ?? 99);
                    }
                    const aDate = new Date(a?.due_date || a?.created_at || 0).getTime();
                    const bDate = new Date(b?.due_date || b?.created_at || 0).getTime();
                    return aDate - bDate;
                });
        }

        function renderServiceWorkspaceReminders() {
            const container = document.getElementById('remindersContainer');
            if (!container) return;

            const reminders = Array.isArray(serviceWorkspaceRemindersState.items) ? serviceWorkspaceRemindersState.items : [];
            const filtered = getServiceReminderFilteredItems();
            const statusCounts = {
                ALL: reminders.length,
                ACTIVE: reminders.filter((item) => getServiceReminderStatusKey(item) === 'ACTIVE').length,
                OVERDUE: reminders.filter((item) => getServiceReminderStatusKey(item) === 'OVERDUE').length,
                COMPLETED: reminders.filter((item) => getServiceReminderStatusKey(item) === 'COMPLETED').length,
            };
            const customers = Array.isArray(serviceWorkspaceState.customers) ? serviceWorkspaceState.customers : [];
            const customerOptions = ['<option value="ALL">Všichni klienti</option>'].concat(
                customers.map((customer) => {
                    const customerId = Number(customer?.customer_id || 0);
                    const selected = String(serviceWorkspaceRemindersState.customerFilter || 'ALL') === String(customerId) ? 'selected' : '';
                    const label = `${customer?.name || customer?.email || `Klient #${customerId}`} (${customer?.email || '-'})`;
                    return `<option value="${customerId}" ${selected}>${escapeHtml(label)}</option>`;
                })
            ).join('');

            const statusBtn = (key, label) => `
                <button
                    type="button"
                    class="reservation-filter-chip ${String(serviceWorkspaceRemindersState.statusFilter || 'ACTIVE') === key ? 'active' : ''}"
                    ${legacyActionAttributes("click", "setServiceReminderStatusFilter_37619866", key)}
                >
                    <span>${escapeHtml(label)}</span>
                    <strong>${escapeHtml(statusCounts[key] || 0)}</strong>
                </button>
            `;

            const cardsHtml = filtered.length
                ? filtered.map((item) => {
                    const reminderId = Number(item?.id || 0);
                    const statusKey = getServiceReminderStatusKey(item);
                    const statusMeta = statusKey === 'OVERDUE'
                        ? { label: 'Po termínu', className: 'expired' }
                        : statusKey === 'COMPLETED'
                            ? { label: 'Dokončeno', className: 'completed' }
                            : { label: 'Aktivní', className: 'active' };
                    const dueDateLabel = item?.due_date ? formatReminderDateTimeCompact(item.due_date) : '-';
                    const notifyLabel = item?.notify_at ? formatReminderDateTimeCompact(item.notify_at) : '-';
                    return `
                        <article class="reminder-card ${escapeHtml(statusMeta.className)}">
                            <div class="card-header">
                                <h3 class="card-title">${escapeHtml(getServiceReminderTypeLabel(item?.type))}</h3>
                                <span class="reminder-status ${escapeHtml(statusMeta.className)}">${escapeHtml(statusMeta.label)}</span>
                            </div>
                            <div class="card-body">
                                <p class="card-field"><span class="card-label">Klient</span><span class="card-value">${escapeHtml(item?.customer_name || item?.customer_email || '-')}</span></p>
                                <p class="card-field"><span class="card-label">Vozidlo</span><span class="card-value">${escapeHtml(item?.vehicle_label || 'Obecná připomínka')}</span></p>
                                <p class="card-field"><span class="card-label">Text</span><span class="card-value">${escapeHtml(item?.text || '-')}</span></p>
                                <p class="card-field"><span class="card-label">Termín</span><span class="card-value">${escapeHtml(dueDateLabel)}</span></p>
                                <p class="card-field"><span class="card-label">Notifikace</span><span class="card-value">${escapeHtml(notifyLabel)}</span></p>
                            </div>
                            <div class="card-actions">
                                ${item?.vehicle_id ? `<button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "openVehicleFromShortcut_81e96af9", Number(item.vehicle_id))}>Otevřít vozidlo</button>` : ''}
                                <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "openEditServiceReminder_5927b4f9", reminderId)}>Upravit</button>
                                <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "toggleServiceReminderCompletion_3c831bda", reminderId, (item?.is_completed ? 'false' : 'true') === 'true')}>
                                    ${item?.is_completed ? 'Znovu aktivovat' : 'Dokončit'}
                                </button>
                                <button type="button" class="btn btn-danger" ${legacyActionAttributes("click", "deleteServiceWorkspaceReminder_a615a2ea", reminderId)}>Smazat</button>
                            </div>
                        </article>
                    `;
                }).join('')
                : '<div class="reminder-empty">Nejsou dostupné žádné připomínky pro vybrané filtry.</div>';

            container.classList.remove('loading');
            container.classList.add('reminders-section');
            container.innerHTML = `
                <div class="reminders-section">
                    <div class="reminder-panel reminder-master">
                        <section class="reservation-dashboard" aria-label="Filtry připomínek servisu">
                            <div class="reservation-dashboard-head">
                                <div>
                                    <h3>Připomínky klientů</h3>
                                    <p>Servis vytváří a spravuje připomínky, které se synchronizují i do klientského účtu.</p>
                                </div>
                            </div>
                            <div class="reservation-filter-chips">
                                ${statusBtn('ALL', 'Vše')}
                                ${statusBtn('ACTIVE', 'Aktivní')}
                                ${statusBtn('OVERDUE', 'Po termínu')}
                                ${statusBtn('COMPLETED', 'Dokončené')}
                            </div>
                            <div class="reservation-filter-controls">
                                <input
                                    type="search"
                                    class="reservation-search-input"
                                    placeholder="Hledat připomínku podle klienta, vozidla nebo textu..."
                                    value="${escapeHtml(serviceWorkspaceRemindersState.query || '')}"
                                    ${legacyActionAttributes("input", "setServiceReminderQuery_3c67ecc8")}
                                >
                                <select class="reservation-sort-select reservation-customer-select" ${legacyActionAttributes("change", "setServiceReminderCustomerFilter_3bcd171d")}>
                                    ${customerOptions}
                                </select>
                                <button type="button" class="btn btn-primary" ${legacyActionAttributes("click", "openServiceReminderComposer_89ec70ca")}>+ Nová připomínka</button>
                            </div>
                        </section>
                        <div class="cards-grid reminders-grid reminder-view reminder-view-grid">
                            ${cardsHtml}
                        </div>
                    </div>
                </div>
            `;
        }

        async function loadServiceWorkspaceReminders(force = false) {
            const container = document.getElementById('remindersContainer');
            if (!container) return;

            if (!isServiceWorkspaceRole()) {
                return;
            }

            const cacheAge = Date.now() - Number(serviceWorkspaceRemindersState.loadedAt || 0);
            if (!force && Array.isArray(serviceWorkspaceRemindersState.items) && serviceWorkspaceRemindersState.items.length && cacheAge < 60 * 1000) {
                renderServiceWorkspaceReminders();
                return;
            }

            container.classList.remove('loading');
            container.innerHTML = '<div class="loading">Načítám servisní připomínky...</div>';

            try {
                if (!Array.isArray(serviceWorkspaceState.customers) || !serviceWorkspaceState.customers.length) {
                    const customers = await apiCall('/api/v1/services/workspace/customers', 'GET');
                    serviceWorkspaceState.customers = Array.isArray(customers) ? customers : [];
                }
                const reminders = await apiCall('/api/v1/services/workspace/reminders?include_completed=true&limit=500', 'GET');
                serviceWorkspaceRemindersState.items = Array.isArray(reminders) ? reminders : [];
                serviceWorkspaceRemindersState.loadedAt = Date.now();
                renderServiceWorkspaceReminders();
            } catch (error) {
                console.error("[SERVICE_REMINDERS] Error loading:");
                container.innerHTML = `
                    <div class="alert alert-error">
                        Nepodařilo se načíst servisní připomínky: ${escapeHtml(error?.message || 'Neznámá chyba')}
                        <br><br>
                        <button class="btn btn-primary" ${legacyActionAttributes("click", "loadServiceWorkspaceReminders_04c8f9af")}>Zkusit znovu</button>
                    </div>
                `;
            }
        }

        function setServiceReminderStatusFilter(status) {
            serviceWorkspaceRemindersState.statusFilter = String(status || 'ACTIVE').toUpperCase();
            renderServiceWorkspaceReminders();
        }

        function setServiceReminderCustomerFilter(customerId) {
            serviceWorkspaceRemindersState.customerFilter = String(customerId || 'ALL');
            renderServiceWorkspaceReminders();
        }

        function setServiceReminderQuery(query) {
            serviceWorkspaceRemindersState.query = String(query || '').trim().toLowerCase();
            renderServiceWorkspaceReminders();
        }

        function updateServiceReminderVehicleSelect(preferredVehicleId = null) {
            const customerSelect = document.getElementById('serviceReminderCustomer');
            const vehicleSelect = document.getElementById('serviceReminderVehicle');
            if (!customerSelect || !vehicleSelect) return;
            const catalog = Array.isArray(serviceWorkspaceRemindersState.catalog) ? serviceWorkspaceRemindersState.catalog : [];
            const customerId = Number(customerSelect.value || 0);
            const customerEntry = catalog.find((item) => Number(item?.customer_id || 0) === customerId);
            const vehicles = Array.isArray(customerEntry?.vehicles) ? customerEntry.vehicles : [];
            const targetVehicleId = Number(preferredVehicleId || 0);

            if (!vehicles.length) {
                vehicleSelect.innerHTML = '<option value="">Bez vozidla</option>';
                return;
            }
            vehicleSelect.innerHTML = ['<option value="">Obecná připomínka</option>'].concat(
                vehicles.map((vehicle) => {
                    const vehicleId = Number(vehicle?.id || 0);
                    const selected = targetVehicleId > 0 && vehicleId === targetVehicleId ? 'selected' : '';
                    const label = `${vehicle?.nickname || vehicle?.plate || `Vozidlo #${vehicleId}`}${vehicle?.plate ? ` - ${vehicle.plate}` : ''}`;
                    return `<option value="${vehicleId}" ${selected}>${escapeHtml(label)}</option>`;
                })
            ).join('');

            if (!vehicleSelect.value && targetVehicleId > 0) {
                vehicleSelect.value = String(targetVehicleId);
            }
        }

        function handleServiceReminderCustomerChange() {
            updateServiceReminderVehicleSelect();
        }

        async function openServiceReminderComposer(customerId = null, vehicleId = null) {
            if (!isServiceWorkspaceRole()) {
                return showCreateReminderForm();
            }
            const catalog = await loadServiceReservationCatalog(false);
            serviceWorkspaceRemindersState.catalog = catalog;
            const customerBuckets = catalog.filter((item) => Number(item?.customer_id || 0) > 0);
            if (!customerBuckets.length) {
                showAlert('Nejdříve propojte klienta se servisním účtem.', 'warning');
                switchTab('serviceWorkspace');
                return;
            }

            let selectedCustomerId = Number(customerId || serviceWorkspaceState.selectedCustomerId || customerBuckets[0]?.customer_id || 0);
            if (!customerBuckets.some((item) => Number(item.customer_id) === selectedCustomerId)) {
                selectedCustomerId = Number(customerBuckets[0]?.customer_id || 0);
            }

            const selectedCustomer = customerBuckets.find((item) => Number(item.customer_id) === selectedCustomerId) || customerBuckets[0];
            let selectedVehicleId = Number(vehicleId || 0);
            if (selectedVehicleId > 0 && !selectedCustomer.vehicles.some((v) => Number(v?.id || 0) === selectedVehicleId)) {
                selectedVehicleId = 0;
            }

            const customerOptions = customerBuckets.map((customer) => {
                const id = Number(customer?.customer_id || 0);
                const selected = id === selectedCustomerId ? 'selected' : '';
                const label = `${customer?.customer_name || customer?.customer_email || `Klient #${id}`} (${customer?.customer_email || '-'})`;
                return `<option value="${id}" ${selected}>${escapeHtml(label)}</option>`;
            }).join('');

            const now = new Date(Date.now() + 30 * 60 * 1000);
            now.setSeconds(0, 0);
            const notifyDefault = `${now.getFullYear()}-${padReservationDatePart(now.getMonth() + 1)}-${padReservationDatePart(now.getDate())}T${padReservationDatePart(now.getHours())}:${padReservationDatePart(now.getMinutes())}`;

            mountFloatingModal(`
                <div class="reminder-modal-overlay" ${legacyActionAttributes("click", "loadServiceWorkspaceReminders_457d84b2")}>
                    <div class="reminder-modal service-account-modal service-reminder-modal">
                        <form class="reminder-create service-account-form" ${legacyActionAttributes("submit", "handleCreateServiceReminder_a7b72be2")}>
                            <div class="reminder-modal-head">
                                <div class="reminder-modal-heading">
                                    <div>
                                        <p class="reminder-modal-kicker">Servisní připomínka</p>
                                        <h2 class="modal-title">Nová připomínka klienta</h2>
                                    </div>
                                </div>
                                <button type="button" class="reminder-modal-close" aria-label="Zavřít okno" ${legacyActionAttributes("click", "loadServiceWorkspaceReminders_04c8f9af")}>×</button>
                            </div>
                            <div class="form-grid">
                                <div class="form-row">
                                    <label for="serviceReminderCustomer">Klient *:</label>
                                    <select id="serviceReminderCustomer" required ${legacyActionAttributes("change", "handleServiceReminderCustomerChange_a5d5063a")}>
                                        ${customerOptions}
                                    </select>
                                </div>
                                <div class="form-row">
                                    <label for="serviceReminderVehicle">Vozidlo:</label>
                                    <select id="serviceReminderVehicle"></select>
                                </div>
                                <div class="form-row">
                                    <label for="serviceReminderType">Typ *:</label>
                                    <select id="serviceReminderType" required>
                                        <option value="STK">STK</option>
                                        <option value="OLEJ">Výměna oleje</option>
                                        <option value="SERVIS">Servisní interval</option>
                                        <option value="PNEU">Pneumatiky</option>
                                        <option value="VLASTNI">Vlastní</option>
                                    </select>
                                </div>
                                <div class="form-row">
                                    <label for="serviceReminderMethod">Notifikace:</label>
                                    <select id="serviceReminderMethod">
                                        <option value="app">Aplikace</option>
                                        <option value="email">E-mail</option>
                                        <option value="both">Aplikace + e-mail</option>
                                    </select>
                                </div>
                                <div class="form-row span-2">
                                    <label for="serviceReminderText">Text *:</label>
                                    <textarea id="serviceReminderText" rows="3" required placeholder="Co má být klientovi připomenuto"></textarea>
                                </div>
                                <div class="form-row">
                                    <label for="serviceReminderDueDate">Datum termínu:</label>
                                    <input type="date" id="serviceReminderDueDate">
                                </div>
                                <div class="form-row">
                                    <label for="serviceReminderNotifyAt">Přesná notifikace:</label>
                                    <input type="datetime-local" id="serviceReminderNotifyAt" value="${escapeHtml(notifyDefault)}">
                                </div>
                            </div>
                            <div class="form-actions">
                                <button type="submit" class="btn btn-primary">Vytvořit připomínku</button>
                                <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "loadServiceWorkspaceReminders_04c8f9af")}>Zrušit</button>
                            </div>
                        </form>
                    </div>
                </div>
            `);
            updateServiceReminderVehicleSelect(selectedVehicleId);
        }

        async function handleCreateServiceReminder() {
            const customerId = Number(document.getElementById('serviceReminderCustomer')?.value || 0);
            const vehicleId = Number(document.getElementById('serviceReminderVehicle')?.value || 0);
            const type = String(document.getElementById('serviceReminderType')?.value || '').trim();
            const text = String(document.getElementById('serviceReminderText')?.value || '').trim();
            const dueDate = String(document.getElementById('serviceReminderDueDate')?.value || '').trim();
            const notifyAt = String(document.getElementById('serviceReminderNotifyAt')?.value || '').trim();
            const method = String(document.getElementById('serviceReminderMethod')?.value || '').trim();

            if (!customerId) {
                showAlert('Vyberte klienta.', 'error');
                return;
            }
            if (!type) {
                showAlert('Vyberte typ připomínky.', 'error');
                return;
            }
            if (!text || text.length < 3) {
                showAlert('Text připomínky musí mít alespoň 3 znaky.', 'error');
                return;
            }

            let notifyAtIso = null;
            if (notifyAt) {
                const parsed = new Date(notifyAt);
                if (Number.isNaN(parsed.getTime())) {
                    showAlert('Neplatný formát data a času notifikace.', 'error');
                    return;
                }
                notifyAtIso = parsed.toISOString();
            }

            try {
                await apiCall('/api/v1/services/workspace/reminders', 'POST', {
                    customer_id: customerId,
                    vehicle_id: vehicleId > 0 ? vehicleId : null,
                    type,
                    text,
                    due_date: dueDate || null,
                    notify_at: notifyAtIso,
                    notification_method: method || null
                });
                showAlert('Připomínka byla vytvořena.', 'success');
                await loadServiceWorkspaceReminders(true);
            } catch (error) {
                console.error("[SERVICE_REMINDERS] Create error:");
                showAlert('Nepodařilo se vytvořit připomínku: ' + (error?.message || 'Neznámá chyba'), 'error');
            }
        }

        async function openEditServiceReminder(reminderId) {
            const reminder = (Array.isArray(serviceWorkspaceRemindersState.items) ? serviceWorkspaceRemindersState.items : [])
                .find((item) => Number(item?.id || 0) === Number(reminderId || 0));
            if (!reminder) {
                showAlert('Připomínka nebyla nalezena. Obnovte seznam.', 'warning');
                return;
            }

            const catalog = await loadServiceReservationCatalog(false);
            serviceWorkspaceRemindersState.catalog = catalog;
            const customerOptions = catalog.map((customer) => {
                const id = Number(customer?.customer_id || 0);
                const selected = id === Number(reminder?.customer_id || 0) ? 'selected' : '';
                const label = `${customer?.customer_name || customer?.customer_email || `Klient #${id}`} (${customer?.customer_email || '-'})`;
                return `<option value="${id}" ${selected}>${escapeHtml(label)}</option>`;
            }).join('');

            let notifyValue = '';
            if (reminder?.notify_at) {
                const parsed = new Date(reminder.notify_at);
                if (!Number.isNaN(parsed.getTime())) {
                    notifyValue = `${parsed.getFullYear()}-${padReservationDatePart(parsed.getMonth() + 1)}-${padReservationDatePart(parsed.getDate())}T${padReservationDatePart(parsed.getHours())}:${padReservationDatePart(parsed.getMinutes())}`;
                }
            }

            mountFloatingModal(`
                <div class="reminder-modal-overlay" ${legacyActionAttributes("click", "loadServiceWorkspaceReminders_457d84b2")}>
                    <div class="reminder-modal service-account-modal service-reminder-modal">
                        <form class="reminder-create service-account-form" ${legacyActionAttributes("submit", "handleUpdateServiceReminder_31b8d644", Number(reminder.id))}>
                            <div class="reminder-modal-head">
                                <div class="reminder-modal-heading">
                                    <div>
                                        <p class="reminder-modal-kicker">Servisní připomínka</p>
                                        <h2 class="modal-title">Upravit připomínku #${Number(reminder.id)}</h2>
                                    </div>
                                </div>
                                <button type="button" class="reminder-modal-close" aria-label="Zavřít okno" ${legacyActionAttributes("click", "loadServiceWorkspaceReminders_04c8f9af")}>×</button>
                            </div>
                            <div class="form-grid">
                                <div class="form-row">
                                    <label for="serviceReminderCustomer">Klient *:</label>
                                    <select id="serviceReminderCustomer" required ${legacyActionAttributes("change", "handleServiceReminderCustomerChange_a5d5063a")} disabled>${customerOptions}</select>
                                </div>
                                <div class="form-row">
                                    <label for="serviceReminderVehicle">Vozidlo:</label>
                                    <select id="serviceReminderVehicle"></select>
                                </div>
                                <div class="form-row">
                                    <label for="serviceReminderType">Typ *:</label>
                                    <select id="serviceReminderType" required>
                                        <option value="STK" ${String(reminder?.type || '').toUpperCase() === 'STK' ? 'selected' : ''}>STK</option>
                                        <option value="OLEJ" ${String(reminder?.type || '').toUpperCase() === 'OLEJ' ? 'selected' : ''}>Výměna oleje</option>
                                        <option value="SERVIS" ${String(reminder?.type || '').toUpperCase() === 'SERVIS' ? 'selected' : ''}>Servisní interval</option>
                                        <option value="PNEU" ${String(reminder?.type || '').toUpperCase() === 'PNEU' ? 'selected' : ''}>Pneumatiky</option>
                                        <option value="VLASTNI" ${String(reminder?.type || '').toUpperCase() === 'VLASTNI' ? 'selected' : ''}>Vlastní</option>
                                    </select>
                                </div>
                                <div class="form-row">
                                    <label for="serviceReminderMethod">Notifikace:</label>
                                    <select id="serviceReminderMethod">
                                        <option value="app" ${String(reminder?.notification_method || '').toLowerCase() === 'app' ? 'selected' : ''}>Aplikace</option>
                                        <option value="email" ${String(reminder?.notification_method || '').toLowerCase() === 'email' ? 'selected' : ''}>E-mail</option>
                                        <option value="both" ${String(reminder?.notification_method || '').toLowerCase() === 'both' ? 'selected' : ''}>Aplikace + e-mail</option>
                                    </select>
                                </div>
                                <div class="form-row span-2">
                                    <label for="serviceReminderText">Text *:</label>
                                    <textarea id="serviceReminderText" rows="3" required>${escapeHtml(reminder?.text || '')}</textarea>
                                </div>
                                <div class="form-row">
                                    <label for="serviceReminderDueDate">Datum termínu:</label>
                                    <input type="date" id="serviceReminderDueDate" value="${escapeHtml(String(reminder?.due_date || '').slice(0, 10))}">
                                </div>
                                <div class="form-row">
                                    <label for="serviceReminderNotifyAt">Přesná notifikace:</label>
                                    <input type="datetime-local" id="serviceReminderNotifyAt" value="${escapeHtml(notifyValue)}">
                                </div>
                                <div class="form-row span-2 reminder-check-row">
                                    <label class="reminder-check-label">
                                        <input type="checkbox" id="serviceReminderCompleted" ${reminder?.is_completed ? 'checked' : ''}>
                                        Označit jako dokončené
                                    </label>
                                </div>
                            </div>
                            <div class="form-actions">
                                <button type="submit" class="btn btn-primary">Uložit změny</button>
                                <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "loadServiceWorkspaceReminders_04c8f9af")}>Zrušit</button>
                            </div>
                        </form>
                    </div>
                </div>
            `);
            updateServiceReminderVehicleSelect(Number(reminder?.vehicle_id || 0));
        }

        async function handleUpdateServiceReminder(reminderId) {
            const customerId = Number(document.getElementById('serviceReminderCustomer')?.value || 0);
            const vehicleId = Number(document.getElementById('serviceReminderVehicle')?.value || 0);
            const type = String(document.getElementById('serviceReminderType')?.value || '').trim();
            const text = String(document.getElementById('serviceReminderText')?.value || '').trim();
            const dueDate = String(document.getElementById('serviceReminderDueDate')?.value || '').trim();
            const notifyAt = String(document.getElementById('serviceReminderNotifyAt')?.value || '').trim();
            const method = String(document.getElementById('serviceReminderMethod')?.value || '').trim();
            const isCompleted = Boolean(document.getElementById('serviceReminderCompleted')?.checked);

            if (!customerId) {
                showAlert('Vyberte klienta.', 'error');
                return;
            }
            if (!type || !text || text.length < 3) {
                showAlert('Vyplňte typ a text připomínky.', 'error');
                return;
            }

            let notifyAtIso = null;
            if (notifyAt) {
                const parsed = new Date(notifyAt);
                if (Number.isNaN(parsed.getTime())) {
                    showAlert('Neplatný formát data a času notifikace.', 'error');
                    return;
                }
                notifyAtIso = parsed.toISOString();
            }

            try {
                await apiCall(`/api/v1/services/workspace/reminders/${Number(reminderId)}`, 'PUT', {
                    type,
                    text,
                    due_date: dueDate || null,
                    notify_at: notifyAtIso,
                    notification_method: method || null,
                    is_completed: isCompleted,
                });
                showAlert('Připomínka byla upravena.', 'success');
                await loadServiceWorkspaceReminders(true);
            } catch (error) {
                console.error("[SERVICE_REMINDERS] Update error:");
                showAlert('Nepodařilo se upravit připomínku: ' + (error?.message || 'Neznámá chyba'), 'error');
            }
        }

        async function toggleServiceReminderCompletion(reminderId, value) {
            try {
                await apiCall(`/api/v1/services/workspace/reminders/${Number(reminderId)}`, 'PUT', {
                    is_completed: Boolean(value)
                });
                await loadServiceWorkspaceReminders(true);
            } catch (error) {
                console.error("[SERVICE_REMINDERS] Completion toggle error:");
                showAlert('Nepodařilo se změnit stav připomínky: ' + (error?.message || 'Neznámá chyba'), 'error');
            }
        }

        async function deleteServiceWorkspaceReminder(reminderId) {
            if (!confirm('Opravdu chcete tuto připomínku smazat?')) {
                return;
            }
            try {
                await apiCall(`/api/v1/services/workspace/reminders/${Number(reminderId)}`, 'DELETE');
                showAlert('Připomínka byla smazána.', 'success');
                await loadServiceWorkspaceReminders(true);
            } catch (error) {
                console.error("[SERVICE_REMINDERS] Delete error:");
                showAlert('Nepodařilo se smazat připomínku: ' + (error?.message || 'Neznámá chyba'), 'error');
            }
        }

        async function openServiceWorkspaceCustomerReminders(customerId, vehicleId = null) {
            const customerIdNum = Number(customerId || 0);
            if (!customerIdNum) {
                showAlert('Neplatný klient pro připomínky.', 'error');
                return;
            }
            serviceWorkspaceRemindersState.customerFilter = String(customerIdNum);
            serviceWorkspaceRemindersState.statusFilter = 'ACTIVE';
            serviceWorkspaceRemindersState.query = '';
            switchTab('reminders');
            await loadServiceWorkspaceReminders(true);
            if (Number(vehicleId || 0) > 0) {
                await openServiceReminderComposer(customerIdNum, Number(vehicleId));
            }
        }

        // Načítání připomínek (v1.0)
        async function loadReminders(force = true) {
            const renderStartTs = performance.now();
            unmountFloatingModal();
            if (isServiceWorkspaceRole()) {
                return loadServiceWorkspaceReminders();
            }
            if (window.__licenseFlags && window.__licenseFlags.remindersEnabled === false) {
                showAlert('Připomínky jsou dostupné od plánu BASIC.', 'info');
                const containerInfo = document.getElementById('remindersContainer');
                if (containerInfo) {
                    renderRemindersUpsell(containerInfo);
                }
                return;
            }
            const container = document.getElementById('remindersContainer');
            if (!container) return;

            // Kontrola auth stavu
            if (!isAuthenticated()) {
                console.warn("[REMINDERS] Uživatel není přihlášen");
                return;
            }

            const cacheOwnerKey = getUiCacheOwnerKey();
            if (!force
                && isUiSectionCacheFresh(remindersUiState)
                && container.dataset.renderedFor === cacheOwnerKey
                && container.innerHTML.trim()) {
                applyReminderViewModeUI();
                return;
            }

            // Trigger backend kontroly notifikací (throttled), aby fungovalo i bez externího cronu.
            triggerReminderNotificationCheck();

            container.innerHTML = '<div class="loading">Načítám připomínky...</div>';
            container.classList.remove('loading');
            container.classList.add('reminders-section');

            try {
                const reminders = await apiCall('/api/v1/reminders', 'GET');
                const settingsInitiallyOpen = false;
                const settingsPanelDisplay = settingsInitiallyOpen ? 'block' : 'none';
                const settingsToggleSymbol = settingsInitiallyOpen ? '▲' : '▼';
                const settingsSubtitle = 'Centrální pravidla (sbaleno, klepněte pro úpravu)';
                const templatesInitiallyOpen = false;
                const templatesPanelDisplay = templatesInitiallyOpen ? 'block' : 'none';
                const templatesToggleSymbol = templatesInitiallyOpen ? '▲' : '▼';
                const templatesSubtitle = 'Rychlé šablony (sbaleno, klepněte pro otevření)';
                remindersUiState.items = Array.isArray(reminders) ? reminders : [];
                const reminderFilterMode = getReminderFilterMode();
                const reminderFilterCounts = getReminderFilterCounts(remindersUiState.items);
                const activeRemindersCount = reminderFilterCounts.active;
                const activeRemindersText = activeRemindersCount === 1
                    ? '1 aktivní položka'
                    : `${activeRemindersCount} aktivních položek`;
                const reminderViewMode = getReminderViewMode();
                const reminderViewControlsHtml = `
                    <div class="reminder-view-bar">
                        <div class="reminder-view-switch" role="group" aria-label="Režim zobrazení připomínek">
                            <button type="button" class="reminder-view-btn" data-view="grid" ${legacyActionAttributes("click", "setReminderView_150bbeba")}>Mřížka</button>
                            <button type="button" class="reminder-view-btn" data-view="list" ${legacyActionAttributes("click", "setReminderView_608a38ee")}>Seznam</button>
                            <button type="button" class="reminder-view-btn" data-view="compact" ${legacyActionAttributes("click", "setReminderView_0e978cf6")}>Kompaktní</button>
                            <button type="button" class="reminder-view-btn" data-view="calendar" ${legacyActionAttributes("click", "setReminderView_05df8aa6")}>Kalendář</button>
                        </div>
                    </div>
                    <div id="reminderViewModeNote" class="reminder-view-note"></div>
                `;

                let html = '<div class="reminders-section"><div class="reminder-panel reminder-master">';

                // Nastavení upozornění (na menších zařízeních defaultně sbalené)
                html += `
                    <div class="panel-block reminder-settings-block">
                        <div class="panel-header" id="reminderSettingsHeader">
                            <div class="panel-title">
                                <span class="panel-icon" aria-hidden="true">
                                    <svg viewBox="0 0 24 24" style="width: 16px; height: 16px; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;">
                                        <circle cx="12" cy="12" r="3"></circle>
                                        <path d="M12 2v3"></path>
                                        <path d="M12 19v3"></path>
                                        <path d="M4.93 4.93l2.12 2.12"></path>
                                        <path d="M16.95 16.95l2.12 2.12"></path>
                                        <path d="M2 12h3"></path>
                                        <path d="M19 12h3"></path>
                                        <path d="M4.93 19.07l2.12-2.12"></path>
                                        <path d="M16.95 7.05l2.12-2.12"></path>
                                    </svg>
                                </span>
                                <div>
                                    <div class="panel-heading">Nastavení upozornění</div>
                                    <div class="panel-subtitle">${settingsSubtitle}</div>
                                </div>
                            </div>
                        <button type="button" id="reminderSettingsToggle" class="panel-toggle">${settingsToggleSymbol}</button>
                        </div>
                        <div id="reminderSettingsPanel" class="panel-body reminder-settings-body" style="display: ${settingsPanelDisplay};">
                            <form id="reminderSettingsForm" class="reminder-form reminder-settings-form">
                                <div class="reminder-settings-intro">
                                    <div class="reminder-scope-badge reminder-scope-badge-global">Centrální výchozí pravidlo</div>
                                    <div class="reminder-scope-badge reminder-scope-badge-item">Na kartě připomínky lze přepsat</div>
                                    <p class="reminder-settings-note">
                                        Toto nastavení se použije pro všechny připomínky, které nemají vlastní čas/kanál. U konkrétní připomínky můžete vytvořit výjimku přes tlačítko hodin.
                                    </p>
                                </div>
                                <div id="reminderSettingsSummary" class="reminder-settings-summary">
                                    Výchozí pravidlo: načítám...
                                </div>
                                <div class="form-group">
                                    <label for="notificationMethod">Výchozí způsob upozornění (globálně):</label>
                                    <select id="notificationMethod">
                                        <option value="app">Aplikace (push / fallback e-mail)</option>
                                        <option value="email">E-mail</option>
                                        <option value="both">Aplikace (push) + e-mail</option>
                                    </select>
                                    <small class="form-hint">Použije se tam, kde připomínka nemá vlastní nastavení.</small>
                                </div>
                                <div class="form-group">
                                    <label for="notifyDaysBefore">Výchozí předstih (dny):</label>
                                    <input type="number" id="notifyDaysBefore" min="0" max="365" value="7">
                                    <small class="form-hint">0 = upozornit v den termínu, 7 = týden předem (rozsah 0-365)</small>
                                </div>
                                <div class="form-group reminder-push-group">
                                    <label>Technický stav push notifikací</label>
                                    <div class="reminder-push-stack">
                                        <div class="reminder-push-badges">
                                            <span id="pushPermissionBadge" class="badge reminder-push-badge">Oprávnění: -</span>
                                            <span id="pushSubscriptionBadge" class="badge reminder-push-badge">Aktivní zařízení: -</span>
                                        </div>
                                        <div class="reminder-push-actions">
                                            <button type="button" id="enablePushBtn" class="btn btn-primary reminder-push-btn reminder-push-btn-enable">Povolit push</button>
                                            <button type="button" id="disablePushBtn" class="btn btn-secondary reminder-push-btn reminder-push-btn-disable">Vypnout push</button>
                                            <button type="button" id="testPushBtn" class="btn btn-secondary reminder-push-btn reminder-push-btn-test">Test push</button>
                                        </div>
                                        <small class="form-hint">Push funguje jen při HTTPS a po povolení notifikací v prohlížeči.</small>
                                        <div id="pushStatusMessage" class="reminder-push-status"></div>
                                    </div>
                                </div>
                            </form>
                            <div class="reminder-settings-actions">
                                <button type="button" id="saveReminderSettingsBtn" class="btn btn-primary reminder-main-btn reminder-main-btn-save">Uložit výchozí nastavení</button>
                                <button type="button" id="refreshReminderSettingsBtn" class="btn btn-secondary reminder-main-btn reminder-main-btn-refresh">Obnovit z serveru</button>
                            </div>
                        </div>
                    </div>
                `;

                // Hlavní akce nad seznamem připomínek
                html += `
                    <div class="reminder-actions reminder-primary-actions">
                        <button class="btn btn-primary reminder-add-btn reminder-main-btn reminder-main-btn-add" ${legacyActionAttributes("click", "showCreateReminderForm_ff2a2251")}>+ Přidat připomínku</button>
                    </div>
                    <div class="reminder-per-item-note">
                        Tip: Centrální pravidla platí pro všechny připomínky. U konkrétní připomínky otevřete ikonu hodin a nastavte vlastní datum, čas nebo kanál.
                    </div>
                `;

                // Šablony připomínek (na mobilu/tabletu sbalené, ale stále viditelně dostupné)
                html += `
                    <div class="panel-block reminder-templates-block">
                        <div class="panel-header" id="reminderTemplatesHeader">
                            <div class="panel-title">
                                <span class="panel-icon" aria-hidden="true">
                                    <svg viewBox="0 0 24 24" style="width: 16px; height: 16px; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;">
                                        <path d="M9 3H5a2 2 0 0 0-2 2v4h3a2 2 0 1 1 0 4H3v6a2 2 0 0 0 2 2h4v-3a2 2 0 1 1 4 0v3h6a2 2 0 0 0 2-2v-4h-3a2 2 0 1 1 0-4h3V5a2 2 0 0 0-2-2h-4v3a2 2 0 1 1-4 0V3z"></path>
                                    </svg>
                                </span>
                                <div>
                                    <div class="panel-heading">Šablony připomínek</div>
                                    <div class="panel-subtitle">${templatesSubtitle}</div>
                                    <div class="panel-meta-hint">STK • OLEJ • PNEUMATIKY • POJISTKA • SERVIS</div>
                                </div>
                            </div>
                            <button type="button" id="reminderTemplatesToggle" class="panel-toggle">${templatesToggleSymbol}</button>
                        </div>
                        <div id="reminderTemplatesPanel" class="panel-body" style="display: ${templatesPanelDisplay};">
                        <div class="reminder-template-grid reminder-templates">
                            <button class="btn reminder-pill-btn reminder-pill-btn--stk" ${legacyActionAttributes("click", "applyReminderTemplate_0b51db63")}><span class="tpl-main">STK</span><span class="tpl-sub">Dynamicky dle vybraného vozidla</span></button>
                            <button class="btn reminder-pill-btn reminder-pill-btn--olej" ${legacyActionAttributes("click", "applyReminderTemplate_ceada0dc")}><span class="tpl-main">OLEJ</span><span class="tpl-sub">Výměna oleje za 6 měsíců</span></button>
                            <button class="btn reminder-pill-btn reminder-pill-btn--pneu" ${legacyActionAttributes("click", "applyReminderTemplate_a3144fbf")}><span class="tpl-main">PNEUMATIKY</span><span class="tpl-sub">Přezutí za 4 měsíce</span></button>
                            <button class="btn reminder-pill-btn reminder-pill-btn--pojistka" ${legacyActionAttributes("click", "applyReminderTemplate_cf38127f")}><span class="tpl-main">POJISTKA</span><span class="tpl-sub">Kontrola / obnova za rok</span></button>
                            <button class="btn reminder-pill-btn reminder-pill-btn--servis" ${legacyActionAttributes("click", "applyReminderTemplate_f6a1c20e")}><span class="tpl-main">SERVIS</span><span class="tpl-sub">Pravidelný servis za 6 měsíců</span></button>
                        </div>
                            <div class="reminder-note">
                                Kliknutím se předvyplní typ a text; u STK se použije pouze známé datum platnosti vybraného vozidla.
                            </div>
                        </div>
                    </div>
                `;

                if (!reminders || reminders.length === 0) {
                    remindersUiState.filteredItems = [];
                    html += `
                        <div class="reminder-list-priority">
                            <div class="reminder-list-head">
                                <span class="reminder-list-head-title">Přidané připomínky</span>
                                <span class="reminder-list-head-count">0 aktivních položek</span>
                            </div>
                            ${reminderViewControlsHtml}
                            ${buildReminderFilterBarHtml(reminderFilterCounts, reminderFilterMode)}
                            <div class="reminder-empty">Žádné připomínky. Všechno je v pořádku.</div>
                        </div>
                    `;
                    html += '</div></div></div>';
                    container.innerHTML = html;
                    container.dataset.renderedFor = cacheOwnerKey;
                    markUiSectionLoaded(remindersUiState);
                    applyReminderViewModeUI();

                    requestAnimationFrame(() => {
                        setupReminderSettingsEventListeners();
                    });
                    return;
                }

                const filteredReminders = remindersUiState.items
                    .filter((item) => reminderMatchesFilter(item, reminderFilterMode))
                    .sort((a, b) => {
                        const aStatus = getReminderStatusMeta(a);
                        const bStatus = getReminderStatusMeta(b);
                        if (aStatus.key !== bStatus.key) {
                            const order = { expired: 0, active: 1, completed: 2 };
                            return (order[aStatus.key] ?? 99) - (order[bStatus.key] ?? 99);
                        }
                        const aDate = getReminderReferenceDate(a);
                        const bDate = getReminderReferenceDate(b);
                        if (!aDate && !bDate) return 0;
                        if (!aDate) return 1;
                        if (!bDate) return -1;
                        return aDate.getTime() - bDate.getTime();
                    });
                remindersUiState.filteredItems = filteredReminders;

                html += `
                    <div class="reminder-list-priority">
                        <div class="reminder-list-head">
                            <span class="reminder-list-head-title">Přidané připomínky</span>
                            <span class="reminder-list-head-count">${escapeHtml(activeRemindersText)}</span>
                        </div>
                        ${reminderViewControlsHtml}
                        ${buildReminderFilterBarHtml(reminderFilterCounts, reminderFilterMode)}
                `;

                if (!filteredReminders.length) {
                    html += '<div class="reminder-empty">V tomto filtru není žádná připomínka.</div>';
                } else if (reminderViewMode === 'calendar') {
                    html += buildReminderCalendarHtml(filteredReminders);
                } else {
                    html += `
                        <div class="cards-grid reminders-grid reminder-view reminder-view-${escapeHtml(reminderViewMode)}">
                            ${filteredReminders.map((reminder, index) => buildReminderCardMinimalHtml(reminder, index)).join('')}
                        </div>
                    `;
                }

                html += '</div></div></div></div>';
                container.innerHTML = html;
                container.dataset.renderedFor = cacheOwnerKey;
                markUiSectionLoaded(remindersUiState);
                applyReminderViewModeUI();


                // Nastavit event listenery pro tlačítka nastavení připomínek po vložení HTML
                requestAnimationFrame(() => {
                    setupReminderSettingsEventListeners();
                });

        } catch (error) {
                remindersUiState.loadedAt = 0;
                console.error("[REMINDERS] Error loading reminders:");
                const errorMessage = error.message || 'Neznámá chyba';
                showErrorWithRetry('remindersContainer', `Nepodařilo se načíst připomínky: ${errorMessage}`, loadReminders);
            }
        }

        // Upsell blok pro připomínky (Free/Basic)
        function renderRemindersUpsell(container) {
            if (!container) return;
            container.innerHTML = `
                <div class="feature-upsell">
                    <div class="feature-upsell-media">⏰</div>
                    <div class="feature-upsell-body">
                        <h4>Připomínky v akci (Premium)</h4>
                        <p>Automatické upozornění na STK, servis, pojistku i olej. Opakování a předvyplněné šablony na pár kliků.</p>
                        <ul>
                            <li>Šablony STK / olej / pneumatiky / pojistka / servis</li>
                            <li>Opakované připomínky a e-mailové notifikace</li>
                            <li>Rychlé otevření vozidla a historie</li>
                        </ul>
                        <div class="feature-upsell-actions">
                            <button class="btn" ${legacyActionAttributes("click", "openLicenseModal_5e411be2")}>Chci Premium</button>
                        </div>
                    </div>
                </div>
            `;
        }

        // Šablony připomínek – předvyplní typ/text/datum a otevřou formulář
        function applyReminderTemplate(type, text, daysAhead, dynamicStk = false) {
            const today = new Date();
            if (Number.isFinite(daysAhead) && daysAhead > 0) {
                today.setDate(today.getDate() + daysAhead);
            }
            const dueDateStr = Number.isFinite(daysAhead) && daysAhead > 0
                ? today.toISOString().split('T')[0]
                : '';
            window.__reminderPreset = {
                type: type,
                text: text,
                due_date: dueDateStr,
                dynamic_stk: dynamicStk === true
            };
            showCreateReminderForm();
        }

        function inspectionDateOnly(value) {
            if (typeof value !== 'string') return '';
            const raw = value.trim();
            if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) return '';
            const date = new Date(raw + 'T00:00:00Z');
            return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === raw ? raw : '';
        }

        function computeStkTemplateDueDate(vehicle) {
            return inspectionDateOnly(vehicle?.stk_valid_until);
        }

        function setupCreateReminderTemplateBehavior(vehicles, preset) {
            const typeSelect = document.getElementById('reminderType');
            const vehicleSelect = document.getElementById('reminderVehicle');
            const dueDateInput = document.getElementById('reminderDueDate');
            if (!typeSelect || !vehicleSelect || !dueDateInput) {
                return;
            }

            const isDynamicStk = preset?.dynamic_stk === true;
            dueDateInput.dataset.autoManaged = isDynamicStk ? '1' : '0';

            const applyDynamicStkDate = () => {
                if (typeSelect.value !== 'STK' || dueDateInput.dataset.autoManaged !== '1') {
                    return;
                }

                const selectedId = Number(vehicleSelect.value);
                const vehicle = Number.isFinite(selectedId)
                    ? vehicles.find(v => Number(v.id) === selectedId)
                    : null;
                dueDateInput.value = computeStkTemplateDueDate(vehicle || null);
            };

            if (isDynamicStk) {
                applyDynamicStkDate();
            }

            typeSelect.addEventListener('change', () => {
                if (typeSelect.value === 'STK' && isDynamicStk) {
                    dueDateInput.dataset.autoManaged = '1';
                    applyDynamicStkDate();
                }
            });

            vehicleSelect.addEventListener('change', applyDynamicStkDate);

            dueDateInput.addEventListener('input', () => {
                // Uživatel upravil datum ručně -> už nepřepisovat automatikou.
                dueDateInput.dataset.autoManaged = '0';
            });
        }

        // Zobrazení formuláře pro vytvoření připomínky
        async function showCreateReminderForm() {
            if (isServiceWorkspaceRole()) {
                return openServiceReminderComposer();
            }
            // Načíst vozidla uživatele
            let vehicles = [];
            try {
                vehicles = await apiCall('/api/v1/vehicles', 'GET');
            } catch (error) {
                console.error("Error loading vehicles:");
            }
            // default šablona (pokud byla zvolena dříve přes applyReminderTemplate)
            const preset = window.__reminderPreset || {};
            window.__reminderPreset = {}; // vyčistit po použití

            const formHtml = `
                <div class="reminder-modal-overlay" ${legacyActionAttributes("click", "loadReminders_e3c8345d")}>
                    <div class="reminder-modal">
                        <form class="reminder-create" ${legacyActionAttributes("submit", "handleCreateReminder_5a2def2a")}>
                            <div class="reminder-modal-head">
                                <div class="reminder-modal-heading">
                                    <span class="reminder-modal-icon" aria-hidden="true">
                                        <svg viewBox="0 0 24 24">
                                            <path d="M8 2v3"></path>
                                            <path d="M16 2v3"></path>
                                            <rect x="3" y="5" width="18" height="16" rx="2"></rect>
                                            <path d="M3 10h18"></path>
                                        </svg>
                                    </span>
                                    <div>
                                        <p class="reminder-modal-kicker">Připomínky</p>
                                        <h2 class="modal-title">Nová připomínka</h2>
                                    </div>
                                </div>
                                <button type="button" class="reminder-modal-close" aria-label="Zavřít okno" ${legacyActionAttributes("click", "loadReminders_d8558427")}>×</button>
                            </div>
                            <p class="reminder-modal-intro">Vytvořte připomínku, nastavte termín a případně i přesný čas notifikace.</p>

                            <div class="form-grid">
                                <div class="form-row">
                                    <label for="reminderType">Typ připomínky *:</label>
                                    <select id="reminderType" required>
                                        <option value="VLASTNI" ${preset.type === 'VLASTNI' ? 'selected' : ''}>Vlastní</option>
                                        <option value="STK" ${preset.type === 'STK' ? 'selected' : ''}>STK</option>
                                        <option value="OLEJ" ${preset.type === 'OLEJ' ? 'selected' : ''}>Olej</option>
                                        <option value="PNEU" ${preset.type === 'PNEU' ? 'selected' : ''}>Pneumatiky</option>
                                        <option value="POJISTKA" ${preset.type === 'POJISTKA' ? 'selected' : ''}>Pojistka</option>
                                        <option value="SERVIS" ${preset.type === 'SERVIS' ? 'selected' : ''}>Servis</option>
                                    </select>
                                </div>

                                <div class="form-row">
                                    <label for="reminderVehicle">Vozidlo (volitelné):</label>
                                    <select id="reminderVehicle">
                                        <option value="">Obecná připomínka</option>
                                        ${vehicles.map(v => `<option value="${escapeHtml(v.id)}">${escapeHtml(v.nickname || v.plate || 'Bez názvu')} - ${escapeHtml(v.plate || 'Bez SPZ')}</option>`).join('')}
                                    </select>
                                </div>

                                <div class="form-row span-2">
                                    <label for="reminderText">Text připomínky *:</label>
                                    <textarea id="reminderText" placeholder="Např. Zkontrolovat brzdy, Vyměnit filtr..." rows="3" required>${escapeHtml(preset.text || '')}</textarea>
                                </div>

                                <div class="form-row">
                                    <label for="reminderDueDate">Datum (volitelné):</label>
                                    <input type="date" id="reminderDueDate" value="${escapeHtml(preset.due_date || '')}">
                                    <small class="form-hint">Bez času se použije standardní denní upozornění.</small>
                                </div>

                                <div class="form-row">
                                    <label for="reminderNotifyAt">Přesná notifikace (datum + čas):</label>
                                    <input type="datetime-local" id="reminderNotifyAt">
                                    <small class="form-hint">Pokud vyplníte, upozornění se odešle v přesný čas.</small>
                                </div>

                                <div class="form-row">
                                    <label for="reminderRepeatCount">Opakování (kolikrát):</label>
                                    <input type="number" id="reminderRepeatCount" min="0" max="24" value="0">
                                    <small class="form-hint">0 = bez opakování</small>
                                </div>

                                <div class="form-row">
                                    <label for="reminderRepeatInterval">Interval opakování (dny):</label>
                                    <input type="number" id="reminderRepeatInterval" min="0" max="3650" value="0">
                                    <small class="form-hint">Např. 30 = každý měsíc; 180 = půl roku</small>
                                </div>
                            </div>

                            <div class="form-actions">
                                <button type="submit" class="btn btn-primary">Vytvořit připomínku</button>
                                <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "loadReminders_d8558427")}>Zrušit</button>
                            </div>
                        </form>
                    </div>
                </div>
            `;

            mountFloatingModal(formHtml);
            setupCreateReminderTemplateBehavior(vehicles, preset);
        }

        // Vytvoření připomínky
        async function handleCreateReminder() {
            if (isServiceWorkspaceRole()) {
                return handleCreateServiceReminder();
            }
            const type = document.getElementById('reminderType').value;
            const vehicleId = document.getElementById('reminderVehicle').value;
            const text = document.getElementById('reminderText').value;
            const dueDate = document.getElementById('reminderDueDate').value;
            const notifyAt = document.getElementById('reminderNotifyAt')?.value || '';
            const repeatCount = Number(document.getElementById('reminderRepeatCount')?.value || 0);
            const repeatInterval = Number(document.getElementById('reminderRepeatInterval')?.value || 0);

            if (!text || !text.trim()) {
                showAlert('Zadejte text připomínky', 'error');
                return;
            }

            let notifyAtIso = null;
            if (notifyAt) {
                const notifyAtDate = new Date(notifyAt);
                if (Number.isNaN(notifyAtDate.getTime())) {
                    showAlert('Datum a čas notifikace má neplatný formát.', 'error');
                    return;
                }
                notifyAtIso = notifyAtDate.toISOString();
            }

            const reminderData = {
                type: type,
                vehicle_id: vehicleId ? parseInt(vehicleId) : null,
                text: text.trim(),
                due_date: dueDate || null,
                notify_at: notifyAtIso
            };
            if (repeatCount > 0 && repeatInterval > 0) {
                reminderData.repeat_count = repeatCount;
                reminderData.repeat_interval_days = repeatInterval;
            }

            try {
                showAlert('Vytvářím připomínku...', 'info');
                await apiCall('/api/v1/reminders', 'POST', reminderData);
                showAlert('Připomínka byla úspěšně vytvořena!', 'success');
                await loadReminders();
            } catch (error) {
                console.error("Error creating reminder:");
                showAlert('Nepodařilo se vytvořit připomínku: ' + (error.message || 'Neznámá chyba'), 'error');
            }
        }

        function toDateInputValue(dateObj) {
            const year = dateObj.getFullYear();
            const month = String(dateObj.getMonth() + 1).padStart(2, '0');
            const day = String(dateObj.getDate()).padStart(2, '0');
            return `${year}-${month}-${day}`;
        }

        function toDateTimeLocalValue(dateObj) {
            const year = dateObj.getFullYear();
            const month = String(dateObj.getMonth() + 1).padStart(2, '0');
            const day = String(dateObj.getDate()).padStart(2, '0');
            const hours = String(dateObj.getHours()).padStart(2, '0');
            const minutes = String(dateObj.getMinutes()).padStart(2, '0');
            return `${year}-${month}-${day}T${hours}:${minutes}`;
        }

        async function showReminderScheduleForm(reminderId) {
            try {
                const reminders = await apiCall('/api/v1/reminders', 'GET');
                const reminder = reminders.find(r => r.id === reminderId && r.is_manual === true);
                if (!reminder) {
                    showAlert('Ruční připomínka nebyla nalezena.', 'error');
                    return;
                }

                let dueDateValue = reminder.due_date
                    ? String(reminder.due_date).slice(0, 10)
                    : '';

                let notifyAtValue = '';
                if (reminder.notify_at) {
                    const notifyAtDate = new Date(reminder.notify_at);
                    if (!Number.isNaN(notifyAtDate.getTime())) {
                        notifyAtValue = toDateTimeLocalValue(notifyAtDate);
                        if (!dueDateValue) {
                            dueDateValue = toDateInputValue(notifyAtDate);
                        }
                    }
                }

                const method = typeof reminder.notification_method === 'string'
                    ? reminder.notification_method.toLowerCase()
                    : 'inherit';
                const methodValue = ['app', 'email', 'both'].includes(method) ? method : 'inherit';

                const modalHtml = `
                    <div class="reminder-modal-overlay" ${legacyActionAttributes("click", "loadReminders_e3c8345d")}>
                        <div class="reminder-modal">
                            <form class="reminder-create" ${legacyActionAttributes("submit", "handleUpdateReminderSchedule_ca45dc6e", reminderId)}>
                                <div class="reminder-modal-head">
                                    <div class="reminder-modal-heading">
                                        <span class="reminder-modal-icon" aria-hidden="true">
                                            <svg viewBox="0 0 24 24">
                                                <circle cx="12" cy="12" r="8"></circle>
                                                <path d="M12 8v5"></path>
                                                <path d="M12 12l3 2"></path>
                                            </svg>
                                        </span>
                                        <div>
                                            <p class="reminder-modal-kicker">Připomínky</p>
                                            <h2 class="modal-title">Nastavení připomenutí</h2>
                                        </div>
                                    </div>
                                    <button type="button" class="reminder-modal-close" aria-label="Zavřít okno" ${legacyActionAttributes("click", "loadReminders_d8558427")}>×</button>
                                </div>
                                <p class="reminder-modal-intro">Pro tuto konkrétní připomínku nastavte datum, čas a způsob upozornění.</p>
                                <div class="form-grid">
                                    <div class="form-row">
                                        <label for="scheduleReminderDueDate">Datum připomínky:</label>
                                        <input type="date" id="scheduleReminderDueDate" value="${escapeHtml(dueDateValue)}">
                                        <small class="form-hint">Datum platí jako základní termín připomínky.</small>
                                    </div>
                                    <div class="form-row">
                                        <label for="scheduleReminderNotifyAt">Přesný termín (datum + čas):</label>
                                        <input type="datetime-local" id="scheduleReminderNotifyAt" value="${escapeHtml(notifyAtValue)}">
                                        <small class="form-hint">Pokud vyplníte, odešle se upozornění přesně v tento čas.</small>
                                    </div>
                                    <div class="form-row span-2">
                                        <label for="scheduleReminderMethod">Jak připomenout:</label>
                                        <select id="scheduleReminderMethod">
                                            <option value="inherit" ${methodValue === 'inherit' ? 'selected' : ''}>Dle globálního nastavení účtu</option>
                                            <option value="app" ${methodValue === 'app' ? 'selected' : ''}>Aplikace (push / fallback e-mail)</option>
                                            <option value="email" ${methodValue === 'email' ? 'selected' : ''}>E-mailem</option>
                                            <option value="both" ${methodValue === 'both' ? 'selected' : ''}>Aplikací + e-mailem</option>
                                        </select>
                                    </div>
                                </div>
                                <div class="form-actions">
                                    <button type="submit" class="btn btn-primary">Uložit nastavení</button>
                                    <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "loadReminders_d8558427")}>Zrušit</button>
                                </div>
                            </form>
                        </div>
                    </div>
                `;

                mountFloatingModal(modalHtml);
            } catch (error) {
                console.error("Error opening reminder schedule modal:");
                showAlert('Nepodařilo se otevřít nastavení připomínky: ' + (error.message || 'Neznámá chyba'), 'error');
            }
        }

        async function handleUpdateReminderSchedule(reminderId) {
            const dueDate = document.getElementById('scheduleReminderDueDate')?.value || '';
            const notifyAt = document.getElementById('scheduleReminderNotifyAt')?.value || '';
            const notificationMethod = document.getElementById('scheduleReminderMethod')?.value || 'inherit';

            let notifyAtIso = null;
            if (notifyAt) {
                const notifyAtDate = new Date(notifyAt);
                if (Number.isNaN(notifyAtDate.getTime())) {
                    showAlert('Datum a čas má neplatný formát.', 'error');
                    return;
                }
                notifyAtIso = notifyAtDate.toISOString();
            }

            const payload = {
                due_date: dueDate || null,
                notify_at: notifyAtIso,
                notification_method: notificationMethod === 'inherit' ? null : notificationMethod
            };

            try {
                showAlert('Ukládám nastavení připomenutí...', 'info');
                await apiCall(`/api/v1/reminders/${reminderId}`, 'PUT', payload);
                showAlert('Nastavení připomenutí bylo uloženo.', 'success');
                await loadReminders();
            } catch (error) {
                console.error("Error updating reminder schedule:");
                showAlert('Nepodařilo se uložit nastavení: ' + (error.message || 'Neznámá chyba'), 'error');
            }
        }

        // ============= NASTAVENÍ EMAIL UPOZORNĚNÍ =============

        // Toggle panelu nastavení
        function toggleReminderSettings() {
            const panel = document.getElementById('reminderSettingsPanel');
            const toggle = document.getElementById('reminderSettingsToggle');
            if (panel && toggle) {
                if (panel.style.display === 'none' || panel.style.display === '') {
                    panel.style.display = 'block';
                    toggle.textContent = '▲';
                    loadReminderSettings(); // Načíst aktuální nastavení
                } else {
                    panel.style.display = 'none';
                    toggle.textContent = '▼';
                }
            }
        }

        // Toggle panelu šablon
        function toggleReminderTemplates() {
            const panel = document.getElementById('reminderTemplatesPanel');
            const toggle = document.getElementById('reminderTemplatesToggle');
            if (panel && toggle) {
                if (panel.style.display === 'none' || panel.style.display === '') {
                    panel.style.display = 'block';
                    toggle.textContent = '▲';
                } else {
                    panel.style.display = 'none';
                    toggle.textContent = '▼';
                }
            }
        }

        function reminderMethodLabel(method) {
            if (method === 'app') return 'Aplikace (push / fallback e-mail)';
            if (method === 'email') return 'E-mail';
            if (method === 'both') return 'Aplikace + e-mail';
            return 'Aplikace + e-mail';
        }

        function updateReminderSettingsSummary() {
            const summaryEl = document.getElementById('reminderSettingsSummary');
            const methodSelect = document.getElementById('notificationMethod');
            const daysInput = document.getElementById('notifyDaysBefore');
            if (!summaryEl || !methodSelect || !daysInput) return;

            const method = methodSelect.value || 'both';
            let days = Number.parseInt(daysInput.value, 10);
            if (!Number.isFinite(days)) days = 7;
            if (days < 0) days = 0;
            if (days > 365) days = 365;

            const dayPart = days === 0
                ? 'v den termínu'
                : `${days} ${days === 1 ? 'den' : (days >= 2 && days <= 4 ? 'dny' : 'dní')} před termínem`;

            summaryEl.innerHTML = `
                <strong>Aktivní výchozí pravidlo:</strong>
                Upozornění přes <strong>${reminderMethodLabel(method)}</strong>, doručit <strong>${escapeHtml(dayPart)}</strong>.
                <span>U konkrétní připomínky lze toto pravidlo přepsat v detailu (ikona hodin).</span>
            `;
        }

        // Načtení nastavení připomínek z API
        async function loadReminderSettings() {
            try {
                const settings = await apiCall('/api/v1/reminders/settings', 'GET');

                if (settings && settings.notification) {
                    const methodSelect = document.getElementById('notificationMethod');
                    const daysInput = document.getElementById('notifyDaysBefore');

                    if (methodSelect) {
                        methodSelect.value = settings.notification.notification_method || 'email';
                    }
                    if (daysInput) {
                        daysInput.value = settings.notification.notify_days_before || 7;
                    }
                }
                updateReminderSettingsSummary();
            } catch (error) {
                console.error("Error loading reminder settings:");
                // Použít výchozí hodnoty
                const methodSelect = document.getElementById('notificationMethod');
                const daysInput = document.getElementById('notifyDaysBefore');
                if (methodSelect) methodSelect.value = 'email';
                if (daysInput) daysInput.value = 7;
                updateReminderSettingsSummary();
            }
        }

        // Uložení nastavení připomínek
        async function handleSaveReminderSettings(event) {
            event.preventDefault();

            const methodSelect = document.getElementById('notificationMethod');
            const daysInput = document.getElementById('notifyDaysBefore');

            if (!methodSelect || !daysInput) {
                showAlert('Chyba: Formulář není správně načten', 'error');
                return;
            }

            const notificationMethod = methodSelect.value;
            const notifyDaysBeforeValue = daysInput.value.trim();
            const notifyDaysBefore = notifyDaysBeforeValue === '' ? 7 : parseInt(notifyDaysBeforeValue);

            if (isNaN(notifyDaysBefore) || notifyDaysBefore < 0 || notifyDaysBefore > 365) {
                showAlert('Počet dní musí být mezi 0 a 365', 'error');
                return;
            }

            try {
                showAlert('Ukládám nastavení...', 'info');

                // Posíláme jen notification blok, abychom nepropašovali staré/nesprávné klíče
                const payload = {
                    notification: {
                        notification_method: notificationMethod,
                        notify_days_before: notifyDaysBefore
                    }
                };

                await apiCall('/api/v1/reminders/settings', 'PUT', payload);
                showAlert('Nastavení bylo úspěšně uloženo! ✅', 'success');
                updateReminderSettingsSummary();

                // Počkat chvíli a znovu načíst nastavení pro ověření
                setTimeout(() => {
                    loadReminderSettings();
                }, 500);

            } catch (error) {
                console.error("Error saving reminder settings:");
                showAlert('Nepodařilo se uložit nastavení: ' + (error.message || 'Neznámá chyba'), 'error');
            }
        }

        // Nastavení event listenerů pro tlačítka nastavení připomínek (volá se po vložení HTML)
        function setupReminderSettingsEventListeners() {


            // Tlačítko "Uložit nastavení"
            const saveBtn = document.getElementById('saveReminderSettingsBtn');
            if (saveBtn) {

                saveBtn.replaceWith(saveBtn.cloneNode(true));
                const reboundSave = document.getElementById('saveReminderSettingsBtn');
                reboundSave.setAttribute('type', 'button');
                reboundSave.addEventListener('click', async (e) => {
                    e.preventDefault();
                    e.stopPropagation();

                    await handleSaveReminderSettings(e);
                });
            } else {
                console.warn("[REMINDER SETTINGS] Tlačítko Uložit nenalezeno!");
            }

            // Tlačítko "Obnovit"
            const refreshBtn = document.getElementById('refreshReminderSettingsBtn');
            if (refreshBtn) {

                refreshBtn.replaceWith(refreshBtn.cloneNode(true));
                const reboundRefresh = document.getElementById('refreshReminderSettingsBtn');
                reboundRefresh.setAttribute('type', 'button');
                reboundRefresh.addEventListener('click', async (e) => {
                    e.preventDefault();
                    e.stopPropagation();

                    await loadReminderSettings();
                    showAlert('Nastavení obnoveno', 'success');
                });
            } else {
                console.warn("[REMINDER SETTINGS] Tlačítko Obnovit nenalezeno!");
            }

            // Formulář submit
            const form = document.getElementById('reminderSettingsForm');
            if (form) {
                form.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    e.stopPropagation();

                    await handleSaveReminderSettings(e);
                });
            }

            const notificationMethod = document.getElementById('notificationMethod');
            if (notificationMethod) {
                notificationMethod.addEventListener('change', () => {
                    updateReminderSettingsSummary();
                });
            }

            const notifyDaysBefore = document.getElementById('notifyDaysBefore');
            if (notifyDaysBefore) {
                notifyDaysBefore.addEventListener('input', () => {
                    updateReminderSettingsSummary();
                });
            }

            // Header pro toggle nastavení
            const header = document.getElementById('reminderSettingsHeader');
            if (header) {
                header.addEventListener('click', (e) => {
                    e.stopPropagation();
                    toggleReminderSettings();
                });
            }
            const toggle = document.getElementById('reminderSettingsToggle');
            if (toggle) {
                toggle.addEventListener('click', (e) => {
                    e.stopPropagation();
                    toggleReminderSettings();
                });
            }

            // Header pro toggle šablon
            const templatesHeader = document.getElementById('reminderTemplatesHeader');
            if (templatesHeader) {
                templatesHeader.addEventListener('click', (e) => {
                    e.stopPropagation();
                    toggleReminderTemplates();
                });
            }
            const templatesToggle = document.getElementById('reminderTemplatesToggle');
            if (templatesToggle) {
                templatesToggle.addEventListener('click', (e) => {
                    e.stopPropagation();
                    toggleReminderTemplates();
                });
            }

            const enablePushBtn = document.getElementById('enablePushBtn');
            if (enablePushBtn) {
                enablePushBtn.addEventListener('click', async (e) => {
                    e.preventDefault();
                    const result = await ensurePushSubscribed({ interactive: true });
                    if (result && result.ok) {
                        showAlert('Push notifikace byly povoleny.', 'success');
                    } else {
                        showAlert(`Push nelze zapnout: ${mapPushFailureReason(result?.reason)}`, 'warning');
                    }
                });
            }

            const disablePushBtn = document.getElementById('disablePushBtn');
            if (disablePushBtn) {
                disablePushBtn.addEventListener('click', async (e) => {
                    e.preventDefault();
                    await disablePushNotifications();
                    showAlert('Push notifikace byly vypnuty.', 'info');
                });
            }

            const testPushBtn = document.getElementById('testPushBtn');
            if (testPushBtn) {
                testPushBtn.addEventListener('click', async (e) => {
                    e.preventDefault();
                    await sendPushTestNotification();
                });
            }

            loadReminderSettings();
            refreshReminderPushStatus();
            updateReminderSettingsSummary();
        }

        // Editace připomínky
        async function editReminder(reminderId) {
            if (isServiceWorkspaceRole()) {
                return openEditServiceReminder(reminderId);
            }
            // Načíst aktuální připomínku
            try {
                const reminders = await apiCall('/api/v1/reminders', 'GET');
                const reminder = reminders.find(r => r.id === reminderId);

                if (!reminder) {
                    showAlert('Připomínka nenalezena', 'error');
                    return;
                }

                // Načíst vozidla
                let vehicles = [];
                try {
                    vehicles = await apiCall('/api/v1/vehicles', 'GET');
                } catch (error) {
                    console.error("Error loading vehicles:");
                }

                const dueDateValue = reminder.due_date
                    ? String(reminder.due_date).slice(0, 10)
                    : '';

                let notifyAtValue = '';
                if (reminder.notify_at) {
                    const notifyAtDate = new Date(reminder.notify_at);
                    if (!Number.isNaN(notifyAtDate.getTime())) {
                        const year = notifyAtDate.getFullYear();
                        const month = String(notifyAtDate.getMonth() + 1).padStart(2, '0');
                        const day = String(notifyAtDate.getDate()).padStart(2, '0');
                        const hours = String(notifyAtDate.getHours()).padStart(2, '0');
                        const minutes = String(notifyAtDate.getMinutes()).padStart(2, '0');
                        notifyAtValue = `${year}-${month}-${day}T${hours}:${minutes}`;
                    }
                }

                const formHtml = `
                    <div class="reminder-modal-overlay" ${legacyActionAttributes("click", "loadReminders_e3c8345d")}>
                        <div class="reminder-modal">
                            <form class="reminder-create" ${legacyActionAttributes("submit", "handleUpdateReminder_9539beae", reminderId)}>
                                <div class="reminder-modal-head">
                                    <div class="reminder-modal-heading">
                                        <span class="reminder-modal-icon" aria-hidden="true">
                                            <svg viewBox="0 0 24 24">
                                                <path d="M12 20h9"></path>
                                                <path d="M16.5 3.5a2.12 2.12 0 1 1 3 3L7 19l-4 1 1-4 12.5-12.5z"></path>
                                            </svg>
                                        </span>
                                        <div>
                                            <p class="reminder-modal-kicker">Připomínky</p>
                                            <h2 class="modal-title">Upravit připomínku</h2>
                                        </div>
                                    </div>
                                    <button type="button" class="reminder-modal-close" aria-label="Zavřít okno" ${legacyActionAttributes("click", "loadReminders_d8558427")}>×</button>
                                </div>
                                <p class="reminder-modal-intro">Změňte detail připomínky a uložte úpravy.</p>

                                <div class="form-grid">
                                    <div class="form-row">
                                        <label for="editReminderType">Typ připomínky *:</label>
                                        <select id="editReminderType" required>
                                            <option value="VLASTNI" ${reminder.type === 'VLASTNI' ? 'selected' : ''}>Vlastní</option>
                                            <option value="STK" ${reminder.type === 'STK' ? 'selected' : ''}>STK</option>
                                            <option value="OLEJ" ${reminder.type === 'OLEJ' ? 'selected' : ''}>Olej</option>
                                            <option value="SERVIS" ${reminder.type === 'SERVIS' ? 'selected' : ''}>Servis</option>
                                        </select>
                                    </div>

                                    <div class="form-row">
                                        <label for="editReminderVehicle">Vozidlo (volitelné):</label>
                                        <select id="editReminderVehicle">
                                            <option value="">Obecná připomínka</option>
                                            ${vehicles.map(v => `<option value="${escapeHtml(v.id)}" ${reminder.vehicle_id === v.id ? 'selected' : ''}>${escapeHtml(v.nickname || v.plate || 'Bez názvu')} - ${escapeHtml(v.plate || 'Bez SPZ')}</option>`).join('')}
                                        </select>
                                    </div>

                                    <div class="form-row span-2">
                                        <label for="editReminderText">Text připomínky *:</label>
                                        <textarea id="editReminderText" rows="3" required>${escapeHtml(reminder.text || '')}</textarea>
                                    </div>

                                    <div class="form-row">
                                        <label for="editReminderDueDate">Datum (volitelné):</label>
                                        <input type="date" id="editReminderDueDate" value="${escapeHtml(dueDateValue)}">
                                        <small class="form-hint">Pokud necháte prázdné, použije se jen přesná notifikace.</small>
                                    </div>

                                    <div class="form-row">
                                        <label for="editReminderNotifyAt">Přesná notifikace (datum + čas):</label>
                                        <input type="datetime-local" id="editReminderNotifyAt" value="${escapeHtml(notifyAtValue)}">
                                    </div>

                                    <div class="form-row span-2 reminder-check-row">
                                        <label class="reminder-check-label">
                                            <input type="checkbox" id="editReminderCompleted" ${reminder.is_completed ? 'checked' : ''}>
                                            Označit jako dokončené
                                        </label>
                                    </div>
                                </div>

                                <div class="form-actions">
                                    <button type="submit" class="btn btn-primary">Uložit změny</button>
                                    <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "loadReminders_d8558427")}>Zrušit</button>
                                </div>
                            </form>
                        </div>
                    </div>
                `;

                mountFloatingModal(formHtml);
            } catch (error) {
                console.error("Error loading reminder:");
                showAlert('Nepodařilo se načíst připomínku: ' + error.message, 'error');
            }
        }

        // Aktualizace připomínky
        async function handleUpdateReminder(reminderId) {
            const type = document.getElementById('editReminderType').value;
            const vehicleId = document.getElementById('editReminderVehicle').value;
            const text = document.getElementById('editReminderText').value;
            const dueDate = document.getElementById('editReminderDueDate').value;
            const notifyAt = document.getElementById('editReminderNotifyAt')?.value || '';
            const isCompleted = document.getElementById('editReminderCompleted').checked;

            if (!text || !text.trim()) {
                showAlert('Zadejte text připomínky', 'error');
                return;
            }

            let notifyAtIso = null;
            if (notifyAt) {
                const notifyAtDate = new Date(notifyAt);
                if (Number.isNaN(notifyAtDate.getTime())) {
                    showAlert('Datum a čas notifikace má neplatný formát.', 'error');
                    return;
                }
                notifyAtIso = notifyAtDate.toISOString();
            }

            const reminderData = {
                type: type,
                vehicle_id: vehicleId ? parseInt(vehicleId) : null,
                text: text.trim(),
                due_date: dueDate || null,
                notify_at: notifyAtIso,
                is_completed: isCompleted
            };

            try {
                showAlert('Ukládám změny...', 'info');
                await apiCall(`/api/v1/reminders/${reminderId}`, 'PUT', reminderData);
                showAlert('Připomínka byla úspěšně aktualizována!', 'success');
                await loadReminders();
            } catch (error) {
                console.error("Error updating reminder:");
                showAlert('Nepodařilo se aktualizovat připomínku: ' + (error.message || 'Neznámá chyba'), 'error');
            }
        }

        // Smazání připomínky
        async function deleteReminder(reminderId) {
            if (isServiceWorkspaceRole()) {
                return deleteServiceWorkspaceReminder(reminderId);
            }
            if (!confirm('Opravdu chcete smazat tuto připomínku?')) {
                return;
            }

            try {
                await apiCall(`/api/v1/reminders/${reminderId}`, 'DELETE');
                showAlert('Připomínka byla smazána', 'success');
                await loadReminders();
            } catch (error) {
                console.error("Error deleting reminder:");
                showAlert('Nepodařilo se smazat připomínku: ' + error.message, 'error');
            }
        }

        function getCurrentUserRole() {
            return String(currentUser?.role || 'user').toLowerCase();
        }

        function isServiceReservationsContext() {
            return getActiveWorkspaceMode() === 'service';
        }

        function canCreateReservationFromUi() {
            return isAuthenticated() && (getActiveWorkspaceMode() === 'user' || isServiceReservationsContext());
        }

        function normalizeReservationStatus(status) {
            return String(status || '').toUpperCase().trim();
        }

        function escapeHtml(value) {
            return String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function getReservationTimestamp(rawValue) {
            const parsed = new Date(rawValue);
            if (Number.isNaN(parsed.getTime())) return 0;
            return parsed.getTime();
        }

        function getReservationCalendarViewMode() {
            const mode = String(reservationsUiState.viewMode || '').toLowerCase();
            if (mode === 'month' || mode === 'week' || mode === 'day' || mode === 'list') {
                return mode;
            }
            return reservationsUiState.isServiceView ? 'month' : 'list';
        }

        function padReservationDatePart(value) {
            return String(value).padStart(2, '0');
        }

        function parseReservationDateKey(dateKey) {
            const key = String(dateKey || '').trim();
            const match = key.match(/^(\d{4})-(\d{2})-(\d{2})$/);
            if (!match) return null;
            const parsed = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
            if (Number.isNaN(parsed.getTime())) return null;
            parsed.setHours(0, 0, 0, 0);
            return parsed;
        }

        function getReservationDateKey(rawValue) {
            const parsed = rawValue instanceof Date ? rawValue : new Date(rawValue);
            if (Number.isNaN(parsed.getTime())) {
                return '';
            }
            return `${parsed.getFullYear()}-${padReservationDatePart(parsed.getMonth() + 1)}-${padReservationDatePart(parsed.getDate())}`;
        }

        function formatReservationDateTime(rawValue) {
            const parsed = new Date(rawValue);
            if (Number.isNaN(parsed.getTime())) {
                return '-';
            }
            return `${parsed.toLocaleDateString('cs-CZ')} ${parsed.toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' })}`;
        }

        function formatReservationDateKeyLabel(dateKey) {
            const dateValue = parseReservationDateKey(dateKey);
            if (!dateValue) {
                return 'vybraný den';
            }
            return dateValue.toLocaleDateString('cs-CZ', {
                weekday: 'long',
                day: 'numeric',
                month: 'long',
                year: 'numeric'
            });
        }

        function formatReservationWeekRangeLabel(baseDate) {
            const date = baseDate instanceof Date ? new Date(baseDate.getTime()) : new Date();
            date.setHours(0, 0, 0, 0);
            const mondayOffset = (date.getDay() + 6) % 7;
            const start = new Date(date.getTime());
            start.setDate(start.getDate() - mondayOffset);
            const end = new Date(start.getTime());
            end.setDate(end.getDate() + 6);
            const startLabel = start.toLocaleDateString('cs-CZ', { day: 'numeric', month: 'short' });
            const endLabel = end.toLocaleDateString('cs-CZ', { day: 'numeric', month: 'short', year: 'numeric' });
            return `${startLabel} - ${endLabel}`;
        }

        function getReservationCalendarMonthDate() {
            const anchor = getReservationCalendarAnchorDate();
            return new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        }

        function setReservationCalendarMonthDate(dateValue) {
            if (!(dateValue instanceof Date) || Number.isNaN(dateValue.getTime())) return;
            reservationsUiState.calendarMonthKey = `${dateValue.getFullYear()}-${padReservationDatePart(dateValue.getMonth() + 1)}`;
            setReservationCalendarAnchorDate(new Date(dateValue.getFullYear(), dateValue.getMonth(), 1));
        }

        function getReservationCalendarAnchorDate() {
            const selected = parseReservationDateKey(reservationsUiState.selectedDateKey);
            if (selected) {
                return selected;
            }
            const anchor = parseReservationDateKey(reservationsUiState.calendarAnchorDateKey);
            if (anchor) {
                return anchor;
            }
            const now = new Date();
            now.setHours(0, 0, 0, 0);
            return now;
        }

        function setReservationCalendarAnchorDate(dateValue) {
            if (!(dateValue instanceof Date) || Number.isNaN(dateValue.getTime())) return;
            const normalized = new Date(dateValue.getTime());
            normalized.setHours(0, 0, 0, 0);
            const dateKey = getReservationDateKey(normalized);
            reservationsUiState.calendarAnchorDateKey = dateKey;
            reservationsUiState.selectedDateKey = dateKey;
            reservationsUiState.calendarMonthKey = `${normalized.getFullYear()}-${padReservationDatePart(normalized.getMonth() + 1)}`;
        }

        function shiftReservationCalendarRange(offset) {
            if (!isServiceReservationsContext()) return;
            const step = Number(offset || 0);
            if (!Number.isFinite(step) || step === 0) return;
            const currentMode = getReservationCalendarViewMode();
            const base = getReservationCalendarAnchorDate();
            const shifted = new Date(base.getTime());
            if (currentMode === 'month') {
                shifted.setDate(1);
                shifted.setMonth(shifted.getMonth() + step);
            } else if (currentMode === 'week') {
                shifted.setDate(shifted.getDate() + (step * 7));
            } else {
                shifted.setDate(shifted.getDate() + step);
            }
            setReservationCalendarAnchorDate(shifted);
            renderReservationsFromState();
        }

        function handleReservationCalendarDateInput(event) {
            const raw = String(event?.target?.value || '').trim();
            const date = parseReservationDateKey(raw);
            if (!date) return;
            setReservationCalendarAnchorDate(date);
            renderReservationsFromState();
        }

        function getReservationCalendarCurrentLabel() {
            const mode = getReservationCalendarViewMode();
            const anchor = getReservationCalendarAnchorDate();
            if (mode === 'month') {
                return anchor.toLocaleDateString('cs-CZ', { month: 'long', year: 'numeric' });
            }
            if (mode === 'week') {
                return formatReservationWeekRangeLabel(anchor);
            }
            if (mode === 'day') {
                return formatReservationDateKeyLabel(getReservationDateKey(anchor));
            }
            return 'Seznam všech rezervací';
        }

        function shiftReservationCalendarMonth(offset) {
            shiftReservationCalendarRange(offset);
        }

        function goToReservationCalendarToday() {
            const today = new Date();
            setReservationCalendarAnchorDate(today);
            renderReservationsFromState();
        }

        function selectReservationCalendarDate(dateKey) {
            const key = String(dateKey || '').trim();
            if (!key) return;
            const parsed = parseReservationDateKey(key);
            if (!parsed) return;
            reservationsUiState.selectedDateKey = key;
            reservationsUiState.calendarAnchorDateKey = key;
            reservationsUiState.calendarMonthKey = `${parsed.getFullYear()}-${padReservationDatePart(parsed.getMonth() + 1)}`;
            renderReservationsFromState();
        }

        function setReservationViewMode(mode) {
            if (!isServiceReservationsContext()) return;
            const normalizedMode = String(mode || '').toLowerCase();
            if (!['month', 'week', 'day', 'list'].includes(normalizedMode)) return;
            reservationsUiState.viewMode = normalizedMode;
            if (!reservationsUiState.selectedDateKey) {
                setReservationCalendarAnchorDate(new Date());
            }
            renderReservationsFromState();
        }

        function buildReservationCalendarToolbar(filteredReservations) {
            if (!isServiceReservationsContext()) return '';
            const mode = getReservationCalendarViewMode();
            if (mode === 'list') return '';

            const selectedDateKey = String(reservationsUiState.selectedDateKey || getReservationDateKey(new Date()));
            const label = getReservationCalendarCurrentLabel();
            const itemCount = Array.isArray(filteredReservations) ? filteredReservations.length : 0;
            const countLabel = itemCount === 1 ? '1 rezervace' : `${itemCount} rezervací`;

            return `
                <section class="reservation-calendar-toolbar" aria-label="Nástroje kalendáře">
                    <div class="reservation-calendar-toolbar-nav">
                        <button type="button" class="reservation-calendar-nav-btn" ${legacyActionAttributes("click", "shiftReservationCalendarRange_8a6e74fe")} aria-label="Předchozí období">‹</button>
                        <button type="button" class="reservation-calendar-today-btn" ${legacyActionAttributes("click", "goToReservationCalendarToday_2eee25da")}>Dnes</button>
                        <button type="button" class="reservation-calendar-nav-btn" ${legacyActionAttributes("click", "shiftReservationCalendarRange_3cc667c9")} aria-label="Další období">›</button>
                    </div>
                    <div class="reservation-calendar-toolbar-meta">
                        <strong>${escapeHtml(label)}</strong>
                        <span>${escapeHtml(countLabel)}</span>
                    </div>
                    <div class="reservation-calendar-toolbar-actions">
                        <input
                            type="date"
                            class="reservation-calendar-date-input"
                            value="${escapeHtml(selectedDateKey)}"
                            ${legacyActionAttributes("change", "handleReservationCalendarDateInput_149bcc11")}
                        >
                        <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "exportReservationSelectedDayCsv_61effc93")}>Export dne (CSV)</button>
                        <button type="button" class="btn" ${legacyActionAttributes("click", "suggestReservationNextFreeSlot_78d49974")}>Najít volný slot</button>
                    </div>
                </section>
            `;
        }

        function setReservationStatusFilter(filterValue) {
            reservationsUiState.statusFilter = String(filterValue || 'ALL').toUpperCase();
            renderReservationsFromState();
        }

        function handleReservationCustomerFilterChange(event) {
            reservationsUiState.customerFilter = String(event?.target?.value || 'ALL');
            renderReservationsFromState();
        }

        function handleReservationSearchInput(event) {
            reservationsUiState.query = String(event?.target?.value || '').trim().toLowerCase();
            renderReservationsFromState();
        }

        function handleReservationSortChange(event) {
            reservationsUiState.sortBy = String(event?.target?.value || 'upcoming');
            renderReservationsFromState();
        }

        function getFilteredReservations(baseList) {
            const statusFilter = String(reservationsUiState.statusFilter || 'ALL').toUpperCase();
            const customerFilter = String(reservationsUiState.customerFilter || 'ALL').trim();
            const query = String(reservationsUiState.query || '').trim().toLowerCase();
            const filtered = (Array.isArray(baseList) ? baseList : []).filter((reservation) => {
                const statusKey = normalizeReservationStatus(reservation?.status);
                if (statusFilter !== 'ALL' && statusKey !== statusFilter) {
                    return false;
                }

                if (reservationsUiState.isServiceView && customerFilter !== 'ALL') {
                    const reservationCustomerId = String(reservation?.customer_id ?? '').trim();
                    if (reservationCustomerId !== customerFilter) {
                        return false;
                    }
                }

                if (!query) return true;

                const haystack = [
                    reservation?.service_type,
                    reservation?.note,
                    reservation?.vehicle_name,
                    reservation?.vehicle_plate,
                    reservation?.customer_name,
                    reservation?.customer_email,
                    reservation?.service_name,
                    reservation?.service_email,
                    reservation?.id,
                    reservation?.vehicle_id,
                    reservation?.customer_id,
                    reservation?.service_id
                ]
                    .filter((item) => item !== null && item !== undefined)
                    .map((item) => String(item).toLowerCase())
                    .join(' ');

                return haystack.includes(query);
            });

            const sorted = [...filtered];
            if (reservationsUiState.sortBy === 'newest') {
                sorted.sort((a, b) => getReservationTimestamp(b?.created_at || b?.start_datetime) - getReservationTimestamp(a?.created_at || a?.start_datetime));
            } else {
                sorted.sort((a, b) => getReservationTimestamp(a?.start_datetime) - getReservationTimestamp(b?.start_datetime));
            }

            return sorted;
        }

        function buildReservationServiceDashboard(reservations) {
            const counts = {
                ALL: reservations.length,
                PENDING: reservations.filter((item) => normalizeReservationStatus(item?.status) === 'PENDING').length,
                CONFIRMED: reservations.filter((item) => normalizeReservationStatus(item?.status) === 'CONFIRMED').length,
                COMPLETED: reservations.filter((item) => normalizeReservationStatus(item?.status) === 'COMPLETED').length,
                CANCELLED: reservations.filter((item) => normalizeReservationStatus(item?.status) === 'CANCELLED').length
            };
            const viewMode = getReservationCalendarViewMode();
            const customersMap = new Map();

            reservations.forEach((item) => {
                const customerId = Number(item?.customer_id || 0);
                if (!customerId || customersMap.has(customerId)) return;
                const label = item?.customer_name || item?.customer_email || `Klient #${customerId}`;
                customersMap.set(customerId, {
                    id: customerId,
                    label: String(label || `Klient #${customerId}`)
                });
            });

            const customerOptions = [{ id: 'ALL', label: 'Všichni klienti' }]
                .concat(
                    Array.from(customersMap.values())
                        .sort((a, b) => String(a.label).localeCompare(String(b.label), 'cs'))
                )
                .map((customer) => {
                    const value = String(customer.id);
                    const selected = String(reservationsUiState.customerFilter || 'ALL') === value ? 'selected' : '';
                    return `<option value="${escapeHtml(value)}" ${selected}>${escapeHtml(customer.label)}</option>`;
                })
                .join('');

            const filterButton = (key, label, count) => `
                <button
                    type="button"
                    class="reservation-filter-chip ${reservationsUiState.statusFilter === key ? 'active' : ''}"
                    ${legacyActionAttributes("click", "setReservationStatusFilter_48fa4ff1", key)}
                >
                    <span>${escapeHtml(label)}</span>
                    <strong>${escapeHtml(count)}</strong>
                </button>
            `;

            const viewButton = (key, label) => `
                <button
                    type="button"
                    class="reservation-view-btn ${viewMode === key ? 'active' : ''}"
                    ${legacyActionAttributes("click", "setReservationViewMode_3d65feab", key)}
                >
                    ${escapeHtml(label)}
                </button>
            `;

            return `
                <section class="reservation-dashboard" aria-label="Filtry rezervací servisu">
                    <div class="reservation-dashboard-head">
                        <div>
                            <h3>Servisní rezervace</h3>
                            <p>Plánovač termínů rezervovaných vašimi klienty.</p>
                        </div>
                        <div class="reservation-view-switch" role="tablist" aria-label="Zobrazení rezervací">
                            ${viewButton('month', 'Měsíc')}
                            ${viewButton('week', 'Týden')}
                            ${viewButton('day', 'Den')}
                            ${viewButton('list', 'Seznam')}
                        </div>
                    </div>
                    <div class="reservation-filter-chips">
                        ${filterButton('ALL', 'Vše', counts.ALL)}
                        ${filterButton('PENDING', 'Čeká', counts.PENDING)}
                        ${filterButton('CONFIRMED', 'Potvrzené', counts.CONFIRMED)}
                        ${filterButton('COMPLETED', 'Dokončené', counts.COMPLETED)}
                        ${filterButton('CANCELLED', 'Zrušené', counts.CANCELLED)}
                    </div>
                    <div class="reservation-filter-controls">
                        <input
                            type="search"
                            class="reservation-search-input"
                            placeholder="Hledat podle vozidla, klienta, poznámky..."
                            value="${escapeHtml(reservationsUiState.query || '')}"
                            ${legacyActionAttributes("input", "handleReservationSearchInput_5f062054")}
                        >
                        <select class="reservation-sort-select" ${legacyActionAttributes("change", "handleReservationSortChange_8ab88d54")}>
                            <option value="upcoming" ${reservationsUiState.sortBy === 'upcoming' ? 'selected' : ''}>Nejbližší termín</option>
                            <option value="newest" ${reservationsUiState.sortBy === 'newest' ? 'selected' : ''}>Nejnovější vytvoření</option>
                        </select>
                        <select class="reservation-sort-select reservation-customer-select" ${legacyActionAttributes("change", "handleReservationCustomerFilterChange_494a1ed6")}>
                            ${customerOptions}
                        </select>
                    </div>
                </section>
            `;
        }

        function buildReservationCardsHtml(reservations, isServiceView, statusMap) {
            if (!Array.isArray(reservations) || !reservations.length) {
                return '';
            }

            let cardsHtml = '<div class="reservations-list">';
            reservations.forEach((reservation) => {
                const statusKey = normalizeReservationStatus(reservation.status);
                const statusMeta = statusMap[statusKey] || {
                    label: reservation.status || 'Neznámý stav',
                    className: 'pending'
                };

                const endDate = reservation.end_datetime ? new Date(reservation.end_datetime) : null;
                const startLabel = formatReservationDateTime(reservation.start_datetime);
                const endLabel = (endDate && !Number.isNaN(endDate.getTime()))
                    ? endDate.toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' })
                    : '';
                const dateLine = endLabel ? `${startLabel} - ${endLabel}` : startLabel;

                const vehicleLabel = reservation.vehicle_name || reservation.vehicle_plate || `Vozidlo #${reservation.vehicle_id}`;
                const customerLabel = reservation.customer_name || reservation.customer_email || `Klient #${reservation.customer_id}`;
                const serviceLabel = reservation.service_name || reservation.service_email || `Servis #${reservation.service_id}`;
                const metaLine = isServiceView
                    ? `${customerLabel} • ${vehicleLabel}`
                    : `${serviceLabel} • ${vehicleLabel}`;

                cardsHtml += `
                    <article class="reservation-card ${escapeHtml(statusMeta.className)}">
                        <div class="reservation-card-head">
                            <div>
                                <h3 class="reservation-card-title">${escapeHtml(reservation.service_type || 'Servisní rezervace')}</h3>
                                <div class="reservation-card-datetime">
                                    ${escapeHtml(dateLine)}
                                </div>
                            </div>
                            <span class="reservation-status-pill ${escapeHtml(statusMeta.className)}">
                                ${escapeHtml(statusMeta.label)}
                            </span>
                        </div>
                        <div class="reservation-card-meta">${escapeHtml(metaLine)}</div>
                        ${reservation.note ? `<p class="reservation-card-note">${escapeHtml(reservation.note)}</p>` : ''}
                        <div class="reservation-card-actions">
                            <button type="button" class="btn" ${legacyActionAttributes("click", "openReservationQuickDetail_89beeb1b", reservation.id)}>
                                Detail
                            </button>
                            ${isServiceView && (statusKey === 'PENDING' || statusKey === 'CONFIRMED') ? `
                                <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "openReservationRescheduleModal_151f279c", reservation.id)}>
                                    Upravit termín
                                </button>
                            ` : ''}
                            <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "openVehicleFromShortcut_e1272e05", reservation.vehicle_id)}>
                                Zobrazit vozidlo
                            </button>
                            ${isServiceView && statusKey === 'PENDING' ? `
                                <button type="button" class="btn btn-primary" ${legacyActionAttributes("click", "confirmReservation_eed62221", reservation.id)}>
                                    Potvrdit
                                </button>
                            ` : ''}
                            ${isServiceView && statusKey === 'CONFIRMED' ? `
                                <button type="button" class="btn btn-success" ${legacyActionAttributes("click", "completeReservation_622da3d8", reservation.id)}>
                                    Dokončeno
                                </button>
                            ` : ''}
                            ${(statusKey === 'PENDING' || statusKey === 'CONFIRMED') ? `
                                <button type="button" class="btn btn-danger" ${legacyActionAttributes("click", "cancelReservation_1410752e", reservation.id)}>
                                    ${isServiceView ? 'Zrušit' : 'Zrušit rezervaci'}
                                </button>
                            ` : ''}
                        </div>
                    </article>
                `;
            });
            cardsHtml += '</div>';
            return cardsHtml;
        }

        function getReservationsByDateKey(reservations) {
            const buckets = {};
            (Array.isArray(reservations) ? reservations : []).forEach((reservation) => {
                const dateKey = getReservationDateKey(reservation?.start_datetime);
                if (!dateKey) return;
                if (!buckets[dateKey]) {
                    buckets[dateKey] = [];
                }
                buckets[dateKey].push(reservation);
            });
            Object.values(buckets).forEach((items) => {
                items.sort((a, b) => getReservationTimestamp(a?.start_datetime) - getReservationTimestamp(b?.start_datetime));
            });
            return buckets;
        }

        function getReservationsForDateKey(reservations, dateKey) {
            if (!dateKey) return [];
            const key = String(dateKey).trim();
            return (Array.isArray(reservations) ? reservations : [])
                .filter((item) => getReservationDateKey(item?.start_datetime) === key)
                .sort((a, b) => getReservationTimestamp(a?.start_datetime) - getReservationTimestamp(b?.start_datetime));
        }

        function formatReservationTimeRange(reservation) {
            const start = new Date(reservation?.start_datetime);
            if (Number.isNaN(start.getTime())) return '--:--';
            const startLabel = start.toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' });
            const end = reservation?.end_datetime ? new Date(reservation.end_datetime) : null;
            if (!end || Number.isNaN(end.getTime())) return `${startLabel}`;
            return `${startLabel} - ${end.toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' })}`;
        }

        function getReservationWeekStart(baseDate) {
            const date = baseDate instanceof Date ? new Date(baseDate.getTime()) : new Date();
            date.setHours(0, 0, 0, 0);
            const mondayOffset = (date.getDay() + 6) % 7;
            date.setDate(date.getDate() - mondayOffset);
            return date;
        }

        function buildReservationMonthView(reservations, statusMap) {
            const monthDate = getReservationCalendarMonthDate();
            const year = monthDate.getFullYear();
            const month = monthDate.getMonth();
            const monthPrefix = `${year}-${padReservationDatePart(month + 1)}`;
            const firstDayOffset = (new Date(year, month, 1).getDay() + 6) % 7;
            const daysInMonth = new Date(year, month + 1, 0).getDate();
            const todayKey = getReservationDateKey(new Date());
            const dayBuckets = getReservationsByDateKey(reservations);
            const monthKeysWithEvents = Object.keys(dayBuckets)
                .filter((key) => key.startsWith(`${monthPrefix}-`))
                .sort();

            let selectedDateKey = String(reservationsUiState.selectedDateKey || '').trim();
            if (!selectedDateKey.startsWith(`${monthPrefix}-`)) {
                selectedDateKey = '';
            }
            if (!selectedDateKey && todayKey.startsWith(`${monthPrefix}-`)) {
                selectedDateKey = todayKey;
            }
            if (!selectedDateKey) {
                selectedDateKey = monthKeysWithEvents[0] || `${monthPrefix}-01`;
            }
            reservationsUiState.selectedDateKey = selectedDateKey;
            reservationsUiState.calendarAnchorDateKey = selectedDateKey;

            const totalCells = Math.max(35, Math.ceil((firstDayOffset + daysInMonth) / 7) * 7);
            const cellsHtml = [];
            for (let cellIndex = 0; cellIndex < totalCells; cellIndex += 1) {
                const dayNumber = cellIndex - firstDayOffset + 1;
                if (dayNumber < 1 || dayNumber > daysInMonth) {
                    cellsHtml.push('<div class="reservation-calendar-day is-empty" aria-hidden="true"></div>');
                    continue;
                }

                const dateKey = `${monthPrefix}-${padReservationDatePart(dayNumber)}`;
                const dayItems = dayBuckets[dateKey] || [];
                const classes = ['reservation-calendar-day'];
                if (dayItems.length) classes.push('has-events');
                if (dateKey === todayKey) classes.push('is-today');
                if (dateKey === selectedDateKey) classes.push('is-selected');

                const dayEvents = dayItems.slice(0, 2).map((item) => {
                    const customerLabel = String(item?.customer_name || item?.customer_email || `Klient #${item?.customer_id || ''}`);
                    const compactCustomer = customerLabel.length > 18 ? `${customerLabel.slice(0, 18)}…` : customerLabel;
                    const statusClass = statusMap[normalizeReservationStatus(item?.status)]?.className || 'pending';
                    return `<span class="reservation-calendar-event ${escapeHtml(statusClass)}">${escapeHtml(formatReservationTimeRange(item))} ${escapeHtml(compactCustomer)}</span>`;
                }).join('');

                const daySummary = dayItems.length > 2
                    ? `<span class="reservation-calendar-overflow">+${dayItems.length - 2} další</span>`
                    : '';

                cellsHtml.push(`
                    <div class="${classes.join(' ')}">
                        <button type="button" class="reservation-calendar-day-btn" ${legacyActionAttributes("click", "selectReservationCalendarDate_c6dce091", dateKey)}>
                            <span class="reservation-calendar-day-top">
                                <span class="reservation-calendar-day-number">${dayNumber}</span>
                                ${dayItems.length ? `<span class="reservation-calendar-day-count">${escapeHtml(dayItems.length)}</span>` : ''}
                            </span>
                            <span class="reservation-calendar-events">
                                ${dayEvents}
                                ${daySummary}
                            </span>
                        </button>
                    </div>
                `);
            }

            const weekdays = ['Po', 'Út', 'St', 'Čt', 'Pá', 'So', 'Ne']
                .map((label) => `<span class="reservation-calendar-weekday">${escapeHtml(label)}</span>`)
                .join('');

            return {
                viewHtml: `
                    <section class="reservation-calendar" aria-label="Měsíční kalendář rezervací">
                        <div class="reservation-calendar-weekdays">${weekdays}</div>
                        <div class="reservation-calendar-grid">${cellsHtml.join('')}</div>
                    </section>
                `,
                selectedDateKey,
                selectedDateLabel: formatReservationDateKeyLabel(selectedDateKey),
                selectedReservations: dayBuckets[selectedDateKey] || []
            };
        }

        function buildReservationWeekView(reservations, statusMap) {
            const anchorDate = getReservationCalendarAnchorDate();
            const weekStart = getReservationWeekStart(anchorDate);
            const dayBuckets = getReservationsByDateKey(reservations);
            let selectedDateKey = String(reservationsUiState.selectedDateKey || '').trim() || getReservationDateKey(anchorDate);
            const selectedDate = parseReservationDateKey(selectedDateKey);
            const weekEnd = new Date(weekStart.getTime());
            weekEnd.setDate(weekStart.getDate() + 6);
            if (!selectedDate || selectedDate < weekStart || selectedDate > weekEnd) {
                selectedDateKey = getReservationDateKey(anchorDate);
            }
            const weekCells = [];

            for (let i = 0; i < 7; i += 1) {
                const dayDate = new Date(weekStart.getTime());
                dayDate.setDate(weekStart.getDate() + i);
                const dateKey = getReservationDateKey(dayDate);
                const dayItems = dayBuckets[dateKey] || [];
                const weekdayLabel = dayDate.toLocaleDateString('cs-CZ', { weekday: 'short' });
                const dayLabel = dayDate.toLocaleDateString('cs-CZ', { day: 'numeric', month: 'numeric' });
                const isToday = dateKey === getReservationDateKey(new Date());
                const isSelected = dateKey === selectedDateKey;
                const cardClasses = ['reservation-week-day'];
                if (isToday) cardClasses.push('is-today');
                if (isSelected) cardClasses.push('is-selected');

                const eventsHtml = dayItems.length
                    ? dayItems.map((item) => {
                        const statusClass = statusMap[normalizeReservationStatus(item?.status)]?.className || 'pending';
                        const title = item?.service_type || 'Rezervace';
                        const customer = item?.customer_name || item?.customer_email || `Klient #${item?.customer_id || ''}`;
                        return `
                            <button type="button" class="reservation-week-event ${escapeHtml(statusClass)}" ${legacyActionAttributes("click", "openReservationQuickDetail_89beeb1b", Number(item.id))}>
                                <strong>${escapeHtml(formatReservationTimeRange(item))}</strong>
                                <span>${escapeHtml(title)}</span>
                                <small>${escapeHtml(customer)}</small>
                            </button>
                        `;
                    }).join('')
                    : '<div class="reservation-week-empty">Bez rezervace</div>';

                weekCells.push(`
                    <article class="${cardClasses.join(' ')}">
                        <button type="button" class="reservation-week-day-head" ${legacyActionAttributes("click", "selectReservationCalendarDate_c6dce091", dateKey)}>
                            <span>${escapeHtml(weekdayLabel)}</span>
                            <strong>${escapeHtml(dayLabel)}</strong>
                            <em>${escapeHtml(dayItems.length)}</em>
                        </button>
                        <div class="reservation-week-events">${eventsHtml}</div>
                    </article>
                `);
            }

            reservationsUiState.selectedDateKey = selectedDateKey;
            reservationsUiState.calendarAnchorDateKey = selectedDateKey;

            return {
                viewHtml: `
                    <section class="reservation-week" aria-label="Týdenní kalendář rezervací">
                        <div class="reservation-week-grid">
                            ${weekCells.join('')}
                        </div>
                    </section>
                `,
                selectedDateKey,
                selectedDateLabel: formatReservationDateKeyLabel(selectedDateKey),
                selectedReservations: dayBuckets[selectedDateKey] || []
            };
        }

        function buildReservationDayView(reservations, statusMap) {
            const selectedDate = parseReservationDateKey(reservationsUiState.selectedDateKey) || getReservationCalendarAnchorDate();
            const selectedDateKey = getReservationDateKey(selectedDate);
            const dayReservations = getReservationsForDateKey(reservations, selectedDateKey);
            const hourStart = 6;
            const hourEnd = 20;
            const hourRows = [];

            for (let hour = hourStart; hour <= hourEnd; hour += 1) {
                const hourItems = dayReservations.filter((item) => {
                    const start = new Date(item?.start_datetime);
                    return !Number.isNaN(start.getTime()) && start.getHours() === hour;
                });
                const hourLabel = `${padReservationDatePart(hour)}:00`;
                const hourEvents = hourItems.length
                    ? hourItems.map((item) => {
                        const statusClass = statusMap[normalizeReservationStatus(item?.status)]?.className || 'pending';
                        const vehicle = item?.vehicle_name || item?.vehicle_plate || `Vozidlo #${item?.vehicle_id || ''}`;
                        return `
                            <button type="button" class="reservation-day-event ${escapeHtml(statusClass)}" ${legacyActionAttributes("click", "openReservationQuickDetail_89beeb1b", Number(item.id))}>
                                <strong>${escapeHtml(formatReservationTimeRange(item))}</strong>
                                <span>${escapeHtml(item?.service_type || 'Servisní rezervace')}</span>
                                <small>${escapeHtml(vehicle)}</small>
                            </button>
                        `;
                    }).join('')
                    : '<div class="reservation-day-empty-slot">-</div>';

                hourRows.push(`
                    <div class="reservation-day-hour-row">
                        <div class="reservation-day-hour-label">${escapeHtml(hourLabel)}</div>
                        <div class="reservation-day-hour-content">${hourEvents}</div>
                    </div>
                `);
            }

            reservationsUiState.selectedDateKey = selectedDateKey;
            reservationsUiState.calendarAnchorDateKey = selectedDateKey;

            return {
                viewHtml: `
                    <section class="reservation-day" aria-label="Denní plán rezervací">
                        <div class="reservation-day-timeline">
                            ${hourRows.join('')}
                        </div>
                    </section>
                `,
                selectedDateKey,
                selectedDateLabel: formatReservationDateKeyLabel(selectedDateKey),
                selectedReservations: dayReservations
            };
        }

        function getReservationByIdFromState(reservationId) {
            const id = Number(reservationId || 0);
            if (!id) return null;
            const list = Array.isArray(reservationsUiState.all) ? reservationsUiState.all : [];
            return list.find((item) => Number(item?.id || 0) === id) || null;
        }

        function closeReservationQuickDetailModal() {
            unmountFloatingModal();
        }

        function closeReservationRescheduleModal(force = false) {
            if (!force && reservationRescheduleState.submitting) {
                return;
            }
            reservationRescheduleState.submitting = false;
            reservationRescheduleState.reservationId = 0;
            unmountFloatingModal();
        }

        function formatReservationLocalDateInput(rawValue) {
            const parsed = new Date(rawValue);
            if (Number.isNaN(parsed.getTime())) return '';
            return `${parsed.getFullYear()}-${padReservationDatePart(parsed.getMonth() + 1)}-${padReservationDatePart(parsed.getDate())}`;
        }

        function formatReservationLocalTimeInput(rawValue) {
            const parsed = new Date(rawValue);
            if (Number.isNaN(parsed.getTime())) return '';
            return `${padReservationDatePart(parsed.getHours())}:${padReservationDatePart(parsed.getMinutes())}`;
        }

        function openReservationRescheduleModal(reservationId) {
            if (!isServiceReservationsContext()) {
                showAlert('Přeplánování je dostupné pouze pro servisní účet.', 'warning');
                return;
            }
            const reservation = getReservationByIdFromState(reservationId);
            if (!reservation) {
                showAlert('Rezervaci se nepodařilo dohledat. Zkuste obnovit načtení.', 'warning');
                return;
            }
            const statusKey = normalizeReservationStatus(reservation?.status);
            if (!['PENDING', 'CONFIRMED'].includes(statusKey)) {
                showAlert('Termín lze upravit pouze u čekajících nebo potvrzených rezervací.', 'warning');
                return;
            }

            const startDateValue = formatReservationLocalDateInput(reservation.start_datetime);
            const startTimeValue = formatReservationLocalTimeInput(reservation.start_datetime);
            const endDateValue = reservation.end_datetime ? formatReservationLocalDateInput(reservation.end_datetime) : '';
            const endTimeValue = reservation.end_datetime ? formatReservationLocalTimeInput(reservation.end_datetime) : '';
            const defaultStatusAction = statusKey === 'PENDING' ? 'keep' : 'confirmed';

            mountFloatingModal(`
                <div class="reminder-modal-overlay" ${legacyActionAttributes("click", "closeReservationRescheduleModal_06ba2dac")}>
                    <div class="reminder-modal reservation-detail-modal reservation-reschedule-modal service-account-modal">
                        <form class="reservation-reschedule-form service-account-form" ${legacyActionAttributes("submit", "handleReservationRescheduleSubmit_1192bc4b", Number(reservation.id))}>
                            <div class="reminder-modal-head">
                                <div class="reminder-modal-heading">
                                    <div>
                                        <p class="reminder-modal-kicker">Přeplánování rezervace #${Number(reservation.id)}</p>
                                        <h2 class="modal-title">${escapeHtml(reservation?.service_type || 'Servisní rezervace')}</h2>
                                    </div>
                                </div>
                                <button type="button" class="reminder-modal-close" aria-label="Zavřít okno" ${legacyActionAttributes("click", "closeReservationRescheduleModal_b19ca30e")}>×</button>
                            </div>
                            <p class="reminder-modal-intro">Upravte termín. Zákazník dostane automaticky e-mail s novým datem a časem.</p>

                            <div class="form-grid">
                                <div class="form-row span-2">
                                    <label>Nový začátek rezervace *:</label>
                                    <div class="reservation-datetime-row">
                                        <input type="date" id="rescheduleStartDate" required value="${escapeHtml(startDateValue)}">
                                        <input type="time" id="rescheduleStartTime" required value="${escapeHtml(startTimeValue)}">
                                    </div>
                                </div>
                                <div class="form-row span-2">
                                    <label>Nový konec rezervace (volitelné):</label>
                                    <div class="reservation-datetime-row">
                                        <input type="date" id="rescheduleEndDate" value="${escapeHtml(endDateValue)}">
                                        <input type="time" id="rescheduleEndTime" value="${escapeHtml(endTimeValue)}">
                                    </div>
                                </div>
                                <div class="form-row span-2">
                                    <label for="rescheduleStatusAction">Po uložení:</label>
                                    <select id="rescheduleStatusAction">
                                        <option value="keep" ${defaultStatusAction === 'keep' ? 'selected' : ''}>Pouze změnit termín</option>
                                        <option value="confirmed" ${defaultStatusAction === 'confirmed' ? 'selected' : ''}>Změnit termín a potvrdit rezervaci</option>
                                    </select>
                                </div>
                            </div>

                            <div class="form-actions reservation-detail-actions">
                                <button type="submit" class="btn btn-primary">Uložit nový termín</button>
                                <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "closeReservationRescheduleModal_b19ca30e")}>Zrušit</button>
                            </div>
                        </form>
                    </div>
                </div>
            `);
            reservationRescheduleState.reservationId = Number(reservation.id);
            setReservationRescheduleSubmitting(false);
        }

        function setReservationRescheduleSubmitting(isSubmitting) {
            reservationRescheduleState.submitting = !!isSubmitting;
            const root = document.getElementById(APP_FLOATING_MODAL_ROOT_ID);
            if (!root) return;
            const form = root.querySelector('.reservation-reschedule-form');
            if (!form) return;

            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn) {
                const defaultLabel = String(submitBtn.dataset.defaultLabel || submitBtn.textContent || 'Uložit nový termín');
                submitBtn.dataset.defaultLabel = defaultLabel;
                submitBtn.disabled = !!isSubmitting;
                submitBtn.textContent = isSubmitting ? 'Ukládám…' : defaultLabel;
                submitBtn.setAttribute('aria-disabled', isSubmitting ? 'true' : 'false');
            }

            form.querySelectorAll('button[type="button"], .reminder-modal-close, input, select, textarea').forEach((element) => {
                if (element === submitBtn) return;
                element.disabled = !!isSubmitting;
                element.setAttribute('aria-disabled', isSubmitting ? 'true' : 'false');
            });
            form.setAttribute('aria-busy', isSubmitting ? 'true' : 'false');
        }

        async function handleReservationRescheduleSubmit(reservationId) {
            const reservationIdNum = Number(reservationId || 0);
            if (!reservationIdNum) {
                showAlert('Neplatná rezervace.', 'error');
                return;
            }
            if (reservationRescheduleState.submitting && reservationRescheduleState.reservationId === reservationIdNum) {
                return;
            }

            const reservation = getReservationByIdFromState(reservationId);
            if (!reservation) {
                showAlert('Rezervaci se nepodařilo dohledat. Zkuste obnovit načtení.', 'error');
                return;
            }

            const startDate = String(document.getElementById('rescheduleStartDate')?.value || '').trim();
            const startTime = String(document.getElementById('rescheduleStartTime')?.value || '').trim();
            const endDate = String(document.getElementById('rescheduleEndDate')?.value || '').trim();
            const endTime = String(document.getElementById('rescheduleEndTime')?.value || '').trim();
            const statusAction = String(document.getElementById('rescheduleStatusAction')?.value || 'keep').trim();

            if (!startDate || !startTime) {
                showAlert('Vyplňte datum a čas začátku.', 'error');
                return;
            }

            const startDatetime = new Date(`${startDate}T${startTime}:00`);
            if (Number.isNaN(startDatetime.getTime())) {
                showAlert('Neplatný formát začátku rezervace.', 'error');
                return;
            }

            let endDatetime = null;
            if (endDate || endTime) {
                if (!endDate || !endTime) {
                    showAlert('Pro konec rezervace vyplňte datum i čas, nebo nechte obě pole prázdná.', 'error');
                    return;
                }
                endDatetime = new Date(`${endDate}T${endTime}:00`);
                if (Number.isNaN(endDatetime.getTime())) {
                    showAlert('Neplatný formát konce rezervace.', 'error');
                    return;
                }
                if (endDatetime <= startDatetime) {
                    showAlert('Konec rezervace musí být po začátku.', 'error');
                    return;
                }
            }

            const payload = {
                start_datetime: startDatetime.toISOString(),
                end_datetime: endDatetime ? endDatetime.toISOString() : null,
            };
            if (statusAction === 'confirmed') {
                payload.status = 'CONFIRMED';
            }

            try {
                reservationRescheduleState.reservationId = reservationIdNum;
                setReservationRescheduleSubmitting(true);
                showAlert('Ukládám nový termín rezervace...', 'info');
                await apiCall(`/api/v1/reservations/${reservationIdNum}`, 'PUT', payload);
                closeReservationRescheduleModal(true);
                showAlert('Termín byl upraven. Zákazník byl informován e-mailem.', 'success');
                await loadReservations();
            } catch (error) {
                console.error("Error rescheduling reservation:");
                showAlert(`Nepodařilo se upravit termín rezervace: ${error?.message || 'Neznámá chyba'}`, 'error');
                setReservationRescheduleSubmitting(false);
            }
        }

        function openReservationQuickDetail(reservationId) {
            const reservation = getReservationByIdFromState(reservationId);
            if (!reservation) {
                showAlert('Rezervaci se nepodařilo dohledat. Zkuste obnovit načtení.', 'warning');
                return;
            }
            const statusKey = normalizeReservationStatus(reservation?.status);
            const statusMap = {
                PENDING: { label: 'Čeká na potvrzení', className: 'pending' },
                CONFIRMED: { label: 'Potvrzeno', className: 'confirmed' },
                CANCELLED: { label: 'Zrušeno', className: 'cancelled' },
                COMPLETED: { label: 'Dokončeno', className: 'completed' }
            };
            const statusMeta = statusMap[statusKey] || { label: reservation?.status || 'Neznámý stav', className: 'pending' };
            const customerLabel = reservation?.customer_name || reservation?.customer_email || `Klient #${reservation?.customer_id || ''}`;
            const serviceLabel = reservation?.service_name || reservation?.service_email || `Servis #${reservation?.service_id || ''}`;
            const vehicleLabel = reservation?.vehicle_name || reservation?.vehicle_plate || `Vozidlo #${reservation?.vehicle_id || ''}`;
            const endDate = reservation?.end_datetime ? new Date(reservation.end_datetime) : null;
            const endTimeLabel = endDate && !Number.isNaN(endDate.getTime())
                ? ` - ${endDate.toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' })}`
                : '';

            const actionButtons = [];
            if (reservationsUiState.isServiceView && (statusKey === 'PENDING' || statusKey === 'CONFIRMED')) {
                actionButtons.push(`<button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "closeReservationQuickDetailModal_6c757235", Number(reservation.id))}>Upravit termín</button>`);
            }
            actionButtons.push(`<button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "closeReservationQuickDetailModal_00c72967", Number(reservation.vehicle_id))}>Zobrazit vozidlo</button>`);
            if (reservationsUiState.isServiceView && statusKey === 'PENDING') {
                actionButtons.push(`<button type="button" class="btn btn-primary" ${legacyActionAttributes("click", "confirmReservation_eed62221", Number(reservation.id))}>Potvrdit</button>`);
            }
            if (reservationsUiState.isServiceView && statusKey === 'CONFIRMED') {
                actionButtons.push(`<button type="button" class="btn btn-success" ${legacyActionAttributes("click", "completeReservation_622da3d8", Number(reservation.id))}>Dokončeno</button>`);
            }
            if (statusKey === 'PENDING' || statusKey === 'CONFIRMED') {
                actionButtons.push(`<button type="button" class="btn btn-danger" ${legacyActionAttributes("click", "cancelReservation_1410752e", Number(reservation.id))}>Zrušit rezervaci</button>`);
            }
            actionButtons.push("<button type=\"button\" class=\"btn btn-secondary\" data-legacy-click=\"closeReservationQuickDetailModal_afdb30ff\" data-legacy-click-args=\"[]\">Zavřít</button>");

            mountFloatingModal(`
                <div class="reminder-modal-overlay" ${legacyActionAttributes("click", "closeReservationQuickDetailModal_39bbfa52")}>
                    <div class="reminder-modal reservation-detail-modal">
                        <div class="reminder-modal-head">
                            <div class="reminder-modal-heading">
                                <div>
                                    <p class="reminder-modal-kicker">Rezervace #${Number(reservation.id)}</p>
                                    <h2 class="modal-title">${escapeHtml(reservation?.service_type || 'Servisní rezervace')}</h2>
                                </div>
                            </div>
                            <button type="button" class="reminder-modal-close" aria-label="Zavřít okno" ${legacyActionAttributes("click", "closeReservationQuickDetailModal_afdb30ff")}>×</button>
                        </div>
                        <div class="reservation-detail-body">
                            <p><strong>Stav:</strong> <span class="reservation-status-pill ${escapeHtml(statusMeta.className)}">${escapeHtml(statusMeta.label)}</span></p>
                            <p><strong>Termín:</strong> ${escapeHtml(formatReservationDateTime(reservation?.start_datetime))}${escapeHtml(endTimeLabel)}</p>
                            <p><strong>Klient:</strong> ${escapeHtml(customerLabel)}</p>
                            <p><strong>Servis:</strong> ${escapeHtml(serviceLabel)}</p>
                            <p><strong>Vozidlo:</strong> ${escapeHtml(vehicleLabel)}</p>
                            ${reservation?.note ? `<p><strong>Poznámka:</strong><br>${escapeHtml(reservation.note)}</p>` : '<p><strong>Poznámka:</strong> -</p>'}
                        </div>
                        <div class="form-actions reservation-detail-actions">
                            ${actionButtons.join('')}
                        </div>
                    </div>
                </div>
            `);
        }

        function escapeReservationCsvField(value) {
            const raw = String(value ?? '');
            if (/[",;\n]/.test(raw)) {
                return `"${raw.replace(/"/g, '""')}"`;
            }
            return raw;
        }

        function downloadReservationFile(filename, content, mimeType = 'text/plain;charset=utf-8') {
            const blob = new Blob([content], { type: mimeType });
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 2000);
        }

        function exportReservationSelectedDayCsv() {
            if (!isServiceReservationsContext()) return;
            const selectedDateKey = String(reservationsUiState.selectedDateKey || getReservationDateKey(new Date()));
            const filtered = getFilteredReservations(reservationsUiState.all);
            const dayReservations = getReservationsForDateKey(filtered, selectedDateKey);
            if (!dayReservations.length) {
                showAlert('Ve vybraném dni nejsou žádné rezervace pro export.', 'warning');
                return;
            }

            const header = ['ID', 'Datum', 'Čas od', 'Čas do', 'Stav', 'Typ služby', 'Klient', 'Email klienta', 'Vozidlo', 'SPZ', 'Poznámka'];
            const rows = dayReservations.map((item) => {
                const start = new Date(item?.start_datetime);
                const end = item?.end_datetime ? new Date(item.end_datetime) : null;
                const dateLabel = Number.isNaN(start.getTime()) ? '' : start.toLocaleDateString('cs-CZ');
                const startLabel = Number.isNaN(start.getTime()) ? '' : start.toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' });
                const endLabel = end && !Number.isNaN(end.getTime())
                    ? end.toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' })
                    : '';
                return [
                    item?.id || '',
                    dateLabel,
                    startLabel,
                    endLabel,
                    item?.status || '',
                    item?.service_type || '',
                    item?.customer_name || '',
                    item?.customer_email || '',
                    item?.vehicle_name || '',
                    item?.vehicle_plate || '',
                    item?.note || ''
                ];
            });

            const csv = [header, ...rows]
                .map((columns) => columns.map((col) => escapeReservationCsvField(col)).join(';'))
                .join('\n');
            const fileDate = selectedDateKey.replace(/-/g, '');
            downloadReservationFile(`rezervace_${fileDate}.csv`, csv, 'text/csv;charset=utf-8');
            showAlert('Export denního plánu byl stažen jako CSV.', 'success');
        }

        function findNextReservationFreeSlot(reservations, options = {}) {
            const durationMinutes = Math.max(15, Number(options.durationMinutes || 60));
            const stepMinutes = Math.max(15, Number(options.stepMinutes || 30));
            const lookAheadDays = Math.max(7, Number(options.lookAheadDays || 45));
            const workStartHour = Math.max(0, Number(options.workStartHour || 8));
            const workEndHour = Math.min(23, Number(options.workEndHour || 17));
            const businessDaysOnly = options.businessDaysOnly !== false;

            const now = new Date();
            now.setSeconds(0, 0);
            const minuteRemainder = now.getMinutes() % stepMinutes;
            if (minuteRemainder !== 0) {
                now.setMinutes(now.getMinutes() + (stepMinutes - minuteRemainder));
            }

            const busyIntervals = (Array.isArray(reservations) ? reservations : [])
                .filter((item) => {
                    const status = normalizeReservationStatus(item?.status);
                    return status !== 'CANCELLED';
                })
                .map((item) => {
                    const start = new Date(item?.start_datetime);
                    if (Number.isNaN(start.getTime())) return null;
                    const end = item?.end_datetime ? new Date(item.end_datetime) : new Date(start.getTime() + durationMinutes * 60000);
                    if (Number.isNaN(end.getTime())) return null;
                    return { start, end };
                })
                .filter(Boolean);

            const slotOverlaps = (slotStart, slotEnd) => busyIntervals.some((interval) => (
                slotStart < interval.end && slotEnd > interval.start
            ));

            for (let dayOffset = 0; dayOffset <= lookAheadDays; dayOffset += 1) {
                const day = new Date(now.getTime());
                day.setDate(now.getDate() + dayOffset);
                day.setHours(0, 0, 0, 0);
                const dayOfWeek = day.getDay();
                if (businessDaysOnly && (dayOfWeek === 0 || dayOfWeek === 6)) {
                    continue;
                }

                const dayStart = new Date(day.getTime());
                dayStart.setHours(workStartHour, 0, 0, 0);
                const dayEnd = new Date(day.getTime());
                dayEnd.setHours(workEndHour, 0, 0, 0);

                let slot = new Date(Math.max(dayStart.getTime(), now.getTime()));
                const slotRemainder = slot.getMinutes() % stepMinutes;
                if (slotRemainder !== 0) {
                    slot.setMinutes(slot.getMinutes() + (stepMinutes - slotRemainder), 0, 0);
                }

                while (slot < dayEnd) {
                    const slotEnd = new Date(slot.getTime() + durationMinutes * 60000);
                    if (slotEnd > dayEnd) break;
                    if (!slotOverlaps(slot, slotEnd)) {
                        return { start: slot, end: slotEnd };
                    }
                    slot = new Date(slot.getTime() + stepMinutes * 60000);
                }
            }

            return null;
        }

        function suggestReservationNextFreeSlot() {
            if (!isServiceReservationsContext()) return;
            const filtered = getFilteredReservations(reservationsUiState.all).filter((item) => normalizeReservationStatus(item?.status) !== 'CANCELLED');
            const slot = findNextReservationFreeSlot(filtered, {
                durationMinutes: 60,
                stepMinutes: 30,
                lookAheadDays: 45,
                workStartHour: 8,
                workEndHour: 17,
                businessDaysOnly: true
            });
            if (!slot) {
                showAlert('V příštích týdnech se nepodařilo najít volný hodinový slot v pracovních dnech.', 'warning');
                return;
            }

            const label = `${slot.start.toLocaleDateString('cs-CZ')} ${slot.start.toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' })} - ${slot.end.toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' })}`;
            reservationsUiState.viewMode = 'day';
            setReservationCalendarAnchorDate(slot.start);
            showAlert(`Nejbližší volný slot: ${label}`, 'success');
            renderReservationsFromState();
        }

        function renderReservationsFromState() {
            const container = document.getElementById('reservationsContainer');
            if (!container) return;

            const isServiceView = !!reservationsUiState.isServiceView;
            const heading = document.getElementById('reservationsHeading');
            if (heading) {
                heading.textContent = isServiceView ? 'Rezervační plán servisu' : 'Moje rezervace';
            }

            if (isServiceView) {
                if (!['month', 'week', 'day', 'list'].includes(String(reservationsUiState.viewMode || '').toLowerCase())) {
                    reservationsUiState.viewMode = 'month';
                }
                if (!reservationsUiState.selectedDateKey) {
                    setReservationCalendarAnchorDate(new Date());
                }
            } else {
                reservationsUiState.viewMode = 'list';
            }

            const allReservations = Array.isArray(reservationsUiState.all) ? reservationsUiState.all : [];
            const reservations = getFilteredReservations(allReservations);
            const statusMap = {
                PENDING: { label: 'Čeká na potvrzení', className: 'pending' },
                CONFIRMED: { label: 'Potvrzeno', className: 'confirmed' },
                CANCELLED: { label: 'Zrušeno', className: 'cancelled' },
                COMPLETED: { label: 'Dokončeno', className: 'completed' }
            };

            let html = '<div class="reservations-shell">';
            if (isServiceView) {
                html += buildReservationServiceDashboard(allReservations);
                html += buildReservationCalendarToolbar(reservations);
            }

            if (!reservations.length) {
                html += `
                    <div class="reservation-empty">
                        ${isServiceView
                            ? 'Podle zvolených filtrů nebyly nalezeny žádné rezervace.'
                            : 'Nemáte žádné rezervace. Vytvořte novou pomocí tlačítka níže.'}
                    </div>
                `;
            } else {
                if (isServiceView) {
                    const viewMode = getReservationCalendarViewMode();
                    if (viewMode === 'list') {
                        html += buildReservationCardsHtml(reservations, true, statusMap);
                    } else {
                        let calendarPayload = null;
                        if (viewMode === 'month') {
                            calendarPayload = buildReservationMonthView(reservations, statusMap);
                        } else if (viewMode === 'week') {
                            calendarPayload = buildReservationWeekView(reservations, statusMap);
                        } else {
                            calendarPayload = buildReservationDayView(reservations, statusMap);
                        }

                        const selectedReservations = Array.isArray(calendarPayload?.selectedReservations)
                            ? calendarPayload.selectedReservations
                            : [];
                        const selectedCount = selectedReservations.length;
                        const selectedCountLabel = selectedCount === 1 ? '1 rezervace' : `${selectedCount} rezervací`;

                        html += String(calendarPayload?.viewHtml || '');
                        html += `
                            <section class="reservation-selected-day">
                                <div class="reservation-selected-day-head">
                                    <h4>Termíny pro ${escapeHtml(calendarPayload?.selectedDateLabel || 'vybraný den')}</h4>
                                    <span>${escapeHtml(selectedCountLabel)}</span>
                                </div>
                                ${selectedReservations.length
                                    ? buildReservationCardsHtml(selectedReservations, true, statusMap)
                                    : `<div class="reservation-empty">Pro ${escapeHtml(calendarPayload?.selectedDateLabel || 'vybraný den')} nejsou žádné rezervace.</div>`}
                            </section>
                        `;
                    }
                } else {
                    html += buildReservationCardsHtml(reservations, false, statusMap);
                }
            }

            if (canCreateReservationFromUi()) {
                html += `
                    <div class="reservation-actions">
                        <button type="button" class="btn btn-primary" ${legacyActionAttributes("click", "showCreateReservationForm_f65cf47c")}>Vytvořit novou rezervaci</button>
                    </div>
                `;
            } else {
                html += `
                    <div class="reservation-scope-note">
                        Rezervace vytváří zákazníci. Zde spravujete přiřazené termíny servisu.
                    </div>
                `;
            }

            html += '</div>';
            container.innerHTML = html;
        }

        // Načítání rezervací (v1.0)
        async function loadReservations(force = true) {
            const renderStartTs = performance.now();
            unmountFloatingModal();
            const container = document.getElementById('reservationsContainer');
            if (!container) return;

            // Kontrola auth stavu
            if (!isAuthenticated()) {
                console.warn("[RESERVATIONS] Uživatel není přihlášen");
                return;
            }

            const cacheOwnerKey = getUiCacheOwnerKey();
            if (!force
                && isUiSectionCacheFresh(reservationsUiState)
                && container.dataset.renderedFor === cacheOwnerKey
                && container.innerHTML.trim()) {
                renderReservationsFromState();
                return;
            }

            container.innerHTML = '<div class="loading">Načítám rezervace...</div>';

            try {
                const isServiceView = isServiceReservationsContext();
                const endpoint = isServiceView ? '/api/v1/reservations/service' : '/api/v1/reservations/my';
                const reservations = await apiCall(endpoint, 'GET');
                reservationsUiState.isServiceView = isServiceView;
                reservationsUiState.all = Array.isArray(reservations) ? reservations : [];
                reservationsUiState.statusFilter = 'ALL';
                reservationsUiState.customerFilter = 'ALL';
                reservationsUiState.query = '';
                reservationsUiState.sortBy = 'upcoming';
                if (isServiceView) {
                    if (!['month', 'week', 'day', 'list'].includes(String(reservationsUiState.viewMode || '').toLowerCase())) {
                        reservationsUiState.viewMode = 'month';
                    }
                    if (!reservationsUiState.selectedDateKey) {
                        setReservationCalendarAnchorDate(new Date());
                    }
                    if (pendingServiceReservationsCustomerFilter !== null) {
                        reservationsUiState.customerFilter = String(pendingServiceReservationsCustomerFilter);
                        pendingServiceReservationsCustomerFilter = null;
                    }
                } else {
                    reservationsUiState.viewMode = 'list';
                    reservationsUiState.calendarAnchorDateKey = '';
                    reservationsUiState.calendarMonthKey = '';
                    reservationsUiState.selectedDateKey = '';
                }
                container.dataset.renderedFor = cacheOwnerKey;
                markUiSectionLoaded(reservationsUiState);
                renderReservationsFromState();

            } catch (error) {
                reservationsUiState.loadedAt = 0;
                console.error("[RESERVATIONS] Error loading reservations:");
                const errorMessage = error.message || 'Neznámá chyba';
                const canCreate = canCreateReservationFromUi();
                container.innerHTML = `
                    <div class="alert alert-error" style="margin: 20px 0;">
                        <strong>Chyba:</strong> Nepodařilo se načíst rezervace: ${escapeHtml(errorMessage)}
                        <br><br>
                        <button class="btn btn-primary" ${legacyActionAttributes("click", "loadReservations_f26a788a")} style="margin-top: 10px;">
                            Zkusit znovu
                        </button>
                        ${canCreate ? `
                            <button class="btn btn-secondary" ${legacyActionAttributes("click", "showCreateReservationForm_f65cf47c")} style="margin-top: 10px; margin-left: 10px;">
                                Vytvořit novou rezervaci
                            </button>
                        ` : ''}
                    </div>
                `;
            }
        }

        function formatServicesDistance(value) {
            const km = Number(value);
            if (!Number.isFinite(km) || km < 0) {
                return null;
            }
            const decimals = km < 10 ? 1 : 0;
            return `${km.toLocaleString('cs-CZ', { minimumFractionDigits: 0, maximumFractionDigits: decimals })} km`;
        }

        function buildServiceAddressLine(service) {
            const directAddress = String(service?.address || '').trim();
            if (directAddress) return directAddress;
            const street = [service?.street, service?.street_number].filter(Boolean).join(' ').trim();
            const cityZip = [service?.zip, service?.city].filter(Boolean).join(' ').trim();
            return [street, cityZip].filter(Boolean).join(', ') || 'Adresa není uvedena';
        }

        function buildServiceVehicleAccessKey(serviceId, vehicleId) {
            return `${Number(serviceId || 0)}:${Number(vehicleId || 0)}`;
        }

        function hasServiceVehicleAccessGrant(serviceId, vehicleId) {
            const key = buildServiceVehicleAccessKey(serviceId, vehicleId);
            const grants = Array.isArray(serviceVehicleAccessState.grants) ? serviceVehicleAccessState.grants : [];
            return grants.some((grant) => buildServiceVehicleAccessKey(grant?.service_id, grant?.vehicle_id) === key);
        }

        function formatServiceVehicleOptionLabel(vehicle) {
            if (!vehicle) return 'Vozidlo';
            const nickname = String(vehicle?.nickname || '').trim();
            const plate = String(vehicle?.plate || '').trim();
            if (nickname && plate) return `${nickname} (${plate})`;
            if (nickname) return nickname;
            if (plate) return plate;
            return `Vozidlo #${vehicle?.id || ''}`;
        }

        function findDefaultVehicleForService(serviceId, vehicles) {
            const list = Array.isArray(vehicles) ? vehicles : [];
            if (!list.length) return null;
            const granted = list.find((vehicle) => hasServiceVehicleAccessGrant(serviceId, vehicle?.id));
            if (granted) return granted;
            return list[0];
        }

        function buildServiceVehicleAccessStatus(serviceId, vehicleId) {
            if (!vehicleId) {
                return {
                    text: 'Vyberte vozidlo pro nastavení správy.',
                    enabled: false,
                };
            }
            const enabled = hasServiceVehicleAccessGrant(serviceId, vehicleId);
            return {
                text: enabled
                    ? 'Toto vozidlo má servis povolené ke správě.'
                    : 'Toto vozidlo ještě není pro servis povolené.',
                enabled,
            };
        }

        function updateServiceVehicleAccessCard(serviceId) {
            const select = document.getElementById(`serviceVehicleSelect-${serviceId}`);
            const button = document.getElementById(`serviceVehicleToggle-${serviceId}`);
            const status = document.getElementById(`serviceVehicleStatus-${serviceId}`);
            if (!select || !button || !status) return;

            const vehicleId = Number(select.value || 0);
            const access = buildServiceVehicleAccessStatus(serviceId, vehicleId);
            status.textContent = access.text;
            status.classList.toggle('enabled', access.enabled);
            button.textContent = access.enabled ? 'Odebrat správu' : 'Povolit správu';
            button.classList.toggle('btn-danger', access.enabled);
            button.classList.toggle('btn-primary', !access.enabled);
            button.disabled = vehicleId <= 0;
        }

        function handleServiceVehicleAccessSelection(serviceId) {
            updateServiceVehicleAccessCard(Number(serviceId || 0));
        }

        function setServiceVehicleAccessFeedback(serviceId, message = '', level = '') {
            const target = document.getElementById(`serviceVehicleFeedback-${Number(serviceId || 0)}`);
            if (!target) return;
            target.textContent = String(message || '').trim();
            target.classList.remove('success', 'error');
            if (level === 'success' || level === 'error') {
                target.classList.add(level);
            }
        }

        async function toggleServiceVehicleAccess(serviceId) {
            const serviceIdNum = Number(serviceId || 0);
            const select = document.getElementById(`serviceVehicleSelect-${serviceIdNum}`);
            const button = document.getElementById(`serviceVehicleToggle-${serviceIdNum}`);
            if (!select || !button) return;

            if (serviceVehicleAccessState.apiAvailable === false) {
                const message = 'Funkce správy vozidel servisu není na serveru dostupná. Kontaktujte podporu nebo obnovte aplikaci.';
                showAlert(message, 'error');
                setServiceVehicleAccessFeedback(serviceIdNum, message, 'error');
                return;
            }

            const vehicleIdNum = Number(select.value || 0);
            if (!vehicleIdNum) {
                showAlert('Vyberte vozidlo, které chcete servisu povolit.', 'error');
                setServiceVehicleAccessFeedback(serviceIdNum, 'Vyberte vozidlo.', 'error');
                return;
            }

            const currentlyGranted = hasServiceVehicleAccessGrant(serviceIdNum, vehicleIdNum);
            button.disabled = true;
            const originalButtonLabel = button.textContent;
            button.textContent = 'Ukládám...';
            setServiceVehicleAccessFeedback(serviceIdNum, 'Ukládám změnu oprávnění...', '');

            try {
                if (currentlyGranted) {
                    await apiCall(`/api/v1/services/vehicle-access/${serviceIdNum}/${vehicleIdNum}`, 'DELETE');
                    serviceVehicleAccessState.grants = (serviceVehicleAccessState.grants || []).filter((grant) => (
                        Number(grant?.service_id) !== serviceIdNum || Number(grant?.vehicle_id) !== vehicleIdNum
                    ));
                    showAlert('Přístup servisu k vozidlu byl odebrán.', 'success');
                    setServiceVehicleAccessFeedback(serviceIdNum, 'Přístup servisu byl odebrán.', 'success');
                } else {
                    let grantResponse = await apiCall('/api/v1/services/vehicle-access', 'POST', {
                        service_id: serviceIdNum,
                        vehicle_id: vehicleIdNum,
                        conflict_strategy: 'ask'
                    });
                    if (grantResponse?.requires_confirmation && grantResponse?.conflict) {
                        const conflictServices = Array.isArray(grantResponse?.conflict_services)
                            ? grantResponse.conflict_services
                            : [];
                        const conflictNames = conflictServices
                            .map((item) => String(item?.service_name || item?.service_email || `Servis #${item?.service_id || ''}`).trim())
                            .filter(Boolean)
                            .join(', ');
                        const replaceOld = confirm(
                            `Vozidlo je už přiřazené k jinému servisu: ${conflictNames || 'jiný servis'}.\n\n` +
                            'OK = odebrat původní servis a přiřadit jen tento servis\n' +
                            'Storno = původní servis ponechat a přidat i tento servis'
                        );
                        grantResponse = await apiCall('/api/v1/services/vehicle-access', 'POST', {
                            service_id: serviceIdNum,
                            vehicle_id: vehicleIdNum,
                            conflict_strategy: replaceOld ? 'replace' : 'keep'
                        });
                    }

                    const revokedConflictIds = Array.isArray(grantResponse?.revoked_conflict_service_ids)
                        ? grantResponse.revoked_conflict_service_ids.map((id) => Number(id || 0)).filter((id) => id > 0)
                        : [];
                    if (revokedConflictIds.length) {
                        serviceVehicleAccessState.grants = (serviceVehicleAccessState.grants || []).filter((grant) => {
                            const grantServiceId = Number(grant?.service_id || 0);
                            const grantVehicleId = Number(grant?.vehicle_id || 0);
                            return !(grantVehicleId === vehicleIdNum && revokedConflictIds.includes(grantServiceId));
                        });
                    }

                    const nextGrants = (serviceVehicleAccessState.grants || []).filter((grant) => (
                        Number(grant?.service_id || 0) !== serviceIdNum || Number(grant?.vehicle_id || 0) !== vehicleIdNum
                    ));
                    nextGrants.push({
                        service_id: serviceIdNum,
                        vehicle_id: vehicleIdNum
                    });
                    serviceVehicleAccessState.grants = nextGrants;

                    const grantMessage = String(grantResponse?.message || '').trim() || 'Přístup servisu k vozidlu byl povolen.';
                    showAlert(grantMessage, 'success');
                    setServiceVehicleAccessFeedback(serviceIdNum, grantMessage, 'success');
                }

                updateServiceVehicleAccessCard(serviceIdNum);
                await Promise.all([
                    loadManagedServiceContacts(true),
                    loadServicesDirectory(true)
                ]);
            } catch (error) {
                console.error("[SERVICE_ACCESS] Chyba při změně oprávnění:");
                showAlert('Nepodařilo se uložit změnu oprávnění: ' + (error?.message || 'Neznámá chyba'), 'error');
                setServiceVehicleAccessFeedback(serviceIdNum, `Chyba uložení: ${error?.message || 'Neznámá chyba'}`, 'error');
            } finally {
                button.disabled = false;
                if (!button.textContent || button.textContent === 'Ukládám...') {
                    button.textContent = originalButtonLabel || button.textContent;
                }
            }
        }

        function renderServicesDirectory(payload) {
            const container = document.getElementById('servicesDirectoryContainer');
            if (!container) return;

            const services = Array.isArray(payload?.services) ? payload.services : [];
            const vehicles = Array.isArray(payload?.userVehicles) ? payload.userVehicles : [];
            const grants = Array.isArray(payload?.vehicleAccessGrants) ? payload.vehicleAccessGrants : [];
            const vehicleAccessApiAvailable = payload?.vehicleAccessApiAvailable !== false;
            const meta = payload?.meta || {};
            const linkedTotal = Number(meta.linked_total || services.filter((service) => Boolean(service?.is_linked)).length || 0);
            const refSource = String(meta.reference_source || 'none');
            const sortedByDistance = !!meta.distance_sorted;
            const isUserContext = isAuthenticated() && getActiveWorkspaceMode() === 'user';

            serviceVehicleAccessState.vehicles = vehicles;
            serviceVehicleAccessState.grants = grants;
            serviceVehicleAccessState.apiAvailable = vehicleAccessApiAvailable;

            const sourceLabel =
                refSource === 'browser'
                    ? 'Podle GPS polohy vašeho zařízení'
                    : refSource === 'profile_address'
                        ? 'Podle adresy ve vašem profilu'
                        : 'Bez určení polohy (abecedně)';

            let html = `
                <div class="services-directory-shell">
                    <div class="services-directory-info">
                        <strong>Seznam aktivních servisů:</strong> ${escapeHtml(services.length)} servisů.<br>
                        Řazení: ${sortedByDistance ? 'podle vzdálenosti' : 'bez vzdálenosti'} • ${escapeHtml(sourceLabel)}<br>
                        Propojené servisy: <strong>${Number.isFinite(linkedTotal) ? linkedTotal : 0}</strong>
                    </div>
            `;

            if (!services.length) {
                const hasManagedServices = linkedTotal > 0 || (Array.isArray(managedServiceContactsState.items) && managedServiceContactsState.items.length > 0);
                html += `
                    <div class="alert ${hasManagedServices ? 'alert-info' : 'alert-warning'}">
                        ${hasManagedServices
                            ? 'Katalog servisů je momentálně prázdný, ale máte propojené servisy v kontaktech dole v zápatí.'
                            : 'V tuto chvíli nejsou dostupné žádné aktivní servisní účty.'}
                    </div>
                `;
            } else {
                html += '<div class="services-directory-grid">';
                services.forEach((service) => {
                    const serviceName = escapeHtml(service?.name || service?.email || 'Servis');
                    const distanceLabel = formatServicesDistance(service?.distance_km);
                    const addressLine = escapeHtml(buildServiceAddressLine(service));
                    const phoneRaw = String(service?.phone || '').trim();
                    const emailRaw = String(service?.email || '').trim();
                    const phone = escapeHtml(phoneRaw || '-');
                    const email = escapeHtml(emailRaw || '-');
                    const ico = escapeHtml(service?.ico || '-');
                    const mapsQuery = encodeURIComponent(buildServiceAddressLine(service));
                    const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${mapsQuery}`;
                    const contactAction = emailRaw
                        ? `<a class="btn" href="mailto:${escapeHtml(encodeURIComponent(emailRaw))}">Kontaktovat</a>`
                        : '<button class="btn btn-secondary" type="button" disabled>Bez emailu</button>';
                    const serviceId = Number(service?.id || 0);
                    const defaultVehicle = findDefaultVehicleForService(serviceId, vehicles);
                    const defaultVehicleId = Number(defaultVehicle?.id || 0);
                    const accessStatus = buildServiceVehicleAccessStatus(serviceId, defaultVehicleId);
                    const sharedVehiclesCount = Number(service?.shared_vehicles_count || 0);
                    const isLinked = Boolean(service?.is_linked);

                    let accessControlsHtml = '';
                    if (isUserContext && vehicles.length && serviceId > 0) {
                        const accessDisabled = !vehicleAccessApiAvailable;
                        const feedbackText = accessDisabled
                            ? 'Správa vozidel servisu je dočasně nedostupná (chybí API podpora na serveru).'
                            : '';
                        accessControlsHtml = `
                            <section class="service-directory-access">
                                <div class="service-directory-access-controls">
                                    <select id="serviceVehicleSelect-${serviceId}" ${legacyActionAttributes("change", "handleServiceVehicleAccessSelection_62102903", serviceId)} ${accessDisabled ? 'disabled' : ''}>
                                        ${vehicles.map((vehicle) => {
                                            const vehicleId = Number(vehicle?.id || 0);
                                            const selectedAttr = vehicleId === defaultVehicleId ? 'selected' : '';
                                            return `<option value="${vehicleId}" ${selectedAttr}>${escapeHtml(formatServiceVehicleOptionLabel(vehicle))}</option>`;
                                        }).join('')}
                                    </select>
                                    <button
                                        type="button"
                                        id="serviceVehicleToggle-${serviceId}"
                                        class="btn ${accessStatus.enabled ? 'btn-danger' : 'btn-primary'}"
                                        ${legacyActionAttributes("click", "toggleServiceVehicleAccess_de541112", serviceId)}
                                        ${accessDisabled ? 'disabled' : ''}
                                    >
                                        ${accessDisabled ? 'Nedostupné' : (accessStatus.enabled ? 'Odebrat správu' : 'Povolit správu')}
                                    </button>
                                </div>
                                <p id="serviceVehicleStatus-${serviceId}" class="service-directory-access-status ${accessStatus.enabled ? 'enabled' : ''}">
                                    ${escapeHtml(accessStatus.text)}
                                </p>
                                <p id="serviceVehicleFeedback-${serviceId}" class="service-directory-access-feedback ${accessDisabled ? 'error' : ''}">${escapeHtml(feedbackText)}</p>
                            </section>
                        `;
                    }

                    html += `
                        <article class="service-directory-card" id="service-directory-card-${serviceId}">
                            <div class="service-directory-head">
                                <h3 class="service-directory-name">${serviceName}</h3>
                                ${distanceLabel ? `<span class="service-directory-distance">${escapeHtml(distanceLabel)}</span>` : '<span class="service-directory-distance">Vzdálenost N/A</span>'}
                            </div>
                            ${isLinked ? '<span class="service-directory-linked-badge">Propojeno s vaším účtem</span>' : ''}
                            <p class="service-directory-meta"><strong>Adresa:</strong> ${addressLine}</p>
                            <p class="service-directory-meta"><strong>Telefon:</strong> ${phone}</p>
                            <p class="service-directory-meta"><strong>Email:</strong> ${email}</p>
                            <p class="service-directory-meta"><strong>IČO:</strong> ${ico}</p>
                            ${isUserContext ? `<p class="service-directory-meta"><strong>Spravovaná vozidla:</strong> ${sharedVehiclesCount}</p>` : ''}
                            <div class="service-directory-actions">
                                <a class="btn btn-secondary" href="${escapeHtml(mapsUrl)}" target="_blank" rel="noopener noreferrer">Navigovat</a>
                                ${contactAction}
                            </div>
                            ${accessControlsHtml}
                        </article>
                    `;
                });
                html += '</div>';
            }

            html += '</div>';
            container.innerHTML = html;

            const focusServiceId = Number(pendingServicesDirectoryFocusServiceId || 0);
            if (focusServiceId > 0) {
                pendingServicesDirectoryFocusServiceId = null;
                setTimeout(() => {
                    const focusCard = document.getElementById(`service-directory-card-${focusServiceId}`);
                    if (!focusCard) return;
                    if (typeof focusCard.scrollIntoView === 'function') {
                        focusCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                    const previousTransition = focusCard.style.transition;
                    const previousOutline = focusCard.style.outline;
                    const previousBoxShadow = focusCard.style.boxShadow;
                    focusCard.style.transition = 'box-shadow 0.25s ease, outline 0.25s ease';
                    focusCard.style.outline = '2px solid #4f46e5';
                    focusCard.style.boxShadow = '0 0 0 4px rgba(79, 70, 229, 0.18)';
                    setTimeout(() => {
                        focusCard.style.transition = previousTransition;
                        focusCard.style.outline = previousOutline;
                        focusCard.style.boxShadow = previousBoxShadow;
                    }, 2200);
                }, 120);
            }
        }

        async function loadServicesDirectory(force = false) {
            const container = document.getElementById('servicesDirectoryContainer');
            if (!container) return;

            if (!isAuthenticated()) {
                container.innerHTML = '<div class="alert alert-error">Pro zobrazení servisů se nejprve přihlaste.</div>';
                return;
            }

            const cacheAge = Date.now() - Number(servicesDirectoryState.loadedAt || 0);
            if (!force && servicesDirectoryState.payload && cacheAge < 2 * 60 * 1000) {
                renderServicesDirectory(servicesDirectoryState.payload);
                return;
            }

            container.classList.add('loading');
            container.innerHTML = '<div class="loading">Načítám seznam servisů...</div>';

            try {
                captureClientGeolocation(true);
                const isUserContext = getActiveWorkspaceMode() === 'user';
                const [payload, userVehicles, accessPayload, managedContactsPayload] = await Promise.all([
                    apiCall('/api/v1/services/discovery', 'GET'),
                    isUserContext
                        ? apiCall('/api/v1/vehicles', 'GET').catch((error) => {
                            console.warn("[SERVICES_DIRECTORY] Nepodařilo se načíst vozidla pro správu přístupu:");
                            return [];
                        })
                        : Promise.resolve([]),
                    isUserContext
                        ? apiCall('/api/v1/services/vehicle-access', 'GET').catch((error) => {
                            console.warn("[SERVICES_DIRECTORY] Nepodařilo se načíst explicitní oprávnění vozidel:");
                            return { grants: [], api_available: false, error_message: String(error?.message || '') };
                        })
                        : Promise.resolve({ grants: [], api_available: true }),
                    isUserContext
                        ? apiCall('/api/v1/services/my-contacts', 'GET').catch((error) => {
                            console.warn("[SERVICES_DIRECTORY] Nepodařilo se načíst propojené kontakty:");
                            return { services: [] };
                        })
                        : Promise.resolve({ services: [] })
                ]);

                const normalizedPayload = payload || { services: [], meta: {} };
                const linkedContacts = Array.isArray(managedContactsPayload?.services)
                    ? managedContactsPayload.services
                    : [];
                const baseServices = Array.isArray(normalizedPayload?.services) ? normalizedPayload.services : [];
                const serviceMap = new Map();
                baseServices.forEach((item) => {
                    const id = Number(item?.id || 0);
                    if (!id) return;
                    serviceMap.set(id, {
                        ...item,
                        is_linked: Boolean(item?.is_linked)
                    });
                });
                linkedContacts.forEach((contact) => {
                    const id = Number(contact?.id || 0);
                    if (!id) return;
                    const existing = serviceMap.get(id);
                    if (existing) {
                        serviceMap.set(id, {
                            ...existing,
                            is_linked: true,
                            name: existing?.name || contact?.name || contact?.email || existing?.email || 'Servis',
                            email: existing?.email || contact?.email || '',
                            phone: existing?.phone || contact?.phone || '',
                            ico: existing?.ico || contact?.ico || '',
                            city: existing?.city || contact?.city || '',
                            street: existing?.street || '',
                            street_number: existing?.street_number || '',
                            address: existing?.address || contact?.address || '',
                            shared_vehicles_count: Number(existing?.shared_vehicles_count || 0)
                        });
                        return;
                    }
                    serviceMap.set(id, {
                        id,
                        name: contact?.name || contact?.email || `Servis #${id}`,
                        email: contact?.email || '',
                        phone: contact?.phone || '',
                        ico: contact?.ico || '',
                        city: contact?.city || '',
                        street: '',
                        street_number: '',
                        zip: '',
                        distance_km: null,
                        has_precise_distance: false,
                        coordinates: null,
                        is_linked: true,
                        shared_vehicles_count: 0,
                        created_at: null,
                        address: contact?.address || ''
                    });
                });
                normalizedPayload.services = Array.from(serviceMap.values()).sort((a, b) => {
                    const aLinked = a?.is_linked ? 0 : 1;
                    const bLinked = b?.is_linked ? 0 : 1;
                    if (aLinked !== bLinked) return aLinked - bLinked;
                    return String(a?.name || a?.email || '').localeCompare(String(b?.name || b?.email || ''), 'cs');
                });
                normalizedPayload.meta = normalizedPayload.meta || {};
                normalizedPayload.meta.linked_total = normalizedPayload.services.filter((item) => Boolean(item?.is_linked)).length;
                normalizedPayload.userVehicles = Array.isArray(userVehicles) ? userVehicles : [];
                normalizedPayload.vehicleAccessGrants = Array.isArray(accessPayload?.grants) ? accessPayload.grants : [];
                normalizedPayload.vehicleAccessApiAvailable = accessPayload?.api_available !== false;
                servicesDirectoryState.payload = normalizedPayload;
                servicesDirectoryState.loadedAt = Date.now();
                renderServicesDirectory(normalizedPayload);
            } catch (error) {
                console.error("[SERVICES_DIRECTORY] Chyba načítání:");
                container.innerHTML = `
                    <div class="alert alert-error">
                        Nepodařilo se načíst seznam servisů: ${escapeHtml(error?.message || 'Neznámá chyba')}
                        <br><br>
                        <button class="btn btn-primary" ${legacyActionAttributes("click", "loadServicesDirectory_d9500fe7")}>Zkusit znovu</button>
                    </div>
                `;
            } finally {
                container.classList.remove('loading');
            }
        }

        function resetServiceReservationDraft(keepCatalog = false) {
            serviceReservationDraftState.customerId = null;
            serviceReservationDraftState.vehicleId = null;
            serviceReservationDraftState.serviceType = '';
            serviceReservationDraftState.note = '';
            serviceReservationDraftState.startDate = '';
            serviceReservationDraftState.startTime = '';
            serviceReservationDraftState.endDate = '';
            serviceReservationDraftState.endTime = '';
            if (!keepCatalog) {
                serviceReservationDraftState.catalog = [];
            }
        }

        function updateServiceReservationVehicleSelect(preferredVehicleId = null) {
            const customerSelect = document.getElementById('reservationCustomer');
            const vehicleSelect = document.getElementById('reservationVehicle');
            if (!customerSelect || !vehicleSelect) return;

            const customerId = Number(customerSelect.value || 0);
            const catalog = Array.isArray(serviceReservationDraftState.catalog) ? serviceReservationDraftState.catalog : [];
            const customerEntry = catalog.find((item) => Number(item?.customer_id || 0) === customerId);
            const vehicles = Array.isArray(customerEntry?.vehicles) ? customerEntry.vehicles : [];

            if (!vehicles.length) {
                vehicleSelect.innerHTML = '<option value="">Klient nemá dostupná vozidla</option>';
                return;
            }

            const targetVehicleId = Number(preferredVehicleId || serviceReservationDraftState.vehicleId || 0);
            vehicleSelect.innerHTML = vehicles.map((vehicle) => {
                const vehicleId = Number(vehicle?.id || 0);
                const selected = targetVehicleId > 0 && vehicleId === targetVehicleId ? 'selected' : '';
                const label = `${vehicle?.nickname || vehicle?.plate || `Vozidlo #${vehicleId}`}${vehicle?.plate ? ` - ${vehicle.plate}` : ''}`;
                return `<option value="${vehicleId}" data-customer-id="${customerId}" ${selected}>${escapeHtml(label)}</option>`;
            }).join('');

            if (!vehicleSelect.value && vehicles[0]?.id) {
                vehicleSelect.value = String(vehicles[0].id);
            }
            serviceReservationDraftState.customerId = customerId || null;
            serviceReservationDraftState.vehicleId = Number(vehicleSelect.value || 0) || null;
        }

        function handleServiceReservationCustomerChange() {
            updateServiceReservationVehicleSelect();
        }

        async function loadServiceReservationCatalog(forceReload = false) {
            let customers = Array.isArray(serviceWorkspaceState.customers) ? serviceWorkspaceState.customers : [];
            if (forceReload || !customers.length) {
                const customerResponse = await apiCall('/api/v1/services/workspace/customers', 'GET');
                customers = Array.isArray(customerResponse) ? customerResponse : [];
                serviceWorkspaceState.customers = customers;
            }

            const catalog = [];
            const originalSelectedCustomerId = serviceWorkspaceState.selectedCustomerId;
            for (const customer of customers) {
                const customerId = Number(customer?.customer_id || 0);
                if (!customerId) continue;

                if (forceReload || !isServiceWorkspaceCustomerVehiclesLoaded(customerId)) {
                    try {
                        await loadServiceWorkspaceCustomerVehicles(customerId, true);
                    } catch (error) {
                        console.warn("[RESERVATION][SERVICE] Nepodařilo se načíst vozidla klienta:");
                    }
                }
                const vehicles = Array.isArray(serviceWorkspaceState.customerVehicles?.[customerId])
                    ? serviceWorkspaceState.customerVehicles[customerId]
                    : [];
                catalog.push({
                    customer_id: customerId,
                    customer_name: customer?.name || customer?.email || `Klient #${customerId}`,
                    customer_email: customer?.email || '',
                    vehicles
                });
            }
            serviceWorkspaceState.selectedCustomerId = originalSelectedCustomerId;
            serviceReservationDraftState.catalog = catalog;
            return catalog;
        }

        async function openServiceReservationComposer(customerId = null, vehicleId = null) {
            if (!isServiceReservationsContext()) {
                switchTab('reservations');
                return showCreateReservationForm();
            }
            if (Number(customerId || 0) > 0) {
                serviceReservationDraftState.customerId = Number(customerId);
            }
            if (Number(vehicleId || 0) > 0) {
                serviceReservationDraftState.vehicleId = Number(vehicleId);
            }
            switchTab('reservations');
            await showCreateReservationForm();
        }

        async function showCreateServiceReservationForm() {
            const serviceId = Number(currentUser?.id || 0);
            if (!serviceId) {
                showAlert('Servisní účet není správně načten.', 'error');
                return;
            }

            let catalog = [];
            try {
                catalog = await loadServiceReservationCatalog(false);
            } catch (error) {
                console.error("[RESERVATION][SERVICE] Chyba načtení klientů:");
                showAlert('Nepodařilo se načíst klienty servisu: ' + (error?.message || 'Neznámá chyba'), 'error');
                return;
            }

            const customersWithVehicles = catalog.filter((item) => Array.isArray(item.vehicles) && item.vehicles.length);
            if (!customersWithVehicles.length) {
                showAlert('Nejsou dostupná žádná klientská vozidla pro rezervaci. Nejprve přidejte klientovi vozidlo.', 'warning');
                switchTab('addVehicle');
                return;
            }

            let selectedCustomerId = Number(serviceReservationDraftState.customerId || serviceWorkspaceState.selectedCustomerId || 0);
            if (!customersWithVehicles.some((item) => Number(item.customer_id) === selectedCustomerId)) {
                selectedCustomerId = Number(customersWithVehicles[0].customer_id);
            }
            const selectedCustomer = customersWithVehicles.find((item) => Number(item.customer_id) === selectedCustomerId) || customersWithVehicles[0];

            let selectedVehicleId = Number(serviceReservationDraftState.vehicleId || 0);
            if (!selectedCustomer.vehicles.some((vehicle) => Number(vehicle?.id || 0) === selectedVehicleId)) {
                selectedVehicleId = Number(selectedCustomer.vehicles[0]?.id || 0);
            }

            const nowPlusHour = new Date(Date.now() + 60 * 60 * 1000);
            nowPlusHour.setSeconds(0, 0);
            const minuteRemainder = nowPlusHour.getMinutes() % 30;
            if (minuteRemainder !== 0) {
                nowPlusHour.setMinutes(nowPlusHour.getMinutes() + (30 - minuteRemainder));
            }
            const defaultStartDate = serviceReservationDraftState.startDate || `${nowPlusHour.getFullYear()}-${padReservationDatePart(nowPlusHour.getMonth() + 1)}-${padReservationDatePart(nowPlusHour.getDate())}`;
            const defaultStartTime = serviceReservationDraftState.startTime || `${padReservationDatePart(nowPlusHour.getHours())}:${padReservationDatePart(nowPlusHour.getMinutes())}`;

            const customerOptions = customersWithVehicles.map((customer) => {
                const customerId = Number(customer?.customer_id || 0);
                const selected = customerId === selectedCustomerId ? 'selected' : '';
                const label = `${customer?.customer_name || `Klient #${customerId}`} (${customer?.customer_email || '-'})`;
                return `<option value="${customerId}" ${selected}>${escapeHtml(label)}</option>`;
            }).join('');

            const vehicleOptions = selectedCustomer.vehicles.map((vehicle) => {
                const vehicleId = Number(vehicle?.id || 0);
                const selected = vehicleId === selectedVehicleId ? 'selected' : '';
                const label = `${vehicle?.nickname || vehicle?.plate || `Vozidlo #${vehicleId}`}${vehicle?.plate ? ` - ${vehicle.plate}` : ''}`;
                return `<option value="${vehicleId}" data-customer-id="${selectedCustomerId}" ${selected}>${escapeHtml(label)}</option>`;
            }).join('');

            const formHtml = `
                <div class="reminder-modal-overlay" ${legacyActionAttributes("click", "closeReservationForm_8ad16ccd")}>
                    <div class="reminder-modal reservation-create-modal service-account-modal">
                        <form class="reminder-create reservation-create service-account-form" ${legacyActionAttributes("submit", "handleCreateReservation_a270c604")}>
                            <div class="reminder-modal-head">
                                <div class="reminder-modal-heading">
                                    <span class="reminder-modal-icon" aria-hidden="true">
                                        <svg viewBox="0 0 24 24">
                                            <path d="M8 2v3"></path>
                                            <path d="M16 2v3"></path>
                                            <rect x="3" y="5" width="18" height="16" rx="2"></rect>
                                            <path d="M3 10h18"></path>
                                        </svg>
                                    </span>
                                    <div>
                                        <p class="reminder-modal-kicker">Servisní kalendář</p>
                                        <h2 class="modal-title">Nová rezervace klienta</h2>
                                    </div>
                                </div>
                                <button type="button" class="reminder-modal-close" aria-label="Zavřít okno" ${legacyActionAttributes("click", "closeReservationForm_6cc4d37f")}>×</button>
                            </div>
                            <p class="reminder-modal-intro">Termín vytvoří servis. Klient uvidí rezervaci ve svém účtu a dostane e-mail při změnách.</p>
                            <div class="form-grid">
                                <div class="form-row">
                                    <label for="reservationCustomer">Klient *:</label>
                                    <select id="reservationCustomer" required ${legacyActionAttributes("change", "handleServiceReservationCustomerChange_ccdff816")}>
                                        ${customerOptions}
                                    </select>
                                </div>
                                <div class="form-row">
                                    <label for="reservationVehicle">Vozidlo *:</label>
                                    <select id="reservationVehicle" required>
                                        ${vehicleOptions}
                                    </select>
                                </div>
                                <input type="hidden" id="reservationServiceId" value="${serviceId}">
                                <div class="form-row span-2">
                                    <label for="reservationServiceType">Typ servisu:</label>
                                    <input type="text" id="reservationServiceType" placeholder="Např. pravidelný servis, STK, výměna oleje" value="${escapeHtml(serviceReservationDraftState.serviceType || '')}">
                                </div>
                                <div class="form-row span-2">
                                    <label>Začátek rezervace *:</label>
                                    <div class="reservation-datetime-row">
                                        <input type="date" id="reservationStartDate" required value="${escapeHtml(defaultStartDate)}">
                                        <input type="time" id="reservationStartTime" required value="${escapeHtml(defaultStartTime)}">
                                    </div>
                                </div>
                                <div class="form-row span-2">
                                    <label>Konec rezervace (volitelné):</label>
                                    <div class="reservation-datetime-row">
                                        <input type="date" id="reservationEndDate" value="${escapeHtml(serviceReservationDraftState.endDate || '')}">
                                        <input type="time" id="reservationEndTime" value="${escapeHtml(serviceReservationDraftState.endTime || '')}">
                                    </div>
                                </div>
                                <div class="form-row span-2">
                                    <label for="reservationNote">Poznámka pro klienta:</label>
                                    <textarea id="reservationNote" placeholder="Doplňující informace k termínu..." rows="3">${escapeHtml(serviceReservationDraftState.note || '')}</textarea>
                                </div>
                            </div>
                            <div class="form-actions">
                                <button type="submit" class="btn btn-primary">Vytvořit rezervaci</button>
                                <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "closeReservationForm_6cc4d37f")}>Zrušit</button>
                            </div>
                        </form>
                    </div>
                </div>
            `;

            mountFloatingModal(formHtml);
            setReservationCreateSubmitting(false);
            updateServiceReservationVehicleSelect(selectedVehicleId);
        }

        // Zobrazení formuláře pro vytvoření rezervace
        async function showCreateReservationForm() {
            if (!canCreateReservationFromUi()) {
                showAlert('Rezervaci nelze v aktuálním režimu vytvořit.', 'warning');
                return;
            }
            if (isServiceReservationsContext()) {
                return showCreateServiceReservationForm();
            }

            // Načíst vozidla uživatele
            let vehicles = [];
            try {
                vehicles = await apiCall('/api/v1/vehicles', 'GET');
            } catch (error) {
                console.error("Error loading vehicles:");
                showAlert('Nepodařilo se načíst vozidla: ' + error.message, 'error');
                return;
            }

            if (!vehicles || vehicles.length === 0) {
                showAlert('Nemáte žádná vozidla. Nejdříve přidejte vozidlo.', 'error');
                switchTab('addVehicle');
                return;
            }

            // Načíst seznam dostupných servisů
            let services = [];
            try {
                const servicesDiscoveryPayload = await apiCall('/api/v1/services/discovery', 'GET');
                services = Array.isArray(servicesDiscoveryPayload?.services) ? servicesDiscoveryPayload.services : [];
            } catch (error) {
                console.error("Error loading services discovery:");
                try {
                    services = await apiCall('/api/v1/services', 'GET');
                } catch (fallbackError) {
                    console.error("Error loading services fallback:");
                    showAlert('Nepodařilo se načíst seznam servisů: ' + (fallbackError.message || error.message), 'error');
                    return;
                }
            }

            if (!services || services.length === 0) {
                showAlert('Není k dispozici žádný servis. Kontaktujte administrátora.', 'error');
                return;
            }

            const formHtml = `
                <div class="reminder-modal-overlay" ${legacyActionAttributes("click", "closeReservationForm_8ad16ccd")}>
                    <div class="reminder-modal reservation-create-modal">
                        <form class="reminder-create reservation-create" ${legacyActionAttributes("submit", "handleCreateReservation_a270c604")}>
                            <div class="reminder-modal-head">
                                <div class="reminder-modal-heading">
                                    <span class="reminder-modal-icon" aria-hidden="true">
                                        <svg viewBox="0 0 24 24">
                                            <path d="M8 2v3"></path>
                                            <path d="M16 2v3"></path>
                                            <rect x="3" y="5" width="18" height="16" rx="2"></rect>
                                            <path d="M3 10h18"></path>
                                        </svg>
                                    </span>
                                    <div>
                                        <p class="reminder-modal-kicker">Rezervace</p>
                                        <h2 class="modal-title">Nová rezervace</h2>
                                    </div>
                                </div>
                                <button type="button" class="reminder-modal-close" aria-label="Zavřít okno" ${legacyActionAttributes("click", "closeReservationForm_6cc4d37f")}>×</button>
                            </div>
                            <p class="reminder-modal-intro">Vyberte vozidlo, servis a nastavte termín návštěvy.</p>

                            <div class="form-grid">
                                <div class="form-row">
                                    <label for="reservationVehicle">Vozidlo *:</label>
                                    <select id="reservationVehicle" required>
                                        <option value="">Vyberte vozidlo...</option>
                                        ${vehicles.map(v => {
                                            const assignedServiceId = v.assigned_service_id || v.service_id || v.default_service_id || '';
                                            return `<option value="${escapeHtml(v.id)}" data-service-id="${escapeHtml(assignedServiceId)}">${escapeHtml(v.nickname || v.plate || 'Bez názvu')} - ${escapeHtml(v.plate || 'Bez SPZ')}</option>`;
                                        }).join('')}
                                    </select>
                                </div>

                                <div class="form-row">
                                    <label for="reservationServiceId">Servis *:</label>
                                    <select id="reservationServiceId" required>
                                        <option value="">Vyberte servis...</option>
                                        ${services.map(s => `<option value="${escapeHtml(s.id)}">${escapeHtml(s.name || s.email)}${escapeHtml(s.city ? ' - ' + s.city : '')}${escapeHtml(s.phone ? ' (' + s.phone + ')' : '')}</option>`).join('')}
                                    </select>
                                    <small class="form-hint">Vyberte servis, který bude rezervaci spravovat.</small>
                                </div>

                                <div class="form-row span-2">
                                    <label for="reservationServiceType">Typ servisu:</label>
                                    <input type="text" id="reservationServiceType" placeholder="Např. Pravidelný servis, STK, oprava...">
                                </div>

                                <div class="form-row span-2">
                                    <label>Začátek rezervace *:</label>
                                    <div class="reservation-datetime-row">
                                        <input type="date" id="reservationStartDate" required>
                                        <input type="time" id="reservationStartTime" required>
                                    </div>
                                </div>

                                <div class="form-row span-2">
                                    <label>Konec rezervace (volitelné):</label>
                                    <div class="reservation-datetime-row">
                                        <input type="date" id="reservationEndDate">
                                        <input type="time" id="reservationEndTime">
                                    </div>
                                </div>

                                <div class="form-row span-2">
                                    <label for="reservationNote">Poznámka:</label>
                                    <textarea id="reservationNote" placeholder="Doplňující informace pro servis..." rows="3"></textarea>
                                </div>
                            </div>

                            <div class="form-actions">
                                <button type="submit" class="btn btn-primary">Vytvořit rezervaci</button>
                                <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "closeReservationForm_6cc4d37f")}>Zrušit</button>
                            </div>
                        </form>
                    </div>
                </div>
            `;

            mountFloatingModal(formHtml);
            setReservationCreateSubmitting(false);

            const vehicleSelect = document.getElementById('reservationVehicle');
            const serviceSelect = document.getElementById('reservationServiceId');

            if (vehicleSelect && serviceSelect) {
                vehicleSelect.addEventListener('change', function() {
                    const selectedOption = vehicleSelect.options[vehicleSelect.selectedIndex];
                    const assignedServiceId = selectedOption.getAttribute('data-service-id');

                    if (assignedServiceId && assignedServiceId !== '') {
                        serviceSelect.value = assignedServiceId;
                    }
                });
            }
        }

        function setReservationCreateSubmitting(isSubmitting) {
            reservationCreateState.submitting = !!isSubmitting;
            const root = document.getElementById(APP_FLOATING_MODAL_ROOT_ID);
            if (!root) return;
            const form = root.querySelector('.reservation-create');
            if (!form) return;
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn) {
                const defaultLabel = String(submitBtn.dataset.defaultLabel || submitBtn.textContent || 'Vytvořit rezervaci');
                submitBtn.dataset.defaultLabel = defaultLabel;
                submitBtn.disabled = !!isSubmitting;
                submitBtn.textContent = isSubmitting ? 'Ukládám…' : defaultLabel;
                submitBtn.setAttribute('aria-disabled', isSubmitting ? 'true' : 'false');
            }
            form.querySelectorAll('button[type="button"], .reminder-modal-close').forEach((button) => {
                button.disabled = !!isSubmitting;
                button.setAttribute('aria-disabled', isSubmitting ? 'true' : 'false');
            });
            form.setAttribute('aria-busy', isSubmitting ? 'true' : 'false');
        }

        // Zavření formuláře
        function closeReservationForm() {
            reservationCreateState.submitting = false;
            unmountFloatingModal();
            loadReservations();
        }

        // Vytvoření rezervace
        async function handleCreateReservation() {
            if (!canCreateReservationFromUi()) {
                showAlert('Rezervaci nelze vytvořit.', 'error');
                return;
            }
            if (reservationCreateState.submitting) {
                return;
            }

            const isServiceView = isServiceReservationsContext();
            const customerIdRaw = document.getElementById('reservationCustomer')?.value || '';
            const vehicleIdRaw = document.getElementById('reservationVehicle')?.value || '';
            const serviceIdRaw = isServiceView
                ? String(Number(currentUser?.id || 0))
                : (document.getElementById('reservationServiceId')?.value || '');
            const serviceType = String(document.getElementById('reservationServiceType')?.value || '').trim();
            const startDate = String(document.getElementById('reservationStartDate')?.value || '').trim();
            const startTime = String(document.getElementById('reservationStartTime')?.value || '').trim();
            const endDate = String(document.getElementById('reservationEndDate')?.value || '').trim();
            const endTime = String(document.getElementById('reservationEndTime')?.value || '').trim();
            const note = String(document.getElementById('reservationNote')?.value || '').trim();

            const vehicleId = Number(vehicleIdRaw || 0);
            const serviceId = Number(serviceIdRaw || 0);
            const customerId = Number(customerIdRaw || 0);

            if (isServiceView && !customerId) {
                showAlert('Vyberte klienta.', 'error');
                return;
            }
            if (!vehicleId) {
                showAlert('Vyberte vozidlo', 'error');
                return;
            }

            if (!serviceId) {
                showAlert('Vyberte servis', 'error');
                return;
            }

            if (!startDate || !startTime) {
                showAlert('Zadejte datum a čas začátku', 'error');
                return;
            }

            const startDatetime = new Date(`${startDate}T${startTime}:00`);
            if (Number.isNaN(startDatetime.getTime())) {
                showAlert('Datum a čas začátku je neplatný.', 'error');
                return;
            }
            let endDatetime = null;

            if (endDate && endTime) {
                endDatetime = new Date(`${endDate}T${endTime}:00`);
                if (Number.isNaN(endDatetime.getTime())) {
                    showAlert('Datum a čas konce je neplatný.', 'error');
                    return;
                }
            } else if (endDate || endTime) {
                showAlert('Pro konec rezervace vyplňte datum i čas, nebo nechte obě pole prázdná.', 'error');
                return;
            }

            if (endDatetime && endDatetime <= startDatetime) {
                showAlert('Datum a čas konce musí být po začátku', 'error');
                return;
            }

            if (isServiceView) {
                const vehicleSelect = document.getElementById('reservationVehicle');
                const selectedOption = vehicleSelect?.options?.[vehicleSelect.selectedIndex] || null;
                const selectedCustomerId = Number(selectedOption?.dataset?.customerId || 0);
                if (selectedCustomerId && selectedCustomerId !== customerId) {
                    showAlert('Vybrané vozidlo nepatří zvolenému klientovi.', 'error');
                    return;
                }
            }

            const reservationData = {
                service_id: serviceId,
                vehicle_id: vehicleId,
                service_type: serviceType || null,
                note: note || null,
                start_datetime: startDatetime.toISOString(),
                end_datetime: endDatetime ? endDatetime.toISOString() : null
            };

            try {
                setReservationCreateSubmitting(true);
                showAlert('Vytvářím rezervaci...', 'info');
                await apiCall('/api/v1/reservations', 'POST', reservationData);
                showAlert('Rezervace byla úspěšně vytvořena!', 'success');
                unmountFloatingModal();
                reservationCreateState.submitting = false;

                if (isServiceView) {
                    resetServiceReservationDraft(true);
                    try {
                        await Promise.all([
                            loadReservations(),
                            loadServiceWorkspace()
                        ]);
                    } catch (refreshError) {
                        console.warn("[RESERVATIONS] Rezervace vytvořena, ale obnovy po uložení selhaly:");
                        showAlert('Rezervace byla uložena, ale nepodařilo se obnovit data. Obnovte stránku.', 'warning');
                    }
                    return;
                }

                try {
                    await loadReservations();
                } catch (refreshError) {
                    console.warn("[RESERVATIONS] Rezervace vytvořena, ale obnovení seznamu selhalo:");
                    showAlert('Rezervace byla uložena, ale nepodařilo se obnovit seznam. Obnovte stránku.', 'warning');
                }
            } catch (error) {
                console.error("Error creating reservation:");
                showAlert('Nepodařilo se vytvořit rezervaci: ' + (error.message || 'Neznámá chyba'), 'error');
                setReservationCreateSubmitting(false);
            }
        }

        // Zrušení rezervace
        async function updateReservationStatus(reservationId, status, confirmText, successText) {
            if (confirmText && !confirm(confirmText)) {
                return;
            }

            try {
                await apiCall(`/api/v1/reservations/${reservationId}`, 'PUT', {
                    status
                });
                showAlert(successText || 'Status rezervace byl aktualizován', 'success');
                await loadReservations();
            } catch (error) {
                console.error("Error updating reservation status:");
                showAlert('Nepodařilo se změnit stav rezervace: ' + error.message, 'error');
            }
        }

        async function cancelReservation(reservationId) {
            return updateReservationStatus(
                reservationId,
                'CANCELLED',
                'Opravdu chcete zrušit tuto rezervaci?',
                'Rezervace byla zrušena'
            );
        }

        async function confirmReservation(reservationId) {
            return updateReservationStatus(
                reservationId,
                'CONFIRMED',
                'Potvrdit tuto rezervaci?',
                'Rezervace byla potvrzena'
            );
        }

        async function completeReservation(reservationId) {
            return updateReservationStatus(
                reservationId,
                'COMPLETED',
                'Označit rezervaci jako dokončenou?',
                'Rezervace byla označena jako dokončená'
            );
        }

        // ============= SERVISNÍ CENTRUM =============

        function formatServiceWorkspaceDate(value) {
            if (!value) return '-';
            const parsed = new Date(value);
            if (Number.isNaN(parsed.getTime())) return '-';
            return parsed.toLocaleString('cs-CZ', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        }

        function getServiceWorkspaceSourceLabel(sourceType) {
            const key = String(sourceType || '').toLowerCase();
            const map = {
                invoice: 'Faktura',
                delivery_note: 'Dodací list',
                work_order: 'Zakázkový list',
                receipt: 'Účtenka',
                manual: 'Ruční vstup'
            };
            return map[key] || 'Doklad';
        }

        function getServiceWorkspaceProcessingStatusMeta(status) {
            const key = String(status || '').toLowerCase();
            if (key === 'processed') {
                return { label: 'Zpracováno', bg: '#dcfce7', color: '#166534', border: '#86efac' };
            }
            if (key === 'needs_review') {
                return { label: 'Ke kontrole', bg: '#fef3c7', color: '#92400e', border: '#fcd34d' };
            }
            if (key === 'failed') {
                return { label: 'Selhalo', bg: '#fee2e2', color: '#991b1b', border: '#fca5a5' };
            }
            return { label: 'Neznámý stav', bg: '#e2e8f0', color: '#334155', border: '#cbd5e1' };
        }

        function getServiceWorkspaceInputMethodLabel(inputMethod) {
            const key = String(inputMethod || '').toLowerCase();
            const map = {
                file: 'Nahraný soubor',
                manual: 'Ruční text',
                'file+manual': 'Soubor + ruční doplnění',
                unknown: 'Neurčeno'
            };
            return map[key] || 'Neurčeno';
        }

        function getServiceWorkspaceExtractionEngineLabel(engine) {
            const key = String(engine || '').toLowerCase();
            const map = {
                manual: 'Ruční vstup',
                'pdf-text': 'PDF text',
                'image-ocr': 'OCR z obrázku',
                text: 'Textový soubor',
                'binary-text-fallback': 'Základní text parser'
            };
            return map[key] || (engine ? String(engine) : 'Neznámé');
        }

        function isServiceWorkspaceInvalidItemName(nameRaw) {
            const name = String(nameRaw || '').trim();
            if (!name) return true;
            const lower = name.toLowerCase();
            if (/@/.test(name)) return true;
            if (/\b\d{1,5}\s*\/\s*\d{1,5}[a-z]?\b/i.test(name)) return true;
            if (/\b\d{5}\b/.test(name)) return true;
            const blocked = [
                'faktura', 'invoice', 'zakázkový list', 'zakazkovy list', 'daňový doklad', 'danovy doklad',
                'dodavatel', 'odběratel', 'odberatel', 'telefon', 'email', 'e-mail', 'web', 'iban', 'swift',
                'účet', 'ucet', 'ičo', 'ico', 'dič', 'dic', 'variabilní symbol', 'variabilni symbol',
                'forma úhrady', 'forma uhrady', 'datum vystavení', 'datum zdanitelného', 'datum splatnosti',
            ];
            return blocked.some((token) => lower.includes(token));
        }

        function sanitizeServiceWorkspaceItems(rawItems, totalWithVat, currency = 'CZK') {
            const sourceItems = Array.isArray(rawItems) ? rawItems : [];
            const parsedTotal = Number(totalWithVat);
            const maxAllowed = Number.isFinite(parsedTotal) && parsedTotal > 0
                ? Math.max(parsedTotal * 1.5, 100000)
                : 500000;
            const seen = new Set();
            const sanitized = [];

            sourceItems.forEach((item) => {
                if (!item || typeof item !== 'object') return;
                const name = String(item.name || '').trim();
                if (!name || isServiceWorkspaceInvalidItemName(name)) return;
                const totalPrice = parseOptionalNumber(item.total_price);
                if (!Number.isFinite(totalPrice) || totalPrice <= 0) return;
                if (totalPrice > maxAllowed) return;
                const quantity = parseOptionalNumber(item.quantity);
                const unitPrice = parseOptionalNumber(item.unit_price);
                const unit = String(item.unit || '').trim() || '—';
                const itemCurrency = String(item.currency || currency || 'CZK').toUpperCase();
                const dedupeKey = `${name.toLowerCase()}|${Number(totalPrice).toFixed(2)}`;
                if (seen.has(dedupeKey)) return;
                seen.add(dedupeKey);
                sanitized.push({
                    name,
                    quantity,
                    unit,
                    unitPrice,
                    totalPrice,
                    currency: itemCurrency,
                });
            });

            return sanitized.slice(0, 20);
        }

        function getServiceWorkspaceInviteStatusMeta(statusRaw, completedHint = false) {
            const status = String(statusRaw || '').toLowerCase();
            if (completedHint || status === 'accepted') {
                return {
                    key: 'accepted',
                    label: 'Vyřízená (přijato)',
                    bg: '#ecfdf3',
                    border: '#86efac',
                    color: '#166534',
                };
            }
            if (status === 'pending') {
                return {
                    key: 'pending',
                    label: 'Čeká na přijetí',
                    bg: '#eff6ff',
                    border: '#bfdbfe',
                    color: '#1d4ed8',
                };
            }
            if (status === 'expired') {
                return {
                    key: 'expired',
                    label: 'Vypršela',
                    bg: '#fff7ed',
                    border: '#fdba74',
                    color: '#9a3412',
                };
            }
            if (status === 'cancelled') {
                return {
                    key: 'cancelled',
                    label: 'Zrušená',
                    bg: '#f8fafc',
                    border: '#cbd5e1',
                    color: '#475569',
                };
            }
            return {
                key: status || 'unknown',
                label: status ? status.toUpperCase() : 'Neznámý stav',
                bg: '#f8fafc',
                border: '#cbd5e1',
                color: '#475569',
            };
        }

        function getServiceWorkspaceCustomerLabel(doc) {
            if (!doc) return '-';
            if (doc.customer_name && doc.customer_email) return `${doc.customer_name} (${doc.customer_email})`;
            if (doc.customer_name) return doc.customer_name;
            if (doc.customer_email) return doc.customer_email;
            if (doc.customer_id) return `Klient #${doc.customer_id}`;
            return '-';
        }

        function getServiceWorkspaceVehicleLabel(doc) {
            if (!doc) return '-';
            if (doc.vehicle_label) return String(doc.vehicle_label);
            const vehicleId = Number(doc.vehicle_id || 0);
            if (!vehicleId) return 'Bez vazby na vozidlo';

            const vehicleBuckets = Object.values(serviceWorkspaceState.customerVehicles || {});
            for (const bucket of vehicleBuckets) {
                if (!Array.isArray(bucket)) continue;
                const match = bucket.find((item) => Number(item?.id || 0) === vehicleId);
                if (match) {
                    const label = `${match.nickname || 'Bez názvu'}${match.plate ? ` • ${match.plate}` : ''}`;
                    return label;
                }
            }
            return `Vozidlo #${vehicleId}`;
        }

        function updateServiceWorkspaceVehicleSelect(customerId) {
            const vehicleSelect = document.getElementById('serviceDocVehicleSelect');
            const infoEl = document.getElementById('serviceDocVehicleInfo');
            if (!vehicleSelect) return;

            const customerIdNum = Number(customerId || 0);
            const vehicles = Array.isArray(serviceWorkspaceState.customerVehicles[customerIdNum])
                ? serviceWorkspaceState.customerVehicles[customerIdNum]
                : [];

            const options = ['<option value="">Obecný záznam bez vazby na konkrétní vozidlo</option>'];
            vehicles.forEach((vehicle) => {
                const sharedLabel = vehicle?.is_shared ? ' • sdílené' : '';
                const label = `${vehicle.nickname || 'Bez názvu'}${vehicle.plate ? ` • ${vehicle.plate}` : ''}${sharedLabel}`;
                options.push(`<option value="${escapeHtml(vehicle.id)}">${escapeHtml(label)}</option>`);
            });
            vehicleSelect.innerHTML = options.join('');

            if (infoEl) {
                const sharedCount = vehicles.filter((vehicle) => Boolean(vehicle?.is_shared)).length;
                infoEl.textContent = vehicles.length
                    ? `Načteno ${vehicles.length} vozidel klienta (${sharedCount} už sdílených se servisem).`
                    : 'Klient zatím nemá žádné vozidlo nebo nebylo načteno.';
            }
        }

        function isServiceWorkspaceCustomerVehiclesLoaded(customerId) {
            const customerIdNum = Number(customerId || 0);
            if (!customerIdNum) return false;
            return Object.prototype.hasOwnProperty.call(serviceWorkspaceState.customerVehicles || {}, customerIdNum);
        }

        function closeServiceClientModal() {
            serviceClientModalState.customerId = null;
            unmountFloatingModal();
        }

        async function openServiceClientModal(customerId) {
            const customerIdNum = Number(customerId || 0);
            if (!customerIdNum) {
                showAlert('Neplatný klient.', 'error');
                return;
            }
            const customer = (Array.isArray(serviceWorkspaceState.customers) ? serviceWorkspaceState.customers : [])
                .find((item) => Number(item?.customer_id || 0) === customerIdNum);
            if (!customer) {
                showAlert('Klient nebyl nalezen.', 'error');
                return;
            }

            if (!isServiceWorkspaceCustomerVehiclesLoaded(customerIdNum)) {
                await loadServiceWorkspaceCustomerVehicles(customerIdNum, true);
            }
            const vehicles = Array.isArray(serviceWorkspaceState.customerVehicles?.[customerIdNum])
                ? serviceWorkspaceState.customerVehicles[customerIdNum]
                : [];
            serviceClientModalState.customerId = customerIdNum;

            const vehicleCards = vehicles.length
                ? vehicles.map((vehicle) => {
                    const vehicleId = Number(vehicle?.id || 0);
                    const label = `${vehicle?.nickname || vehicle?.plate || `Vozidlo #${vehicleId}`}${vehicle?.plate ? ` - ${vehicle.plate}` : ''}`;
                    return `
                        <article class="card" style="padding:12px;">
                            <div style="display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap; align-items:flex-start;">
                                <div>
                                    <h4 style="margin:0 0 4px;">${escapeHtml(label)}</h4>
                                    <p style="margin:0; color:#64748b; font-size:0.9rem;">VIN: ${escapeHtml(vehicle?.vin || '-')} • Rok: ${escapeHtml(vehicle?.year || '-')}</p>
                                    <p style="margin:4px 0 0; color:#64748b; font-size:0.9rem;">STK: ${escapeHtml(vehicle?.stk_valid_until || '-')}</p>
                                </div>
                                <div class="service-workspace-customer-actions">
                                    <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "closeServiceClientModal_a4d59e29", vehicleId)}>Detail vozidla</button>
                                    <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "closeServiceClientModal_ad07d9ed", customerIdNum, vehicleId)}>Nová rezervace</button>
                                    <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "closeServiceClientModal_648bac6a", customerIdNum, vehicleId)}>Nová připomínka</button>
                                </div>
                            </div>
                        </article>
                    `;
                }).join('')
                : '<div class="alert alert-info">Klient zatím nemá žádné vozidlo.</div>';

            mountFloatingModal(`
                <div class="reminder-modal-overlay" ${legacyActionAttributes("click", "closeServiceClientModal_be06b081")}>
                    <div class="reminder-modal service-account-modal service-client-modal">
                        <div class="reminder-modal-head">
                            <div class="reminder-modal-heading">
                                <div>
                                    <p class="reminder-modal-kicker">Klient servisu</p>
                                    <h2 class="modal-title">${escapeHtml(customer?.name || customer?.email || `Klient #${customerIdNum}`)}</h2>
                                </div>
                            </div>
                            <button type="button" class="reminder-modal-close" aria-label="Zavřít okno" ${legacyActionAttributes("click", "closeServiceClientModal_48f60cb7")}>×</button>
                        </div>
                        <p class="reminder-modal-intro service-client-meta">
                            Email: ${escapeHtml(customer?.email || '-')} • Telefon: ${escapeHtml(customer?.phone || '-')} • Poslední servis: ${escapeHtml(customer?.last_service_date ? formatServiceWorkspaceDate(customer.last_service_date) : '-')}
                        </p>
                        <div class="form-actions service-client-quick-actions">
                            <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "closeServiceClientModal_a6e7d7ac", customerIdNum)}>Přidat vozidlo</button>
                            <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "closeServiceClientModal_ac3714d3", customerIdNum)}>Rezervace klienta</button>
                            <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "closeServiceClientModal_1a201e5f", customerIdNum)}>Připomínky klienta</button>
                        </div>
                        <div class="cards-grid service-client-vehicles-grid">
                            ${vehicleCards}
                        </div>
                    </div>
                </div>
            `);
        }

        async function openServiceWorkspaceCustomer(customerId, forceReload = false) {
            const customerIdNum = Number(customerId || 0);
            if (!customerIdNum) {
                showAlert('Neplatný klient.', 'error');
                return;
            }

            serviceWorkspaceState.selectedCustomerId = customerIdNum;
            const shouldReload = forceReload || !isServiceWorkspaceCustomerVehiclesLoaded(customerIdNum);
            if (shouldReload) {
                await loadServiceWorkspaceCustomerVehicles(customerIdNum, false);
            } else {
                renderServiceWorkspace();
                updateServiceWorkspaceVehicleSelect(customerIdNum);
            }
        }

        async function prefillServiceWorkspaceDocumentTarget(customerId, vehicleId = null) {
            const customerIdNum = Number(customerId || 0);
            const vehicleIdNum = Number(vehicleId || 0);
            if (!customerIdNum) {
                showAlert('Neplatný klient pro předvyplnění.', 'error');
                return;
            }

            if (!isServiceWorkspaceCustomerVehiclesLoaded(customerIdNum)) {
                await loadServiceWorkspaceCustomerVehicles(customerIdNum, true);
            }

            serviceWorkspaceState.selectedCustomerId = customerIdNum;
            renderServiceWorkspace();

            const customerSelect = document.getElementById('serviceDocCustomerSelect');
            if (customerSelect) {
                customerSelect.value = String(customerIdNum);
            }
            updateServiceWorkspaceVehicleSelect(customerIdNum);

            const vehicleSelect = document.getElementById('serviceDocVehicleSelect');
            if (vehicleSelect && vehicleIdNum > 0) {
                const optionExists = Array.from(vehicleSelect.options || []).some((option) => Number(option.value || 0) === vehicleIdNum);
                if (optionExists) {
                    vehicleSelect.value = String(vehicleIdNum);
                }
            }

            const targetCard = document.getElementById('serviceWorkspaceDocCard');
            if (targetCard && typeof targetCard.scrollIntoView === 'function') {
                targetCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
            showAlert('Klient a vozidlo jsou připravené pro zápis dokladu.', 'info');
        }

        function openServiceWorkspaceCustomerReservations(customerId) {
            const customerIdNum = Number(customerId || 0);
            if (!customerIdNum) {
                showAlert('Neplatný klient pro filtrování rezervací.', 'error');
                return;
            }
            pendingServiceReservationsCustomerFilter = String(customerIdNum);
            switchTab('reservations');
        }

        async function loadServiceWorkspaceCustomerVehicles(customerId, silent = false) {
            const customerIdNum = Number(customerId || 0);
            if (!customerIdNum) {
                updateServiceWorkspaceVehicleSelect(null);
                return;
            }

            serviceWorkspaceState.selectedCustomerId = customerIdNum;
            if (!silent) {
                serviceWorkspaceState.loadingCustomerVehiclesId = customerIdNum;
                renderServiceWorkspace();
            }

            try {
                const vehicles = await apiCall(`/api/v1/services/workspace/customers/${customerIdNum}/vehicles`, 'GET');
                serviceWorkspaceState.customerVehicles[customerIdNum] = Array.isArray(vehicles) ? vehicles : [];
                updateServiceWorkspaceVehicleSelect(customerIdNum);
            } catch (error) {
                console.error("[SERVICE_WORKSPACE] Nepodařilo se načíst vozidla klienta:");
                serviceWorkspaceState.customerVehicles[customerIdNum] = [];
                updateServiceWorkspaceVehicleSelect(customerIdNum);
                if (!silent) {
                    showAlert(`Nepodařilo se načíst vozidla klienta: ${error.message || 'Neznámá chyba'}`, 'error');
                }
            } finally {
                serviceWorkspaceState.loadingCustomerVehiclesId = null;
                if (!silent) {
                    renderServiceWorkspace();
                }
            }
        }

        async function handleServiceWorkspaceCustomerChange() {
            const customerSelect = document.getElementById('serviceDocCustomerSelect');
            if (!customerSelect) return;
            const selectedCustomerId = Number(customerSelect.value || 0);
            serviceWorkspaceState.selectedCustomerId = selectedCustomerId || null;
            await loadServiceWorkspaceCustomerVehicles(selectedCustomerId);
        }

        function renderServiceWorkspace() {
            const container = document.getElementById('serviceWorkspaceContainer');
            if (!container) return;

            const customers = Array.isArray(serviceWorkspaceState.customers) ? serviceWorkspaceState.customers : [];
            const invitations = Array.isArray(serviceWorkspaceState.invitations) ? serviceWorkspaceState.invitations : [];
            const documents = Array.isArray(serviceWorkspaceState.documents) ? serviceWorkspaceState.documents : [];
            const selectedCustomerId = Number(serviceWorkspaceState.selectedCustomerId || 0);
            const loadingCustomerVehiclesId = Number(serviceWorkspaceState.loadingCustomerVehiclesId || 0);

            const customerCards = customers.length
                ? customers.map((customer) => {
                    const customerId = Number(customer.customer_id || 0);
                    const hasLoadedVehicles = isServiceWorkspaceCustomerVehiclesLoaded(customerId);
                    const loadedVehicles = hasLoadedVehicles
                        ? (Array.isArray(serviceWorkspaceState.customerVehicles[customerId]) ? serviceWorkspaceState.customerVehicles[customerId] : [])
                        : [];
                    const isLoading = loadingCustomerVehiclesId === customerId;
                    const isSelected = selectedCustomerId === customerId;
                    const vehicles = hasLoadedVehicles ? loadedVehicles.length : Number(customer.vehicles_count || 0);
                    const sharedVehicles = hasLoadedVehicles
                        ? loadedVehicles.filter((vehicle) => Boolean(vehicle?.is_shared)).length
                        : Number(customer.shared_vehicles_count || 0);

                    const vehiclesDetailHtml = (() => {
                        if (!isSelected) return '';
                        if (isLoading) {
                            return '<div class="service-workspace-vehicle-panel"><p class="service-workspace-vehicle-meta">Načítám vozidla klienta...</p></div>';
                        }
                        if (!hasLoadedVehicles) {
                            return `
                                <div class="service-workspace-vehicle-panel">
                                    <p class="service-workspace-vehicle-meta">Vozidla nejsou načtená. Klikněte na „Obnovit vozidla“.</p>
                                </div>
                            `;
                        }
                        if (!loadedVehicles.length) {
                            return `
                                <div class="service-workspace-vehicle-panel">
                                    <p class="service-workspace-vehicle-meta">Klient zatím nemá žádné vozidlo v evidenci.</p>
                                </div>
                            `;
                        }

                        const pendingVehicleCount = loadedVehicles.filter((vehicle) => !Boolean(vehicle?.is_shared)).length;
                        return `
                            <div class="service-workspace-vehicle-panel">
                                ${pendingVehicleCount > 0 ? `
                                    <p class="service-workspace-vehicle-meta">
                                        ${escapeHtml(pendingVehicleCount)} vozidel čeká na potvrzení klientem. Klient potvrzuje sdílení ve své záložce <strong>Servisy</strong>.
                                    </p>
                                ` : ''}
                                ${loadedVehicles.map((vehicle) => {
                                    const vehicleId = Number(vehicle?.id || 0);
                                    const isShared = Boolean(vehicle?.is_shared);
                                    const statusClass = isShared ? 'shared' : 'pending';
                                    const statusLabel = isShared ? 'Sdílené se servisem' : 'Čeká na povolení klienta';
                                    const detailDisabled = isShared ? '' : 'disabled';
                                    const detailTitle = isShared ? '' : 'title="Klient zatím nepovolil detailní správu tohoto vozidla."';
                                    const vehicleLabel = `${vehicle?.nickname || 'Bez názvu'}${vehicle?.plate ? ` • ${vehicle.plate}` : ''}`;
                                    const vinLabel = String(vehicle?.vin || '').trim();
                                    const yearLabel = Number(vehicle?.year || 0) > 0 ? String(vehicle.year) : '-';
                                    return `
                                        <article class="service-workspace-vehicle-item">
                                            <div>
                                                <p style="margin:0; font-weight:700; color:#0f172a;">${escapeHtml(vehicleLabel)}</p>
                                                <p class="service-workspace-vehicle-meta">VIN: ${escapeHtml(vinLabel || '-')} • Rok: ${escapeHtml(yearLabel)}</p>
                                                <p class="service-workspace-vehicle-meta">STK: ${escapeHtml(vehicle?.stk_valid_until || '-')}</p>
                                                <span class="service-workspace-status-pill ${statusClass}">${escapeHtml(statusLabel)}</span>
                                            </div>
                                            <div class="service-workspace-customer-actions">
                                                <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "openServiceReservationComposer_fd52392c", customerId, vehicleId)}>
                                                    Nová rezervace
                                                </button>
                                                <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "openServiceReminderComposer_ab64b1f8", customerId, vehicleId)}>
                                                    Připomínka
                                                </button>
                                                <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "prefillServiceWorkspaceDocumentTarget_0b744773", customerId, vehicleId)}>
                                                    Připravit doklad
                                                </button>
                                                <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "openVehicleFromShortcut_82ac6bf3", vehicleId)} ${detailDisabled} ${detailTitle}>
                                                    Detail vozidla
                                                </button>
                                            </div>
                                        </article>
                                    `;
                                }).join('')}
                            </div>
                        `;
                    })();

                    return `
                        <article class="card service-workspace-customer-card ${isSelected ? 'is-active' : ''}" style="padding:14px; margin-bottom:10px;">
                            <div style="display:flex; justify-content:space-between; gap:12px; align-items:flex-start; flex-wrap:wrap;">
                                <div>
                                    <h4 style="margin:0 0 4px;">${escapeHtml(customer.name || customer.email || `Klient #${customerId}`)}</h4>
                                    <div style="color:#64748b; font-size:0.92rem;">${escapeHtml(customer.email || '-')}</div>
                                    <div style="color:#64748b; font-size:0.9rem; margin-top:4px;">
                                        Telefon: ${escapeHtml(customer.phone || '-')} • Poslední servis: ${escapeHtml(customer.last_service_date ? formatServiceWorkspaceDate(customer.last_service_date) : '-')}
                                    </div>
                                    <div style="color:#64748b; font-size:0.9rem; margin-top:6px;">
                                        Vozidla: <strong>${escapeHtml(vehicles)}</strong> • Sdílená: <strong>${escapeHtml(sharedVehicles)}</strong> • Napojeno: ${escapeHtml(formatServiceWorkspaceDate(customer.created_at))}
                                    </div>
                                </div>
                                <div class="service-workspace-customer-actions">
                                    <button class="btn btn-secondary" type="button" ${legacyActionAttributes("click", "openServiceWorkspaceCustomer_faefa5e5", customerId)}>
                                        ${isSelected ? 'Aktivní klient' : 'Otevřít klienta'}
                                    </button>
                                    <button class="btn btn-secondary" type="button" ${legacyActionAttributes("click", "loadServiceWorkspaceCustomerVehicles_6aec8672", customerId)}>
                                        Obnovit vozidla
                                    </button>
                                    <button class="btn btn-secondary" type="button" ${legacyActionAttributes("click", "openServiceWorkspaceCustomerReservations_8b4ab9d5", customerId)}>
                                        Rezervace klienta
                                    </button>
                                    <button class="btn btn-secondary" type="button" ${legacyActionAttributes("click", "openServiceWorkspaceCustomerReminders_0411a86b", customerId)}>
                                        Připomínky klienta
                                    </button>
                                    <button class="btn btn-secondary" type="button" ${legacyActionAttributes("click", "openServiceAddVehicleForCustomer_9327e9bd", customerId)}>
                                        Přidat vozidlo
                                    </button>
                                    <button class="btn btn-secondary" type="button" ${legacyActionAttributes("click", "openServiceClientModal_c7be19a8", customerId)}>
                                        Detail klienta
                                    </button>
                                </div>
                            </div>
                            ${vehiclesDetailHtml}
                        </article>
                    `;
                }).join('')
                : '<div class="card" style="padding:14px; color:#64748b;">Zatím nemáte přiřazené žádné klienty. Přidejte existující účet nebo odešlete pozvánku.</div>';

            const invitationRows = invitations.length
                ? invitations.map((invite) => {
                    const inviteId = Number(invite?.id || 0);
                    const statusMeta = getServiceWorkspaceInviteStatusMeta(invite?.status, Boolean(invite?.is_completed));
                    const statusLabel = String(invite?.status_label || statusMeta.label || '-');
                    const canResend = invite?.can_resend !== undefined
                        ? Boolean(invite.can_resend)
                        : ['pending', 'expired', 'cancelled'].includes(statusMeta.key);
                    const canDelete = invite?.can_delete !== undefined
                        ? Boolean(invite.can_delete)
                        : true;
                    const inviteName = String(invite?.invite_name || '').trim();
                    const emailCell = inviteName
                        ? `${escapeHtml(invite.invite_email || '-')}<div style="font-size:0.82rem; color:#64748b;">${escapeHtml(inviteName)}</div>`
                        : `${escapeHtml(invite.invite_email || '-')}`;
                    return `
                        <tr>
                            <td style="padding:8px; border-bottom:1px solid #f1f5f9;">${emailCell}</td>
                            <td style="padding:8px; border-bottom:1px solid #f1f5f9;">
                                <span style="display:inline-flex; align-items:center; border:1px solid ${escapeHtml(statusMeta.border)}; background:${escapeHtml(statusMeta.bg)}; color:${escapeHtml(statusMeta.color)}; border-radius:999px; padding:4px 10px; font-size:0.8rem; font-weight:700;">
                                    ${escapeHtml(statusLabel)}
                                </span>
                            </td>
                            <td style="padding:8px; border-bottom:1px solid #f1f5f9;">${escapeHtml(formatServiceWorkspaceDate(invite.sent_at))}</td>
                            <td style="padding:8px; border-bottom:1px solid #f1f5f9;">${escapeHtml(invite.accepted_at ? formatServiceWorkspaceDate(invite.accepted_at) : '-')}</td>
                            <td style="padding:8px; border-bottom:1px solid #f1f5f9;">
                                <div style="display:flex; gap:6px; flex-wrap:wrap;">
                                    <button
                                        type="button"
                                        class="btn btn-secondary"
                                        style="padding:6px 10px; font-size:0.8rem;"
                                        ${canResend && inviteId > 0 ? '' : 'disabled'}
                                        ${legacyActionAttributes("click", "resendServiceInvitation_ceea120d", inviteId)}
                                    >
                                        Odeslat znovu
                                    </button>
                                    <button
                                        type="button"
                                        class="btn"
                                        style="padding:6px 10px; font-size:0.8rem; background:#dc2626; color:#fff; border:none;"
                                        ${canDelete && inviteId > 0 ? '' : 'disabled'}
                                        ${legacyActionAttributes("click", "deleteServiceInvitation_5e4b9c08", inviteId)}
                                    >
                                        Smazat
                                    </button>
                                </div>
                            </td>
                        </tr>
                    `;
                }).join('')
                : '<tr><td colspan="5" style="color:#64748b;">Žádné pozvánky.</td></tr>';

            const documentCards = documents.length
                ? documents.map((doc) => {
                    const total = Number(doc?.total_with_vat);
                    const amount = Number.isFinite(total)
                        ? `${total.toLocaleString('cs-CZ')} ${escapeHtml(doc.currency || 'CZK')}`
                        : '-';
                    const confidenceRaw = Number(doc?.parse_confidence);
                    const confidence = Number.isFinite(confidenceRaw) ? Math.round(confidenceRaw * 100) : 0;
                    const statusMeta = getServiceWorkspaceProcessingStatusMeta(doc?.processing_status);
                    const customerLabel = getServiceWorkspaceCustomerLabel(doc);
                    const vehicleLabel = getServiceWorkspaceVehicleLabel(doc);
                    const createdRecordLabel = doc?.auto_created_service_record_id
                        ? `Servisní záznam #${doc.auto_created_service_record_id}`
                        : 'Servisní záznam nevytvořen';
                    const inputMethod = getServiceWorkspaceInputMethodLabel(doc?.input_method);
                    const extractionEngine = getServiceWorkspaceExtractionEngineLabel(doc?.extraction_engine || doc?.parsed_data?.extraction_engine);
                    const sourceFile = doc?.original_filename ? escapeHtml(doc.original_filename) : 'bez souboru';
                    const extractionWarning = doc?.extraction_warning || doc?.parsed_data?.extraction_warning || null;
                    const textPreview = String(doc?.extracted_text_preview || '').trim();
                    const parsedItems = sanitizeServiceWorkspaceItems(
                        doc?.parsed_data?.items,
                        doc?.parsed_data?.total_with_vat ?? doc?.total_with_vat,
                        String(doc?.currency || doc?.parsed_data?.currency || 'CZK').toUpperCase()
                    ).slice(0, 8);
                    const parsedItemsRows = parsedItems.map((item) => `
                        <tr>
                            <td>${escapeHtml(item.name)}</td>
                            <td style="text-align:center;">${escapeHtml(formatRecordQuantity(item.quantity))}</td>
                            <td style="text-align:center;">${escapeHtml(item.unit)}</td>
                            <td style="text-align:right; white-space:nowrap; font-weight:700;">${escapeHtml(formatRecordMoney(item.totalPrice, item.currency))}</td>
                        </tr>
                    `).join('');
                    const parsedItemsHtml = parsedItemsRows
                        ? `
                            <div style="margin-top:8px; border:1px solid #e2e8f0; border-radius:8px; overflow:hidden;">
                                <table style="width:100%; border-collapse:collapse; font-size:0.84rem;">
                                    <thead>
                                        <tr style="background:#f8fafc; color:#475569;">
                                            <th style="padding:6px 8px; text-align:left;">Položka</th>
                                            <th style="padding:6px 8px; text-align:center; width:12%;">Počet</th>
                                            <th style="padding:6px 8px; text-align:center; width:12%;">Jedn.</th>
                                            <th style="padding:6px 8px; text-align:right; width:20%;">Celkem</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${parsedItemsRows}
                                    </tbody>
                                </table>
                            </div>
                        `
                        : '';
                    return `
                        <article class="card" style="padding:14px; margin-bottom:10px;">
                            <div style="display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap; align-items:flex-start;">
                                <div>
                                    <h4 style="margin:0 0 4px;">${escapeHtml(getServiceWorkspaceSourceLabel(doc.source_type))} • ${escapeHtml(doc.document_number || 'Bez čísla')}</h4>
                                    <div style="font-size:0.92rem; color:#64748b;">
                                        Dodavatel: ${escapeHtml(doc.supplier_name || '-')} • Cena s DPH: <strong>${escapeHtml(amount)}</strong>
                                    </div>
                                    <div style="font-size:0.9rem; color:#64748b; margin-top:6px;">
                                        <strong>Kam se přidalo:</strong> ${escapeHtml(customerLabel)} • ${escapeHtml(vehicleLabel)} • ${escapeHtml(createdRecordLabel)}
                                    </div>
                                    <div style="font-size:0.9rem; color:#64748b; margin-top:4px;">
                                        <strong>Jak se zpracovalo:</strong> ${escapeHtml(inputMethod)} • ${escapeHtml(extractionEngine)} • Důvěra ${escapeHtml(confidence)}%
                                    </div>
                                    <div style="font-size:0.88rem; color:#64748b; margin-top:4px;">
                                        Soubor: ${sourceFile} • ${escapeHtml(formatServiceWorkspaceDate(doc.created_at))}
                                    </div>
                                    ${extractionWarning ? `<div style="margin-top:6px; font-size:0.86rem; color:#92400e; background:#fffbeb; border:1px solid #fcd34d; border-radius:8px; padding:6px 8px;">Upozornění parseru: ${escapeHtml(extractionWarning)}</div>` : ''}
                                    ${textPreview ? `
                                        <details style="margin-top:8px;">
                                            <summary style="cursor:pointer; color:#475569; font-size:0.88rem;">Náhled rozpoznaného textu</summary>
                                            <div style="margin-top:6px; font-size:0.84rem; color:#64748b; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:8px; white-space:pre-wrap; max-height:110px; overflow:auto;">
                                                ${escapeHtml(textPreview)}
                                            </div>
                                        </details>
                                    ` : ''}
                                    ${parsedItemsHtml}
                                    ${doc?.auto_created_service_record_id && doc?.vehicle_id ? `
                                        <button type="button" class="btn btn-secondary" style="margin-top:8px;" ${legacyActionAttributes("click", "showServiceRecordDetail_941afdd3", Number(doc.auto_created_service_record_id), Number(doc.vehicle_id))}>
                                            Otevřít vytvořený záznam
                                        </button>
                                    ` : ''}
                                </div>
                                <div style="display:flex; flex-direction:column; gap:8px; align-items:flex-end;">
                                    <div style="display:inline-flex; align-items:center; border:1px solid ${escapeHtml(statusMeta.border)}; background:${escapeHtml(statusMeta.bg)}; color:${escapeHtml(statusMeta.color)}; border-radius:999px; padding:4px 10px; font-size:0.82rem; font-weight:700;">
                                        ${escapeHtml(statusMeta.label)}
                                    </div>
                                    <div style="display:inline-flex; align-items:center; border:1px solid #dbeafe; background:#eff6ff; color:#1d4ed8; border-radius:999px; padding:4px 10px; font-size:0.82rem; font-weight:700;">
                                        ${escapeHtml(confidence)}%
                                    </div>
                                </div>
                            </div>
                        </article>
                    `;
                }).join('')
                : '<div class="card" style="padding:14px; color:#64748b;">Zatím nejsou zpracované žádné dokumenty.</div>';

            const customerSelectOptions = ['<option value="">Vyberte klienta...</option>'].concat(
                customers.map((customer) => {
                    const selected = Number(customer.customer_id) === selectedCustomerId ? 'selected' : '';
                    const label = `${customer.name || customer.email} (${customer.email || '-'})`;
                    return `<option value="${escapeHtml(customer.customer_id)}" ${selected}>${escapeHtml(label)}</option>`;
                })
            ).join('');

            container.classList.remove('loading');
            container.innerHTML = `
                <div id="serviceWorkspaceCustomersCard" class="card" style="padding:16px; margin-bottom:16px;">
                    <h3 style="margin:0 0 10px;">Klienti servisu</h3>
                    <p style="margin:0 0 12px; color:#64748b;">
                        Připojte existující účet zákazníka nebo odešlete pozvánku k registraci. Po propojení vidíte historii vozidel a můžete zapisovat servisní práci.
                    </p>
                    <div class="form-row" style="display:grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap:10px; margin-bottom:12px;">
                        <div class="form-group" style="margin:0;">
                            <label for="serviceLinkCustomerEmail">Existující účet (email):</label>
                            <input id="serviceLinkCustomerEmail" type="email" placeholder="klient@email.cz">
                        </div>
                        <div class="form-group" style="margin:0;">
                            <label for="serviceLinkCustomerNote">Poznámka (volitelně):</label>
                            <input id="serviceLinkCustomerNote" type="text" placeholder="např. stálý klient">
                        </div>
                    </div>
                    <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "linkServiceExistingCustomer_19053366")}>Přiřadit existující účet</button>
                    <div style="height:12px;"></div>
                    ${customerCards}
                </div>

                <div id="serviceWorkspaceInvitesCard" class="card" style="padding:16px; margin-bottom:16px;">
                    <h3 style="margin:0 0 10px;">Pozvánka k registraci</h3>
                    <p style="margin:0 0 12px; color:#64748b;">
                        Pokud zákazník účet nemá, pošlete mu pozvánku mailem. Po registraci se může jedním klikem spárovat se servisem.
                    </p>
                    <div class="form-row" style="display:grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap:10px;">
                        <div class="form-group" style="margin:0;">
                            <label for="serviceInviteEmail">Email zákazníka:</label>
                            <input id="serviceInviteEmail" type="email" placeholder="novy.klient@email.cz">
                        </div>
                        <div class="form-group" style="margin:0;">
                            <label for="serviceInviteName">Jméno zákazníka:</label>
                            <input id="serviceInviteName" type="text" placeholder="Jan Novák">
                        </div>
                        <div class="form-group" style="margin:0;">
                            <label for="serviceInviteMessage">Zpráva:</label>
                            <input id="serviceInviteMessage" type="text" placeholder="Máte připravenou servisní historii vašeho auta">
                        </div>
                    </div>
                    <button type="button" class="btn" style="margin-top:10px;" ${legacyActionAttributes("click", "sendServiceInvitation_7750021b")}>Odeslat pozvánku</button>

                    <div style="margin-top:14px; overflow:auto;">
                        <table style="width:100%; border-collapse:collapse;">
                            <thead>
                                <tr style="text-align:left;">
                                    <th style="padding:8px; border-bottom:1px solid #e2e8f0;">Email</th>
                                    <th style="padding:8px; border-bottom:1px solid #e2e8f0;">Stav</th>
                                    <th style="padding:8px; border-bottom:1px solid #e2e8f0;">Odesláno</th>
                                    <th style="padding:8px; border-bottom:1px solid #e2e8f0;">Přijato</th>
                                    <th style="padding:8px; border-bottom:1px solid #e2e8f0;">Akce</th>
                                </tr>
                            </thead>
                            <tbody>${invitationRows}</tbody>
                        </table>
                    </div>
                </div>

                <div id="serviceWorkspaceDocCard" class="card" style="padding:16px; margin-bottom:16px;">
                    <h3 style="margin:0 0 10px;">Automatická evidence z dokladu</h3>
                    <p style="margin:0 0 12px; color:#64748b;">
                        Nahrajte fakturu, dodací list, fotku dokladu nebo vložte text ručně. Aplikace vytěží položky (práce, materiál, DPH, celkem) a může automaticky vytvořit servisní záznam.
                    </p>
                    <div class="form-row" style="display:grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap:10px;">
                        <div class="form-group" style="margin:0;">
                            <label for="serviceDocCustomerSelect">Klient *:</label>
                            <select id="serviceDocCustomerSelect" ${legacyActionAttributes("change", "handleServiceWorkspaceCustomerChange_4af2f865")}>
                                ${customerSelectOptions}
                            </select>
                        </div>
                        <div class="form-group" style="margin:0;">
                            <label for="serviceDocVehicleSelect">Vozidlo:</label>
                            <select id="serviceDocVehicleSelect"></select>
                            <small id="serviceDocVehicleInfo" class="form-hint">Vyberte klienta pro načtení vozidel.</small>
                        </div>
                        <div class="form-group" style="margin:0;">
                            <label for="serviceDocSourceType">Typ dokladu:</label>
                            <select id="serviceDocSourceType">
                                <option value="invoice">Faktura</option>
                                <option value="delivery_note">Dodací list</option>
                                <option value="work_order">Zakázkový list</option>
                                <option value="receipt">Účtenka</option>
                                <option value="manual">Ruční zápis</option>
                            </select>
                        </div>
                    </div>
                    <div class="form-group" style="margin-top:10px;">
                        <label for="serviceDocManualText">Ruční text (volitelně):</label>
                        <textarea id="serviceDocManualText" rows="4" placeholder="Sem můžete vložit text z dokladu nebo doplnit poznámky..."></textarea>
                    </div>
                    <div class="form-row" style="display:grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap:10px; margin-top:10px;">
                        <div class="form-group" style="margin:0;">
                            <label for="serviceDocManualNote">Poznámka do záznamu:</label>
                            <input id="serviceDocManualNote" type="text" placeholder="např. urgentní oprava, schváleno telefonicky">
                        </div>
                        <div class="form-group" style="margin:0;">
                            <label for="serviceDocFileInput">Soubor (PDF/foto/txt):</label>
                            <input id="serviceDocFileInput" type="file" accept=".pdf,.txt,.csv,.json,image/*">
                        </div>
                    </div>
                    <label class="checkbox-label" style="margin-top:10px;">
                        <input id="serviceDocAutoCreateRecord" type="checkbox" checked>
                        <span class="checkbox-text">Po zpracování automaticky vytvořit servisní záznam</span>
                    </label>
                    <button type="button" class="btn" style="margin-top:10px;" ${legacyActionAttributes("click", "ingestServiceDocument_646c7d3c")}>Zpracovat doklad</button>
                    <div id="serviceDocResult" style="margin-top:12px;"></div>
                </div>

                <div class="card" style="padding:16px;">
                    <h3 style="margin:0 0 10px;">Naposledy zpracované doklady</h3>
                    ${documentCards}
                </div>
            `;

            updateServiceWorkspaceVehicleSelect(selectedCustomerId || null);
        }

        async function loadServiceWorkspace() {
            const container = document.getElementById('serviceWorkspaceContainer');
            if (!container) return;

            if (!isServiceWorkspaceRole()) {
                container.classList.remove('loading');
                container.innerHTML = `
                    <div class="alert alert-info">
                        Servisní centrum je dostupné pouze pro servisní účty.
                    </div>
                `;
                return;
            }

            container.classList.add('loading');
            container.innerHTML = 'Načítám servisní centrum...';

            try {
                const [customers, invitations, documents] = await Promise.all([
                    apiCall('/api/v1/services/workspace/customers', 'GET'),
                    apiCall('/api/v1/services/workspace/invitations', 'GET'),
                    apiCall('/api/v1/services/workspace/documents?limit=20', 'GET')
                ]);

                serviceWorkspaceState.customers = Array.isArray(customers) ? customers : [];
                serviceWorkspaceState.invitations = Array.isArray(invitations) ? invitations : [];
                serviceWorkspaceState.documents = Array.isArray(documents) ? documents : [];
                serviceWorkspaceState.loadingCustomerVehiclesId = null;

                const customerIds = serviceWorkspaceState.customers.map((item) => Number(item.customer_id)).filter((id) => id > 0);
                if (!serviceWorkspaceState.selectedCustomerId || !customerIds.includes(Number(serviceWorkspaceState.selectedCustomerId))) {
                    serviceWorkspaceState.selectedCustomerId = customerIds.length ? customerIds[0] : null;
                }

                renderServiceWorkspace();

                if (serviceWorkspaceState.selectedCustomerId) {
                    await loadServiceWorkspaceCustomerVehicles(serviceWorkspaceState.selectedCustomerId, true);
                    renderServiceWorkspace();
                }
            } catch (error) {
                console.error("[SERVICE_WORKSPACE] Error loading service workspace:");
                container.classList.remove('loading');
                container.innerHTML = `
                    <div class="alert alert-error">
                        Nepodařilo se načíst servisní centrum: ${escapeHtml(error.message || 'Neznámá chyba')}
                    </div>
                `;
            }
        }

        async function linkServiceExistingCustomer() {
            const emailInput = document.getElementById('serviceLinkCustomerEmail');
            const noteInput = document.getElementById('serviceLinkCustomerNote');
            const email = String(emailInput?.value || '').trim();
            const note = String(noteInput?.value || '').trim();

            if (!email) {
                showAlert('Zadejte email existujícího zákazníka.', 'error');
                return;
            }

            try {
                const response = await apiCall('/api/v1/services/workspace/customers/link-existing', 'POST', {
                    customer_email: email,
                    note: note || null
                });
                showAlert(response?.message || 'Klient byl úspěšně přiřazen.', 'success');
                if (emailInput) emailInput.value = '';
                if (noteInput) noteInput.value = '';
                await loadServiceWorkspace();
            } catch (error) {
                console.error("[SERVICE_WORKSPACE] link existing customer error:");
                showAlert(`Nepodařilo se přiřadit klienta: ${error.message || 'Neznámá chyba'}`, 'error');
            }
        }

        async function sendServiceInvitation() {
            const email = String(document.getElementById('serviceInviteEmail')?.value || '').trim();
            const name = String(document.getElementById('serviceInviteName')?.value || '').trim();
            const message = String(document.getElementById('serviceInviteMessage')?.value || '').trim();

            if (!email) {
                showAlert('Zadejte email pro pozvánku.', 'error');
                return;
            }

            try {
                const response = await apiCall('/api/v1/services/workspace/invitations/send', 'POST', {
                    invite_email: email,
                    invite_name: name || null,
                    invite_message: message || null
                });

                if (response?.already_linked) {
                    showAlert(response?.message || 'Účet už existuje, klient byl rovnou propojen.', 'success');
                } else if (response?.email_sent) {
                    showAlert(response?.message || 'Pozvánka byla odeslána na email zákazníka.', 'success');
                } else {
                    const linkText = response?.registration_url ? ` Registrační odkaz: ${response.registration_url}` : '';
                    showAlert((response?.message || 'Pozvánka byla vytvořena.') + linkText, 'info');
                }

                const inviteEmailInput = document.getElementById('serviceInviteEmail');
                const inviteNameInput = document.getElementById('serviceInviteName');
                const inviteMessageInput = document.getElementById('serviceInviteMessage');
                if (inviteEmailInput) inviteEmailInput.value = '';
                if (inviteNameInput) inviteNameInput.value = '';
                if (inviteMessageInput) inviteMessageInput.value = '';

                await loadServiceWorkspace();
            } catch (error) {
                console.error("[SERVICE_WORKSPACE] send invitation error:");
                showAlert(`Nepodařilo se odeslat pozvánku: ${error.message || 'Neznámá chyba'}`, 'error');
            }
        }

        async function resendServiceInvitation(inviteId) {
            const id = Number(inviteId || 0);
            if (!id) {
                showAlert('Neplatné ID pozvánky.', 'error');
                return;
            }
            try {
                showAlert('Odesílám pozvánku znovu...', 'info');
                const response = await apiCall(`/api/v1/services/workspace/invitations/${id}/resend`, 'POST');
                if (response?.linked_now) {
                    showAlert(response?.message || 'Účet už existuje, pozvánka je vyřízená.', 'success');
                } else if (response?.email_sent) {
                    showAlert(response?.message || 'Pozvánka byla znovu odeslána.', 'success');
                } else {
                    const linkText = response?.registration_url ? ` Registrační odkaz: ${response.registration_url}` : '';
                    showAlert((response?.message || 'Pozvánka byla obnovena.') + linkText, 'info');
                }
                await loadServiceWorkspace();
            } catch (error) {
                console.error("[SERVICE_WORKSPACE] resend invitation error:");
                showAlert(`Nepodařilo se pozvánku odeslat znovu: ${error.message || 'Neznámá chyba'}`, 'error');
            }
        }

        async function deleteServiceInvitation(inviteId) {
            const id = Number(inviteId || 0);
            if (!id) {
                showAlert('Neplatné ID pozvánky.', 'error');
                return;
            }
            const confirmed = confirm('Opravdu chcete tuto pozvánku smazat?');
            if (!confirmed) {
                return;
            }
            try {
                await apiCall(`/api/v1/services/workspace/invitations/${id}`, 'DELETE');
                showAlert('Pozvánka byla smazána.', 'success');
                await loadServiceWorkspace();
            } catch (error) {
                console.error("[SERVICE_WORKSPACE] delete invitation error:");
                showAlert(`Nepodařilo se smazat pozvánku: ${error.message || 'Neznámá chyba'}`, 'error');
            }
        }

        function readFileAsBase64(file) {
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => {
                    try {
                        const result = String(reader.result || '');
                        const base64 = result.includes(',') ? result.split(',', 2)[1] : result;
                        resolve(base64);
                    } catch (error) {
                        reject(error);
                    }
                };
                reader.onerror = () => reject(new Error('Nepodařilo se načíst soubor.'));
                reader.readAsDataURL(file);
            });
        }

        function renderServiceDocumentResult(result) {
            const target = document.getElementById('serviceDocResult');
            if (!target) return;

            const parsed = result?.parsed_data || {};
            const rawItems = Array.isArray(parsed?.items) ? parsed.items : [];
            const currency = String(parsed?.currency || result?.currency || 'CZK').toUpperCase();
            const totalWithVat = parsed?.total_with_vat ?? result?.total_with_vat ?? null;
            const items = sanitizeServiceWorkspaceItems(rawItems, totalWithVat, currency);
            const labor = parsed?.labor_total ?? result?.labor_total ?? null;
            const materials = parsed?.materials_total ?? result?.materials_total ?? null;
            const confidenceRaw = Number(result?.parse_confidence ?? parsed?.confidence ?? 0);
            const confidence = Number.isFinite(confidenceRaw) ? Math.round(confidenceRaw * 100) : 0;
            const statusMeta = getServiceWorkspaceProcessingStatusMeta(result?.processing_status);
            const inputMethod = getServiceWorkspaceInputMethodLabel(result?.input_method);
            const extractionEngine = getServiceWorkspaceExtractionEngineLabel(result?.extraction_engine || parsed?.extraction_engine);
            const extractionWarning = result?.extraction_warning || parsed?.extraction_warning || null;
            const sourceFile = result?.original_filename || 'bez souboru';
            const createdAt = formatServiceWorkspaceDate(result?.created_at);

            const customerSelect = document.getElementById('serviceDocCustomerSelect');
            const selectedCustomerText = customerSelect?.selectedOptions?.[0]?.textContent || '';
            const customerLabel = getServiceWorkspaceCustomerLabel(result) !== '-'
                ? getServiceWorkspaceCustomerLabel(result)
                : (selectedCustomerText || '-');

            const vehicleSelect = document.getElementById('serviceDocVehicleSelect');
            const selectedVehicleRaw = vehicleSelect?.selectedOptions?.[0]?.textContent || '';
            const selectedVehicleText = selectedVehicleRaw && !selectedVehicleRaw.toLowerCase().includes('obecný záznam')
                ? selectedVehicleRaw
                : 'Bez vazby na vozidlo';
            const vehicleLabel = getServiceWorkspaceVehicleLabel(result) !== '-'
                ? getServiceWorkspaceVehicleLabel(result)
                : selectedVehicleText;

            const createdRecordLabel = result?.auto_created_service_record_id
                ? `Servisní záznam #${result.auto_created_service_record_id}`
                : 'Servisní záznam nebyl automaticky vytvořen';
            const hasRecordLink = Number(result?.auto_created_service_record_id || 0) > 0 && Number(result?.vehicle_id || 0) > 0;
            const serviceSummary = String(parsed?.service_summary || '').trim();
            const issueDescription = String(parsed?.issue_description || '').trim();
            const technicianName = String(parsed?.technician_name || '').trim();
            const technicianInitials = String(parsed?.technician_initials || '').trim();
            const supplierName = String(parsed?.supplier_name || '').trim();
            const supplierEmail = String(parsed?.supplier_email || '').trim();

            const rowsHtml = items.map((item) => `
                <tr>
                    <td>${escapeHtml(item.name || 'Položka')}</td>
                    <td class="col-qty">${escapeHtml(formatRecordQuantity(item.quantity))}</td>
                    <td class="col-unit">${escapeHtml(item.unit || '—')}</td>
                    <td class="col-price">${escapeHtml(formatRecordMoney(item.unitPrice, item.currency))}</td>
                    <td class="col-total">${escapeHtml(formatRecordMoney(item.totalPrice, item.currency))}</td>
                </tr>
            `).join('');
            const itemsTableHtml = rowsHtml
                ? `
                    <div class="card" style="margin-top:10px; padding:10px;">
                        <div style="font-weight:700; margin-bottom:8px;">Rozpoznané položky (kontrola před uložením):</div>
                        <div class="record-items-table-wrap" style="margin-top:0;">
                            <table class="record-items-table">
                                <thead>
                                    <tr>
                                        <th style="width:44%;">Položka</th>
                                        <th style="width:11%;">Počet</th>
                                        <th style="width:11%;">Jedn.</th>
                                        <th class="col-price" style="width:17%;">Cena/ks</th>
                                        <th class="col-total" style="width:17%;">Celkem</th>
                                    </tr>
                                </thead>
                                <tbody>${rowsHtml}</tbody>
                            </table>
                        </div>
                    </div>
                `
                : '';

            target.innerHTML = `
                <div class="alert alert-success" style="margin:0;">
                    <div style="display:flex; justify-content:space-between; gap:10px; align-items:flex-start; flex-wrap:wrap;">
                        <div>
                            <strong>Doklad zpracován</strong><br>
                            Doklad #${escapeHtml(parsed?.document_number || '-')} • ${escapeHtml(getServiceWorkspaceSourceLabel(result?.source_type || parsed?.source_type))}
                        </div>
                        <div style="display:inline-flex; align-items:center; border:1px solid ${escapeHtml(statusMeta.border)}; background:${escapeHtml(statusMeta.bg)}; color:${escapeHtml(statusMeta.color)}; border-radius:999px; padding:4px 10px; font-size:0.82rem; font-weight:700;">
                            ${escapeHtml(statusMeta.label)}
                        </div>
                    </div>
                    <div style="margin-top:8px;">
                        <strong>Kam se přidalo:</strong> ${escapeHtml(customerLabel)} • ${escapeHtml(vehicleLabel)} • ${escapeHtml(createdRecordLabel)}
                    </div>
                    <div style="margin-top:4px;">
                        <strong>Jak se zpracovalo:</strong> ${escapeHtml(inputMethod)} • ${escapeHtml(extractionEngine)} • Důvěra ${escapeHtml(confidence)}% • ${escapeHtml(createdAt)}
                    </div>
                    <div style="margin-top:4px;">
                        <strong>Soubor:</strong> ${escapeHtml(sourceFile)}
                    </div>
                    ${supplierName ? `<div style="margin-top:4px;"><strong>Dodavatel:</strong> ${escapeHtml(supplierName)}</div>` : ''}
                    ${supplierEmail ? `<div style="margin-top:4px;"><strong>Kontakt:</strong> ${escapeHtml(supplierEmail)}</div>` : ''}
                    ${serviceSummary ? `<div style="margin-top:4px;"><strong>Rozsah prací:</strong> ${escapeHtml(serviceSummary)}</div>` : ''}
                    ${issueDescription ? `<div style="margin-top:4px;"><strong>Popis závady:</strong> ${escapeHtml(issueDescription)}</div>` : ''}
                    ${technicianName ? `<div style="margin-top:4px;"><strong>Technik:</strong> ${escapeHtml(technicianName)}${technicianInitials ? ` (${escapeHtml(technicianInitials)})` : ''}</div>` : ''}
                    <div style="margin-top:4px;">
                        Cena s DPH: <strong>${escapeHtml(formatRecordMoney(totalWithVat, currency))}</strong> •
                        Práce: ${escapeHtml(formatRecordMoney(labor, currency))} •
                        Materiál: ${escapeHtml(formatRecordMoney(materials, currency))}
                    </div>
                    ${extractionWarning ? `<div style="margin-top:8px; color:#92400e;">Upozornění parseru: ${escapeHtml(extractionWarning)}</div>` : ''}
                    ${hasRecordLink ? `
                        <button type="button" class="btn btn-secondary" style="margin-top:10px;" ${legacyActionAttributes("click", "showServiceRecordDetail_941afdd3", Number(result.auto_created_service_record_id), Number(result.vehicle_id))}>
                            Otevřít vytvořený servisní záznam
                        </button>
                    ` : ''}
                </div>
                ${itemsTableHtml}
            `;
        }

        async function ingestServiceDocument() {
            const customerId = Number(document.getElementById('serviceDocCustomerSelect')?.value || 0);
            const vehicleIdRaw = Number(document.getElementById('serviceDocVehicleSelect')?.value || 0);
            const sourceType = String(document.getElementById('serviceDocSourceType')?.value || 'invoice');
            const manualText = String(document.getElementById('serviceDocManualText')?.value || '').trim();
            const manualNote = String(document.getElementById('serviceDocManualNote')?.value || '').trim();
            const fileInput = document.getElementById('serviceDocFileInput');
            const autoCreateRecord = document.getElementById('serviceDocAutoCreateRecord')?.checked === true;

            if (!customerId) {
                showAlert('Vyberte klienta, ke kterému doklad patří.', 'error');
                return;
            }

            const file = fileInput && fileInput.files && fileInput.files.length ? fileInput.files[0] : null;
            if (!file && !manualText) {
                showAlert('Nahrajte soubor nebo vložte ruční text dokladu.', 'error');
                return;
            }

            let fileBase64 = null;
            if (file) {
                const maxBytes = 12 * 1024 * 1024;
                if (file.size > maxBytes) {
                    showAlert('Soubor je příliš velký (max 12 MB).', 'error');
                    return;
                }
                try {
                    fileBase64 = await readFileAsBase64(file);
                } catch (error) {
                    showAlert(`Nepodařilo se načíst soubor: ${error.message || 'Neznámá chyba'}`, 'error');
                    return;
                }
            }

            try {
                showAlert('Zpracovávám doklad a vytěžuji položky...', 'info');
                const response = await apiCall('/api/v1/services/workspace/documents/ingest', 'POST', {
                    customer_id: customerId,
                    vehicle_id: vehicleIdRaw > 0 ? vehicleIdRaw : null,
                    source_type: sourceType,
                    manual_note: manualNote || null,
                    manual_text: manualText || null,
                    file_name: file ? file.name : null,
                    file_mime_type: file ? (file.type || null) : null,
                    file_content_base64: fileBase64,
                    auto_create_service_record: autoCreateRecord
                });
                if (fileInput) {
                    fileInput.value = '';
                }
                const manualTextInput = document.getElementById('serviceDocManualText');
                if (manualTextInput) manualTextInput.value = '';
                const manualNoteInput = document.getElementById('serviceDocManualNote');
                if (manualNoteInput) manualNoteInput.value = '';
                await loadServiceWorkspace();
                renderServiceDocumentResult(response || {});
                showAlert('Doklad byl úspěšně zpracován.', 'success');
            } catch (error) {
                console.error("[SERVICE_WORKSPACE] ingest document error:");
                showAlert(`Nepodařilo se zpracovat doklad: ${error.message || 'Neznámá chyba'}`, 'error');
            }
        }

        // ============= PROFIL =============

        // Načtení profilu
        async function loadProfile(force = true) {
            const container = document.getElementById('profileContainer');
            if (!container) {
                console.error("[PROFILE] Kontejner profileContainer nenalezen!");
                return;
            }

            // Kontrola auth stavu
            if (!isAuthenticated()) {
                console.warn("[PROFILE] Uživatel není přihlášen");
                return;
            }

            const cacheOwnerKey = getUiCacheOwnerKey();
            if (!force
                && isUiSectionCacheFresh(profileUiState)
                && container.dataset.renderedFor === cacheOwnerKey
                && container.innerHTML.trim()) {
                return;
            }

            try {
                container.classList.remove('error', 'empty');
                container.classList.add('loading');
                container.innerHTML = '<div class="loading">Načítám profil...</div>';
                const profile = await apiCall('/user/me');

                container.innerHTML = `
                    <div class="settings-shell">
                        <aside class="settings-sidebar">
                            <div class="settings-sidebar-head">
                                <h3>Nastavení</h3>
                                <p>Účet: ${escapeHtml(profile.email || '-')}</p>
                            </div>
                            <button type="button" class="settings-nav-item active" data-settings-panel-btn="account" ${legacyActionAttributes("click", "setSettingsPanel_f5f3303d")}>
                                Osobní údaje
                            </button>
                            <button type="button" class="settings-nav-item" data-settings-panel-btn="notifications" ${legacyActionAttributes("click", "setSettingsPanel_95747cd8")}>
                                Notifikace
                            </button>
                            <button type="button" class="settings-nav-item" data-settings-panel-btn="security" ${legacyActionAttributes("click", "setSettingsPanel_4b5ae01d")}>
                                Zabezpečení
                            </button>
                            <button type="button" class="settings-nav-item" data-settings-panel-btn="data" ${legacyActionAttributes("click", "setSettingsPanel_efbbe57d")}>
                                Data a účet
                            </button>
                        </aside>

                        <div class="settings-main">
                            <div class="settings-main-head">
                                <h3 id="settingsMainTitle">Osobní údaje</h3>
                                <button type="button" id="settingsSaveButton" class="btn-primary" ${legacyActionAttributes("click", "handleSaveProfile_d7573d4d")}>Uložit změny</button>
                            </div>
                            <div id="profileErrorContainer" class="profile-form-status"></div>

                            <section class="settings-panel active" data-settings-panel="account">
                                <div class="card profile-panel">
                                    <div class="card-header">
                                        <h3 class="card-title">Fakturační a kontaktní údaje</h3>
                                        <span class="profile-panel-subtitle">Jednotné nastavení firmy, adresy a kontaktu</span>
                                    </div>
                                    <div class="card-body">
                                        <div class="profile-grid">
                                            <div class="form-group">
                                                <label for="profileEmail">Email</label>
                                                <input type="email" id="profileEmail" value="${escapeHtml(profile.email || '')}" disabled class="input-disabled">
                                                <small class="form-hint">Email nelze změnit</small>
                                            </div>
                                            <div class="form-group">
                                                <label for="profileName">Jméno / Název</label>
                                                <input type="text" id="profileName" value="${escapeHtml(profile.name || '')}" placeholder="Vaše jméno nebo název firmy">
                                            </div>
                                            <div class="form-group">
                                                <label for="profileIco">IČO</label>
                                                <div class="profile-inline-actions">
                                                    <input type="text" id="profileIco" value="${escapeHtml(profile.ico || '')}" placeholder="8 číslic">
                                                    <button type="button" id="profileAresLookupBtn" class="btn-secondary profile-ares-btn" ${legacyActionAttributes("click", "handleProfileAresLookup_6d72ab6e")}>🔎 Načíst z ARES</button>
                                                </div>
                                                <small class="form-hint">ARES vyplní název, DIČ a adresní údaje podle IČO.</small>
                                            </div>
                                            <div class="form-group">
                                                <label for="profileDic">DIČ</label>
                                                <input type="text" id="profileDic" value="${escapeHtml(profile.dic || '')}" placeholder="Daňové identifikační číslo">
                                            </div>
                                        </div>
                                        <div class="profile-grid">
                                            <div class="form-group">
                                                <label for="profileStreet">Ulice</label>
                                                <input type="text" id="profileStreet" value="${escapeHtml(profile.street || '')}" placeholder="Název ulice">
                                            </div>
                                            <div class="form-group">
                                                <label for="profileStreetNumber">Číslo popisné</label>
                                                <input type="text" id="profileStreetNumber" value="${escapeHtml(profile.street_number || '')}" placeholder="Č.p.">
                                            </div>
                                        </div>
                                        <div class="profile-grid profile-grid-3">
                                            <div class="form-group">
                                                <label for="profileCity">Město</label>
                                                <input type="text" id="profileCity" value="${escapeHtml(profile.city || '')}" placeholder="Město">
                                            </div>
                                            <div class="form-group">
                                                <label for="profileZip">PSČ</label>
                                                <input type="text" id="profileZip" value="${escapeHtml(profile.zip || '')}" placeholder="123 45">
                                            </div>
                                            <div class="form-group">
                                                <label for="profilePhone">Telefon</label>
                                                <input type="text" id="profilePhone" value="${escapeHtml(profile.phone || '')}" placeholder="+420 123 456 789">
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </section>

                            <section class="settings-panel" data-settings-panel="notifications">
                                <div class="card profile-panel">
                                    <div class="card-header">
                                        <h3 class="card-title">Notifikační preference</h3>
                                        <span class="profile-panel-subtitle">Vyberte, které události vám máme připomínat</span>
                                    </div>
                                    <div class="card-body">
                                        <div class="notifications-list">
                                            <label class="checkbox-label profile-notify-item">
                                                <input type="checkbox" id="profileNotifyEmail" ${profile.notify_email ? 'checked' : ''} class="checkbox-input">
                                                <span class="profile-notify-copy">
                                                    <span class="checkbox-text">Emailové notifikace</span>
                                                    <small>Souhrnné zprávy a upozornění do emailu</small>
                                                </span>
                                            </label>
                                            <label class="checkbox-label profile-notify-item">
                                                <input type="checkbox" id="profileNotifySms" ${profile.notify_sms ? 'checked' : ''} class="checkbox-input">
                                                <span class="profile-notify-copy">
                                                    <span class="checkbox-text">SMS notifikace</span>
                                                    <small>Krátká upozornění na důležité termíny</small>
                                                </span>
                                            </label>
                                            <label class="checkbox-label profile-notify-item">
                                                <input type="checkbox" id="profileNotifyStk" ${profile.notify_stk ? 'checked' : ''} class="checkbox-input">
                                                <span class="profile-notify-copy">
                                                    <span class="checkbox-text">Připomínky STK</span>
                                                    <small>Blížící se konec platnosti technické</small>
                                                </span>
                                            </label>
                                            <label class="checkbox-label profile-notify-item">
                                                <input type="checkbox" id="profileNotifyOil" ${profile.notify_oil ? 'checked' : ''} class="checkbox-input">
                                                <span class="profile-notify-copy">
                                                    <span class="checkbox-text">Výměna oleje</span>
                                                    <small>Servisní interval podle času/nájezdu</small>
                                                </span>
                                            </label>
                                            <label class="checkbox-label profile-notify-item">
                                                <input type="checkbox" id="profileNotifyGeneral" ${profile.notify_general ? 'checked' : ''} class="checkbox-input">
                                                <span class="profile-notify-copy">
                                                    <span class="checkbox-text">Obecné připomínky</span>
                                                    <small>Další servisní termíny a poznámky</small>
                                                </span>
                                            </label>
                                        </div>
                                        <small class="form-hint">Změny uložíte tlačítkem „Uložit změny“ nahoře.</small>
                                    </div>
                                </div>
                            </section>

                            <section class="settings-panel" data-settings-panel="security">
                                <div class="card profile-panel">
                                    <div class="card-header">
                                        <h3 class="card-title">Zabezpečení přihlášení</h3>
                                        <span class="profile-panel-subtitle">Nastavte 2FA, biometrické preference a bezpečné heslo</span>
                                    </div>
                                    <div class="card-body">
                                        <div class="profile-security-feature-grid">
                                            <article class="profile-security-feature">
                                                <h4>Dvoufázové ověření (2FA)</h4>
                                                <p>Po zadání hesla budete při každém přihlášení potvrzovat kód z autentizační aplikace.</p>
                                                <div class="profile-security-chips">
                                                    <span id="securityStatus2faChip" class="profile-security-chip is-muted">2FA vypnuto</span>
                                                    <span id="securityStatusTotpChip" class="profile-security-chip is-muted">Aplikace: nenastaveno</span>
                                                </div>
                                                <div class="profile-security-actions">
                                                    <label>Současné heslo pro nové nastavení<input type="password" id="securitySetupPassword" autocomplete="current-password"></label>
                                                    <button type="button" class="btn" id="securityStartTotpSetupBtn" ${legacyActionAttributes("click", "startTotpSetup_86b09af7")}>Nastavit 2FA</button>
                                                    <button type="button" class="btn btn-secondary" id="securityShowTotpDisableBtn" ${legacyActionAttributes("click", "toggleTotpDisableForm_30eac346")}>Vypnout 2FA</button>
                                                </div>
                                                <div id="securityTotpSetupPanel" class="profile-security-inline-form hidden">
                                                    <p>1) Přidejte nový účet v Google/Microsoft Authenticator a použijte klíč níže.</p>
                                                    <div id="securityTotpSecretValue" class="profile-security-key">-</div>
                                                    <div class="profile-security-actions" style="margin-top: 8px;">
                                                        <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "copyTotpSecret_f501e39e")}>Kopírovat klíč</button>
                                                    </div>
                                                    <p style="margin-top: 8px;">Volitelně můžete použít URI:</p>
                                                    <input type="text" id="securityTotpUriValue" readonly class="input-disabled" style="font-size:0.85rem;">
                                                    <div class="profile-security-actions" style="margin-top: 8px;">
                                                        <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "copyTotpUri_dcfc561b")}>Kopírovat URI</button>
                                                    </div>
                                                    <p style="margin-top: 6px;">2) Zadejte 6místný kód pro aktivaci 2FA.</p>
                                                    <div class="form-group">
                                                        <label for="securityTotpEnableCode">Ověřovací kód</label>
                                                        <input type="text" id="securityTotpEnableCode" inputmode="numeric" maxlength="6" placeholder="123456">
                                                    </div>
                                                    <div class="profile-security-actions">
                                                        <button type="button" class="btn" ${legacyActionAttributes("click", "confirmTotpEnable_66bbb5e2")}>Aktivovat 2FA</button>
                                                        <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "cancelTotpSetup_42e90c93")}>Zavřít</button>
                                                    </div>
                                                </div>
                                                <div id="securityTotpDisablePanel" class="profile-security-inline-form hidden">
                                                    <p>Pro vypnutí 2FA potvrďte heslo a aktuální kód z autentizační aplikace.</p>
                                                    <div class="profile-security-grid">
                                                        <div class="form-group">
                                                            <label for="securityDisable2faPassword">Současné heslo</label>
                                                            <input type="password" id="securityDisable2faPassword" autocomplete="current-password">
                                                        </div>
                                                        <div class="form-group">
                                                            <label for="securityDisable2faCode">2FA kód</label>
                                                            <input type="text" id="securityDisable2faCode" inputmode="numeric" maxlength="6" placeholder="123456">
                                                        </div>
                                                    </div>
                                                    <div class="profile-security-actions">
                                                        <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "confirmTotpDisable_ac0dbb07")}>Potvrdit vypnutí</button>
                                                        <button type="button" class="btn btn-secondary" ${legacyActionAttributes("click", "toggleTotpDisableForm_9df89fb9")}>Zrušit</button>
                                                    </div>
                                                </div>
                                                <div id="security2faMessage" class="profile-form-status"></div>
                                            </article>

                                            <article class="profile-security-feature">
                                                <h4>Biometrické přihlášení</h4>
                                                <p>Face ID / Touch ID / Windows Hello (Passkeys) pro rychlé ověření na podporovaném zařízení.</p>
                                                <div class="profile-security-chips">
                                                    <span id="securityBiometricSupportChip" class="profile-security-chip is-muted">Kontroluji zařízení...</span>
                                                    <span id="securityBiometricStateChip" class="profile-security-chip is-muted">Biometrie vypnuta</span>
                                                </div>
                                                <div class="profile-security-actions">
                                                    <button type="button" class="btn" id="securityBiometricToggleBtn" ${legacyActionAttributes("click", "toggleBiometricPreference_7337fd8f")}>Zapnout biometriku</button>
                                                </div>
                                                <small class="form-hint">Doporučení: biometriku používejte spolu s 2FA. Na iOS Safari funguje nejspolehlivěji po přidání aplikace na plochu.</small>
                                                <div id="securityBiometricMessage" class="profile-form-status"></div>
                                            </article>
                                        </div>
                                    </div>
                                </div>

                                <div class="card profile-panel" style="margin-top: 12px;">
                                    <div class="card-header">
                                        <h3 class="card-title">Změna hesla</h3>
                                        <span class="profile-panel-subtitle">Doporučujeme použít silné heslo (min. 6 znaků)</span>
                                    </div>
                                    <div class="card-body">
                                        <div id="changePasswordForm">
                                            <form id="changePasswordFormContent" ${legacyActionAttributes("submit", "handleChangePassword_4688b77d")}>
                                                <div class="profile-security-grid">
                                                    <div class="form-group">
                                                        <label for="currentPassword">Současné heslo</label>
                                                        <input type="password" id="currentPassword" required minlength="6">
                                                    </div>
                                                    <div class="form-group">
                                                        <label for="newPassword">Nové heslo</label>
                                                        <input type="password" id="newPassword" required minlength="6" placeholder="Minimálně 6 znaků">
                                                    </div>
                                                    <div class="form-group">
                                                        <label for="confirmNewPassword">Potvrzení nového hesla</label>
                                                        <input type="password" id="confirmNewPassword" required minlength="6">
                                                    </div>
                                                </div>
                                                <div class="form-actions">
                                                    <button type="submit" class="btn-primary">Změnit heslo</button>
                                                </div>
                                                <div id="changePasswordErrorContainer" class="profile-form-status"></div>
                                            </form>
                                        </div>
                                    </div>
                                </div>
                            </section>

                            <section class="settings-panel" data-settings-panel="data">
                                <div class="card profile-panel">
                                    <div class="card-header">
                                        <h3 class="card-title">Export dat</h3>
                                        <span class="profile-panel-subtitle">Nejdříve stáhněte kompletní archiv, potom případně smažte účet</span>
                                    </div>
                                    <div class="card-body">
                                        <div class="profile-data-export-grid">
                                            <div class="profile-export-box">
                                                <h4>Kompletní export (.zip)</h4>
                                                <p>Archiv obsahuje JSON data účtu a strukturované PDF reporty pro všechna vozidla.</p>
                                                <div class="profile-delete-actions">
                                                    <button type="button" class="btn" id="profileDownloadExportBtn" ${legacyActionAttributes("click", "handleAccountDataExport_089c7e18")}>⬇️ Stáhnout export dat</button>
                                                </div>
                                                <small class="form-hint">Soubor si bezpečně uložte. Export je doporučený před každým nevratným smazáním.</small>
                                                <div id="profileExportStatus" class="profile-form-status"></div>
                                            </div>
                                            <div class="profile-danger-zone">
                                                <h4>Trvalé smazání účtu</h4>
                                                <p>Tento krok odstraní účet, vlastní obsah a vozidla bez dalšího vlastníka. Cizí a spoluvlastněná vozidla zůstanou zachovaná. Platební záznamy pro účetnictví a ochranu nákupů se uchovávají odděleně.</p>
                                                <div class="profile-delete-confirm">
                                                    <div class="form-group">
                                                        <label for="profileDeletePassword">Současné heslo</label>
                                                        <input type="password" id="profileDeletePassword" autocomplete="current-password" placeholder="Zadejte heslo">
                                                    </div>
                                                    <div class="form-group">
                                                        <label for="profileDeleteConfirmText">Potvrzovací text</label>
                                                        <input type="text" id="profileDeleteConfirmText" placeholder="SMAZAT UCET">
                                                        <small class="form-hint">Pro potvrzení napište přesně <strong>SMAZAT UCET</strong>.</small>
                                                    </div>
                                                    <label class="profile-delete-check" for="profileDeleteExportConfirmed">
                                                        <input type="checkbox" id="profileDeleteExportConfirmed">
                                                        <span>Stáhl(a) jsem export dat (dobrovolné).</span>
                                                    </label>
                                                    <div class="profile-delete-actions">
                                                        <button type="button" class="btn-danger" id="profileDeleteAccountBtn" ${legacyActionAttributes("click", "handleDeleteAccount_4f319180")}>🗑️ Smazat účet a data</button>
                                                    </div>
                                                </div>
                                                <div id="profileDeleteStatus" class="profile-form-status"></div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </section>
                        </div>
                    </div>
                `;
                container.classList.remove('loading');
                window.CustomerFeatures?.profileLoaded();
                container.dataset.renderedFor = cacheOwnerKey;
                markUiSectionLoaded(profileUiState);
                setSettingsPanel('account');
                initProfileAresAutofill();
                refreshProfileSecuritySettings();
            } catch (error) {
                profileUiState.loadedAt = 0;
                console.error("[PROFILE] Chyba při načítání profilu:");
                const errorMessage = error.message || 'Neznámá chyba';
                container.classList.remove('loading');
                showErrorWithRetry('profileContainer', `Nepodařilo se načíst profil: ${errorMessage}`, loadProfile);
            }
        }

        function setSettingsPanel(panelKey) {
            const normalized = (panelKey || 'account').toLowerCase();
            const panelTitles = {
                account: 'Osobní údaje',
                notifications: 'Notifikace',
                security: 'Zabezpečení',
                data: 'Data a účet'
            };

            document.querySelectorAll('[data-settings-panel]').forEach((panel) => {
                const isActive = panel.getAttribute('data-settings-panel') === normalized;
                panel.classList.toggle('active', isActive);
            });

            document.querySelectorAll('[data-settings-panel-btn]').forEach((button) => {
                const isActive = button.getAttribute('data-settings-panel-btn') === normalized;
                button.classList.toggle('active', isActive);
                button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
            });

            const titleEl = document.getElementById('settingsMainTitle');
            if (titleEl) {
                titleEl.textContent = panelTitles[normalized] || 'Nastavení';
            }

            const showProfileSave = normalized !== 'security' && normalized !== 'data';
            const saveButton = document.getElementById('settingsSaveButton');
            if (saveButton) {
                saveButton.classList.toggle('hidden', !showProfileSave);
            }

            const profileErrorContainer = document.getElementById('profileErrorContainer');
            if (profileErrorContainer) {
                profileErrorContainer.classList.toggle('hidden', !showProfileSave);
                if (!showProfileSave) {
                    profileErrorContainer.innerHTML = '';
                }
            }
        }

        // Uložení profilu
        async function handleSaveProfile(event) {
            if (event && typeof event.preventDefault === 'function') {
                event.preventDefault();
            }
            const errorContainer = document.getElementById('profileErrorContainer');

            try {
                const updateData = {
                    name: document.getElementById('profileName').value.trim() || null,
                    ico: document.getElementById('profileIco').value.trim().replace(/[^\d]/g, '') || null,
                    dic: document.getElementById('profileDic').value.trim() || null,
                    street: document.getElementById('profileStreet').value.trim() || null,
                    street_number: document.getElementById('profileStreetNumber').value.trim() || null,
                    city: document.getElementById('profileCity').value.trim() || null,
                    zip: document.getElementById('profileZip').value.trim() || null,
                    phone: document.getElementById('profilePhone').value.trim() || null,
                    notify_email: document.getElementById('profileNotifyEmail').checked,
                    notify_sms: document.getElementById('profileNotifySms').checked,
                    notify_stk: document.getElementById('profileNotifyStk').checked,
                    notify_oil: document.getElementById('profileNotifyOil').checked,
                    notify_general: document.getElementById('profileNotifyGeneral').checked
                };

                // Validace IČO (pokud je zadáno, musí být 8 číslic)
                if (updateData.ico && (!/^\d{8}$/.test(updateData.ico))) {
                    showFormError('profileErrorContainer', 'IČO musí obsahovat přesně 8 číslic');
                    return;
                }

                await apiCall('/user/me', 'PUT', updateData);
                showFormError('profileErrorContainer', '');
                showAlert('Profil byl úspěšně aktualizován', 'success');

                // Znovu načíst profil pro zobrazení aktualizovaných dat
                await loadProfile();
            } catch (error) {
                console.error("[PROFILE] Chyba při ukládání profilu:");
                showFormError('profileErrorContainer', 'Nepodařilo se uložit změny: ' + error.message);
            }
        }

        function setProfileDataStatus(containerId, message, type = 'info') {
            const container = document.getElementById(containerId);
            if (!container) return;
            if (!message) {
                container.innerHTML = '';
                return;
            }
            let cls = 'alert alert-info';
            if (type === 'success') cls = 'alert alert-success';
            if (type === 'error') cls = 'alert alert-error';
            if (type === 'warning') cls = 'alert alert-warning';
            container.innerHTML = `<div class="${cls}">${escapeHtml(message)}</div>`;
            container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }

        async function handleAccountDataExport() {
            if (!isAuthenticated()) {
                showAlert('Nejprve se přihlaste.', 'error');
                return;
            }

            const button = document.getElementById('profileDownloadExportBtn');
            const statusBoxId = 'profileExportStatus';
            setProfileDataStatus(statusBoxId, '');

            if (button) {
                button.disabled = true;
                button.textContent = 'Připravuji export...';
            }

            try {
                API_URL = getApiBaseUrl();
                if (!API_URL) {
                    throw new Error('API URL není nastavena');
                }

                const headers = {
                    'Accept': 'application/zip',
                    'Accept-Language': 'cs-CZ,cs;q=0.9,en;q=0.8'
                };
                if (accessToken) {
                    headers['Authorization'] = `Bearer ${accessToken}`;
                }
                appendClientGeoHeaders(headers);

                const response = await AdminBrowserSession.request(`${API_URL}/user/me/export`, {
                    method: 'GET',
                    headers,
                    credentials: 'include',
                    mode: 'cors',
                    cache: 'no-cache'
                });

                if (!response.ok) {
                    let detail = `HTTP ${response.status}`;
                    try {
                        const errorData = await response.json();
                        detail = errorData?.detail || detail;
                    } catch (_) {
                        // ignore JSON parse errors
                    }
                    throw new Error(detail);
                }

                const blob = await response.blob();
                if (!blob || blob.size === 0) {
                    throw new Error('Export je prázdný soubor');
                }

                const contentDisposition = response.headers.get('Content-Disposition') || '';
                let filename = `sprava_vozidel_export_${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '')}.zip`;
                const match = contentDisposition.match(/filename="?([^"]+)"?/i);
                if (match && match[1]) {
                    filename = match[1];
                }

                const objectUrl = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = objectUrl;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                setTimeout(() => {
                    document.body.removeChild(a);
                    URL.revokeObjectURL(objectUrl);
                }, 200);

                const exportCheckbox = document.getElementById('profileDeleteExportConfirmed');
                if (exportCheckbox) {
                    exportCheckbox.checked = true;
                }

                setProfileDataStatus('profileDeleteStatus', '');
                setProfileDataStatus(statusBoxId, 'Export dat byl vygenerován a stažen. Nyní můžete případně pokračovat se smazáním účtu.', 'success');
            } catch (error) {
                console.error("[PROFILE] Export dat selhal:");
                setProfileDataStatus(statusBoxId, `Export dat se nepodařil: ${error.message || 'Neznámá chyba'}`, 'error');
            } finally {
                if (button) {
                    button.disabled = false;
                    button.textContent = '⬇️ Stáhnout export dat';
                }
            }
        }

        async function handleDeleteAccount() {
            if (!isAuthenticated()) {
                showAlert('Nejprve se přihlaste.', 'error');
                return;
            }

            const password = String(document.getElementById('profileDeletePassword')?.value || '');
            const confirmationText = String(document.getElementById('profileDeleteConfirmText')?.value || '').trim();
            const normalizedConfirmationText = confirmationText
                .normalize('NFD')
                .replace(/[\u0300-\u036f]/g, '')
                .toUpperCase()
                .replace(/\s+/g, ' ')
                .trim();
            const exportConfirmed = document.getElementById('profileDeleteExportConfirmed')?.checked === true;
            const statusBoxId = 'profileDeleteStatus';
            const deleteButton = document.getElementById('profileDeleteAccountBtn');

            setProfileDataStatus(statusBoxId, '');

            if (!password) {
                setProfileDataStatus(statusBoxId, 'Zadejte současné heslo.', 'error');
                return;
            }
            if (normalizedConfirmationText !== 'SMAZAT UCET') {
                setProfileDataStatus(statusBoxId, 'Do potvrzovacího pole zadejte přesně text SMAZAT UCET.', 'error');
                return;
            }

            const hardConfirm = window.confirm(
                'Opravdu chcete TRVALE smazat účet a všechna data? Tento krok nelze vrátit zpět.'
            );
            if (!hardConfirm) {
                return;
            }

            if (deleteButton) {
                deleteButton.disabled = true;
                deleteButton.textContent = 'Mažu účet...';
            }

            try {
                const response = await apiCall('/user/me', 'DELETE', {
                    current_password: password,
                    confirmation_text: confirmationText,
                    export_downloaded: exportConfirmed
                });

                setProfileDataStatus(
                    statusBoxId,
                    response?.message || 'Účet byl odstraněn.',
                    'success'
                );
                showAlert(response?.message || 'Účet byl odstraněn.', 'success');

                setTimeout(() => {
                    handleLogout();
                }, 1200);
            } catch (error) {
                console.error("[PROFILE] Smazání účtu selhalo:");
                setProfileDataStatus(statusBoxId, `Smazání účtu se nepodařilo: ${error.message || 'Neznámá chyba'}`, 'error');
            } finally {
                if (deleteButton) {
                    deleteButton.disabled = false;
                    deleteButton.textContent = '🗑️ Smazat účet a data';
                }
            }
        }

        function setSecurityInlineMessage(containerId, message, type = 'info') {
            const container = document.getElementById(containerId);
            if (!container) return;
            if (!message) {
                container.innerHTML = '';
                return;
            }

            let alertClass = 'alert alert-info';
            if (type === 'success') {
                alertClass = 'alert alert-success';
            } else if (type === 'error') {
                alertClass = 'alert alert-error';
            } else if (type === 'warning') {
                alertClass = 'alert alert-warning';
            }
            container.innerHTML = `<div class="${alertClass}">${escapeHtml(message)}</div>`;
        }

        function setSecurityChipState(elementId, text, isOk) {
            const chip = document.getElementById(elementId);
            if (!chip) return;
            chip.textContent = text;
            chip.classList.toggle('is-ok', !!isOk);
            chip.classList.toggle('is-muted', !isOk);
        }

        function getBiometricClientSupport() {
            const hasWindow = typeof window !== 'undefined';
            const hasPublicKeyCredential = hasWindow && typeof window.PublicKeyCredential !== 'undefined';
            const isSecure = hasWindow ? !!window.isSecureContext : false;
            if (!hasPublicKeyCredential) {
                return {
                    supported: false,
                    label: 'Zařízení nepodporuje Passkey',
                    reason: 'V tomto prohlížeči není dostupné WebAuthn API.'
                };
            }
            if (!isSecure) {
                return {
                    supported: false,
                    label: 'Vyžaduje HTTPS',
                    reason: 'Biometrika funguje pouze na HTTPS nebo localhost.'
                };
            }
            return {
                supported: true,
                label: 'Zařízení podporuje Passkey',
                reason: 'Můžete použít Face ID/Touch ID/Windows Hello.'
            };
        }

        function renderProfileSecuritySettings() {
            const settings = authSecuritySettingsCache || {
                two_factor_enabled: false,
                totp_configured: false,
                biometric_enabled: false,
                biometric_preferred: false
            };
            const userRole = String(currentUser?.role || 'user').toLowerCase();

            setSecurityChipState(
                'securityStatus2faChip',
                settings.two_factor_enabled ? '2FA aktivní' : '2FA vypnuto',
                !!settings.two_factor_enabled
            );
            setSecurityChipState(
                'securityStatusTotpChip',
                settings.totp_configured ? 'Aplikace: nastaveno' : 'Aplikace: nenastaveno',
                !!settings.totp_configured
            );

            const support = getBiometricClientSupport();
            setSecurityChipState(
                'securityBiometricSupportChip',
                support.label,
                support.supported
            );
            setSecurityChipState(
                'securityBiometricStateChip',
                settings.biometric_enabled ? 'Biometrie aktivní' : 'Biometrie vypnuta',
                !!settings.biometric_enabled
            );

            const startSetupBtn = document.getElementById('securityStartTotpSetupBtn');
            if (startSetupBtn) {
                startSetupBtn.textContent = settings.two_factor_enabled ? 'Obnovit 2FA klíč' : 'Nastavit 2FA';
            }

            const showDisableBtn = document.getElementById('securityShowTotpDisableBtn');
            if (showDisableBtn) {
                showDisableBtn.disabled = !settings.two_factor_enabled;
            }

            const biometricToggleBtn = document.getElementById('securityBiometricToggleBtn');
            if (biometricToggleBtn) {
                biometricToggleBtn.disabled = !support.supported;
                biometricToggleBtn.textContent = settings.biometric_enabled ? 'Vypnout biometriku' : 'Zapnout biometriku';
            }

            if (!settings.two_factor_enabled && (userRole === 'service' || userRole === 'admin' || userRole === 'developer_admin')) {
                setSecurityInlineMessage(
                    'security2faMessage',
                    'Doporučení: pro servisní/developer účet zapněte 2FA kvůli ochraně dat zákazníků.',
                    'warning'
                );
            }
            if (!support.supported) {
                setSecurityInlineMessage('securityBiometricMessage', support.reason, 'warning');
            }
        }

        async function refreshProfileSecuritySettings() {
            if (!isAuthenticated()) return;
            try {
                const settings = await apiCall('/user/security/settings', 'GET');
                authSecuritySettingsCache = settings || {};
                renderProfileSecuritySettings();
            } catch (error) {
                console.error("[SECURITY] Chyba při načítání nastavení zabezpečení:");
                setSecurityInlineMessage(
                    'security2faMessage',
                    `Nepodařilo se načíst bezpečnostní nastavení: ${error.message || 'Neznámá chyba'}`,
                    'error'
                );
                renderProfileSecuritySettings();
            }
        }

        async function replaceSecuritySession(result) {
            if (!result?.access_token) return;
            saveAuthSession(result.access_token, currentUser);
            await AdminBrowserSession.verify();
            if (window.CustomerWeb) return;
            const response = await AdminBrowserSession.request('/admin-web-session', {method:'POST'});
            if (!response.ok) throw new Error('Přihlaste se znovu pro otevření administrace.');
            await response.text();
        }

        async function startTotpSetup() {
            setSecurityInlineMessage('security2faMessage', '');
            const setupPanel = document.getElementById('securityTotpSetupPanel');
            const disablePanel = document.getElementById('securityTotpDisablePanel');
            if (disablePanel) disablePanel.classList.add('hidden');

            try {
                const passwordInput = document.getElementById('securitySetupPassword');
                const currentPassword = passwordInput?.value || '';
                if (!currentPassword) throw new Error('Zadejte současné heslo.');
                let response;
                try { response = await apiCall('/user/security/totp/setup', 'POST', {current_password: currentPassword}); }
                finally { if (passwordInput) passwordInput.value = ''; }
                const secretEl = document.getElementById('securityTotpSecretValue');
                if (secretEl) {
                    secretEl.textContent = response.secret || '-';
                }
                const uriEl = document.getElementById('securityTotpUriValue');
                if (uriEl) {
                    uriEl.value = response.otpauth_uri || '';
                }
                if (setupPanel) {
                    setupPanel.classList.remove('hidden');
                }
                showAlert('2FA klíč byl vygenerován. Zadejte ověřovací kód z aplikace.', 'info');
            } catch (error) {
                setSecurityInlineMessage(
                    'security2faMessage',
                    `Nepodařilo se spustit nastavení 2FA: ${error.message || 'Neznámá chyba'}`,
                    'error'
                );
            }
        }

        async function copyTotpSecret() {
            const secret = String(document.getElementById('securityTotpSecretValue')?.textContent || '').trim();
            if (!secret || secret === '-') {
                setSecurityInlineMessage('security2faMessage', 'Nejprve vygenerujte 2FA klíč.', 'warning');
                return;
            }
            try {
                await navigator.clipboard.writeText(secret);
                setSecurityInlineMessage('security2faMessage', '2FA klíč byl zkopírován do schránky.', 'success');
            } catch (error) {
                setSecurityInlineMessage('security2faMessage', 'Nepodařilo se zkopírovat klíč. Zkopírujte ho ručně.', 'warning');
            }
        }

        async function copyTotpUri() {
            const uri = String(document.getElementById('securityTotpUriValue')?.value || '').trim();
            if (!uri) {
                setSecurityInlineMessage('security2faMessage', 'Nejprve vygenerujte 2FA URI.', 'warning');
                return;
            }
            try {
                await navigator.clipboard.writeText(uri);
                setSecurityInlineMessage('security2faMessage', '2FA URI bylo zkopírováno do schránky.', 'success');
            } catch (error) {
                setSecurityInlineMessage('security2faMessage', 'Nepodařilo se zkopírovat URI. Zkopírujte ho ručně.', 'warning');
            }
        }

        function cancelTotpSetup(clearMessage = true) {
            const setupPanel = document.getElementById('securityTotpSetupPanel');
            if (setupPanel) {
                setupPanel.classList.add('hidden');
            }
            const codeInput = document.getElementById('securityTotpEnableCode');
            if (codeInput) {
                codeInput.value = '';
            }
            const uriEl = document.getElementById('securityTotpUriValue');
            if (uriEl) { uriEl.value = ''; }
            const secretEl = document.getElementById('securityTotpSecretValue');
            if (secretEl) { secretEl.textContent = '-'; }
            if (clearMessage) {
                setSecurityInlineMessage('security2faMessage', '');
            }
        }

        async function confirmTotpEnable() {
            const code = String(document.getElementById('securityTotpEnableCode')?.value || '').trim();
            if (!/^\d{6}$/.test(code)) {
                setSecurityInlineMessage('security2faMessage', 'Zadejte platný 6místný kód.', 'error');
                return;
            }

            try {
                const result = await apiCall('/user/security/totp/enable', 'POST', { code });
                await replaceSecuritySession(result);
                cancelTotpSetup(false);
                setSecurityInlineMessage('security2faMessage', '2FA bylo úspěšně aktivováno. Další přihlášení už bude vyžadovat kód.', 'success');
                await refreshProfileSecuritySettings();
            } catch (error) {
                setSecurityInlineMessage(
                    'security2faMessage',
                    `Aktivace 2FA selhala: ${error.message || 'Neznámá chyba'}`,
                    'error'
                );
            }
        }

        function toggleTotpDisableForm(forceOpen) {
            const panel = document.getElementById('securityTotpDisablePanel');
            if (!panel) return;
            const shouldOpen = typeof forceOpen === 'boolean' ? forceOpen : panel.classList.contains('hidden');
            panel.classList.toggle('hidden', !shouldOpen);
            if (!shouldOpen) {
                document.getElementById('securityDisable2faPassword').value = '';
                document.getElementById('securityDisable2faCode').value = '';
            }
            setSecurityInlineMessage('security2faMessage', '');
        }

        async function confirmTotpDisable() {
            const currentPassword = String(document.getElementById('securityDisable2faPassword')?.value || '');
            const code = String(document.getElementById('securityDisable2faCode')?.value || '').trim();

            if (!currentPassword) {
                setSecurityInlineMessage('security2faMessage', 'Zadejte současné heslo.', 'error');
                return;
            }
            if (!/^\d{6}$/.test(code)) {
                setSecurityInlineMessage('security2faMessage', 'Zadejte platný 6místný 2FA kód.', 'error');
                return;
            }

            try {
                const result = await apiCall('/user/security/totp/disable', 'POST', {
                    current_password: currentPassword,
                    code
                });
                await replaceSecuritySession(result);
                toggleTotpDisableForm(false);
                setSecurityInlineMessage('security2faMessage', '2FA bylo vypnuto.', 'success');
                await refreshProfileSecuritySettings();
            } catch (error) {
                setSecurityInlineMessage(
                    'security2faMessage',
                    `Vypnutí 2FA selhalo: ${error.message || 'Neznámá chyba'}`,
                    'error'
                );
            }
        }

        async function toggleBiometricPreference() {
            const support = getBiometricClientSupport();
            if (!support.supported) {
                setSecurityInlineMessage('securityBiometricMessage', support.reason, 'warning');
                return;
            }

            const currentState = !!(authSecuritySettingsCache && authSecuritySettingsCache.biometric_enabled);
            const nextState = !currentState;
            try {
                await apiCall('/user/security/biometric', 'POST', {
                    enabled: nextState,
                    preferred: nextState
                });
                setSecurityInlineMessage(
                    'securityBiometricMessage',
                    nextState
                        ? 'Biometrická preference je aktivní. Přihlášení musí probíhat přes podporovaný prohlížeč/zařízení.'
                        : 'Biometrická preference byla vypnuta.',
                    'success'
                );
                await refreshProfileSecuritySettings();
            } catch (error) {
                setSecurityInlineMessage(
                    'securityBiometricMessage',
                    `Nepodařilo se uložit biometrické nastavení: ${error.message || 'Neznámá chyba'}`,
                    'error'
                );
            }
        }

        async function loadSupportPanel(force = true) {
            const container = document.getElementById('supportContainer');
            if (!container) return;

            if (!isAuthenticated()) {
                container.innerHTML = '<div class="alert alert-error">Pro kontakt podpory se nejprve přihlaste.</div>';
                return;
            }

            const cacheOwnerKey = getUiCacheOwnerKey();
            if (!force
                && isUiSectionCacheFresh(supportUiState)
                && container.dataset.renderedFor === cacheOwnerKey
                && container.innerHTML.trim()) {
                return;
            }

            const userName = (currentUser && currentUser.name) ? currentUser.name : 'Uživatel';
            const userEmail = (currentUser && currentUser.email) ? currentUser.email : '-';
            const userPhone = (currentUser && currentUser.phone) ? currentUser.phone : '';

            container.innerHTML = `
                <div class="support-layout">
                    <div class="card">
                        <div class="card-header">
                            <h3 class="card-title">Technická podpora</h3>
                        </div>
                        <div class="card-body">
                            <p><strong>${escapeHtml(userName)}</strong>, zde můžete odeslat dotaz nebo nahlásit problém.</p>
                            <ul class="support-info-list">
                                <li>Váš požadavek bude odeslán na email podpory.</li>
                                <li>Při zapnutí diagnostiky se přidá IP, URL a technické informace pro rychlejší řešení.</li>
                                <li>Čím přesnější popis problému, tím rychlejší vyřešení.</li>
                            </ul>
                        </div>
                    </div>
                    <div class="card">
                        <div class="card-header">
                            <h3 class="card-title">Nový požadavek</h3>
                        </div>
                        <div class="card-body">
                            <form id="supportForm" class="support-form" ${legacyActionAttributes("submit", "handleSendSupportRequest_52acbcec")}>
                                <div class="form-row">
                                    <div class="form-group">
                                        <label for="supportCategory">Kategorie</label>
                                        <select id="supportCategory">
                                            <option value="technický problém">Technický problém</option>
                                            <option value="licence a platby">Licence a platby</option>
                                            <option value="data vozidel">Data vozidel</option>
                                            <option value="návrh zlepšení">Návrh zlepšení</option>
                                            <option value="obecné">Obecné</option>
                                        </select>
                                    </div>
                                    <div class="form-group">
                                        <label for="supportPhone">Telefon (volitelně)</label>
                                        <input type="text" id="supportPhone" value="${escapeHtml(userPhone)}" placeholder="+420 ...">
                                    </div>
                                </div>
                                <div class="form-group">
                                    <label for="supportSubject">Předmět *</label>
                                    <input type="text" id="supportSubject" maxlength="180" placeholder="Krátce popište problém" required>
                                </div>
                                <div class="form-group">
                                    <label for="supportMessage">Zpráva *</label>
                                    <textarea id="supportMessage" maxlength="4000" placeholder="Popište prosím problém co nejpřesněji..." required></textarea>
                                </div>
                                <div class="form-group">
                                    <label class="checkbox-label" for="supportIncludeDiag">
                                        <input type="checkbox" id="supportIncludeDiag" checked>
                                        <span>Zahrnout diagnostiku (IP, URL, User-Agent)</span>
                                    </label>
                                </div>
                                <div class="form-group">
                                    <label>Email odesílatele</label>
                                    <input type="email" value="${escapeHtml(userEmail)}" disabled class="input-disabled">
                                </div>
                                <div class="form-actions">
                                    <button type="submit" id="supportSubmitBtn" class="btn-primary">Odeslat na podporu</button>
                                </div>
                                <div id="supportResult" class="support-result"></div>
                            </form>
                        </div>
                    </div>
                </div>
            `;
            container.dataset.renderedFor = cacheOwnerKey;
            markUiSectionLoaded(supportUiState);
        }

        async function handleSendSupportRequest(event) {
            event.preventDefault();
            const resultBox = document.getElementById('supportResult');
            const submitBtn = document.getElementById('supportSubmitBtn');

            const category = (document.getElementById('supportCategory')?.value || 'obecné').trim();
            const subject = (document.getElementById('supportSubject')?.value || '').trim();
            const message = (document.getElementById('supportMessage')?.value || '').trim();
            const phone = (document.getElementById('supportPhone')?.value || '').trim() || null;
            const includeDiagnostics = Boolean(document.getElementById('supportIncludeDiag')?.checked);

            if (subject.length < 3) {
                showFormError('supportResult', 'Předmět musí mít alespoň 3 znaky.');
                return;
            }
            if (message.length < 10) {
                showFormError('supportResult', 'Zpráva musí mít alespoň 10 znaků.');
                return;
            }

            clearFormError('supportResult');

            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = 'Odesílám...';
            }

            try {
                await apiCall('/user/support', 'POST', {
                    category: category,
                    subject: subject,
                    message: message,
                    phone: phone,
                    include_diagnostics: includeDiagnostics,
                    page_url: window.location.href,
                    user_agent: navigator.userAgent
                });

                if (resultBox) {
                    resultBox.innerHTML = '<div class="alert alert-success">Požadavek byl odeslán na podporu.</div>';
                }
                document.getElementById('supportMessage').value = '';
                showAlert('Podpora byla kontaktována.', 'success');
            } catch (error) {
                showFormError('supportResult', `Nepodařilo se odeslat požadavek: ${error.message}`);
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Odeslat na podporu';
                }
            }
        }

        // ============================================
        // COMMAND BOT FUNCTIONS - PLOVOUCÍ BUBLINA
        // ============================================

        let commandBotChatOpen = false;

        function toggleCommandBotChat() {
            const chat = document.getElementById('commandBotChat');
            if (!chat) return;

            commandBotChatOpen = !commandBotChatOpen;

            if (commandBotChatOpen) {
                chat.style.display = 'flex';
                // Načíst historii při otevření
                loadCommandBotHistory();
                // Focus na input
                setTimeout(() => {
                    const input = document.getElementById('commandBotInput');
                    if (input) input.focus();
                }, 100);
            } else {
                chat.style.display = 'none';
            }
        }

        async function sendCommandBot() {
            const input = document.getElementById('commandBotInput');
            const message = input?.value.trim();

            if (!message) {
                showAlert('Zadejte prosím příkaz', 'error');
                return;
            }

            if (!currentUser || !currentUser.email) {
                showAlert('Musíte být přihlášeni', 'error');
                return;
            }

            // Disable input a tlačítko
            if (input) input.disabled = true;
            const sendBtn = document.querySelector('.command-bot-send');
            if (sendBtn) sendBtn.disabled = true;

            // Zobrazit zprávu uživatele
            addCommandBotMessage('user', message);
            if (input) input.value = '';

            try {
                // Získat aktuální vozidlo (pokud je otevřený detail)
                const vehicleId = currentVehicleId || null;

                // Zavolat API
                const response = await apiCall('/api/customer-commands', 'POST', {
                    source: 'web_chat',
                    customer_name: currentUser.name || null,
                    customer_email: currentUser.email,
                    vehicle_id: vehicleId,
                    message: message
                });

                // Pokud bot potřebuje výběr vozidla, zobrazit interaktivní výběr
                if (response.requires_vehicle_selection && response.available_vehicles && response.available_vehicles.length > 0) {
                    addCommandBotVehicleSelection(response.command_id, response.available_vehicles, message);
                } else {
                    // Zobrazit odpověď bota
                    const botMessage = response.result_summary ||
                        `Příkaz byl zpracován. Typ: ${response.intent_type}, Status: ${response.status}`;
                    const isError = response.status === 'FAILED';
                    addCommandBotMessage('bot', botMessage, response.intent_type, response.status, isError);
                }

                // Pokud byl vytvořen úkol nebo rezervace, načíst aktualizované seznamy
                if (response.intent_type === 'CREATE_BOOKING') {
                    // Načíst rezervace, pokud je otevřený tab
                    if (document.getElementById('reservationsTab')?.classList.contains('active')) {
                        loadReservations();
                    }
                } else if (response.intent_type === 'CREATE_TASK') {
                    // Načíst připomínky, pokud je otevřený tab
                    if (document.getElementById('remindersTab')?.classList.contains('active')) {
                        loadReminders();
                    }
                }

            } catch (error) {
                console.error("[COMMAND BOT] Chyba:");
                addCommandBotMessage('bot', `Chyba: ${error.message || 'Nepodařilo se zpracovat příkaz'}`, null, 'FAILED', true);
            } finally {
                // Re-enable input a tlačítko (jen pokud není výběr vozidla)
                const container = document.getElementById('commandBotMessages');
                const hasVehicleSelection = container && container.querySelector('[id^="vehicle-selection-"]');
                if (!hasVehicleSelection) {
                    if (input) input.disabled = false;
                    if (sendBtn) sendBtn.disabled = false;
                    if (input) input.focus();
                }
            }
        }

        function addCommandBotMessage(type, message, intentType = null, status = null, isError = false) {
            const container = document.getElementById('commandBotMessages');
            if (!container) return;

            // Odstranit welcome message
            const welcome = container.querySelector('.command-bot-welcome');
            if (welcome) welcome.remove();

            const messageDiv = document.createElement('div');
            messageDiv.className = `command-bot-message ${type}${isError ? ' error' : ''}`;

            let statusBadge = '';
            if (status) {
                const statusColors = {
                    'EXECUTED': '#10b981',
                    'FAILED': '#ef4444',
                    'RECEIVED': '#f59e0b'
                };
                statusBadge = `<span class="command-bot-message-badge" style="background: ${escapeHtml(statusColors[status] || '#94a3b8')}; color: white;">${escapeHtml(status)}</span>`;
            }

            let intentBadge = '';
            if (intentType) {
                const intentLabels = {
                    'CREATE_BOOKING': '📅 Rezervace',
                    'CREATE_TASK': '✅ Úkol',
                    'ADD_NOTE': '📝 Poznámka',
                    'QUESTION': '❓ Otázka',
                    'UNKNOWN': '❓ Neznámé'
                };
                intentBadge = `<span class="command-bot-message-badge" style="background: #6366f1; color: white;">${escapeHtml(intentLabels[intentType] || intentType)}</span>`;
            }

            messageDiv.innerHTML = `
                ${intentBadge}${statusBadge}
                <div style="margin-top: ${intentBadge || statusBadge ? '4px' : '0'};">
                    ${escapeHtml(message).replace(/\n/g, '<br>')}
                </div>
            `;

            container.appendChild(messageDiv);
            container.scrollTop = container.scrollHeight;
        }

        function addCommandBotVehicleSelection(commandId, vehicles, originalMessage) {
            const container = document.getElementById('commandBotMessages');
            if (!container) return;

            // Odstranit welcome message
            const welcome = container.querySelector('.command-bot-welcome');
            if (welcome) welcome.remove();

            const messageDiv = document.createElement('div');
            messageDiv.className = 'command-bot-message bot';
            messageDiv.id = `vehicle-selection-${commandId}`;

            let vehiclesHtml = vehicles.map(v => `
                <button
                    ${legacyActionAttributes("click", "selectVehicleForCommand_27b22fb1", commandId, v.id, v.display_name, originalMessage)}
                    style="
                        width: 100%;
                        padding: 12px;
                        margin: 8px 0;
                        background: white;
                        border: 2px solid #6366f1;
                        border-radius: 8px;
                        cursor: pointer;
                        text-align: left;
                        transition: all 0.2s;
                        font-size: 14px;
                    "
                    class="command-vehicle-option"
                >
                    <strong>${escapeHtml(v.display_name || 'Vozidlo')}</strong>
                    ${v.plate ? `<br><small style="color: #64748b;">SPZ: ${escapeHtml(v.plate)}</small>` : ''}
                </button>
            `).join('');

            messageDiv.innerHTML = `
                <div style="margin-bottom: 8px;">
                    <strong>Prosím vyberte vozidlo:</strong>
                </div>
                <div style="max-height: 300px; overflow-y: auto;">
                    ${vehiclesHtml}
                </div>
            `;

            container.appendChild(messageDiv);
            container.scrollTop = container.scrollHeight;
        }

        async function selectVehicleForCommand(commandId, vehicleId, vehicleName, originalMessage) {
            // Zobrazit zprávu o výběru
            addCommandBotMessage('user', `Vybrané vozidlo: ${vehicleName}`);

            // Disable všechny tlačítka výběru
            const selectionDiv = document.getElementById(`vehicle-selection-${commandId}`);
            if (selectionDiv) {
                const buttons = selectionDiv.querySelectorAll('button');
                buttons.forEach(btn => {
                    btn.disabled = true;
                    btn.style.opacity = '0.5';
                    btn.style.cursor = 'not-allowed';
                });
            }

            // Zobrazit načítání
            addCommandBotMessage('bot', 'Zpracovávám příkaz s vybraným vozidlem...', null, 'RECEIVED');

            try {
                // Odeslat příkaz znovu s vehicle_id
                const response = await apiCall('/api/customer-commands', 'POST', {
                    source: 'web_chat',
                    customer_name: currentUser.name || null,
                    customer_email: currentUser.email,
                    vehicle_id: vehicleId,
                    message: originalMessage
                });

                // Odstranit zprávu o načítání
                const messages = document.getElementById('commandBotMessages');
                if (messages) {
                    const loadingMsg = Array.from(messages.children).find(child =>
                        child.textContent.includes('Zpracovávám příkaz')
                    );
                    if (loadingMsg) loadingMsg.remove();
                }

                // Zobrazit výsledek
                const botMessage = response.result_summary ||
                    `Příkaz byl zpracován. Typ: ${response.intent_type}, Status: ${response.status}`;
                const isError = response.status === 'FAILED';
                addCommandBotMessage('bot', botMessage, response.intent_type, response.status, isError);

                // Pokud byl vytvořen úkol nebo rezervace, načíst aktualizované seznamy
                if (response.intent_type === 'CREATE_BOOKING') {
                    if (document.getElementById('reservationsTab')?.classList.contains('active')) {
                        loadReservations();
                    }
                } else if (response.intent_type === 'CREATE_TASK') {
                    if (document.getElementById('remindersTab')?.classList.contains('active')) {
                        loadReminders();
                    }
                }

            } catch (error) {
                console.error("[COMMAND BOT] Chyba při zpracování s vozidlem:");
                addCommandBotMessage('bot', `Chyba: ${error.message || 'Nepodařilo se zpracovat příkaz'}`, null, 'FAILED', true);
            } finally {
                // Re-enable input a tlačítko po výběru vozidla
                const input = document.getElementById('commandBotInput');
                const sendBtn = document.querySelector('.command-bot-send');
                if (input) input.disabled = false;
                if (sendBtn) sendBtn.disabled = false;
                if (input) input.focus();
            }
        }

        async function loadCommandBotHistory() {
            const container = document.getElementById('commandBotMessages');
            if (!container) return;

            // Zobrazit welcome message, pokud není historie
            const welcome = container.querySelector('.command-bot-welcome');
            if (!welcome && container.children.length === 0) {
                const welcomeDiv = document.createElement('div');
                welcomeDiv.className = 'command-bot-welcome';
                welcomeDiv.innerHTML = `
                    <p>👋 Ahoj! Jsem Command Bot.</p>
                    <p>Napište mi příkaz v běžné češtině a já ho automaticky zpracuji.</p>
                    <p style="margin-top: 12px; font-size: 12px; color: #64748b;">
                        <strong>Příklady:</strong><br>
                        • "Chci se objednat na servis"<br>
                        • "Připomeň mi výměnu oleje"<br>
                        • "Zapiš si poznámku o brzdách"
                    </p>
                `;
                container.appendChild(welcomeDiv);
            }

            if (!currentUser || !currentUser.email) {
                return;
            }

            try {
                const data = await apiCall('/api/customer-commands?limit=20', 'GET');

                if (!data.commands || data.commands.length === 0) {
                    return;
                }

                // Zobrazit pouze příkazy aktuálního uživatele
                const userCommands = data.commands.filter(cmd =>
                    cmd.customer_email === currentUser.email
                );

                if (userCommands.length === 0) {
                    return;
                }

                // Odstranit welcome message
                const welcomeMsg = container.querySelector('.command-bot-welcome');
                if (welcomeMsg) welcomeMsg.remove();

                // Zobrazit historii (nejnovější první)
                userCommands.reverse().forEach(cmd => {
                    addCommandBotMessage('user', cmd.raw_text);
                    if (cmd.result_summary || cmd.error_message) {
                        const message = cmd.result_summary || cmd.error_message;
                        const isError = cmd.status === 'FAILED';
                        addCommandBotMessage('bot', message, cmd.intent_type, cmd.status, isError);
                    }
                });

            } catch (error) {
                console.error("[COMMAND BOT] Chyba při načítání historie:");
            }
        }

        // Zobrazení formuláře pro změnu hesla
        function showChangePasswordForm() {
            // Formulář je nyní vždy viditelný v kartě, takže tato funkce není potřeba
            // Ale můžeme scrollovat na formulář
            const form = document.getElementById('changePasswordForm');
            if (form) {
                form.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        }

        // Skrytí formuláře pro změnu hesla (reset formuláře)
        function hideChangePasswordForm() {
            const form = document.getElementById('changePasswordFormContent');
            if (form) {
                form.reset();
                const errorContainer = document.getElementById('changePasswordErrorContainer');
                if (errorContainer) {
                    errorContainer.innerHTML = '';
                }
            }
        }

        // Změna hesla
        async function handleChangePassword(event) {
            event.preventDefault();
            const errorContainer = document.getElementById('changePasswordErrorContainer');
            const button = event.target.querySelector('button[type="submit"]');
            const originalButtonText = button ? button.textContent : 'Změnit heslo';

            try {
                // Disable tlačítka
                if (button) {
                    button.disabled = true;
                    button.textContent = 'Měním heslo...';
                }

                const currentPassword = document.getElementById('currentPassword').value;
                const newPassword = document.getElementById('newPassword').value;
                const confirmPassword = document.getElementById('confirmNewPassword').value;

                // Validace
                if (!currentPassword) {
                    showFormError('changePasswordErrorContainer', 'Zadejte současné heslo');
                    if (button) {
                        button.disabled = false;
                        button.textContent = originalButtonText;
                    }
                    return;
                }

                if (!newPassword || newPassword.length < 6) {
                    showFormError('changePasswordErrorContainer', 'Nové heslo musí mít alespoň 6 znaků');
                    if (button) {
                        button.disabled = false;
                        button.textContent = originalButtonText;
                    }
                    return;
                }

                if (newPassword !== confirmPassword) {
                    showFormError('changePasswordErrorContainer', 'Hesla se neshodují');
                    if (button) {
                        button.disabled = false;
                        button.textContent = originalButtonText;
                    }
                    return;
                }

                const response = await apiCall('/user/change-password', 'PUT', {
                    current_password: currentPassword,
                    new_password: newPassword
                });

                // Zobrazit úspěšnou zprávu
                showFormError('changePasswordErrorContainer', '');

                let successMessage = 'Heslo bylo úspěšně změněno';
                if (response.email_sent) {
                    successMessage += ' a potvrzovací email byl odeslán na váš email';
                } else if (response.message && response.message.includes('email')) {
                    successMessage += '. ' + (response.message.includes('není nakonfigurován') ? 'Email není nakonfigurován.' : '');
                }

                showAlert(successMessage, 'success');

                // Vyčistit formulář a schovat ho po 2 sekundách
                document.getElementById('changePasswordFormContent').reset();
                setTimeout(() => {
                    hideChangePasswordForm();
                }, 2000);

            } catch (error) {
                console.error("[PROFILE] Chyba při změně hesla:");
                showFormError('changePasswordErrorContainer', 'Nepodařilo se změnit heslo: ' + error.message);
            } finally {
                // Re-enable tlačítka
                if (button) {
                    button.disabled = false;
                    button.textContent = originalButtonText;
                }
            }
        }

        // ============= VERZE APLIKACE =============

        // Načtení informací o verzi
        async function loadVersionInfo() {
            return;
        }

        // Zobrazit/skrýt Command Bot bublinu podle přihlášení
        // Command Bot DOČASNĚ VYPNUT
        function updateCommandBotVisibility() {
            // Command Bot je dočasně vypnutý
            return;
        }

        // Vyčistit interval při opuštění stránky
        window.addEventListener('beforeunload', () => {
            if (serverStatusCheckInterval) {
                clearInterval(serverStatusCheckInterval);
            }
        });

        // Inicializace viditelnosti bubliny (voláno po načtení uživatele v DOMContentLoaded)
        // Funkce se volá automaticky po načtení uživatele z localStorage

        // Debug Panel Functions
        function toggleDebugPanel() {
            const panel = document.getElementById('debugPanel');
            if (!panel) return;

            if (panel.classList.contains('hidden')) {
                panel.classList.remove('hidden');
                panel.style.display = 'block';
                updateDebugPanel();
            } else {
                panel.classList.add('hidden');
                panel.style.display = 'none';
            }
        }

        function updateDebugPanel() {
            // Location info
            document.getElementById('debug-location-href').textContent = window.location.href;
            document.getElementById('debug-location-origin').textContent = window.location.origin;
            document.getElementById('debug-location-hostname').textContent = window.location.hostname;
            document.getElementById('debug-api-base-url').textContent = getApiBaseUrl();

            // Auth info
            const token = getAuthStorageItem(AUTH_STORAGE_KEYS.token);
            document.getElementById('debug-token-present').textContent = token ? 'Yes' : 'No';
            document.getElementById('debug-token-present').style.color = token ? '#10b981' : '#ef4444';

            const rawStoredUser = getAuthStorageItem(AUTH_STORAGE_KEYS.user);
            let parsedStoredUser = null;
            if (rawStoredUser) {
                try {
                    parsedStoredUser = JSON.parse(rawStoredUser);
                } catch (e) {
                    parsedStoredUser = null;
                }
            }
            const user = currentUser || parsedStoredUser;
            document.getElementById('debug-user-email').textContent = user?.email || '-';

            // Recent requests
            const requestsList = document.getElementById('debug-requests-list');
            if (debugRequests.length === 0) {
                requestsList.innerHTML = '<p style="color: #666;">Žádné requesty zatím</p>';
            } else {
                requestsList.innerHTML = debugRequests.map(req => {
                    const statusClass = req.status >= 200 && req.status < 300 ? 'success' :
                                       req.status >= 400 ? 'error' : '';
                    return `
                        <div class="debug-request-item ${statusClass}">
                            <div>
                                <span class="debug-request-method ${escapeHtml(req.method)}">${escapeHtml(req.method)}</span>
                                <strong>${escapeHtml(req.url)}</strong>
                            </div>
                            <div style="margin-top: 5px; font-size: 0.85rem;">
                                <strong>Status:</strong> ${escapeHtml(req.status)} |
                                <strong>Time:</strong> ${escapeHtml(new Date(req.timestamp).toLocaleTimeString())}
                            </div>
                            <div style="margin-top: 5px; font-size: 0.8rem; color: #666;">
                                <strong>Response:</strong> ${escapeHtml(req.responseBody || '[prázdné]')}
                            </div>
                        </div>
                    `;
                }).join('');
            }
        }

        function resetApiUrl() {
            if (typeof SpravaVozidelStorage !== 'undefined') {
                SpravaVozidelStorage.removeLocal('apiUrl');
            } else {
                localStorage.removeItem('toozhub_api_url');
                localStorage.removeItem('sprava_vozidel_api_url');
            }
            API_URL = getApiBaseUrl();
            updateDebugPanel();
            showAlert('API URL resetována', 'success');
        }

        // Jednoduchý dropdown Licence v topbaru (statický obsah)
        function initLicenseQuickBadge() {
            const toggle = document.getElementById('licenseQuickToggle');
            const dropdown = document.getElementById('licenseQuickDropdown');

            if (!toggle || !dropdown) return;

            // Dropdown nebudeme používat, držíme ho skrytý
            const closeDropdown = () => dropdown.classList.add('hidden');
            closeDropdown();

            toggle.addEventListener('click', (e) => {
                e.stopPropagation();
                // Kontrola, jestli je uživatel přihlášený
                if (!isAuthenticated()) {
                    console.warn("[LICENSE] Uživatel není přihlášen - zobrazuji přihlašovací okno");
                    showLogin();
                    return;
                }
                openLicensePlans();
            });

            dropdown.addEventListener('click', (e) => {
                // Nepropagovat kliknutí z bubliny, aby se nezavřela
                e.stopPropagation();
            });

            dropdown.querySelectorAll('.license-quick-upgrade').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    openLicensePlans();
                });
            });

            document.addEventListener('click', () => {
                closeDropdown();
            });

            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    closeDropdown();
                }
            });
        }

        document.addEventListener('DOMContentLoaded', initLicenseQuickBadge);

        document.addEventListener('DOMContentLoaded', () => {
            schedulePaymentBrandContrastRefresh();
            window.addEventListener('resize', schedulePaymentBrandContrastRefresh);

            if (typeof MutationObserver === 'function') {
                const observer = new MutationObserver(() => {
                    schedulePaymentBrandContrastRefresh();
                });
                const observeTargets = [
                    document.documentElement,
                    document.body,
                    document.querySelector('.payment-legal-footer'),
                    document.getElementById('licenseModal'),
                    document.getElementById('licenseComgateBrand'),
                ].filter(Boolean);
                observeTargets.forEach((target) => {
                    observer.observe(target, {
                        attributes: true,
                        attributeFilter: ['class', 'style'],
                    });
                });
            }
        });

        // Debug button držet skrytý pro běžné uživatele
        document.addEventListener('DOMContentLoaded', function() {
            const debugBtn = document.getElementById('debugButton');
            if (!debugBtn) {
                return;
            }

            const isProduction = window.location.hostname === 'app.toozservis.cz';
            const params = new URLSearchParams(window.location.search || '');
            const isAdmin = params.get('admin') === '1';
            const forceDebug = params.get('debug') === '1';

            // V produkci skryto; v dev jen pro admina nebo při explicitním debug=1
            if ((!isProduction && isAdmin) || forceDebug) {
                debugBtn.classList.remove('hidden');
            } else {
                debugBtn.classList.add('hidden');
            }
        });

// Session closure must also remove local previews and stop background refreshes.
function clearLegacySessionData() {
    window.CustomerFeatures?.reset();
    stopInactivityTimer(); stopLicenseRefresh(); stopClientGeoRefresh(); stopReminderNotificationHeartbeat(); stopSystemNotificationsPolling();
    clearInterval(serverStatusCheckInterval); serverStatusCheckInterval = null;
    currentUser = null; accessToken = null; authSecuritySettingsCache = null; clearClientGeoTelemetry();
    stopAuthStoryAutoplay(); servicesDirectoryState.payload = null;
    pendingTwoFactorChallenge = null; pendingServiceInviteToken = null; pendingReservationClaimToken = null;
    comgateConfigCache = null; currentLicenseSubscriptionForUi = null; debugRequests = [];
    reservationsUiState.all = []; serviceWorkspaceState.customers = [];
    serviceWorkspaceState.customerVehicles = {}; serviceWorkspaceState.documents = []; serviceWorkspaceState.invitations = [];
    for (const url of vehiclePhotoObjectUrls.values()) URL.revokeObjectURL(url);
    vehiclePhotoObjectUrls.clear();
    if (activeAttachmentPreviewUrl) URL.revokeObjectURL(activeAttachmentPreviewUrl);
    activeAttachmentPreviewUrl = null;
}
