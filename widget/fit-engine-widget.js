/**
 * Beymen AI Personal Shopper - Floating Widget
 * 
 * Self-contained overlay widget (Intercom-style).
 * Paste this script on any page to enable the AI assistant.
 * 
 * v4.0 - Accordion Combo, Smart Size Flow, Reset Chat
 */

(function (window, document) {
    'use strict';

    // =========================================================================
    // CONFIGURATION
    // =========================================================================

    const CONFIG = {
        apiUrl: 'http://localhost:8000',
        apiKey: 'test-api-key'
    };

    // State
    let isOpen = false;
    let messages = [];
    let currentProductId = null;
    let userHeight = null;
    let userWeight = null;
    let productsCache = {}; // Store product details by ID

    // =========================================================================
    // STYLES (Injected via JS)
    // =========================================================================

    const STYLES = `
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;500;600&family=Inter:wght@300;400;500;600&display=swap');
        
        #beymen-widget-fab {
            position: fixed;
            bottom: 24px;
            right: 24px;
            width: 60px;
            height: 60px;
            background: #000000;
            border: none;
            border-radius: 50%;
            cursor: pointer;
            box-shadow: 0 4px 24px rgba(0,0,0,0.3);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 999998;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        #beymen-widget-fab:hover {
            transform: scale(1.05);
            box-shadow: 0 6px 32px rgba(0,0,0,0.4);
        }
        
        #beymen-widget-fab svg {
            width: 26px;
            height: 26px;
            fill: #FFFFFF;
            transition: transform 0.3s;
        }
        
        #beymen-widget-fab.open svg {
            transform: rotate(45deg);
        }
        
        #beymen-widget-window {
            position: fixed;
            bottom: 100px;
            right: 24px;
            width: 380px;
            height: 560px;
            background: #FFFFFF;
            border-radius: 16px;
            box-shadow: 0 12px 48px rgba(0,0,0,0.2);
            display: flex;
            flex-direction: column;
            z-index: 999999;
            opacity: 0;
            visibility: hidden;
            transform: translateY(16px) scale(0.96);
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            overflow: hidden;
        }
        
        #beymen-widget-window.open {
            opacity: 1;
            visibility: visible;
            transform: translateY(0) scale(1);
        }
        
        @media (max-width: 420px) {
            #beymen-widget-window {
                width: calc(100vw - 24px);
                right: 12px;
                left: 12px;
                height: 75vh;
            }
        }
        
        /* Header */
        .bw-header {
            background: #000000;
            padding: 14px 16px;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .bw-avatar {
            width: 36px;
            height: 36px;
            background: #FFFFFF;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }
        
        .bw-avatar svg {
            width: 20px;
            height: 20px;
            fill: #000000;
        }
        
        .bw-header-text {
            flex: 1;
        }
        
        .bw-header-title {
            font-family: 'Playfair Display', serif;
            font-size: 15px;
            font-weight: 500;
            color: #FFFFFF;
        }
        
        .bw-header-status {
            font-family: 'Inter', sans-serif;
            font-size: 11px;
            color: rgba(255,255,255,0.6);
        }
        
        .bw-header-actions {
            display: flex;
            gap: 8px;
        }
        
        .bw-header-btn {
            width: 32px;
            height: 32px;
            background: rgba(255,255,255,0.1);
            border: none;
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background 0.2s;
        }
        
        .bw-header-btn:hover {
            background: rgba(255,255,255,0.2);
        }
        
        .bw-header-btn svg {
            width: 16px;
            height: 16px;
            fill: #FFFFFF;
        }
        
        /* Body */
        .bw-body {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
            background: #F5F5F5;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        
        .bw-body::-webkit-scrollbar {
            width: 4px;
        }
        
        .bw-body::-webkit-scrollbar-thumb {
            background: #CCC;
            border-radius: 2px;
        }
        
        /* Messages */
        .bw-msg {
            display: flex;
            gap: 10px;
            animation: bwMsgIn 0.3s ease;
        }
        
        @keyframes bwMsgIn {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .bw-msg.user {
            flex-direction: row-reverse;
        }
        
        .bw-msg-avatar {
            width: 28px;
            height: 28px;
            border-radius: 50%;
            background: #000;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }
        
        .bw-msg.user .bw-msg-avatar {
            background: #DDD;
        }
        
        .bw-msg-avatar svg {
            width: 14px;
            height: 14px;
            fill: #FFF;
        }
        
        .bw-msg.user .bw-msg-avatar svg {
            fill: #666;
        }
        
        .bw-bubble {
            max-width: 260px;
            padding: 12px 14px;
            background: #FFFFFF;
            border-radius: 14px;
            border-top-left-radius: 4px;
            font-family: 'Inter', sans-serif;
            font-size: 13px;
            line-height: 1.5;
            color: #1a1a1a;
            box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        }
        
        .bw-msg.user .bw-bubble {
            background: #000000;
            color: #FFFFFF;
            border-radius: 14px;
            border-top-right-radius: 4px;
        }
        
        /* Product Card */
        .bw-card {
            background: #FFFFFF;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 2px 12px rgba(0,0,0,0.08);
            max-width: 280px;
        }
        
        .bw-card-img {
            width: 100%;
            height: 160px;
            object-fit: cover;
        }
        
        .bw-card-body {
            padding: 14px;
        }
        
        .bw-card-brand {
            font-size: 9px;
            font-weight: 600;
            letter-spacing: 1px;
            text-transform: uppercase;
            color: #999;
            margin-bottom: 4px;
        }
        
        .bw-card-name {
            font-family: 'Playfair Display', serif;
            font-size: 15px;
            font-weight: 500;
            color: #000;
            margin-bottom: 6px;
            line-height: 1.3;
        }
        
        .bw-card-price {
            font-size: 14px;
            font-weight: 600;
            color: #000;
            margin-bottom: 12px;
        }
        
        .bw-card-actions {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        
        .bw-btn {
            width: 100%;
            padding: 11px 14px;
            font-family: 'Inter', sans-serif;
            font-size: 12px;
            font-weight: 500;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }
        
        .bw-btn-primary {
            background: #000;
            color: #FFF;
        }
        
        .bw-btn-primary:hover {
            background: #222;
        }
        
        .bw-btn-secondary {
            background: #F0F0F0;
            color: #333;
        }
        
        .bw-btn-secondary:hover {
            background: #E5E5E5;
        }
        
        .bw-btn-secondary.active {
            background: #E0E0E0;
        }
        
        /* Combo Accordion */
        .bw-combo-container {
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.35s ease, padding 0.35s ease;
            background: #F8F8F8;
            margin: 0 -14px -14px;
            padding: 0 14px;
        }
        
        .bw-combo-container.open {
            max-height: 300px;
            padding: 14px;
            border-top: 1px solid #E5E5E5;
        }
        
        .bw-combo-label {
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            color: #666;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        
        .bw-combo-card {
            display: flex;
            gap: 12px;
            background: #FFF;
            border-radius: 8px;
            padding: 10px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.05);
        }
        
        .bw-combo-img {
            width: 70px;
            height: 70px;
            object-fit: cover;
            border-radius: 6px;
            flex-shrink: 0;
        }
        
        .bw-combo-info {
            flex: 1;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        
        .bw-combo-name {
            font-size: 12px;
            font-weight: 500;
            color: #000;
            margin-bottom: 4px;
            line-height: 1.3;
        }
        
        .bw-combo-price {
            font-size: 11px;
            font-weight: 600;
            color: #000;
            margin-bottom: 8px;
        }
        
        .bw-combo-btn {
            padding: 6px 10px;
            font-size: 10px;
            font-weight: 500;
            background: #000;
            color: #FFF;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            align-self: flex-start;
        }
        
        .bw-combo-btn:hover {
            background: #222;
        }
        
        /* Size Result */
        .bw-size-result {
            background: linear-gradient(135deg, #000 0%, #1a1a1a 100%);
            color: #FFF;
            padding: 20px;
            border-radius: 12px;
            text-align: center;
            max-width: 220px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.2);
        }
        
        .bw-size-result-label {
            font-size: 10px;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            opacity: 0.7;
            margin-bottom: 6px;
        }
        
        .bw-size-result-size {
            font-family: 'Playfair Display', serif;
            font-size: 48px;
            font-weight: 600;
            margin-bottom: 6px;
        }
        
        .bw-size-result-conf {
            font-size: 13px;
            opacity: 0.9;
        }
        
        .bw-size-result-conf.high { color: #4ade80; }
        .bw-size-result-conf.medium { color: #fbbf24; }
        .bw-size-result-conf.low { color: #f87171; }
        
        /* Typing */
        .bw-typing {
            display: flex;
            gap: 4px;
            padding: 4px 0;
        }
        
        .bw-typing-dot {
            width: 6px;
            height: 6px;
            background: #999;
            border-radius: 50%;
            animation: bwTyping 1.2s ease-in-out infinite;
        }
        
        .bw-typing-dot:nth-child(2) { animation-delay: 0.15s; }
        .bw-typing-dot:nth-child(3) { animation-delay: 0.3s; }
        
        @keyframes bwTyping {
            0%, 60%, 100% { transform: translateY(0); }
            30% { transform: translateY(-5px); }
        }
        
        /* Footer */
        .bw-footer {
            padding: 12px 16px;
            background: #FFFFFF;
            border-top: 1px solid #E5E5E5;
        }
        
        .bw-input-wrap {
            display: flex;
            align-items: center;
            gap: 10px;
            background: #F5F5F5;
            border-radius: 24px;
            padding: 4px 4px 4px 16px;
        }
        
        .bw-input {
            flex: 1;
            border: none;
            background: none;
            font-family: 'Inter', sans-serif;
            font-size: 13px;
            color: #1a1a1a;
            outline: none;
        }
        
        .bw-input::placeholder {
            color: #999;
        }
        
        .bw-send {
            width: 36px;
            height: 36px;
            background: #000;
            border: none;
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background 0.2s;
        }
        
        .bw-send:hover {
            background: #222;
        }
        
        .bw-send svg {
            width: 16px;
            height: 16px;
            fill: #FFF;
        }
    `;

    // =========================================================================
    // WIDGET CREATION
    // =========================================================================

    function injectStyles() {
        if (document.getElementById('beymen-widget-styles')) return;
        const style = document.createElement('style');
        style.id = 'beymen-widget-styles';
        style.textContent = STYLES;
        document.head.appendChild(style);
    }

    function createWidget() {
        // FAB Button
        const fab = document.createElement('button');
        fab.id = 'beymen-widget-fab';
        fab.innerHTML = `
            <svg viewBox="0 0 24 24">
                <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z"/>
                <path d="M7 9h2v2H7zm4 0h2v2h-2zm4 0h2v2h-2z"/>
            </svg>
        `;
        fab.onclick = toggleChat;
        document.body.appendChild(fab);

        // Chat Window
        const win = document.createElement('div');
        win.id = 'beymen-widget-window';
        win.innerHTML = `
            <div class="bw-header">
                <div class="bw-avatar">
                    <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>
                </div>
                <div class="bw-header-text">
                    <div class="bw-header-title">Beymen AI Stylist</div>
                    <div class="bw-header-status">Çevrimiçi</div>
                </div>
                <div class="bw-header-actions">
                    <button class="bw-header-btn" id="bw-reset" title="Yeni Sohbet">
                        <svg viewBox="0 0 24 24"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>
                    </button>
                </div>
            </div>
            <div class="bw-body" id="bw-messages"></div>
            <div class="bw-footer">
                <div class="bw-input-wrap">
                    <input type="text" class="bw-input" id="bw-input" placeholder="Mesajınızı yazın...">
                    <button class="bw-send" id="bw-send">
                        <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
                    </button>
                </div>
            </div>
        `;
        document.body.appendChild(win);

        // Events
        document.getElementById('bw-send').onclick = sendMessage;
        document.getElementById('bw-input').onkeypress = (e) => {
            if (e.key === 'Enter') sendMessage();
        };
        document.getElementById('bw-reset').onclick = resetChat;
    }

    // =========================================================================
    // CHAT LOGIC
    // =========================================================================

    function toggleChat() {
        isOpen = !isOpen;
        const fab = document.getElementById('beymen-widget-fab');
        const win = document.getElementById('beymen-widget-window');

        fab.classList.toggle('open', isOpen);
        win.classList.toggle('open', isOpen);

        // Update FAB icon
        fab.innerHTML = isOpen
            ? `<svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>`
            : `<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z"/><path d="M7 9h2v2H7zm4 0h2v2h-2zm4 0h2v2h-2z"/></svg>`;

        // Greeting
        if (isOpen && messages.length === 0) {
            setTimeout(() => addBotMessage("Beymen'e hoş geldiniz. Bugün size nasıl yardımcı olabilirim?\n\n<em>(Örn: \"Gömlek arıyorum\", \"Ceket var mı?\", \"Kombin öner\")</em>"), 400);
        }

        if (isOpen) {
            setTimeout(() => document.getElementById('bw-input')?.focus(), 300);
        }
    }

    function resetChat() {
        // Clear state
        messages = [];
        currentProductId = null;
        userHeight = null;
        userWeight = null;
        productsCache = {};

        // Clear UI
        const container = document.getElementById('bw-messages');
        container.innerHTML = '';

        // Show greeting
        setTimeout(() => addBotMessage("Beymen'e hoş geldiniz. Bugün size nasıl yardımcı olabilirim?\n\n<em>(Örn: \"Gömlek arıyorum\", \"Ceket var mı?\", \"Kombin öner\")</em>"), 300);
    }

    function addBotMessage(html, isCard = false) {
        addMessage(html, false, isCard);
    }

    function addUserMessage(text) {
        addMessage(text, true);
    }

    function addMessage(content, isUser, isCard = false) {
        const container = document.getElementById('bw-messages');
        const msg = document.createElement('div');
        msg.className = `bw-msg ${isUser ? 'user' : 'bot'}`;

        const avatarSvg = isUser
            ? '<path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>'
            : '<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>';

        if (isCard) {
            msg.innerHTML = `
                <div class="bw-msg-avatar"><svg viewBox="0 0 24 24">${avatarSvg}</svg></div>
                ${content}
            `;
        } else {
            msg.innerHTML = `
                <div class="bw-msg-avatar"><svg viewBox="0 0 24 24">${avatarSvg}</svg></div>
                <div class="bw-bubble">${content}</div>
            `;
        }

        container.appendChild(msg);
        container.scrollTop = container.scrollHeight;
        messages.push({ content, isUser });
    }

    function showTyping() {
        const container = document.getElementById('bw-messages');
        const typing = document.createElement('div');
        typing.className = 'bw-msg bot';
        typing.id = 'bw-typing';
        typing.innerHTML = `
            <div class="bw-msg-avatar"><svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg></div>
            <div class="bw-bubble"><div class="bw-typing"><div class="bw-typing-dot"></div><div class="bw-typing-dot"></div><div class="bw-typing-dot"></div></div></div>
        `;
        container.appendChild(typing);
        container.scrollTop = container.scrollHeight;
    }

    function hideTyping() {
        document.getElementById('bw-typing')?.remove();
    }

    // =========================================================================
    // MESSAGE PROCESSING
    // =========================================================================

    function sendMessage() {
        const input = document.getElementById('bw-input');
        const text = input.value.trim();
        if (!text) return;

        addUserMessage(text);
        input.value = '';

        processInput(text);
    }

    function processInput(text) {
        // Check for measurements in text
        const measurements = parseMeasurements(text);

        if (measurements) {
            userHeight = measurements.height;
            userWeight = measurements.weight;

            // If we have a pending product, calculate size
            if (currentProductId) {
                addBotMessage(`Boy: ${userHeight}cm, Kilo: ${userWeight}kg olarak kaydettim. Hesaplıyorum...`);
                getSizeRecommendation(currentProductId);
            } else {
                addBotMessage(`Ölçülerinizi kaydettim (${userHeight}cm / ${userWeight}kg). Şimdi bir ürün seçin, bedeninizi hemen hesaplayalım!`);
            }
            return;
        }

        // Send to Chat API
        callChatAPI(text);
    }

    function parseMeasurements(text) {
        // Match patterns like "180 80", "180cm 80kg", "boyum 180 kilom 80"
        const patterns = [
            /(\d{2,3})\s*(?:cm)?\s+(\d{2,3})\s*(?:kg)?/i,
            /boy[um]*\s*[:\s]*(\d{2,3}).*?kilo[m]*\s*[:\s]*(\d{2,3})/i,
            /(\d{2,3})\s*[\/\-,]\s*(\d{2,3})/
        ];

        for (const pattern of patterns) {
            const match = text.match(pattern);
            if (match) {
                let num1 = parseInt(match[1]);
                let num2 = parseInt(match[2]);

                // Determine which is height and which is weight
                let height, weight;
                if (num1 > 100 && num1 <= 220) {
                    height = num1;
                    weight = num2;
                } else if (num2 > 100 && num2 <= 220) {
                    height = num2;
                    weight = num1;
                } else {
                    // Assume larger is height
                    height = Math.max(num1, num2);
                    weight = Math.min(num1, num2);
                }

                if (height >= 140 && height <= 220 && weight >= 35 && weight <= 180) {
                    return { height, weight };
                }
            }
        }
        return null;
    }

    // =========================================================================
    // API CALLS
    // =========================================================================

    async function callChatAPI(message) {
        showTyping();

        try {
            const response = await fetch(`${CONFIG.apiUrl}/api/v1/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': CONFIG.apiKey
                },
                body: JSON.stringify({ message })
            });

            hideTyping();

            if (!response.ok) {
                throw new Error('API Error');
            }

            const data = await response.json();
            handleChatResponse(data);

        } catch (error) {
            hideTyping();
            addBotMessage("Üzgünüm, şu anda bir sorun yaşıyorum. Lütfen tekrar deneyin.");
            console.error('Chat API Error:', error);
        }
    }

    function handleChatResponse(data) {
        // Add text message
        if (data.message) {
            addBotMessage(data.message);
        }

        // If we have products, show the card
        if (data.main_product) {
            const main = data.main_product;
            const combo = data.combo_product;

            // Cache products
            productsCache[main.id] = main;
            if (combo) productsCache[combo.id] = combo;

            setTimeout(() => {
                const cardHtml = buildProductCard(main, combo);
                addBotMessage(cardHtml, true);
            }, 400);
        }
    }

    function buildProductCard(main, combo) {
        let html = `
            <div class="bw-card">
                <img src="${main.image_url}" alt="${main.name}" class="bw-card-img">
                <div class="bw-card-body">
                    <div class="bw-card-brand">${main.brand}</div>
                    <div class="bw-card-name">${main.name}</div>
                    <div class="bw-card-price">${main.price}</div>
                    <div class="bw-card-actions">
                        <button class="bw-btn bw-btn-primary" onclick="BeymenAI.triggerSizeCheck('${main.id}')">
                            📏 Bedenimi Bul
                        </button>
        `;

        if (combo) {
            html += `
                        <button class="bw-btn bw-btn-secondary" onclick="BeymenAI.toggleCombo('${main.id}')">
                            ✨ Kombini Gör
                        </button>
                    </div>
                    <div class="bw-combo-container" id="combo-${main.id}">
                        <div class="bw-combo-label">✨ Kombin Önerisi</div>
                        <div class="bw-combo-card">
                            <img src="${combo.image_url}" alt="${combo.name}" class="bw-combo-img">
                            <div class="bw-combo-info">
                                <div class="bw-combo-name">${combo.name}</div>
                                <div class="bw-combo-price">${combo.price}</div>
                                <button class="bw-combo-btn" onclick="BeymenAI.triggerSizeCheck('${combo.id}')">📏 Bedenini Bul</button>
                            </div>
                        </div>
                    </div>
            `;
        } else {
            html += `</div>`;
        }

        html += `
                </div>
            </div>
        `;

        return html;
    }

    // =========================================================================
    // SIZE CHECK FLOW
    // =========================================================================

    function triggerSizeCheck(productId) {
        currentProductId = productId;
        const product = productsCache[productId];
        const productName = product ? product.name : 'bu ürün';

        if (userHeight && userWeight) {
            // We have measurements, calculate directly
            addBotMessage(`<strong>${productName}</strong> için bedeninizi hesaplıyorum...`);
            getSizeRecommendation(productId);
        } else {
            // Ask for measurements
            addBotMessage(`<strong>${productName}</strong> için beden hesaplayabilmem için boy ve kilonuzu yazar mısınız?\n\n<em>Örn: "180 80" veya "Boyum 180, kilom 80"</em>`);
            document.getElementById('bw-input')?.focus();
        }
    }

    function toggleCombo(productId) {
        const container = document.getElementById(`combo-${productId}`);
        if (container) {
            container.classList.toggle('open');

            // Update button state
            const buttons = document.querySelectorAll('.bw-btn-secondary');
            buttons.forEach(btn => {
                if (btn.onclick.toString().includes(productId)) {
                    btn.classList.toggle('active', container.classList.contains('open'));
                }
            });
        }
    }

    async function getSizeRecommendation(productId) {
        showTyping();

        try {
            const response = await fetch(`${CONFIG.apiUrl}/api/v1/recommend`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': CONFIG.apiKey
                },
                body: JSON.stringify({
                    product_id: productId,
                    user_height: userHeight,
                    user_weight: userWeight,
                    body_shape: 'average',
                    preferred_fit: 'true_to_size'
                })
            });

            hideTyping();

            if (!response.ok) throw new Error('API Error');

            const data = await response.json();
            displaySizeResult(data);

        } catch (error) {
            hideTyping();
            addBotMessage("Üzgünüm, şu anda beden hesaplayamıyorum. Lütfen tekrar deneyin.");
            console.error('Size API Error:', error);
        }
    }

    function displaySizeResult(data) {
        const size = data.recommended_size;
        const confidence = data.confidence_score;

        let confClass = 'high';
        if (confidence < 80) confClass = 'medium';
        if (confidence < 60) confClass = 'low';

        const resultHtml = `
            <div class="bw-size-result">
                <div class="bw-size-result-label">Önerilen Beden</div>
                <div class="bw-size-result-size">${size}</div>
                <div class="bw-size-result-conf ${confClass}">%${confidence} Uyum</div>
            </div>
        `;

        addBotMessage(resultHtml, true);

        setTimeout(() => {
            let note = data.fit_description_tr || data.fit_description || 'Bu beden size uygun görünüyor.';
            if (data.alternative_size) {
                note += `\n\nAlternatif: <strong>${data.alternative_size}</strong> beden de deneyebilirsiniz.`;
            }
            addBotMessage(note);
        }, 500);

        setTimeout(() => {
            addBotMessage("Başka bir ürün veya sorunuz var mı?");
        }, 1000);
    }

    // =========================================================================
    // INITIALIZATION
    // =========================================================================

    function init(options = {}) {
        Object.assign(CONFIG, options);
        injectStyles();
        createWidget();
        console.log('Beymen AI Shopper v4.0 initialized');
    }

    // Expose globally
    window.BeymenAI = {
        init,
        toggle: toggleChat,
        reset: resetChat,
        triggerSizeCheck,
        toggleCombo
    };

})(window, document);
