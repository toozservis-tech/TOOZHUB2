(function() {
    // Vytvoření HTML struktury pro widget
    const widgetHTML = `
        <div id="support-widget-container" style="position: fixed; bottom: 20px; right: 20px; z-index: 9999; font-family: sans-serif;">
            <!-- Tlačítko pro otevření -->
            <button id="support-widget-button" style="width: 60px; height: 60px; border-radius: 50%; background-color: var(--color-primary, #2563eb); color: white; border: none; box-shadow: 0 4px 12px rgba(0,0,0,0.15); cursor: pointer; display: flex; align-items: center; justify-content: center; transition: transform 0.2s;">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path>
                </svg>
            </button>

            <!-- Okno chatu -->
            <div id="support-widget-window" style="display: none; position: absolute; bottom: 80px; right: 0; width: 350px; max-width: calc(100vw - 40px); background: white; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.15); overflow: hidden; border: 1px solid var(--color-border, #e2e8f0); flex-direction: column;">
                <!-- Hlavička -->
                <div style="background-color: var(--color-primary, #2563eb); color: white; padding: 16px; display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h3 style="margin: 0; font-size: 16px; font-weight: 600;">Podpora</h3>
                        <p id="support-widget-status" style="margin: 4px 0 0 0; font-size: 12px; opacity: 0.9; display: flex; align-items: center; gap: 6px;">
                            <span id="support-widget-status-dot" style="width: 8px; height: 8px; border-radius: 50%; background-color: #cbd5e1;"></span>
                            <span id="support-widget-status-text">Načítání...</span>
                        </p>
                    </div>
                    <button id="support-widget-close" style="background: none; border: none; color: white; cursor: pointer; padding: 4px;">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <line x1="18" y1="6" x2="6" y2="18"></line>
                            <line x1="6" y1="6" x2="18" y2="18"></line>
                        </svg>
                    </button>
                </div>

                <!-- Tělo -->
                <div id="support-widget-body" style="padding: 16px; height: 300px; overflow-y: auto; background: #f8fafc; display: flex; flex-direction: column; gap: 12px;">
                </div>

                <!-- Formulář -->
                <div style="padding: 16px; background: white; border-top: 1px solid var(--color-border, #e2e8f0);">
                    <textarea id="support-widget-input" placeholder="Napište zprávu..." style="width: 100%; height: 60px; padding: 8px; border: 1px solid #cbd5e1; border-radius: 6px; resize: none; font-family: inherit; font-size: 14px; margin-bottom: 8px; outline: none;"></textarea>
                    <button id="support-widget-submit" style="width: 100%; padding: 10px; background-color: var(--color-primary, #2563eb); color: white; border: none; border-radius: 6px; font-weight: 500; cursor: pointer; transition: background-color 0.2s;">
                        Odeslat zprávu
                    </button>
                </div>
            </div>
        </div>
    `;

    // Přidání do DOM
    document.body.insertAdjacentHTML('beforeend', widgetHTML);

    // Elementy
    const button = document.getElementById('support-widget-button');
    const chatWindow = document.getElementById('support-widget-window');
    const closeBtn = document.getElementById('support-widget-close');
    const submitBtn = document.getElementById('support-widget-submit');
    const inputField = document.getElementById('support-widget-input');
    const chatBody = document.getElementById('support-widget-body');
    const statusDot = document.getElementById('support-widget-status-dot');
    const statusText = document.getElementById('support-widget-status-text');

    let ws = null;
    let isAdminOnline = false;
    let hasLoadedHistory = false;
    let isConnecting = false;

    function updateStatusUI() {
        if (isAdminOnline) {
            statusDot.style.backgroundColor = '#4ade80'; // green
            statusText.textContent = 'Admin je online';
        } else {
            statusDot.style.backgroundColor = '#cbd5e1'; // gray
            statusText.textContent = 'Admin je offline (odpovíme e-mailem)';
        }
    }

    function addMessageToChat(text, isUser = false, saveToDom = true) {
        const msgDiv = document.createElement('div');
        msgDiv.style.padding = '12px';
        msgDiv.style.borderRadius = '8px';
        msgDiv.style.fontSize = '14px';
        msgDiv.style.maxWidth = '85%';
        msgDiv.style.wordBreak = 'break-word';
        
        if (isUser) {
            msgDiv.style.background = 'var(--color-primary, #2563eb)';
            msgDiv.style.color = 'white';
            msgDiv.style.alignSelf = 'flex-end';
        } else {
            msgDiv.style.background = 'white';
            msgDiv.style.color = '#334155';
            msgDiv.style.border = '1px solid #e2e8f0';
            msgDiv.style.alignSelf = 'flex-start';
        }
        
        // Convert newlines to br
        msgDiv.innerHTML = text.replace(/\n/g, '<br>');
        
        if (saveToDom) {
            chatBody.appendChild(msgDiv);
            chatBody.scrollTop = chatBody.scrollHeight;
        }
        return msgDiv;
    }

    async function loadHistory(token) {
        try {
            const response = await fetch('/api/v1/support/history', {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            if (response.ok) {
                const messages = await response.json();
                chatBody.innerHTML = ''; // Clear
                if (messages.length === 0) {
                    addMessageToChat('Dobrý den! 👋\n\nJak vám můžeme pomoci?', false);
                } else {
                    messages.forEach(msg => {
                        addMessageToChat(msg.text, msg.sender_type === 'user');
                    });
                }
                hasLoadedHistory = true;
            }
        } catch (e) {
            console.error('Failed to load chat history', e);
        }
    }

    function connectWebSocket() {
        if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
        if (isConnecting) return;
        
        const token = localStorage.getItem('accessToken') || sessionStorage.getItem('accessToken');
        if (!token) {
            statusText.textContent = 'Nepřihlášen';
            return;
        }

        isConnecting = true;
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/v1/support/ws/user?token=${token}`;
        
        ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
            console.log('Support WebSocket connected');
            isConnecting = false;
            if (!hasLoadedHistory) {
                loadHistory(token);
            }
        };
        
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'admin_status') {
                    isAdminOnline = data.online;
                    updateStatusUI();
                } else if (data.type === 'message') {
                    if (data.sender_type === 'admin') {
                        addMessageToChat(data.text, false);
                    }
                }
            } catch (e) {
                console.error('Error parsing WS message', e);
            }
        };
        
        ws.onclose = () => {
            console.log('Support WebSocket disconnected');
            isConnecting = false;
            isAdminOnline = false;
            updateStatusUI();
            setTimeout(connectWebSocket, 5000); // Reconnect
        };
    }

    // Event listenery
    button.addEventListener('click', () => {
        chatWindow.style.display = chatWindow.style.display === 'none' ? 'flex' : 'none';
        if (chatWindow.style.display === 'flex') {
            inputField.focus();
            connectWebSocket();
        }
    });

    closeBtn.addEventListener('click', () => {
        chatWindow.style.display = 'none';
    });

    submitBtn.addEventListener('click', () => {
        const message = inputField.value.trim();
        if (!message) return;

        const token = localStorage.getItem('accessToken') || sessionStorage.getItem('accessToken');
        if (!token) {
            addMessageToChat('Pro odeslání zprávy musíte být přihlášeni.', false);
            return;
        }

        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: 'message',
                text: message
            }));
            addMessageToChat(message, true);
            inputField.value = '';
            inputField.focus();
        } else {
            // Fallback k REST API
            inputField.disabled = true;
            submitBtn.disabled = true;
            submitBtn.textContent = 'Odesílám...';

            addMessageToChat(message, true);
            inputField.value = '';

            fetch('/api/v1/support/message', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ message })
            }).then(response => {
                if (!response.ok) {
                    addMessageToChat('Zpráva odeslána e-mailem (offline režim).', false);
                }
            }).catch(() => {
                addMessageToChat('Chyba připojení. Zkuste to prosím později.', false);
            }).finally(() => {
                inputField.disabled = false;
                submitBtn.disabled = false;
                submitBtn.textContent = 'Odeslat zprávu';
                inputField.focus();
            });
        }
    });

    inputField.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submitBtn.click();
        }
    });

    // Zkusit se připojit, pokud jsme přihlášeni
    setTimeout(() => {
        const token = localStorage.getItem('accessToken') || sessionStorage.getItem('accessToken');
        if (token) {
            connectWebSocket();
        }
    }, 2000);
})();