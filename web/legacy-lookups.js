(() => {
      function norm(s){ return (s||"").toString().trim(); }
      function isVin(v){ v=norm(v).toUpperCase(); return /^[A-HJ-NPR-Z0-9]{17}$/.test(v); } // bez I,O,Q
      function isIco(v){ v=norm(v); return /^[0-9]{8}$/.test(v); }

      function getApiBaseUrl(){
        if (typeof window.getApiBaseUrl === "function") return window.getApiBaseUrl();
        return window.location.origin;
      }

      // Debug tracking - přidat request do debug panelu
      function trackDebugRequest(method, url, status, responseBody){
        if (typeof window.debugRequests === 'undefined') {
          window.debugRequests = [];
        }
        const requestInfo = {
          method: method,
          url: url,
          status: status,
          timestamp: new Date().toISOString(),
          responseBody: (responseBody || '').substring(0, 200)
        };
        window.debugRequests.unshift(requestInfo);
        if (window.debugRequests.length > 3) {
          window.debugRequests.pop();
        }
        // Aktualizovat debug panel pokud existuje
        if (typeof updateDebugPanel === 'function') {
          updateDebugPanel();
        }
      }

      // -------- VIN --------
      function vinInputs(){
        // Najít sekci "Přidat nové vozidlo"
        const allElements = Array.from(document.querySelectorAll('*'));
        const headerEl = allElements.find(el => {
          const text = (el.textContent || '').trim();
          return text === 'Přidat nové vozidlo' || text.startsWith('Přidat nové vozidlo');
        });

        if (!headerEl) {
          console.warn("[VIN] Sekce 'Přidat nové vozidlo' nenalezena");
          return { vinInput: null, nameInput: null, modelInput: null, yearInput: null, engineInput: null };
        }

        // Najít parent kontejner s formulářem (nejmenší parent s alespoň 6 inputy)
        let formContainer = headerEl.parentElement;
        while (formContainer && formContainer !== document.body) {
          const inputs = formContainer.querySelectorAll('input[type="text"], input[type="number"], textarea');
          if (inputs.length >= 6) {
            break;
          }
          formContainer = formContainer.parentElement;
        }

        if (!formContainer) {
          console.warn("[VIN] Formulář kontejner nenalezen");
          return { vinInput: null, nameInput: null, modelInput: null, yearInput: null, engineInput: null };
        }

        // Najít inputy podle pořadí
        const textInputs = Array.from(formContainer.querySelectorAll('input[type="text"]'));
        const numberInputs = Array.from(formContainer.querySelectorAll('input[type="number"]'));

        return {
          vinInput: textInputs[0] || null,      // první text input = VIN
          nameInput: textInputs[1] || null,     // druhý text input = Název
          spzInput: textInputs[2] || null,      // třetí text input = SPZ
          modelInput: textInputs[3] || null,    // čtvrtý text input = Model
          yearInput: numberInputs[0] || null,   // první number input = Rok
          engineInput: textInputs[4] || null    // pátý text input = Motor (nebo text input po yearInput)
        };
      }

      let vinAbort = null;
      async function lookupVin(vin){
        const base = getApiBaseUrl();
        const url = `${base}/api/v1/vin/${encodeURIComponent(vin)}`;

        if (vinAbort) vinAbort.abort();
        vinAbort = new AbortController();


        try {
          const res = await fetch(url, { method:"GET", headers:{Accept:"application/json"}, signal: vinAbort.signal });
          const text = await res.text();
          let data=null;
          try{ data=JSON.parse(text); }catch(e){}

          // Debug tracking
          trackDebugRequest('GET', url, res.status, text);


          if (!res.ok) throw new Error((data && data.detail) ? data.detail : text.slice(0,200));
          return data || {};
        } catch (error) {
          // Debug tracking i pro chyby
          trackDebugRequest('GET', url, 0, error.message);
          throw error;
        }
      }

      function fillVin(data){
        const { nameInput, modelInput, yearInput, engineInput } = vinInputs();
        const make   = data.make || data.brand || data.manufacturer || "";
        const model  = data.model || "";
        const year   = data.year || data.modelYear || "";
        const engine = data.engine || data.engineName || data.engineCode || "";

        if (nameInput && make && !nameInput.value.trim()) nameInput.value = make;
        if (modelInput && model) modelInput.value = model;
        if (yearInput && year) yearInput.value = year;
        if (engineInput && engine) engineInput.value = engine;

        [nameInput, modelInput, yearInput, engineInput].forEach(inp => {
          if (!inp) return;
          inp.dispatchEvent(new Event("input", { bubbles:true }));
          inp.dispatchEvent(new Event("change", { bubbles:true }));
        });


      }

      function attachVin(){
        const { vinInput } = vinInputs();
        if (!vinInput) {
          console.warn("[VIN] VIN input not found");
          return;
        }

        // Zkontrolovat, zda už není listener připojen
        if (vinInput.dataset.vinListenerAttached === 'true') {
          return;
        }
        vinInput.dataset.vinListenerAttached = 'true';



        let t=null;
        vinInput.addEventListener("input", () => {
          const vin = norm(vinInput.value).toUpperCase();
          if (t) clearTimeout(t);
          t = setTimeout(async () => {
            if (!isVin(vin)) return;
            try {
              fillVin(await lookupVin(vin));
            } catch(e){
              console.warn("[VIN] error:");
            }
          }, 500);
        });

        // Pokud už je VIN vyplněný, okamžitě zavolat lookup
        const existing = norm(vinInput.value).toUpperCase();
        if (isVin(existing)) {
          setTimeout(() => {

            vinInput.dispatchEvent(new Event("input",{bubbles:true}));
          }, 250);
        }
      }

      // -------- ARES / IČO --------
      function aresInputs(){
        // Najít sekci "Registrace"
        const allElements = Array.from(document.querySelectorAll('*'));
        const headerEl = allElements.find(el => {
          const text = (el.textContent || '').trim();
          return text === 'Registrace' || text.startsWith('Registrace');
        });

        if (!headerEl) {
          console.warn("[ARES] Sekce 'Registrace' nenalezena");
          return { icoInput: null, name: null, dic: null, street: null, house: null, city: null, zip: null };
        }

        // Najít parent kontejner s formulářem
        let formContainer = headerEl.parentElement;
        while (formContainer && formContainer !== document.body) {
          const inputs = formContainer.querySelectorAll('input[type="text"]');
          if (inputs.length >= 7) { // IČO + 6 dalších polí
            break;
          }
          formContainer = formContainer.parentElement;
        }

        if (!formContainer) {
          console.warn("[ARES] Formulář kontejner nenalezen");
          return { icoInput: null, name: null, dic: null, street: null, house: null, city: null, zip: null };
        }

        // Najít inputy podle pořadí
        const textInputs = Array.from(formContainer.querySelectorAll('input[type="text"]'));

        return {
          icoInput: textInputs[0] || null,      // první text input = IČO
          name: textInputs[1] || null,          // druhý text input = Název firmy
          dic: textInputs[2] || null,          // třetí text input = DIČ
          street: textInputs[3] || null,       // čtvrtý text input = Ulice
          house: textInputs[4] || null,        // pátý text input = Číslo popisné
          city: textInputs[5] || null,         // šestý text input = Město
          zip: textInputs[6] || null           // sedmý text input = PSČ
        };
      }

      let aresAbort=null;
      async function lookupAres(ico){
        const base = getApiBaseUrl();
        const url = `${base}/api/v1/ares/${encodeURIComponent(ico)}`;
        if (aresAbort) aresAbort.abort();
        aresAbort = new AbortController();


        try {
          const res = await fetch(url, { method:"GET", headers:{Accept:"application/json"}, signal: aresAbort.signal });
          const text = await res.text();
          let data=null;
          try{ data=JSON.parse(text); }catch(e){}

          // Debug tracking
          trackDebugRequest('GET', url, res.status, text);


          if (!res.ok) throw new Error((data && data.detail) ? data.detail : text.slice(0,200));
          return data || {};
        } catch (error) {
          // Debug tracking i pro chyby
          trackDebugRequest('GET', url, 0, error.message);
          throw error;
        }
      }

      function fillAres(data){
        const { name, dic, street, house, city, zip } = aresInputs();
        const company_name = data.company_name || data.name || "";
        const dicVal = data.dic || data.vat || "";
        const streetVal = data.street || "";
        const houseVal = data.house_number || data.house || "";
        const cityVal = data.city || "";
        const zipVal  = data.zip || data.postal_code || "";

        if (name && company_name) name.value = company_name;
        if (dic && dicVal) dic.value = dicVal;
        if (street && streetVal) street.value = streetVal;
        if (house && houseVal) house.value = houseVal;
        if (city && cityVal) city.value = cityVal;
        if (zip && zipVal) zip.value = zipVal;

        [name,dic,street,house,city,zip].forEach(inp=>{
          if(!inp) return;
          inp.dispatchEvent(new Event("input",{bubbles:true}));
          inp.dispatchEvent(new Event("change",{bubbles:true}));
        });


      }

      function attachAres(){
        const { icoInput } = aresInputs();
        if (!icoInput) {
          console.warn("[ARES] IČO input not found");
          return;
        }

        // Zkontrolovat, zda už není listener připojen
        if (icoInput.dataset.aresListenerAttached === 'true') {
          return;
        }
        icoInput.dataset.aresListenerAttached = 'true';



        let t=null;
        icoInput.addEventListener("input", () => {
          const ico = norm(icoInput.value);
          if (t) clearTimeout(t);
          t = setTimeout(async () => {
            if (!isIco(ico)) return;
            try {
              fillAres(await lookupAres(ico));
            } catch(e){
              console.warn("[ARES] error:");
            }
          }, 500);
        });
      }

      // Připojit listenery při DOMContentLoaded
      document.addEventListener("DOMContentLoaded", () => {
        attachVin();
        attachAres();
      });

      // Připojit listenery i když se formuláře zobrazí později (MutationObserver)
      const observer = new MutationObserver((mutations) => {
        // Zkusit připojit listenery při každé změně DOM
        attachVin();
        attachAres();
      });

      // Spustit observer po DOMContentLoaded
      document.addEventListener("DOMContentLoaded", () => {
        observer.observe(document.body, { childList: true, subtree: true });
        // Také zkusit připojit okamžitě
        setTimeout(() => {
          attachVin();
          attachAres();
        }, 100);
      });
    })();
