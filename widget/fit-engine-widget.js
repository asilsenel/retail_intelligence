/**
 * Beymen AI Personal Shopper - Floating Widget
 *
 * Self-contained overlay widget (Intercom-style).
 * Paste this script on any page to enable the AI assistant.
 *
 * v8.0 - Stepped flow: search → select → size → combo (skip option) → cart
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

    // =========================================================================
    // GLOBAL STATE
    // =========================================================================

    let isOpen = false;
    let isExpanded = false;
    let messages = [];
    let currentActiveProductId = null;
    let userHeight = null;
    let userWeight = null;
    let productsCache = {};
    let cardCounter = 0;
    let selectedProducts = {};
    let cardProductMap = {};
    let pickedComboCategories = {};   // productId → Set of already-picked combo categories
    let userShoeSize = null;          // e.g. "43"
    let pendingShoeCombo = null;      // { productId, targetCategory } — waiting for shoe size input
    let comboParentProductId = null;  // tracks which product started the combo flow

    // =========================================================================
    // STYLES
    // =========================================================================

    const STYLES = `
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;500;600&family=Inter:wght@300;400;500;600&display=swap');

        /* ---- FAB ---- */
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

        /* ---- Window ---- */
        #beymen-widget-window {
            position: fixed;
            bottom: 100px;
            right: 24px;
            width: 380px;
            height: 580px;
            background: #FFFFFF;
            border-radius: 16px;
            box-shadow: 0 12px 48px rgba(0,0,0,0.2);
            display: flex;
            flex-direction: column;
            z-index: 999999;
            opacity: 0;
            visibility: hidden;
            transform: translateY(16px) scale(0.96);
            transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
            overflow: hidden;
        }

        #beymen-widget-window.open {
            opacity: 1;
            visibility: visible;
            transform: translateY(0) scale(1);
        }

        #beymen-widget-window.expanded {
            width: 680px;
            height: 85vh;
            bottom: 40px;
        }

        @media (max-width: 420px) {
            #beymen-widget-window {
                width: calc(100vw - 16px);
                right: 8px;
                left: 8px;
                bottom: 80px;
                height: 80vh;
                border-radius: 12px;
            }
        }

        /* ---- Header ---- */
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

        .bw-header-text { flex: 1; }

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

        .bw-header-actions { display: flex; gap: 8px; }

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

        .bw-header-btn:hover { background: rgba(255,255,255,0.2); }
        .bw-header-btn svg { width: 16px; height: 16px; fill: #FFFFFF; }

        /* ---- Body ---- */
        .bw-body {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
            background: #F5F5F5;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .bw-body::-webkit-scrollbar { width: 4px; }
        .bw-body::-webkit-scrollbar-thumb { background: #CCC; border-radius: 2px; }

        /* ---- Messages ---- */
        .bw-msg {
            display: flex;
            gap: 10px;
            animation: bwMsgIn 0.3s ease;
        }

        @keyframes bwMsgIn {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .bw-msg.user { flex-direction: row-reverse; }

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

        .bw-msg.user .bw-msg-avatar { background: #DDD; }
        .bw-msg-avatar svg { width: 14px; height: 14px; fill: #FFF; }
        .bw-msg.user .bw-msg-avatar svg { fill: #666; }

        .bw-bubble {
            max-width: 270px;
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

        /* ---- Image Preview ---- */
        .bw-image-preview {
            max-width: 200px;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }

        .bw-image-preview img {
            width: 100%;
            height: auto;
            display: block;
        }

        /* ---- Product Card ---- */
        .bw-card {
            background: #FFFFFF;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 1px 8px rgba(0,0,0,0.06);
            max-width: 280px;
            border: 1px solid rgba(0,0,0,0.04);
            transition: box-shadow 0.3s ease, transform 0.3s ease;
        }

        .bw-card:hover {
            box-shadow: 0 8px 24px rgba(0,0,0,0.12);
            transform: translateY(-2px);
        }

        .bw-card-img-wrap {
            overflow: hidden;
            position: relative;
        }

        .bw-card-img {
            width: 100%;
            height: 180px;
            object-fit: cover;
            display: block;
            transition: transform 0.5s cubic-bezier(0.25, 0.1, 0.25, 1);
        }

        .bw-card:hover .bw-card-img {
            transform: scale(1.03);
        }

        .bw-card-body { padding: 14px; }

        .bw-card-brand {
            font-family: 'Inter', sans-serif;
            font-size: 9px;
            font-weight: 600;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            color: #888;
            margin-bottom: 6px;
        }

        .bw-card-name {
            font-family: 'Playfair Display', serif;
            font-size: 14px;
            font-weight: 500;
            color: #000;
            margin-bottom: 8px;
            line-height: 1.4;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        .bw-card-price {
            font-family: 'Inter', sans-serif;
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

        /* ---- Size Result Inline (compact text) ---- */
        .bw-card-size-inline {
            font-family: 'Inter', sans-serif;
            font-size: 12px;
            color: #4ade80;
            font-weight: 500;
            margin-bottom: 8px;
        }

        @keyframes bwFadeIn {
            from { opacity: 0; transform: scale(0.95); }
            to { opacity: 1; transform: scale(1); }
        }

        /* ---- Step Prompt (size / combo question) ---- */
        .bw-step-prompt {
            background: #FFFFFF;
            border-radius: 12px;
            padding: 16px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.06);
            max-width: 280px;
            border: 1px solid rgba(0,0,0,0.06);
            animation: bwSlideUp 0.3s ease;
        }

        .bw-step-prompt-title {
            font-family: 'Playfair Display', serif;
            font-size: 13px;
            font-weight: 500;
            color: #000;
            margin-bottom: 10px;
        }

        .bw-step-prompt-actions {
            display: flex;
            gap: 8px;
        }

        .bw-step-prompt-actions .bw-btn {
            flex: 1;
        }

        .bw-step-prompt-categories {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }

        .bw-combo-cat-btn {
            width: auto !important;
            padding: 8px 14px !important;
            font-size: 11px !important;
        }

        /* ---- Buttons ---- */
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

        .bw-btn-primary { background: #000; color: #FFF; }
        .bw-btn-primary:hover { background: #222; }
        .bw-btn-primary:disabled { background: #999; cursor: not-allowed; }
        .bw-btn-primary.active { background: #1a1a1a; }

        .bw-btn-secondary { background: #F0F0F0; color: #333; }
        .bw-btn-secondary:hover { background: #E5E5E5; }
        .bw-btn-secondary.active { background: #E0E0E0; }

        .bw-btn-select { background: #F0F0F0; color: #333; }
        .bw-btn-select:hover { background: #E5E5E5; }
        .bw-btn-select.selected { background: #000; color: #FFF; }

        .bw-btn svg.bw-icon {
            width: 14px;
            height: 14px;
            flex-shrink: 0;
        }

        /* ---- Skeleton Loader ---- */
        .bw-combo-skeleton {
            display: flex;
            gap: 12px;
            padding: 12px;
            animation: bwPulse 1.5s infinite;
        }

        .bw-combo-skeleton-img {
            width: 72px;
            height: 72px;
            background: #EBEBEB;
            border-radius: 8px;
            flex-shrink: 0;
        }

        .bw-combo-skeleton-lines {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 8px;
            justify-content: center;
        }

        .bw-combo-skeleton-line {
            height: 10px;
            background: #EBEBEB;
            border-radius: 4px;
        }

        .bw-combo-skeleton-line:first-child { width: 80%; }
        .bw-combo-skeleton-line:nth-child(2) { width: 50%; }

        @keyframes bwPulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
        }

        /* ---- Typing ---- */
        .bw-typing { display: flex; gap: 4px; padding: 4px 0; }

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

        /* ---- Footer ---- */
        .bw-footer {
            padding: 12px 16px;
            background: #FFFFFF;
            border-top: 1px solid #E5E5E5;
        }

        .bw-input-wrap {
            display: flex;
            align-items: center;
            gap: 8px;
            background: #F5F5F5;
            border-radius: 24px;
            padding: 4px 4px 4px 6px;
        }

        .bw-upload-btn {
            width: 32px;
            height: 32px;
            background: transparent;
            border: none;
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background 0.2s;
        }

        .bw-upload-btn:hover { background: rgba(0,0,0,0.05); }
        .bw-upload-btn svg { width: 18px; height: 18px; fill: #666; }

        .bw-input {
            flex: 1;
            border: none;
            background: none;
            font-family: 'Inter', sans-serif;
            font-size: 13px;
            color: #1a1a1a;
            outline: none;
            min-width: 0;
        }

        .bw-input::placeholder { color: #999; }

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
            flex-shrink: 0;
        }

        .bw-send:hover { background: #222; }
        .bw-send svg { width: 16px; height: 16px; fill: #FFF; }

        #bw-file-input { display: none; }

        /* ---- Selection Summary ---- */
        .bw-selection-summary {
            background: #FFFFFF;
            border-radius: 12px;
            padding: 16px;
            box-shadow: 0 2px 16px rgba(0,0,0,0.08);
            max-width: 280px;
            animation: bwSlideUp 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            border: 1px solid rgba(0,0,0,0.04);
        }

        @keyframes bwSlideUp {
            from { opacity: 0; transform: translateY(12px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .bw-selection-title {
            font-family: 'Playfair Display', serif;
            font-size: 13px;
            font-weight: 500;
            letter-spacing: 0.3px;
            color: #000;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid #F0F0F0;
        }

        .bw-selection-item {
            display: flex;
            gap: 10px;
            align-items: center;
            padding: 8px 0;
            border-bottom: 1px solid #F0F0F0;
        }

        .bw-selection-item:last-child { border-bottom: none; }

        .bw-selection-img {
            width: 44px;
            height: 44px;
            object-fit: cover;
            border-radius: 8px;
            flex-shrink: 0;
        }

        .bw-selection-info { flex: 1; }

        .bw-selection-name {
            font-family: 'Inter', sans-serif;
            font-size: 12px;
            font-weight: 500;
            color: #000;
            line-height: 1.3;
        }

        .bw-selection-meta {
            font-family: 'Inter', sans-serif;
            font-size: 11px;
            color: #888;
            margin-top: 2px;
        }

        .bw-selection-size {
            font-family: 'Inter', sans-serif;
            font-size: 11px;
            font-weight: 600;
            color: #4ade80;
        }

        .bw-selection-cart-btn {
            width: 100%;
            margin-top: 14px;
            padding: 13px 16px;
            font-family: 'Inter', sans-serif;
            font-size: 13px;
            font-weight: 600;
            letter-spacing: 0.5px;
            background: #000;
            color: #FFF;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            transition: background 0.2s, transform 0.15s;
        }

        .bw-selection-cart-btn:hover {
            background: #222;
        }

        .bw-selection-cart-btn:active {
            transform: scale(0.97);
        }

        .bw-selection-cart-btn svg.bw-icon {
            width: 16px;
            height: 16px;
            flex-shrink: 0;
        }

        /* (Action panel removed in v8.0 — flow uses step prompts instead) */

        /* ---- Cart Total ---- */
        .bw-cart-total {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 12px;
            padding-top: 12px;
            border-top: 2px solid #000;
        }

        .bw-cart-total-label {
            font-family: 'Inter', sans-serif;
            font-size: 13px;
            font-weight: 500;
            color: #666;
        }

        .bw-cart-total-value {
            font-family: 'Playfair Display', serif;
            font-size: 18px;
            font-weight: 600;
            color: #000;
        }

        /* ---- Expand button responsive ---- */
        @media (max-width: 420px) {
            #beymen-widget-window.expanded {
                width: calc(100vw - 16px);
                height: 90vh;
            }
        }

        /* ---- Mobile Responsive ---- */
        @media (max-width: 420px) {
            .bw-card { max-width: 100%; }
            .bw-card-img { height: 140px; }
            .bw-combo-img { width: 56px; height: 56px; }
            .bw-selection-summary { max-width: 100%; }
            .bw-action-panel { flex-direction: column; }
        }
    `;

    // =========================================================================
    // SVG ICONS
    // =========================================================================

    const ICONS = {
        heart: '<svg class="bw-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>',
        heartFill: '<svg class="bw-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>',
        ruler: '<svg class="bw-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 2.5l-18 18M7 2.5H2.5V7M17 22.5h4.5V18M2.5 12l4-4M12 2.5l-4 4M22.5 12l-4 4M12 22.5l4-4"/></svg>',
        sparkle: '<svg class="bw-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L14.5 9.5L22 12L14.5 14.5L12 22L9.5 14.5L2 12L9.5 9.5L12 2Z"/></svg>',
        check: '<svg class="bw-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
        cart: '<svg class="bw-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>',
        expand: '<svg class="bw-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>',
        collapse: '<svg class="bw-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" y1="10" x2="21" y2="3"/><line x1="3" y1="21" x2="10" y2="14"/></svg>',
    };

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
        // FAB
        const fab = document.createElement('button');
        fab.id = 'beymen-widget-fab';
        fab.innerHTML = `<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z"/><path d="M7 9h2v2H7zm4 0h2v2h-2zm4 0h2v2h-2z"/></svg>`;
        fab.onclick = toggleChat;
        document.body.appendChild(fab);

        // Window
        const win = document.createElement('div');
        win.id = 'beymen-widget-window';
        win.innerHTML = `
            <div class="bw-header">
                <div class="bw-avatar">
                    <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>
                </div>
                <div class="bw-header-text">
                    <div class="bw-header-title">Beymen AI Stylist</div>
                    <div class="bw-header-status">Online</div>
                </div>
                <div class="bw-header-actions">
                    <button class="bw-header-btn" id="bw-expand" title="Buyut/Kucult">
                        <svg viewBox="0 0 24 24"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
                    </button>
                    <button class="bw-header-btn" id="bw-reset" title="Yeni Sohbet">
                        <svg viewBox="0 0 24 24"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>
                    </button>
                </div>
            </div>
            <div class="bw-body" id="bw-messages"></div>
            <div class="bw-footer">
                <div class="bw-input-wrap">
                    <button class="bw-upload-btn" id="bw-upload-btn" title="Fotoraf Yukle">
                        <svg viewBox="0 0 24 24"><path d="M16.5 6v11.5c0 2.21-1.79 4-4 4s-4-1.79-4-4V5c0-1.38 1.12-2.5 2.5-2.5s2.5 1.12 2.5 2.5v10.5c0 .55-.45 1-1 1s-1-.45-1-1V6H10v9.5c0 1.38 1.12 2.5 2.5 2.5s2.5-1.12 2.5-2.5V5c0-2.21-1.79-4-4-4S7 2.79 7 5v12.5c0 3.04 2.46 5.5 5.5 5.5s5.5-2.46 5.5-5.5V6h-1.5z"/></svg>
                    </button>
                    <input type="file" id="bw-file-input" accept="image/jpeg,image/png,image/webp">
                    <input type="text" class="bw-input" id="bw-input" placeholder="Mesajinizi yazin...">
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
        document.getElementById('bw-expand').onclick = toggleExpand;
        document.getElementById('bw-upload-btn').onclick = () => {
            document.getElementById('bw-file-input').click();
        };
        document.getElementById('bw-file-input').onchange = handleFileUpload;
    }

    // =========================================================================
    // CHAT CORE
    // =========================================================================

    function toggleChat() {
        isOpen = !isOpen;
        const fab = document.getElementById('beymen-widget-fab');
        const win = document.getElementById('beymen-widget-window');

        fab.classList.toggle('open', isOpen);
        win.classList.toggle('open', isOpen);

        fab.innerHTML = isOpen
            ? `<svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>`
            : `<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z"/><path d="M7 9h2v2H7zm4 0h2v2h-2zm4 0h2v2h-2z"/></svg>`;

        if (isOpen && messages.length === 0) {
            setTimeout(() => addBotMessage("Beymen'e hos geldiniz!\n\nSize nasil yardimci olabilirim?\n\n<em>\"Siyah palto ariyorum\" yazabilir\nveya bir fotograf yukleyebilirsiniz.</em>"), 400);
        }

        if (isOpen) setTimeout(() => document.getElementById('bw-input')?.focus(), 300);
    }

    function toggleExpand() {
        isExpanded = !isExpanded;
        const win = document.getElementById('beymen-widget-window');
        const expandBtn = document.getElementById('bw-expand');
        win.classList.toggle('expanded', isExpanded);
        if (expandBtn) {
            expandBtn.innerHTML = isExpanded
                ? '<svg viewBox="0 0 24 24"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" y1="10" x2="21" y2="3"/><line x1="3" y1="21" x2="10" y2="14"/></svg>'
                : '<svg viewBox="0 0 24 24"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>';
        }
    }

    function resetChat() {
        messages = [];
        currentActiveProductId = null;
        userHeight = null;
        userWeight = null;
        productsCache = {};
        cardCounter = 0;
        selectedProducts = {};
        cardProductMap = {};
        pickedComboCategories = {};
        userShoeSize = null;
        pendingShoeCombo = null;
        comboParentProductId = null;
        isExpanded = false;
        document.getElementById('beymen-widget-window')?.classList.remove('expanded');

        document.getElementById('bw-messages').innerHTML = '';
        setTimeout(() => addBotMessage("Beymen'e hos geldiniz!\n\nSize nasil yardimci olabilirim?\n\n<em>\"Siyah palto ariyorum\" yazabilir\nveya bir fotograf yukleyebilirsiniz.</em>"), 300);
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

        msg.innerHTML = isCard
            ? `<div class="bw-msg-avatar"><svg viewBox="0 0 24 24">${avatarSvg}</svg></div>${content}`
            : `<div class="bw-msg-avatar"><svg viewBox="0 0 24 24">${avatarSvg}</svg></div><div class="bw-bubble">${content}</div>`;

        container.appendChild(msg);
        container.scrollTop = container.scrollHeight;
        messages.push({ content, isUser });
    }

    function addImagePreview(imageUrl) {
        const container = document.getElementById('bw-messages');
        const msg = document.createElement('div');
        msg.className = 'bw-msg user';
        msg.innerHTML = `
            <div class="bw-msg-avatar"><svg viewBox="0 0 24 24"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg></div>
            <div class="bw-image-preview"><img src="${imageUrl}" alt="Uploaded"></div>
        `;
        container.appendChild(msg);
        container.scrollTop = container.scrollHeight;
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

    function parseShoeSize(text) {
        const match = text.trim().match(/^(\d{2})$/);
        if (match) {
            const num = parseInt(match[1]);
            if (num >= 36 && num <= 48) return String(num);
        }
        return null;
    }

    function processInput(text) {
        // Check if we're waiting for shoe size (combo flow)
        if (pendingShoeCombo) {
            const shoeSize = parseShoeSize(text);
            if (shoeSize) {
                userShoeSize = shoeSize;
                addBotMessage(`Ayakkabi numaraniz: <strong>${shoeSize}</strong>`);
                const { productId, targetCategory } = pendingShoeCombo;
                pendingShoeCombo = null;
                completeLookByCategory(productId, targetCategory);
                return;
            }
            // If not a valid shoe size, show hint
            addBotMessage('Lutfen gecerli bir ayakkabi numarasi girin (36-48).\n\n<em>Orn: "43"</em>');
            return;
        }

        // Check if we're waiting for shoe size (direct shoe selection)
        if (currentActiveProductId) {
            const activeProduct = productsCache[currentActiveProductId];
            if (_isShoeProduct(activeProduct)) {
                const shoeSize = parseShoeSize(text);
                if (shoeSize) {
                    userShoeSize = shoeSize;
                    addBotMessage(`Ayakkabi numaraniz: <strong>${shoeSize}</strong>`);
                    const pid = currentActiveProductId;
                    const comboTarget = comboParentProductId || pid;
                    const selData = selectedProducts[pid];
                    const cid = selData ? selData.cardId : null;
                    currentActiveProductId = null;
                    autoSizeForCard(pid, cid).then(() => {
                        showSelections();
                        promptComboStep(comboTarget);
                    });
                    return;
                }
                // If not a valid shoe size, show hint
                addBotMessage('Lutfen gecerli bir ayakkabi numarasi girin (36-48).\n\n<em>Orn: "43"</em>');
                return;
            }
        }

        const measurements = parseMeasurements(text);

        if (measurements) {
            userHeight = measurements.height;
            userWeight = measurements.weight;

            addBotMessage(`${userHeight}cm / ${userWeight}kg kaydedildi. Bedeninizi hesapliyorum...`);

            if (currentActiveProductId) {
                // Size step for the selected product → then combo step
                const pid = currentActiveProductId;
                const comboTarget = comboParentProductId || pid;
                const selData = selectedProducts[pid];
                const cid = selData ? selData.cardId : null;
                currentActiveProductId = null;
                autoSizeForCard(pid, cid).then(() => {
                    showSelections();
                    promptComboStep(comboTarget);
                });
            } else {
                // No specific product — size all visible cards
                autoSizeAllVisibleCards();
            }
            return;
        }

        callChatAPI(text);
    }

    function parseMeasurements(text) {
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

                let height = num1 > 100 ? num1 : num2;
                let weight = num1 > 100 ? num2 : num1;

                if (height >= 140 && height <= 220 && weight >= 35 && weight <= 180) {
                    return { height, weight };
                }
            }
        }
        return null;
    }

    function formatPrice(price) {
        if (!price && price !== 0) return '';
        return new Intl.NumberFormat('tr-TR', {
            style: 'currency',
            currency: 'TRY',
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
        }).format(price);
    }

    // =========================================================================
    // FILE UPLOAD
    // =========================================================================

    async function handleFileUpload(e) {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (ev) => addImagePreview(ev.target.result);
        reader.readAsDataURL(file);

        e.target.value = '';

        showTyping();
        addBotMessage("Fotografi analiz ediyorum...");

        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch(`${CONFIG.apiUrl}/api/v1/analyze-image`, {
                method: 'POST',
                headers: { 'X-API-Key': CONFIG.apiKey },
                body: formData
            });

            hideTyping();
            if (!response.ok) throw new Error('Upload failed');

            const data = await response.json();
            handleChatResponse(data);

        } catch (error) {
            hideTyping();
            addBotMessage("Fotograf yuklenirken bir sorun olustu. Lutfen tekrar deneyin.");
            console.error('Upload error:', error);
        }
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
            if (!response.ok) throw new Error('API Error');

            const data = await response.json();
            handleChatResponse(data);

        } catch (error) {
            hideTyping();
            addBotMessage("Uzgunum, bir sorun olustu. Lutfen tekrar deneyin.");
            console.error('Chat API Error:', error);
        }
    }

    function handleChatResponse(data) {
        if (data.message) addBotMessage(data.message);

        const products = data.products && data.products.length > 0
            ? data.products
            : (data.main_product ? [data.main_product] : []);

        if (products.length === 0) return;

        // Cache all products
        products.forEach(p => { productsCache[p.id] = p; });

        // Render each product card WITHOUT combos (combos come on-demand)
        products.forEach((product, idx) => {
            setTimeout(() => {
                const cardHtml = buildProductCard(product);
                addBotMessage(cardHtml, true);
            }, 400 + idx * 300);
        });
    }

    // =========================================================================
    // PRODUCT CARD BUILDER
    // =========================================================================

    function buildProductCard(main) {
        const cardId = `card-${++cardCounter}`;
        cardProductMap[cardId] = main.id;
        const brandText = main.brand || 'Beymen';
        const priceText = main.price || (main.price_raw ? formatPrice(main.price_raw) : '');
        const mainUrl = main.url || '#';

        // Check if size is already known (for combo cards rendered after size step)
        const sizeText = main._recommendedSize
            ? `<div class="bw-card-size-inline">Beden: <strong>${main._recommendedSize}</strong></div>`
            : '';

        let html = `
            <div class="bw-card" id="${cardId}">
                <a href="${mainUrl}" target="_blank" rel="noopener" style="text-decoration:none;color:inherit">
                    <div class="bw-card-img-wrap">
                        <img src="${main.image_url}" alt="${main.name}" class="bw-card-img"
                             onerror="this.style.background='#f0f0f0';this.alt='Gorsel yuklenemedi'">
                    </div>
                </a>
                <div class="bw-card-body">
                    <div class="bw-card-brand">${brandText}</div>
                    <div class="bw-card-name">${main.name}</div>
                    ${priceText ? `<div class="bw-card-price">${priceText}</div>` : ''}
                    ${sizeText}
                    <div class="bw-card-actions">
                        <button class="bw-btn bw-btn-select" id="sel-${cardId}" onclick="BeymenAI.selectProduct('${main.id}', '${cardId}')">
                            ${ICONS.heart} Sec
                        </button>
                    </div>
                </div>
            </div>`;

        return html;
    }

    // =========================================================================
    // SIZE CHECK
    // =========================================================================

    function _isShoeProduct(product) {
        if (!product) return false;
        const cat = (product.category || '').toLowerCase();
        const name = (product.name || '').toLowerCase();
        const shoeKeywords = ['ayakkabı', 'ayakkabi', 'loafer', 'sneaker', 'bot', 'oxford', 'derby', 'monk'];
        return shoeKeywords.some(k => cat.includes(k) || name.includes(k));
    }

    async function autoSizeForCard(productId, cardId) {
        try {
            const product = productsCache[productId];

            // For shoe products, use the user's stated shoe size directly
            if (_isShoeProduct(product) && userShoeSize) {
                const syntheticData = {
                    recommended_size: userShoeSize,
                    confidence_score: 99,
                    fit_description: 'User-provided shoe size',
                    fit_description_tr: 'Kullanicinin belirttigi ayakkabi numarasi',
                    size_breakdown: [],
                    alternative_size: null,
                    notes: null
                };
                displaySizeResult(syntheticData, cardId, productId, true);
                return;
            }

            const response = await fetch(`${CONFIG.apiUrl}/api/v1/recommend`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-API-Key': CONFIG.apiKey },
                body: JSON.stringify({
                    product_id: productId,
                    user_height: userHeight,
                    user_weight: userWeight,
                    body_shape: 'average',
                    preferred_fit: 'true_to_size'
                })
            });
            if (!response.ok) return;
            const data = await response.json();
            displaySizeResult(data, cardId, productId, true);
        } catch (e) {
            console.error('Auto size error:', e);
        }
    }

    function autoSizeAllVisibleCards() {
        Object.entries(cardProductMap).forEach(([cardId, productId]) => {
            const product = productsCache[productId];
            if (product && !product._recommendedSize) {
                autoSizeForCard(productId, cardId);
            }
        });
    }

    function triggerSizeCheck(productId, cardId) {
        // Legacy — kept for backward compat but flow now goes through selectProduct
        currentActiveProductId = productId;
        if (userHeight && userWeight) {
            autoSizeForCard(productId, cardId);
        } else {
            const product = productsCache[productId];
            addBotMessage(`<strong>${product?.name || 'Bu urun'}</strong> icin boy ve kilonuzu yazar misiniz?\n\n<em>Orn: "180 80"</em>`);
            document.getElementById('bw-input')?.focus();
        }
    }

    function displaySizeResult(data, cardId, productId, silent = false) {
        const size = data.recommended_size;
        const confidence = data.confidence_score;

        // Update cache
        if (productsCache[productId]) {
            productsCache[productId]._recommendedSize = size;
            productsCache[productId]._confidence = confidence;
        }

        // Update select button text to show size
        const selBtn = document.getElementById(`sel-${cardId}`);
        if (selBtn && selectedProducts[productId]) {
            selBtn.innerHTML = `${ICONS.heartFill} ${size} Beden`;
        }

        if (!silent) {
            const product = productsCache[productId];
            let msg = `<strong>${product?.name || 'Bu urun'}</strong> icin onerilen beden: <strong>${size}</strong>`;
            if (confidence) {
                msg += ` (%${confidence} uyum)`;
            }
            if (data.alternative_size) {
                msg += `. Alternatif: <strong>${data.alternative_size}</strong>`;
            }
            addBotMessage(msg);
        }
    }

    // =========================================================================
    // PRODUCT SELECTION
    // =========================================================================

    function selectProduct(productId, cardId) {
        const btn = document.getElementById(`sel-${cardId}`);
        if (selectedProducts[productId]) {
            // Deselect
            delete selectedProducts[productId];
            if (btn) {
                btn.classList.remove('selected');
                btn.innerHTML = `${ICONS.heart} Sec`;
            }
        } else {
            // Select
            const product = productsCache[productId];
            if (product) {
                selectedProducts[productId] = { product, cardId };
                if (btn) {
                    btn.classList.add('selected');
                    btn.innerHTML = `${ICONS.heartFill} Secildi`;
                }

                // Determine which product to show combo prompt for
                // If user selects a combo suggestion card, continue the parent's combo flow
                const comboPromptTarget = comboParentProductId || productId;

                // Step 2: Ask for size
                const isShoe = _isShoeProduct(product);

                if (product._recommendedSize) {
                    // Size already known — go straight to combo step
                    showSelections();
                    promptComboStep(comboPromptTarget);
                } else if (isShoe && userShoeSize) {
                    // Shoe with known shoe size — apply directly
                    autoSizeForCard(productId, cardId).then(() => {
                        showSelections();
                        promptComboStep(comboPromptTarget);
                    });
                } else if (isShoe && !userShoeSize) {
                    // Shoe but no shoe size — ask for it
                    currentActiveProductId = productId;
                    pendingShoeCombo = null; // not a combo request, just direct shoe selection
                    showSelections();
                    addBotMessage(`<strong>${product.name}</strong> secildi! Ayakkabi numaranizi yazar misiniz?\n\n<em>Orn: "43" veya "42"</em>`);
                    document.getElementById('bw-input')?.focus();
                } else if (userHeight && userWeight) {
                    // Measurements known but not calculated yet
                    addBotMessage(`Bedeninizi hesapliyorum...`);
                    autoSizeForCard(productId, cardId).then(() => {
                        showSelections();
                        promptComboStep(comboPromptTarget);
                    });
                } else {
                    // Need measurements — prompt user
                    currentActiveProductId = productId;
                    showSelections();
                    addBotMessage(`<strong>${product.name}</strong> secildi! Beden onerebilmem icin boy ve kilonuzu yazar misiniz?\n\n<em>Orn: "180 80" veya "Boyum 180, kilom 80"</em>`);
                    document.getElementById('bw-input')?.focus();
                }
                return; // showSelections already called above
            }
        }
        showSelections();
    }

    // Category display labels (Turkish)
    const _CATEGORY_LABELS = {
        'pantolon': 'Pantolon',
        'gömlek': 'Gomlek',
        'gomlek': 'Gomlek',
        'kazak': 'Kazak',
        'ayakkabı': 'Ayakkabi',
        'ayakkabi': 'Ayakkabi',
        'ceket': 'Ceket',
        'blazer': 'Blazer',
        'palto': 'Palto',
        'mont': 'Mont',
        'kaban': 'Kaban',
        'parka': 'Parka',
        'yelek': 'Yelek',
        'pardösü': 'Pardosu',
        'takım': 'Takim Elbise',
        'takim': 'Takim Elbise',
        'tişört': 'Tisort',
    };

    async function promptComboStep(productId) {
        const product = productsCache[productId];
        if (!product) return;

        // Initialize picked set for this product
        if (!pickedComboCategories[productId]) {
            pickedComboCategories[productId] = new Set();
        }

        // Fetch combo categories from backend
        try {
            const response = await fetch(
                `${CONFIG.apiUrl}/api/v1/products/${productId}/combos?limit=0`,
                { headers: { 'X-API-Key': CONFIG.apiKey } }
            );
            if (!response.ok) return;
            const data = await response.json();

            const allCats = data.combo_categories || [];
            const picked = pickedComboCategories[productId];
            const remaining = allCats.filter(c => !picked.has(c));

            if (remaining.length === 0) {
                addBotMessage('Tum kombin kategorileri tamamlandi!');
                showSelections();
                return;
            }

            // Build category buttons
            let buttonsHtml = remaining.map(cat => {
                const label = _CATEGORY_LABELS[cat] || cat.charAt(0).toUpperCase() + cat.slice(1);
                return `<button class="bw-btn bw-btn-primary bw-combo-cat-btn" onclick="BeymenAI.completeLookByCategory('${productId}', '${cat}')">${label}</button>`;
            }).join('');

            const html = `
                <div class="bw-step-prompt">
                    <div class="bw-step-prompt-title">Gorunumu tamamlamak icin bir kategori secin:</div>
                    <div class="bw-step-prompt-categories">
                        ${buttonsHtml}
                        <button class="bw-btn bw-btn-secondary" onclick="BeymenAI.skipCombo()">
                            ${ICONS.cart} Sepeti Goster
                        </button>
                    </div>
                </div>`;
            addBotMessage(html, true);

        } catch (e) {
            console.error('Combo categories error:', e);
            showSelections();
        }
    }

    function skipCombo() {
        showSelections();
    }

    function showSelections() {
        // Remove old summary
        document.getElementById('bw-selection-summary')?.closest('.bw-msg')?.remove();

        const ids = Object.keys(selectedProducts);
        if (ids.length === 0) return;

        let totalPrice = 0;
        let html = `<div class="bw-selection-summary" id="bw-selection-summary">
            <div class="bw-selection-title">Secimlerim (${ids.length})</div>`;

        ids.forEach(id => {
            const { product } = selectedProducts[id];
            const size = product._recommendedSize;
            const sizeText = size ? `Beden: ${size}` : '';
            const rawPrice = product.price_raw || 0;
            totalPrice += rawPrice;
            const priceText = product.price || (rawPrice ? formatPrice(rawPrice) : '');

            html += `
                <div class="bw-selection-item">
                    <img src="${product.image_url}" alt="" class="bw-selection-img">
                    <div class="bw-selection-info">
                        <div class="bw-selection-name">${product.brand || 'Beymen'} - ${product.name}</div>
                        <div class="bw-selection-meta">
                            ${priceText ? `${priceText}` : ''}
                            ${sizeText && priceText ? ' &middot; ' : ''}
                            ${sizeText ? `<span class="bw-selection-size">${sizeText}</span>` : ''}
                        </div>
                    </div>
                </div>`;
        });

        if (totalPrice > 0) {
            html += `
                <div class="bw-cart-total">
                    <span class="bw-cart-total-label">Toplam</span>
                    <span class="bw-cart-total-value">${formatPrice(totalPrice)}</span>
                </div>`;
        }

        html += `
            <button class="bw-selection-cart-btn" onclick="BeymenAI.addToCart()">
                ${ICONS.cart} Sepete Ekle (${ids.length})
            </button>
        </div>`;
        addBotMessage(html, true);
    }

    // =========================================================================
    // ADD TO CART
    // =========================================================================

    async function addToCart() {
        const ids = Object.keys(selectedProducts);
        if (ids.length === 0) return;

        const items = ids.map(id => {
            const { product } = selectedProducts[id];
            return {
                product_id: id,
                size: product._recommendedSize || null,
                quantity: 1,
            };
        });

        try {
            const response = await fetch(`${CONFIG.apiUrl}/api/v1/cart`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': CONFIG.apiKey
                },
                body: JSON.stringify({ items })
            });

            if (!response.ok) throw new Error('Cart API Error');

            const data = await response.json();
            addBotMessage(`<strong>${data.added_count || items.length} urun</strong> sepete eklendi.`);
        } catch (error) {
            console.error('Cart error:', error);
            addBotMessage(`<strong>${items.length} urun</strong> sepete eklendi.`);
        }
    }

    function addSingleToCart(productId) {
        const product = productsCache[productId];
        if (!product) return;
        if (!selectedProducts[productId]) {
            selectedProducts[productId] = { product, cardId: null };
        }
        addBotMessage(`<strong>${product.brand || 'Beymen'} ${product.name}</strong> sepete eklendi.`);
        showSelections();
    }

    async function completeLookByCategory(productId, targetCategory) {
        const product = productsCache[productId];
        if (!product) return;

        // Remember which product started the combo flow
        comboParentProductId = productId;

        // Track this category as picked
        if (!pickedComboCategories[productId]) {
            pickedComboCategories[productId] = new Set();
        }
        pickedComboCategories[productId].add(targetCategory);

        const catLabel = _CATEGORY_LABELS[targetCategory] || targetCategory;

        // Check if shoe category — ask shoe size if not known
        const isShoeCategory = ['ayakkabı', 'ayakkabi', 'loafer'].includes(targetCategory.toLowerCase());
        if (isShoeCategory && !userShoeSize) {
            // Store pending combo request and ask for shoe size
            pendingShoeCombo = { productId, targetCategory };
            addBotMessage(`Ayakkabi numaranizi yazar misiniz?\n\n<em>Orn: "43" veya "42"</em>`);
            document.getElementById('bw-input')?.focus();
            return;
        }

        addBotMessage(`<strong>${catLabel}</strong> onerileri araniyor...`);

        try {
            const response = await fetch(
                `${CONFIG.apiUrl}/api/v1/products/${productId}/combos?limit=3&target_category=${encodeURIComponent(targetCategory)}`,
                { headers: { 'X-API-Key': CONFIG.apiKey } }
            );
            if (!response.ok) {
                addBotMessage('Kombin onerileri yuklenemedi.');
                return;
            }
            const data = await response.json();

            if (data.combos && data.combos.length > 0) {
                data.combos.forEach(c => { productsCache[c.id] = c; });
                addBotMessage(`Iste <strong>${catLabel}</strong> onerileri:`);
                data.combos.forEach((combo, idx) => {
                    setTimeout(() => {
                        const comboCardHtml = buildProductCard(combo);
                        addBotMessage(comboCardHtml, true);
                    }, 300 + idx * 250);
                });
                // Do NOT auto-prompt next combo here — wait for user to select a card
            } else {
                addBotMessage(`Bu urun icin <strong>${catLabel}</strong> onerisi bulunamadi.`);
                // Show remaining categories only when nothing found
                promptComboStep(productId);
            }
        } catch (e) {
            console.error('Complete look error:', e);
            addBotMessage('Kombin onerileri yuklenemedi.');
        }
    }

    // Legacy wrapper — kept for backward compat
    async function completeLook(productId, cardId) {
        promptComboStep(productId);
    }

    function goToCart() {
        showSelections();
        // Scroll to selection summary
        setTimeout(() => {
            const summary = document.getElementById('bw-selection-summary');
            if (summary) {
                summary.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }, 300);
    }

    async function comboFromCombo(productId, comboCardId) {
        // This is now just an alias for completeLook
        await completeLook(productId, comboCardId);
    }

    // =========================================================================
    // INIT
    // =========================================================================

    function init(options = {}) {
        Object.assign(CONFIG, options);
        injectStyles();
        createWidget();
        console.log('Beymen AI Shopper v8.0 initialized');
    }

    window.BeymenAI = {
        init,
        toggle: toggleChat,
        reset: resetChat,
        triggerSizeCheck,
        selectProduct,
        completeLook,
        completeLookByCategory,
        comboFromCombo,
        skipCombo,
        addToCart,
        addSingleToCart,
        goToCart
    };

})(window, document);
