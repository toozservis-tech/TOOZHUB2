(function () {
  'use strict';

  const rootId = 'product-sections';

  function icon(name) {
    const common = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';
    const icons = {
      garage: '<path d="M4 10.5 12 5l8 5.5v8.5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-8.5Z"/><path d="M8 20v-6.5h8V20"/><path d="M9.5 10.5h5"/><path d="M9.5 16.5h5"/>',
      search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/>',
      plus: '<path d="M12 5v14"/><path d="M5 12h14"/>',
      chevron: '<path d="m9 18 6-6-6-6"/>',
      play: '<circle cx="12" cy="12" r="9"/><path d="m10 8 6 4-6 4V8Z"/>',
      check: '<path d="M20 6 9 17l-5-5"/>',
      calendar: '<path d="M7 3v4"/><path d="M17 3v4"/><path d="M4 9h16"/><path d="M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z"/>',
      wrench: '<path d="M14.7 6.3a4.6 4.6 0 0 0-5.8 5.8L4 17l3 3 4.9-4.9a4.6 4.6 0 0 0 5.8-5.8l-3 3-3-3 3-3Z"/>',
      document: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z"/><path d="M14 3v5h5"/><path d="M9 13h6"/><path d="M9 17h4"/>',
      users: '<path d="M16 20v-1.5a3.5 3.5 0 0 0-7 0V20"/><circle cx="12.5" cy="8" r="3.5"/><path d="M4 19v-1a3 3 0 0 1 3-3"/><path d="M20 19v-1a3 3 0 0 0-3-3"/>',
      shield: '<path d="M12 3 20 6v5c0 5-3.4 8.2-8 10-4.6-1.8-8-5-8-10V6l8-3Z"/><path d="m8.8 12 2.1 2.1 4.5-4.7"/>',
      lock: '<rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
      qr: '<path d="M4 4h6v6H4Z"/><path d="M14 4h6v6h-6Z"/><path d="M4 14h6v6H4Z"/><path d="M14 14h2"/><path d="M20 14v2"/><path d="M16 16h4"/><path d="M14 18h2"/><path d="M18 18h2v2h-4"/>',
      menu: '<path d="M4 7h16"/><path d="M4 12h16"/><path d="M4 17h16"/>',
      bell: '<path d="M18 9a6 6 0 0 0-12 0c0 7-3 6-3 8h18c0-2-3-1-3-8Z"/><path d="M10 21h4"/>',
      car: '<path d="M5 15h14"/><path d="m7 15 1.5-4.5A2 2 0 0 1 10.4 9h3.2a2 2 0 0 1 1.9 1.5L17 15"/><circle cx="8" cy="17" r="1.5"/><circle cx="16" cy="17" r="1.5"/>'
    };
    return `<svg ${common}>${icons[name] || icons.check}</svg>`;
  }

  function brand() {
    return `
      <span class="landing-brand-mark">${icon('garage')}</span>
      <span class="landing-brand-name">Správa vozidel</span>
    `;
  }

  function goRegister() {
    if (typeof window.showRegister === 'function') {
      window.showRegister();
    }
  }

  function goLogin() {
    if (typeof window.showLogin === 'function') {
      window.showLogin();
    }
  }

  function closeMenu() {
    const root = document.getElementById(rootId);
    const menu = root?.querySelector('[data-landing-mobile-menu]');
    const button = root?.querySelector('[data-landing-menu-toggle]');
    if (menu) menu.hidden = true;
    if (button) button.setAttribute('aria-expanded', 'false');
  }

  function scrollToSection(id) {
    closeMenu();
    const root = document.getElementById(rootId);
    const target = root?.querySelector(`#${id}`);
    if (!target) return;
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function toggleMenu() {
    const root = document.getElementById(rootId);
    const menu = root?.querySelector('[data-landing-mobile-menu]');
    const button = root?.querySelector('[data-landing-menu-toggle]');
    if (!menu || !button) return;
    const nextOpen = menu.hidden;
    menu.hidden = !nextOpen;
    button.setAttribute('aria-expanded', nextOpen ? 'true' : 'false');
  }

  window.publicLandingScrollTo = scrollToSection;
  window.publicLandingShowLogin = goLogin;
  window.publicLandingShowRegister = goRegister;
  window.publicLandingToggleMenu = toggleMenu;
  window.publicLandingCloseMenu = closeMenu;

  function benefitCard(iconName, title, text, tone) {
    return `
      <article class="landing-benefit-card landing-tone-${tone}">
        <span class="landing-benefit-icon">${icon(iconName)}</span>
        <div>
          <h3>${title}</h3>
          <p>${text}</p>
        </div>
        <span class="landing-card-arrow">${icon('chevron')}</span>
      </article>
    `;
  }

  function renderLanding() {
    const root = document.getElementById(rootId);
    if (!root || root.dataset.publicLandingRestyled === '1') return;

    root.dataset.publicLandingRestyled = '1';
    root.classList.add('public-landing-v2');
    root.innerHTML = `
      <header class="landing-header" aria-label="Veřejná navigace">
        <div class="landing-nav">
          <a href="/" class="landing-brand" onclick="publicLandingScrollTo('landing-home'); return false;">${brand()}</a>
          <nav class="landing-nav-links" aria-label="Sekce veřejného webu">
            <a href="#landing-features" onclick="publicLandingScrollTo('landing-features'); return false;">Funkce</a>
            <a href="#landing-owners" onclick="publicLandingScrollTo('landing-owners'); return false;">Pro majitele</a>
            <a href="#landing-services" onclick="publicLandingScrollTo('landing-services'); return false;">Pro servisy</a>
            <a href="#landing-pricing" onclick="publicLandingScrollTo('landing-pricing'); return false;">Ceník</a>
            <a href="#landing-how" onclick="publicLandingScrollTo('landing-how'); return false;">Jak to funguje</a>
          </nav>
          <div class="landing-nav-actions">
            <button type="button" class="landing-btn landing-btn-ghost" onclick="publicLandingShowLogin(); return false;">Přihlásit se</button>
            <button type="button" class="landing-btn landing-btn-primary" onclick="publicLandingShowRegister(); return false;">Vyzkoušet zdarma</button>
          </div>
          <button type="button" class="landing-menu-btn" data-landing-menu-toggle aria-expanded="false" aria-controls="landingMobileMenu" onclick="publicLandingToggleMenu(); return false;" aria-label="Otevřít menu">${icon('menu')}</button>
        </div>
        <div id="landingMobileMenu" class="landing-mobile-menu" data-landing-mobile-menu hidden>
          <a href="#landing-features" onclick="publicLandingScrollTo('landing-features'); return false;">Funkce</a>
          <a href="#landing-owners" onclick="publicLandingScrollTo('landing-owners'); return false;">Pro majitele</a>
          <a href="#landing-services" onclick="publicLandingScrollTo('landing-services'); return false;">Pro servisy</a>
          <a href="#landing-pricing" onclick="publicLandingScrollTo('landing-pricing'); return false;">Ceník</a>
          <a href="#landing-how" onclick="publicLandingScrollTo('landing-how'); return false;">Jak to funguje</a>
          <button type="button" class="landing-btn landing-btn-ghost" onclick="publicLandingShowLogin(); return false;">Přihlásit se</button>
          <button type="button" class="landing-btn landing-btn-primary" onclick="publicLandingShowRegister(); return false;">Vyzkoušet zdarma</button>
        </div>
      </header>

      <main class="landing-page" id="landing-home">
        <section class="landing-hero" aria-labelledby="landingHeroTitle">
          <div class="landing-hero-copy">
            <span class="landing-badge">${icon('garage')} Digitální garáž pro vaše vozidla</span>
            <h1 id="landingHeroTitle">Mějte všechna vozidla,<br>servis a dokumenty<br><span>pod kontrolou</span></h1>
            <p class="landing-lead">Správa vozidel spojuje servisní historii, STK, připomínky, faktury, dokumenty a propojení se servisy na jednom bezpečném místě.</p>
            <div class="landing-hero-actions">
              <button type="button" class="landing-btn landing-btn-primary landing-btn-large" onclick="publicLandingShowRegister(); return false;">Začít zdarma ${icon('chevron')}</button>
              <button type="button" class="landing-btn landing-btn-soft landing-btn-large" onclick="publicLandingScrollTo('landing-features'); return false;">${icon('play')} Zobrazit ukázku</button>
            </div>
            <div class="landing-trust-row" aria-label="Hlavní výhody">
              <span>${icon('check')} Bez papírování</span>
              <span>${icon('users')} Pro osobní i firemní vozidla</span>
              <span>${icon('shield')} Připraveno pro autoservisy</span>
            </div>
          </div>

          <div class="landing-hero-art" aria-label="Ukázka dashboardu Správy vozidel">
            <div class="landing-road-bg" aria-hidden="true"></div>
            <div class="landing-app-mockup">
              <aside class="landing-mock-sidebar">
                <div class="landing-mock-brand">${brand()}</div>
                <span class="is-active">${icon('garage')} Přehled</span>
                <span>${icon('car')} Moje vozidla</span>
                <span>${icon('wrench')} Servisní historie</span>
                <span>${icon('document')} Dokumenty</span>
                <span>${icon('calendar')} Připomínky</span>
                <span>${icon('users')} Servisy</span>
              </aside>
              <div class="landing-mock-main">
                <div class="landing-mock-topbar">
                  <div class="landing-mock-search">${icon('search')} Hledat podle SPZ, VIN, značky...</div>
                  <button type="button">${icon('plus')} Přidat vozidlo</button>
                  <span class="landing-mock-bell">${icon('bell')}<i>3</i></span>
                  <span class="landing-mock-avatar"></span>
                </div>
                <div class="landing-mock-hero">
                  <div>
                    <strong>Dobrý den, Tomáši</strong>
                    <p>Máte 3 vozidla, 1 blížící se STK, 2 aktivní připomínky a 1 nové upozornění od servisu.</p>
                  </div>
                  <span class="landing-mock-ok">${icon('check')} Vozidla pod kontrolou</span>
                  <span class="landing-car-visual"></span>
                </div>
                <div class="landing-mock-stats">
                  <span>${icon('calendar')}<b>STK / SME</b><small>za 18 dní</small></span>
                  <span>${icon('shield')}<b>Pojištění</b><small>v pořádku</small></span>
                  <span>${icon('wrench')}<b>Servis</b><small>před 2 měsíci</small></span>
                  <span>${icon('document')}<b>Dokumenty</b><small>čekají na doplnění</small></span>
                </div>
                <div class="landing-mock-vehicles">
                  <article><span class="vehicle-img v1"></span><b>Volkswagen Transporter</b><small>5M2 1254</small><em>V pořádku</em></article>
                  <article><span class="vehicle-img v2"></span><b>Škoda Kodiaq</b><small>4AB 5678</small><em>Blíží se STK</em></article>
                  <article><span class="vehicle-img v3"></span><b>BMW 320d xDrive</b><small>7AZ 9876</small><em>V pořádku</em></article>
                  <article class="add-car">${icon('plus')} Přidat vozidlo</article>
                </div>
              </div>
            </div>
            <div class="landing-float-card float-1">${icon('calendar')}<span><b>STK za 18 dní</b><small>Škoda Kodiaq</small></span>${icon('chevron')}</div>
            <div class="landing-float-card float-2">${icon('wrench')}<span><b>Nový servisní záznam</b><small>Volkswagen T5.1</small></span>${icon('chevron')}</div>
            <div class="landing-float-card float-3">${icon('shield')}<span><b>Dokument ověřen</b><small>STK protokol</small></span>${icon('chevron')}</div>
            <div class="landing-float-card float-4">${icon('users')}<span><b>Sdíleno se servisem</b><small>AutoPoint Praha</small></span>${icon('chevron')}</div>
          </div>
        </section>

        <section class="landing-benefits" id="landing-features" aria-label="Základní funkce">
          ${benefitCard('garage', 'Digitální garáž', 'Evidence všech vozidel podle VIN, SPZ, fotek a technických údajů.', 'blue')}
          ${benefitCard('calendar', 'Servisní historie', 'Opravy, nájezdy, doklady a záznamy v jedné časové ose.', 'violet')}
          ${benefitCard('document', 'Dokumenty a faktury', 'Technické průkazy, pojistky, faktury, STK a PDF výpisy na jednom místě.', 'green')}
          ${benefitCard('users', 'Propojení se servisem', 'Bezpečně sdílejte vybraná vozidla se servisem a mějte přehled o práci.', 'orange')}
        </section>

        <section class="landing-audience" id="landing-pricing" aria-label="Pro majitele a autoservisy">
          <article class="landing-audience-card landing-audience-owner" id="landing-owners">
            <div>
              <h2>Pro majitele vozidel</h2>
              <ul>
                <li>${icon('check')} Správa osobních i firemních aut</li>
                <li>${icon('check')} STK, pojištění a připomínky pod kontrolou</li>
                <li>${icon('check')} Všechny dokumenty a náklady na jednom místě</li>
                <li>${icon('check')} Kompletní historie vozidla při prodeji</li>
              </ul>
              <button type="button" class="landing-btn landing-btn-light" onclick="publicLandingScrollTo('landing-how'); return false;">Zjistit více ${icon('chevron')}</button>
            </div>
            <div class="landing-owner-visual" aria-hidden="true">
              <span class="landing-owner-car"></span>
              <div class="landing-phone">
                <b>Moje vozidlo</b>
                <span>Volkswagen T5.1</span>
                <p>STK za 18 dní</p>
                <p>Pojištění v pořádku</p>
                <p>Faktura uložena</p>
              </div>
            </div>
          </article>

          <article class="landing-audience-card landing-audience-service" id="landing-services">
            <div>
              <h2>Pro autoservisy</h2>
              <ul>
                <li>${icon('check')} Přístup k povoleným vozidlům</li>
                <li>${icon('check')} Servisní záznamy a dokumentace oprav</li>
                <li>${icon('check')} Zakázky, faktury a komunikace s klienty</li>
                <li>${icon('check')} Profesní nástroj, který šetří čas</li>
              </ul>
              <button type="button" class="landing-btn landing-btn-light" onclick="publicLandingScrollTo('landing-how'); return false;">Zjistit více ${icon('chevron')}</button>
            </div>
            <div class="landing-laptop" aria-hidden="true">
              <div class="landing-laptop-screen">
                <b>Servisní dashboard</b>
                <span></span><span></span><span></span>
                <p>Schválená vozidla</p>
              </div>
              <div class="landing-toolbox"></div>
            </div>
          </article>
        </section>

        <section class="landing-how" id="landing-how" aria-labelledby="landingHowTitle">
          <h2 id="landingHowTitle">Jak to funguje</h2>
          <div class="landing-steps">
            <article>
              <span class="landing-step-number">1</span>
              <span class="landing-step-icon">${icon('car')}</span>
              <h3>Přidejte vozidlo</h3>
              <p>Zadejte VIN nebo SPZ a vytvořte digitální kartu vozidla během pár vteřin.</p>
            </article>
            <span class="landing-step-arrow" aria-hidden="true">${icon('chevron')}</span>
            <article>
              <span class="landing-step-number">2</span>
              <span class="landing-step-icon">${icon('document')}</span>
              <h3>Doplňte historii</h3>
              <p>Přidejte servisní záznamy, dokumenty, fotky a připomínky.</p>
            </article>
            <span class="landing-step-arrow" aria-hidden="true">${icon('chevron')}</span>
            <article>
              <span class="landing-step-number">3</span>
              <span class="landing-step-icon">${icon('shield')}</span>
              <h3>Sdílejte bezpečně</h3>
              <p>Umožněte servisu přístup jen k vybraným vozidlům a údajům.</p>
            </article>
          </div>
        </section>

        <section class="landing-security" aria-label="Důvěra a bezpečnost">
          <article>${icon('shield')}<div><h3>Data máte pod kontrolou</h3><p>Vaše data jsou bezpečně uložená a nikdo k nim nemá přístup bez vašeho svolení.</p></div></article>
          <article>${icon('lock')}<div><h3>Servis vidí jen to, co mu povolíte</h3><p>Přidělte přístup ke konkrétním vozidlům a vybraným informacím.</p></div></article>
          <article>${icon('qr')}<div><h3>Veřejný výpis vozidla přes QR</h3><p>Sdílejte ověřenou historii vozidla jednoduše a bezpečně.</p></div></article>
          <article>${icon('check')}<div><h3>Připraveno pro transparentní historii</h3><p>Kompletní a důvěryhodná historie zvyšuje hodnotu vozidla.</p></div></article>
        </section>

        <section class="landing-bottom-cta" aria-labelledby="landingCtaTitle">
          <div class="landing-cta-car" aria-hidden="true"></div>
          <div>
            <h2 id="landingCtaTitle">Začněte si budovat digitální historii vozidla ještě dnes</h2>
            <p>Přidejte první vozidlo zdarma a mějte servis, dokumenty i termíny konečně na jednom místě.</p>
          </div>
          <div class="landing-bottom-actions">
            <button type="button" class="landing-btn landing-btn-white" onclick="publicLandingShowRegister(); return false;">Vytvořit účet zdarma ${icon('chevron')}</button>
            <button type="button" class="landing-btn landing-btn-outline-white" onclick="publicLandingShowLogin(); return false;">Přihlásit se</button>
          </div>
        </section>
      </main>

      <footer class="landing-footer">
        <div class="landing-footer-brand">${brand()}<p>Digitální správa vozidel pro majitele, firmy a autoservisy.</p></div>
        <nav aria-label="Footer">
          <a href="#landing-features" onclick="publicLandingScrollTo('landing-features'); return false;">Funkce</a>
          <a href="#landing-pricing" onclick="publicLandingScrollTo('landing-pricing'); return false;">Ceník</a>
          <a href="#landing-how" onclick="publicLandingScrollTo('landing-how'); return false;">Jak to funguje</a>
          <a href="#landing-owners" onclick="publicLandingScrollTo('landing-owners'); return false;">Pro majitele</a>
          <a href="#landing-services" onclick="publicLandingScrollTo('landing-services'); return false;">Pro servisy</a>
          <a href="#landing-features" onclick="publicLandingScrollTo('landing-features'); return false;">Podpora</a>
          <a href="#landing-features" onclick="publicLandingScrollTo('landing-features'); return false;">Kontakt</a>
        </nav>
        <span class="landing-copy">© 2026 Správa vozidel. Všechna práva vyhrazena.</span>
      </footer>
    `;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderLanding, { once: true });
  } else {
    renderLanding();
  }
})();
