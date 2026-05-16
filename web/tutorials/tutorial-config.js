/**
 * Konfigurace interaktivních návodů (guidance layer).
 * Rozhraní: USER — user-index.html, SERVICE — service-index.html (+ service-shell.js).
 * __TUTORIAL_HUB_LAYOUT = USER (zpětná kompatibilita); SERVICE používá __TUTORIAL_HUB_LAYOUT_SERVICE.
 */
(function () {
  'use strict';

  /** Placeholder návody doplněné postupně; copy je lidské, neslibuje funkcionalitu která teprve dorazí. */
  var P =
    'Klikací průvodce se připravuje. Použijte už spuštěné návody nahoře v hubu („Orientace“, „Přidat vozidlo“, servisní mapa prostředí), nebo napište podpoře.';

  /** @typedef {Object} TutorialStepCfg */

  /** @type {typeof window.__TUTORIAL_HUB_LAYOUT_USER} */
  window.__TUTORIAL_HUB_LAYOUT_USER = [
    {
      categoryId: 'zacatek',
      title: 'Začínáme (uživatelské účty)',
      items: [
        { tutorialId: 'user-overview-map', label: 'Orientace na první pohled', disabled: false },
        {
          tutorialId: null,
          label: 'První přihlášení — co ověříme u účtu',
          disabled: true,
          hint: P,
        },
        {
          tutorialId: null,
          label: 'Přehled (dashboard): co znamenají dlaždice',
          disabled: true,
          hint: P,
        },
        {
          tutorialId: null,
          label: 'Jak funguje aplikace jako celek — workflow vlastního vozu',
          disabled: true,
          hint:
            'Má vlastní řadu kroků: garáž → servisní záznamy → dokumentace → dílčí sdílení se servisem. Podrobnosti doplníme do samostatného průvodce.',
        },
      ],
    },
    {
      categoryId: 'vozidla',
      title: 'Vozidla a historie',
      items: [
        { tutorialId: 'add-vehicle', label: 'Přidat vozidlo (VIN, STK…)', disabled: false },
        { tutorialId: null, label: 'Upravit údaje vozidla', disabled: true, hint: P },
        { tutorialId: null, label: 'Servisní historie vlastní údržby', disabled: true, hint: P },
        { tutorialId: null, label: 'Přidání servisního záznamu', disabled: true, hint: P },
        {
          tutorialId: null,
          label: 'Tachometr — historie a ruční vstupy',
          disabled: true,
          hint: P,
        },
        {
          tutorialId: null,
          label: 'Časová osa událostí na vozidle',
          disabled: true,
          hint: P,
        },
        {
          tutorialId: null,
          label: 'Sdílení vozidla se servisem (schválení přístupu)',
          disabled: true,
          hint: P,
        },
        { tutorialId: null, label: 'Převod vozidla na nového vlastníka', disabled: true, hint: P },
        {
          tutorialId: null,
          label: 'Vyhledání STK / SME pomocníkem aplikace',
          disabled: true,
          hint: P,
        },
      ],
    },
    {
      categoryId: 'dokumenty-qr',
      title: 'Dokumenty, QR a výpisy',
      items: [
        { tutorialId: null, label: 'Jak doplnit PDF / doklad k autu', disabled: true, hint: P },
        { tutorialId: null, label: 'Jak bezpečně sdílet historii QR kódem', disabled: true, hint: P },
        { tutorialId: null, label: 'Veřejný / exportovatelný přehled', disabled: true, hint: P },
      ],
    },
    {
      categoryId: 'pripomenuti',
      title: 'Úkoly, STK a servisně-rezervační blok',
      items: [
        { tutorialId: null, label: 'Připomínky na STK, servis či vlastní práce', disabled: true, hint: P },
        { tutorialId: null, label: 'Rezervace u servisu (co pošlete servisu)', disabled: true, hint: P },
      ],
    },
    {
      categoryId: 'nastaveni',
      title: 'Účet, licence a kontakty na podporu',
      items: [
        {
          tutorialId: null,
          label: 'Nastavení profilu, kontaktů a notifikací',
          disabled: true,
          hint: P,
        },
        {
          tutorialId: null,
          label: 'Licence a předplatné — kde co uvidím',
          disabled: true,
          hint: P,
        },
        { tutorialId: null, label: 'Mobilní ovládání (lišta na malém displeji)', disabled: true, hint: P },
        { tutorialId: null, label: 'Globální vyhledávání v účtu', disabled: true, hint: P },
      ],
    },
  ];

  window.__TUTORIAL_HUB_LAYOUT_SERVICE = [
    {
      categoryId: 'servis-start',
      title: 'Start v servisu',
      items: [
        { tutorialId: 'svc-overview-map', label: 'Mapa prostředí servisu (90 s)', disabled: false },
        { tutorialId: null, label: 'Úvodní onboarding po schválení účtu', disabled: true, hint: P },
        {
          tutorialId: null,
          label: 'Jak řídit dashboard (KPI, fronta zakázek)',
          disabled: true,
          hint: P,
        },
        {
          tutorialId: null,
          label: 'Jak funguje celek USER ↔ SERVICE (propojení zákazníka)',
          disabled: true,
          hint:
            'Z pohledu servisu začíná vždy oprávnění v aplikaci „Správa vozidel“ — kompletní průvodce připravíme po finálních cílových prvcích GUI.',
        },
      ],
    },
    {
      categoryId: 'servis-customers',
      title: 'Zákazníci a vozidla',
      items: [
        { tutorialId: null, label: 'Přidat nového servisního zákazníka', disabled: true, hint: P },
        { tutorialId: null, label: 'Propojit uživatele se stávajícím Tooz účtem', disabled: true, hint: P },
        { tutorialId: null, label: 'Přidat vůz přímo tomu klientovi', disabled: true, hint: P },
        { tutorialId: null, label: 'Přehled zákazníků vs. filtrování', disabled: true, hint: P },
      ],
    },
    {
      categoryId: 'servis-ops',
      title: 'Servisní provoz',
      items: [
        { tutorialId: null, label: 'Work orders — životní cyklus zakázky', disabled: true, hint: P },
        { tutorialId: null, label: 'Příjem vozidla a hand-off technikovi', disabled: true, hint: P },
        { tutorialId: null, label: 'Servisní záznamy (interní × viditelný text)', disabled: true, hint: P },
        { tutorialId: null, label: 'Čerpání prací a času', disabled: true, hint: P },
        {
          tutorialId: null,
          label: 'Fotografie, přílohy a interní jen pro servis',
          disabled: true,
          hint: P,
        },
        {
          tutorialId: null,
          label: 'Připomínky před STK či dílenskými lhůtami',
          disabled: true,
          hint: P,
        },
        { tutorialId: null, label: 'GDPR pohled na data zákazníka', disabled: true, hint: P },
      ],
    },
    {
      categoryId: 'servis-money-docs',
      title: 'Doklady, fakturace a veřejné výstupy',
      items: [
        { tutorialId: null, label: 'Faktury a navázaný workflow', disabled: true, hint: P },
        { tutorialId: null, label: 'Interní dokumenty vs. dokumenty viditelné zákazníkovi', disabled: true, hint: P },
        { tutorialId: null, label: 'Veřejná historie přes QR / export', disabled: true, hint: P },
      ],
    },
  ];

  window.__TUTORIAL_HUB_LAYOUT = window.__TUTORIAL_HUB_LAYOUT_USER;

  /**
   * @type {Record<string, {
   *   id: string,
   *   title: string,
   *   roles: string[],
   *   modalGuardId?: string|null,
   *   routeTabOnce?: boolean,
   *   serviceSectionOnce?: boolean,
   *   startRouteTab?: string,
   *   startServiceSection?: string,
   *   category: string,
   *   steps: TutorialStepCfg[]
   * }>}
   */
  window.__TUTORIAL_REGISTRY = {
    'user-overview-map': {
      id: 'user-overview-map',
      title: 'Orientace na první pohled',
      roles: ['user'],
      category: 'zacatek',
      routeTabOnce: true,
      startRouteTab: 'home',
      modalGuardId: null,
      steps: [
        {
          id: 'uo-intro',
          target: '',
          title: 'Vítejte mezi vlastníky vozů',
          text:
            'V horní mapě aplikace je schovaný váš proces: přehled → vozy → dokumenty → podpora/Nastavení. Návod vás jemně provede pár kliky — aplikaci neovládám za vás a data na server nemusím posílat dříve než vy.',
          actionType: 'next',
          placement: 'center',
          timeoutMs: 60000,
        },
        {
          id: 'uo-tab-dashboard',
          target: 'user-tab-home',
          title: 'Přehled = domovská obrazovka',
          text:
            'Tady začínáte po přihlášení — rychlé stavy a úkoly. Jen potvrďte „Další“ a zůstaneme na kartě jako doma.',
          actionType: 'review',
          placement: 'bottom',
          timeoutMs: 60000,
        },
        {
          id: 'uo-click-vehicles',
          target: 'user-tab-vehicles',
          title: 'Přejděte do garáže',
          text:
            'Ťukněte na „Vozidla“. Tady řešíte VIN/SPZ, STK či dílenské díly – přesně jako v ostrém provozu. Níže v hubu už máme hotový průvodce „Přidat vozidlo“, pokud začínáte od nuly.',
          actionType: 'click',
          placement: 'bottom',
          timeoutMs: 120000,
        },
        {
          id: 'uo-click-documents',
          target: 'user-tab-documents',
          title: 'Úschovna dokumentů ke každému autu',
          text:
            'Sekce „Dokumenty“ drží faktury, protokoly, PDF výpisy či dílenské dokumenty u konkrétního auta bez posílání e-mailů do éteru.',
          actionType: 'click',
          placement: 'bottom',
          timeoutMs: 120000,
        },
        {
          id: 'uo-how-to-menu',
          target: '',
          title: 'Jak najdete jakýkoli delší návod',
          text:
            'Otevřete své uživatelské menu (ikona účtu) → „Jak na to“. Všechny budoucí průvodce budou jen tam — stejně jako tento rozcestník, takže ani po reloadu nepřijdeme o způsob startu.',
          actionType: 'next',
          placement: 'center',
          timeoutMs: 60000,
        },
        {
          id: 'uo-outro',
          target: '',
          title: 'Hotovo — zpět za volant',
          text:
            'Tutorial neobchází validace ani role. Kdykoliv něco nevíte, vraťte se do hubu v menu účtu, nejdříve ale dokončete rozpracovaný krok formuláře — návod jen ztmaví šum kolem.',
          actionType: 'next',
          placement: 'center',
          timeoutMs: 60000,
        },
      ],
    },
    'svc-overview-map': {
      id: 'svc-overview-map',
      title: 'Mapa prostředí Tooz Servis',
      roles: ['service'],
      category: 'servis-start',
      modalGuardId: null,
      startServiceSection: 'dashboard',
      serviceSectionOnce: true,
      steps: [
        {
          id: 'sv-intro',
          target: '',
          title: 'Vítejte v servisní části aplikace',
          text:
            'Levá lišta = moduly jako fakturační zóna či dokumenty. Horní řádek pod logem řídí denní provoz přes zákazníky a zakázky. Nežádám server o změnu stavu — jen vás provedu ostrým rozhraním, které vidí dílna.',
          actionType: 'next',
          placement: 'center',
          timeoutMs: 60000,
        },
        {
          id: 'sv-rail-dashboard',
          target: 'svc-shell-dashboard',
          title: 'Přehled (levá lišta „Přehled“)',
          text:
            'Zde řešíte metriku provozovny — čímž zachytíte dřív problémové lhůty. Pokračujte „Další“, kdy máte pocit, že místo dává smysl.',
          actionType: 'review',
          placement: 'right',
          timeoutMs: 60000,
        },
        {
          id: 'sv-click-clients',
          target: 'svc-topnav-clients',
          title: 'Evidence zákazníků (horní řádek)',
          text:
            'Klikněte na „Přehled zákazníků“. V databázi servisu řešíte firmy/osoby bez obcházení propojení s Tooz aplikací majitele vozidel.',
          actionType: 'click',
          placement: 'bottom',
          timeoutMs: 120000,
        },
        {
          id: 'sv-bridge-explainer',
          target: '',
          title: 'Jak vlastně sedí vlastní → servisní data',
          text:
            'Majitel vozidla ve svém účtu rozhodne, co servis vidí — část historie umí držet jen interně u vás dílně (např. vnitrodílenské poznámky). Návod to neobchází; jen vás naviguje jako na instruktáži.',
          actionType: 'next',
          placement: 'center',
          timeoutMs: 90000,
        },
        {
          id: 'sv-click-workorders',
          target: 'svc-topnav-work-orders',
          title: 'Fronta zakázek',
          text:
            'Přesuňte se na horní řádek → „Příchozí objednávky“. Zde začíná a končí reálný dílenský workflow – od příchodu přes dokumentaci až po fakturu.',
          actionType: 'click',
          placement: 'bottom',
          timeoutMs: 120000,
        },
        {
          id: 'sv-help-rail',
          target: 'svc-shell-help-center',
          title: 'Modul Jak na to (levá lišta Nápověda)',
          text:
            'Otevřete „Nápověda“ v levém sloupci. Uvnitř je tlačítko přímo do hubu všech dostupných průvodců Servisu — stejná vrstva jako u majitelů.',
          actionType: 'click',
          placement: 'right',
          timeoutMs: 120000,
        },
        {
          id: 'sv-outro',
          target: '',
          title: 'Dáleuž jen živý provoz',
          text:
            'Hotové průvodce najdete v hubu („Otevřít Jak na to“). Každý krok stále prochází běžné validace — jen jsme zaměřili rozhraní, aby dílna netápala po registraci účtu.',
          actionType: 'next',
          placement: 'center',
          timeoutMs: 90000,
        },
      ],
    },
    'add-vehicle': {
      id: 'add-vehicle',
      title: 'Jak přidat vozidlo',
      roles: ['user'],
      modalGuardId: 'addVehicleModal',
      category: 'vozidla',
      startRouteTab: 'vehicles',
      routeTabOnce: false,
      steps: [
        {
          id: 'go-vehicles-tab',
          target: '',
          title: 'Sekce Vozidla',
          text:
            'Návod začíná v záložce Vozidla. Pokud už jste tady, pokračujte tlačítkem „Další“. Jinak aplikaci na tuto záložku přepneme.',
          actionType: 'next',
          placement: 'center',
          required: false,
          timeoutMs: 20000,
          failureCodes: ['ROUTE_MISMATCH', 'PERMISSION_DENIED', 'UNKNOWN_TUTORIAL_FAILURE'],
          prefetchRoute: true,
        },
        {
          id: 'highlight-add-open',
          target: 'add-vehicle-button',
          title: 'Přidat vozidlo',
          text: 'Klikněte na „Přidat vozidlo“, aby se otevřel formulář v platném aplikačním postupu (žádné zkraty).',
          actionType: 'click',
          placement: 'bottom',
          required: true,
          timeoutMs: 120000,
          failureCodes: [
            'TUTORIAL_SELECTOR_MISSING',
            'UI_TARGET_NOT_VISIBLE',
            'UI_TARGET_DISABLED',
            'ROUTE_MISMATCH',
          ],
        },
        {
          id: 'wait-add-modal',
          target: 'vehicle-create-modal',
          title: 'Formulář nového vozidla',
          text:
            'Počkejte, až se zobrazí celý formulář. Vše vyplňujete normálně — návod jen zvýrazňuje prvky. Po zavření modalu návod automaticky doběhne bezpečnou cestou (ukončení + vyčištění overlay).',
          actionType: 'waitForModal',
          placement: 'center',
          required: true,
          timeoutMs: 60000,
          failureCodes: ['MODAL_NOT_OPENED', 'TUTORIAL_SELECTOR_MISSING', 'TUTORIAL_CONFIG_ERROR'],
        },
        {
          id: 'field-vin',
          target: 'vehicle-vin-input',
          title: 'VIN kód',
          text:
            'Vypište VIN přímo do pole (nejčastěji 17 znaků). Návod pokračuje až tehdy, když má pole platných 17 znaků — nepočítáme první písmenka, jen stav formuláře. Po doplnění klidně využijte databázové načítání aplikace, ale řídicí slovo má uživatel.',
          actionType: 'waitForValid',
          waitPredicate: 'vinLen17',
          blocking: true,
          failureCode: 'VALIDATION_BLOCKED',
          placement: 'bottom',
          required: false,
          timeoutMs: 180000,
          failureCodes: [
            'TUTORIAL_SELECTOR_MISSING',
            'UI_TARGET_NOT_VISIBLE',
            'MODAL_NOT_OPENED',
            'UNKNOWN_TUTORIAL_FAILURE',
          ],
        },
        {
          id: 'field-name',
          target: 'vehicle-name-input',
          title: 'Název vozidla',
          text:
            'Pro uložení je potřeba název alespoň se 2 znaky. Aplikace po VIN něco doplní sama — k dalšímu kroku jde použít až kontrolně „Další“ (bez skoku jen podle databáze).',
          actionType: 'review',
          waitPredicate: 'nameMin2',
          placement: 'bottom',
          required: false,
          timeoutMs: 120000,
          failureCodes: [
            'TUTORIAL_SELECTOR_MISSING',
            'UI_TARGET_NOT_VISIBLE',
            'MODAL_NOT_OPENED',
            'UNKNOWN_TUTORIAL_FAILURE',
          ],
        },
        {
          id: 'field-plate',
          target: 'vehicle-plate-input',
          title: 'SPZ',
          text:
            'Registrační značku dopište klasicky jako v provozním provozu. Po doplnění pokračujte „Další“ — ani tady neděláme automatický skok jen po změně textu bez potvrzení.',
          actionType: 'review',
          waitPredicate: 'plateNonEmpty',
          placement: 'bottom',
          required: false,
          timeoutMs: 120000,
          failureCodes: [
            'TUTORIAL_SELECTOR_MISSING',
            'UI_TARGET_NOT_VISIBLE',
            'MODAL_NOT_OPENED',
            'UNKNOWN_TUTORIAL_FAILURE',
          ],
        },
        {
          id: 'review-technical-block',
          target: 'vehicle-technical-summary',
          title: 'Načtené technické údaje',
          text:
            'Zkontrolujte značku (pole „Model“, kompletní technický řádek, ročník…) a teprve pak pokračujte. Nesedí-li něco lidsky, měňte přímo v polích — jen vás držíme v kontextu, ne měníme data bez vás.',
          actionType: 'review',
          placement: 'top',
          required: false,
          timeoutMs: 60000,
          failureCodes: ['TUTORIAL_SELECTOR_MISSING', 'UI_TARGET_NOT_VISIBLE'],
        },
        {
          id: 'field-stk',
          target: 'vehicle-stk-input',
          title: 'Platnost STK',
          text:
            'Datum konce platnosti STK nastavte klasicky jako v produkčním použití formuláře — je povinný údaj a návod jej také nesnižuje na volitelnou položku.',
          actionType: 'waitForValid',
          waitPredicate: 'stkDateNonEmpty',
          blocking: true,
          failureCode: 'VALIDATION_BLOCKED',
          placement: 'top',
          required: true,
          timeoutMs: 120000,
          failureCodes: [
            'TUTORIAL_SELECTOR_MISSING',
            'UI_TARGET_NOT_VISIBLE',
            'UI_TARGET_DISABLED',
            'MODAL_NOT_OPENED',
            'UNKNOWN_TUTORIAL_FAILURE',
          ],
        },
        {
          id: 'field-odometer',
          target: 'vehicle-odometer-input',
          title: 'Stav tachometru',
          text:
            'Nájezd dopište jen pokud jej znáte; pole zůstat může prázdně. Slouží hlavně pro budoucí záznamy servisu přímo nad vozem.',
          actionType: 'review',
          placement: 'top',
          required: false,
          timeoutMs: 120000,
          failureCodes: ['TUTORIAL_SELECTOR_MISSING'],
        },
        {
          id: 'precheck-required',
          target: '',
          title: 'Kontrola povinných údajů',
          text:
            '',
          actionType: 'observeFormValidation',
          placement: 'center',
          required: true,
          timeoutMs: 60000,
          failureCodes: ['VALIDATION_BLOCKED', 'UNKNOWN_TUTORIAL_FAILURE'],
        },
        {
          id: 'cta-save',
          target: 'vehicle-save-button',
          title: 'Uložení vozidla',
          text:
            '„Přidat vozidlo“ jen potvrdíte kliknutím — žádné simulované API odpovědi ani neviditelný POST. Bez validovaného formuláře se stejně neposune.',
          actionType: 'click',
          placement: 'top',
          required: true,
          timeoutMs: 120000,
          failureCodes: [
            'TUTORIAL_SELECTOR_MISSING',
            'UI_TARGET_NOT_VISIBLE',
            'UI_TARGET_DISABLED',
            'UNKNOWN_TUTORIAL_FAILURE',
          ],
        },
        {
          id: 'wait-save-api',
          target: '',
          title: 'Ukládám…',
          text:
            'Počkejte na pravou síťovou odpověď. Jakmile server potvrdí, návod jen pogratuluje.',
          actionType: 'waitForApiSuccess',
          placement: 'center',
          required: true,
          timeoutMs: 120000,
          failureCodes: ['API_ERROR', 'PERMISSION_DENIED', 'UNKNOWN_TUTORIAL_FAILURE'],
        },
        {
          id: 'done-celebrate',
          target: '',
          title: 'Hotovo',
          text:
            'Vůz už je v aplikaci. Teď mohou začít dílenské záznamy, fotky či dokumenty — když nevíte „jak přesně“, vraťte se do Jak na to v menu uživatele.',
          actionType: 'next',
          placement: 'center',
          required: false,
          timeoutMs: 60000,
          failureCodes: [],
        },
      ],
    },
  };
})();
