from fastapi import FastAPI, File, UploadFile, Form, Request, Header
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from rembg import remove, new_session
import io
import os

# Load .env if exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from database import init_db
from license import can_use, record_usage, verify_license, create_license
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sk = os.getenv("STRIPE_SECRET_KEY", "NOT_FOUND")
print(f"DEBUG APP LOAD - SK: {sk[:10]}...")

# Initialize DB on startup
init_db()

# Pre-load default model
session = new_session("isnet-general-use")


@app.get("/", response_class=HTMLResponse)
async def main():
    return """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>ClearCut</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;600;700&display=swap" rel="stylesheet">
        <style>
            *, *::before, *::after {
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }

            body {
                font-family: 'Noto Sans JP', sans-serif;
                background: #f5f5f5;
                color: #3a3a3a;
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                align-items: center;
                padding: 30px 16px 60px;
            }

            h1 {
                font-size: 2.4rem;
                font-weight: 700;
                color: #2d2d2d;
                margin-bottom: 6px;
                letter-spacing: -0.5px;
            }

            .subtitle {
                font-size: 0.9rem;
                color: #6b6b6b;
                margin-bottom: 28px;
            }

            /* Upload Area */
            .upload-area {
                background: #f8fafc;
                border: 2px dashed #cbd5e1;
                border-radius: 16px;
                padding: 36px 40px;
                text-align: center;
                max-width: 500px;
                width: 100%;
                transition: border-color 0.3s, background 0.3s;
                cursor: pointer;
            }
            .upload-area:hover, .upload-area.drag-over {
                border-color: #2563eb;
                background: #eff6ff;
            }
            .upload-area input[type="file"] {
                display: none;
            }
            .upload-icon {
                font-size: 2.4rem;
                margin-bottom: 10px;
            }
            .upload-text {
                font-size: 0.95rem;
                color: #6b7280;
            }
            .upload-text strong {
                color: #2563eb;
            }

            /* Model selector */
            .model-selector {
                margin-top: 12px;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                font-size: 0.85rem;
                color: #6b7280;
            }
            .model-selector select {
                background: #f1f5f9;
                color: #1e293b;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 6px 12px;
                font-family: inherit;
                font-size: 0.85rem;
                cursor: pointer;
            }

            /* Buttons */
            .btn {
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 12px 28px;
                border: none;
                border-radius: 10px;
                font-size: 1rem;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.15s, box-shadow 0.3s, opacity 0.3s;
                font-family: inherit;
            }
            .btn:hover { transform: translateY(-2px); }
            .btn:active { transform: translateY(0); }
            .btn-primary {
                background: linear-gradient(135deg, #2563eb, #7c3aed);
                color: #fff;
                box-shadow: 0 4px 15px rgba(37,99,235,0.3);
            }
            .btn-primary:disabled {
                opacity: 0.5;
                cursor: not-allowed;
                transform: none;
            }
            .btn-download {
                background: linear-gradient(135deg, #059669, #10b981);
                color: #fff;
                box-shadow: 0 4px 15px rgba(16,185,129,0.3);
            }
            .btn-erase {
                background: linear-gradient(135deg, #ef4444, #f97316);
                color: #fff;
                box-shadow: 0 4px 15px rgba(239,68,68,0.25);
            }
            .btn-erase.active-mode {
                outline: 3px solid #ef4444;
                outline-offset: 2px;
            }
            .btn-restore {
                background: linear-gradient(135deg, #8b5cf6, #a855f7);
                color: #fff;
                box-shadow: 0 4px 15px rgba(139,92,246,0.25);
            }
            .btn-restore.active-mode {
                outline: 3px solid #8b5cf6;
                outline-offset: 2px;
            }
            .btn-secondary {
                background: #f1f5f9;
                color: #475569;
                border: 1px solid #e2e8f0;
            }
            .btn-secondary:hover {
                background: #e2e8f0;
            }

            .action-bar {
                margin-top: 20px;
                display: flex;
                gap: 12px;
                justify-content: center;
                flex-wrap: wrap;
            }

            /* Image container */
            .container {
                display: flex;
                gap: 30px;
                margin-top: 30px;
                width: 100%;
                max-width: 960px;
                flex-wrap: wrap;
                justify-content: center;
            }
            .box {
                flex: 1;
                min-width: 280px;
                max-width: 450px;
                background: #ffffff;
                border-radius: 16px;
                padding: 20px;
                border: 1px solid #e2e8f0;
                box-shadow: 0 1px 3px rgba(0,0,0,0.06);
            }
            .box h3 {
                font-size: 0.95rem;
                color: #6b7280;
                margin-bottom: 14px;
                font-weight: 600;
            }
            .image-wrapper {
                position: relative;
                background: repeating-conic-gradient(#f3f4f6 0% 25%, #ffffff 0% 50%) 50% / 20px 20px;
                border-radius: 10px;
                overflow: hidden;
                min-height: 200px;
                display: flex;
                align-items: center;
                justify-content: center;
                border: 1px solid #e5e7eb;
            }
            .image-wrapper img {
                max-width: 100%;
                max-height: 400px;
                display: block;
            }

            /* Canvas overlay */
            .canvas-wrapper {
                position: relative;
                display: inline-block;
            }
            .canvas-wrapper canvas {
                position: absolute;
                top: 0;
                left: 0;
            }

            /* Brush toolbar */
            .brush-toolbar {
                display: none;
                flex-direction: column;
                gap: 12px;
                margin-top: 16px;
                padding: 16px;
                background: #f8fafc;
                border-radius: 12px;
            }
            .brush-toolbar.active {
                display: flex;
            }
            .btn-icon {
                width: 16px;
                height: 16px;
                vertical-align: -2px;
            }

            .brush-row {
                display: flex;
                align-items: center;
                gap: 12px;
                font-size: 0.85rem;
            }
            .brush-row label {
                min-width: 90px;
                color: #6b7280;
            }
            .brush-row input[type="range"] {
                flex: 1;
                accent-color: #2563eb;
            }
            .brush-row .value {
                min-width: 36px;
                text-align: right;
                color: #2563eb;
                font-weight: 600;
            }
            .brush-actions {
                display: flex;
                gap: 10px;
                flex-wrap: wrap;
                align-items: center;
            }
            .brush-actions .btn {
                font-size: 0.85rem;
                padding: 8px 18px;
            }
            .mode-badge {
                font-size: 0.8rem;
                padding: 4px 14px;
                border-radius: 20px;
                font-weight: 600;
                margin-left: auto;
            }
            .mode-badge.erase {
                background: #fef2f2;
                color: #ef4444;
                border: 1px solid #fecaca;
            }
            .mode-badge.restore {
                background: #f5f3ff;
                color: #8b5cf6;
                border: 1px solid #ddd6fe;
            }

            /* Full-screen loading overlay */
            .loading-fullscreen {
                position: fixed;
                inset: 0;
                background: rgba(255,255,255,0.92);
                backdrop-filter: blur(6px);
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                z-index: 9999;
                opacity: 0;
                pointer-events: none;
                transition: opacity 0.3s;
            }
            .loading-fullscreen.active {
                opacity: 1;
                pointer-events: all;
            }
            .loading-spinner {
                width: 56px;
                height: 56px;
                border: 4px solid #e2e8f0;
                border-top-color: #2563eb;
                border-right-color: #7c3aed;
                border-radius: 50%;
                animation: spin 0.8s linear infinite;
            }
            @keyframes spin { to { transform: rotate(360deg); } }
            .loading-label {
                margin-top: 20px;
                font-size: 1.1rem;
                color: #1e293b;
                font-weight: 600;
            }
            .loading-sub {
                margin-top: 8px;
                font-size: 0.85rem;
                color: #6b7280;
            }

            .hidden { display: none !important; }

            /* Usage bar */
            .usage-bar {
                margin-top: 18px;
                text-align: center;
                font-size: 0.88rem;
                color: #6b7280;
            }
            .usage-bar .uses-left {
                font-weight: 600;
                color: #3a3a3a;
            }
            .usage-bar.pro {
                color: #059669;
                font-weight: 600;
            }
            .upgrade-link {
                display: inline-block;
                margin-top: 8px;
                padding: 10px 28px;
                background: linear-gradient(135deg, #2563eb, #7c3aed);
                color: #fff;
                border: none;
                border-radius: 10px;
                font-size: 0.95rem;
                font-weight: 600;
                cursor: pointer;
                font-family: inherit;
                transition: transform 0.15s, box-shadow 0.3s;
                box-shadow: 0 4px 15px rgba(37,99,235,0.3);
            }
            .upgrade-link:hover { transform: translateY(-2px); }
            .license-link {
                display: block;
                margin-top: 8px;
                font-size: 0.82rem;
                color: #6b7280;
                cursor: pointer;
                text-decoration: underline;
                background: none;
                border: none;
                font-family: inherit;
            }

            /* License modal */
            .modal-overlay {
                position: fixed;
                inset: 0;
                background: rgba(0,0,0,0.4);
                backdrop-filter: blur(4px);
                z-index: 9998;
                display: flex;
                align-items: center;
                justify-content: center;
                opacity: 0;
                pointer-events: none;
                transition: opacity 0.25s;
            }
            .modal-overlay.active {
                opacity: 1;
                pointer-events: all;
            }
            .modal-box {
                background: #fff;
                border-radius: 16px;
                padding: 32px;
                max-width: 420px;
                width: 90%;
                box-shadow: 0 8px 30px rgba(0,0,0,0.12);
            }
            .modal-box h2 {
                font-size: 1.2rem;
                color: #2d2d2d;
                margin-bottom: 12px;
            }
            .modal-box p {
                font-size: 0.88rem;
                color: #6b7280;
                margin-bottom: 16px;
            }
            .modal-box input {
                width: 100%;
                padding: 10px 14px;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                font-size: 1rem;
                font-family: monospace;
                letter-spacing: 1px;
                text-align: center;
                margin-bottom: 12px;
            }
            .modal-box input:focus {
                outline: none;
                border-color: #2563eb;
                box-shadow: 0 0 0 3px rgba(37,99,235,0.1);
            }
            .modal-actions {
                display: flex;
                gap: 10px;
                justify-content: flex-end;
            }
            .modal-msg {
                font-size: 0.82rem;
                margin-top: 8px;
                text-align: center;
            }
            .modal-msg.error { color: #ef4444; }
            .modal-msg.success { color: #059669; }

            /* Language Switcher Custom Dropdown */
            .lang-switcher {
                position: absolute;
                top: 20px;
                right: 20px;
                z-index: 10000;
            }
            .custom-select-wrapper {
                position: relative;
                user-select: none;
                width: 160px;
            }
            .custom-select {
                background: #f1f5f9;
                color: #1e293b;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 0.85rem;
                cursor: pointer;
                display: flex;
                align-items: center;
                gap: 8px;
                transition: background 0.2s;
            }
            .custom-select:hover {
                background: #e2e8f0;
            }
            .custom-select::after {
                content: "▼";
                font-size: 0.6rem;
                color: #64748b;
                margin-left: auto;
            }
            .custom-options {
                position: absolute;
                top: 100%;
                left: 0;
                right: 0;
                background: #fff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                margin-top: 4px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                overflow: hidden;
                display: none;
            }
            .custom-options.open {
                display: block;
            }
            .custom-option {
                padding: 8px 10px;
                font-size: 0.85rem;
                cursor: pointer;
                display: flex;
                align-items: center;
                gap: 8px;
                transition: background 0.2s;
            }
            .custom-option:hover {
                background: #f8fafc;
            }

            /* Flag Icons */
            .flag-icon {
                width: 20px;
                height: 14px;
                display: inline-block;
                background-size: contain;
                background-repeat: no-repeat;
                background-position: center;
                border-radius: 2px;
                box-shadow: 0 0 1px rgba(0,0,0,0.2);
            }
            .flag-en { background-image: url("https://cdnjs.cloudflare.com/ajax/libs/flag-icon-css/3.5.0/flags/4x3/us.svg"); }
            .flag-ja { background-image: url("https://cdnjs.cloudflare.com/ajax/libs/flag-icon-css/3.5.0/flags/4x3/jp.svg"); }
            .flag-zh { background-image: url("https://cdnjs.cloudflare.com/ajax/libs/flag-icon-css/3.5.0/flags/4x3/cn.svg"); }
            .flag-hi { background-image: url("https://cdnjs.cloudflare.com/ajax/libs/flag-icon-css/3.5.0/flags/4x3/in.svg"); }
            .flag-pt { background-image: url("https://cdnjs.cloudflare.com/ajax/libs/flag-icon-css/3.5.0/flags/4x3/br.svg"); }
            .modal-box input {
                width: 100%;
                padding: 10px 14px;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                font-size: 1rem;
                font-family: monospace;
                letter-spacing: 1px;
                text-align: center;
                margin-bottom: 12px;
            }
            .modal-box input:focus {
                outline: none;
                border-color: #2563eb;
                box-shadow: 0 0 0 3px rgba(37,99,235,0.1);
            }
            .modal-actions {
                display: flex;
                gap: 10px;
                justify-content: flex-end;
            }
            .modal-msg {
                font-size: 0.82rem;
                margin-top: 8px;
                text-align: center;
            }
            .modal-msg.error { color: #ef4444; }
            .modal-msg.success { color: #059669; }

            @media (max-width: 640px) {
                h1 { font-size: 1.5rem; }
                .container { flex-direction: column; align-items: center; }
                .box { max-width: 100%; }
                .upload-area { padding: 24px 20px; }
            }
        </style>
    </head>
    <body>
        <!-- Language Switcher -->
        <div class="lang-switcher">
            <div class="custom-select-wrapper" id="langDropdown">
                <div class="custom-select" id="langSelectBtn">
                    <span class="flag-icon flag-en"></span> English
                </div>
                <div class="custom-options" id="langOptions">
                    <div class="custom-option" data-value="en"><span class="flag-icon flag-en"></span> English</div>
                    <div class="custom-option" data-value="ja"><span class="flag-icon flag-ja"></span> 日本語</div>
                    <div class="custom-option" data-value="zh"><span class="flag-icon flag-zh"></span> 中文</div>
                    <div class="custom-option" data-value="hi"><span class="flag-icon flag-hi"></span> हिन्दी</div>
                    <div class="custom-option" data-value="pt"><span class="flag-icon flag-pt"></span> Português (BR)</div>
                </div>
            </div>
        </div>

        <!-- Full-screen loading overlay -->
        <div class="loading-fullscreen" id="loadingFullscreen">
            <div class="loading-spinner"></div>
            <div class="loading-label" data-i18n="loading_label">Removing background…</div>
            <div class="loading-sub" data-i18n="loading_sub">This may take a few seconds</div>
        </div>

        <h1>ClearCut</h1>
        <p class="subtitle" data-i18n="subtitle">Simple. Fast. Just works.</p>

        <!-- Upload area -->
        <div class="upload-area" id="dropZone" onclick="document.getElementById('fileInput').click()">
            <p class="upload-text" data-i18n="upload_text">Drop image here or <strong>click to upload</strong></p>
            <input type="file" id="fileInput" accept="image/*">
        </div>

        <!-- Model selector -->
        <div class="model-selector">
            <label for="modelSelect" data-i18n="model_label">Model:</label>
            <select id="modelSelect">
                <option value="isnet-general-use" selected data-i18n="model_hq">ISNet (High Quality)</option>
                <option value="u2net" data-i18n="model_std">U2Net (Standard)</option>
                <option value="u2net_human_seg" data-i18n="model_portrait">U2Net (Portrait)</option>
                <option value="silueta" data-i18n="model_fast">Silueta (Fast)</option>
            </select>
        </div>

        <div class="action-bar">
            <button class="btn btn-primary" id="removeBgBtn" disabled data-i18n="remove_bg_btn">Remove Background</button>
        </div>

        <!-- Usage bar -->
        <div class="usage-bar" id="usageBar"></div>
        <div style="text-align:center;">
            <button class="upgrade-link hidden" id="upgradeBtn" data-i18n="upgrade_btn">Upgrade to Pro</button>
            <button class="license-link" id="licenseLink" data-i18n="has_license">Already have a license? Enter here.</button>
        </div>

        <!-- License modal -->
        <div class="modal-overlay" id="licenseModal">
            <div class="modal-box">
                <h2 data-i18n="modal_license_title">Enter License Key</h2>
                <p data-i18n="modal_license_desc">Paste the key you received after purchase.</p>
                <input type="text" id="licenseInput" placeholder="CC-XXXX-XXXX-XXXX-XXXX" maxlength="24">
                <div class="modal-msg hidden" id="licenseMsg"></div>
                <div class="modal-actions">
                    <button class="btn btn-secondary" id="licenseCancel" data-i18n="cancel">Cancel</button>
                    <button class="btn btn-primary" id="licenseSubmit" data-i18n="activate">Activate</button>
                </div>
            </div>
        </div>

        <!-- Success modal -->
        <div class="modal-overlay" id="successModal">
            <div class="modal-box">
                <h2 data-i18n="modal_payment_title">🎉 Payment Successful!</h2>
                <p data-i18n="modal_payment_desc">Thank you for upgrading! Your License Key is below. It has been automatically saved, but please copy and keep it safe.</p>
                <div style="display: flex; gap: 8px; margin-top: 15px; margin-bottom: 20px;">
                    <input type="text" id="successLicenseInput" readonly style="flex: 1; font-weight: bold; text-align: center; font-size: 1.1rem; color: #3b82f6; background: #f8fafc; cursor: text;">
                    <button class="btn btn-primary" id="copyLicenseBtn" style="padding: 10px 16px;" data-i18n="copy">Copy</button>
                </div>
                <div class="modal-actions" style="justify-content: center;">
                    <button class="btn btn-secondary" id="successCloseBtn" data-i18n="close">Close</button>
                </div>
            </div>
        </div>

        <div class="container hidden" id="resultContainer">
            <!-- Original -->
            <div class="box">
                <h3 data-i18n="result_original">Original</h3>
                <div class="image-wrapper" style="background: #fff;">
                    <img id="preview" />
                </div>
            </div>

            <!-- Result -->
            <div class="box">
                <h3 data-i18n="result_final">Result</h3>
                <div class="image-wrapper" id="resultWrapper">
                    <div class="canvas-wrapper" id="canvasWrapper">
                        <img id="resultImg" />
                        <canvas id="eraserCanvas"></canvas>
                    </div>
                </div>

                <!-- Brush toolbar -->
                <div class="brush-toolbar" id="brushToolbar">
                    <div class="brush-row">
                        <label data-i18n="brush_size">Brush Size</label>
                        <input type="range" id="brushSize" min="3" max="80" value="20">
                        <span class="value" id="brushSizeVal">20</span>
                    </div>
                    <div class="brush-actions">
                        <button class="btn btn-erase active-mode" id="eraseBtn"><svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="8" y1="8" x2="16" y2="16"/><line x1="16" y1="8" x2="8" y2="16"/></svg> <span data-i18n="brush_erase">Erase</span></button>
                        <button class="btn btn-restore" id="restoreBtn"><svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 4l-1 1 4 4 1-1a2.83 2.83 0 0 0-4-4Z"/><path d="M13.5 6.5 5 15v4h4l8.5-8.5"/><line x1="2" y1="2" x2="5" y2="5"/><line x1="18" y1="13" x2="21" y2="10"/><line x1="3" y1="8" x2="1" y2="6"/></svg> <span data-i18n="brush_restore">Restore</span></button>
                        <button class="btn btn-secondary" id="undoBtn" data-i18n="brush_undo">Undo</button>
                        <span class="mode-badge erase" id="modeBadge" data-i18n="brush_erase">Erase</span>
                    </div>
                </div>

                <!-- Download button -->
                <div class="action-bar" id="resultActions" style="display:none;">
                    <button class="btn btn-download" id="downloadBtn" data-i18n="download_btn">Download</button>
                </div>
            </div>
        </div>

        <script>
        (() => {
            // Record page access
            fetch('/record-access', { method: 'POST' }).catch(e => console.error("Access record failed", e));

            // Localization Dictionary
            const translations = {
                en: {
                    loading_label: "Removing background…",
                    loading_sub: "This may take a few seconds",
                    subtitle: "Simple. Fast. Just works.",
                    upload_text: "Drop image here or <strong>click to upload</strong>",
                    model_label: "Model:",
                    model_hq: "ISNet (High Quality)",
                    model_std: "U2Net (Standard)",
                    model_portrait: "U2Net (Portrait)",
                    model_fast: "Silueta (Fast)",
                    remove_bg_btn: "Remove Background",
                    upgrade_btn: "Upgrade to Pro",
                    has_license: "Already have a license? Enter here.",
                    modal_license_title: "Enter License Key",
                    modal_license_desc: "Paste the key you received after purchase.",
                    cancel: "Cancel",
                    activate: "Activate",
                    modal_payment_title: "🎉 Payment Successful!",
                    modal_payment_desc: "Thank you for upgrading! Your License Key is below. It has been automatically saved, but please copy and keep it safe.",
                    copy: "Copy",
                    close: "Close",
                    result_original: "Original",
                    result_final: "Result",
                    brush_size: "Brush Size",
                    brush_erase: "Erase",
                    brush_restore: "Restore",
                    brush_undo: "Undo",
                    download_btn: "Download"
                },
                ja: {
                    loading_label: "背景を切り抜いています…",
                    loading_sub: "数秒かかる場合があります",
                    subtitle: "シンプル。爆速。美しい。",
                    upload_text: "ここに画像をドロップするか、<strong>クリックしてアップロード</strong>",
                    model_label: "AIモデル:",
                    model_hq: "ISNet (最高画質)",
                    model_std: "U2Net (標準)",
                    model_portrait: "U2Net (人物向け)",
                    model_fast: "Silueta (超高速)",
                    remove_bg_btn: "背景を削除",
                    upgrade_btn: "Pro版へアップグレード",
                    has_license: "ライセンスをお持ちの方はこちら",
                    modal_license_title: "ライセンスキー入力",
                    modal_license_desc: "購入時に発行されたキーを貼り付けてください。",
                    cancel: "キャンセル",
                    activate: "有効化",
                    modal_payment_title: "🎉 お支払いが完了しました！",
                    modal_payment_desc: "アップグレードありがとうございます！あなたのライセンスキーは以下の通りです。自動で保存されますが、念のためコピーして保管してください。",
                    copy: "コピー",
                    close: "閉じる",
                    result_original: "元画像",
                    result_final: "切り抜き結果",
                    brush_size: "ブラシサイズ",
                    brush_erase: "消す",
                    brush_restore: "戻す",
                    brush_undo: "元に戻す",
                    download_btn: "ダウンロード"
                },
                zh: {
                    loading_label: "正在抠图中…",
                    loading_sub: "这可能需要几秒钟",
                    subtitle: "极简。极速。效果完美。",
                    upload_text: "将图片拖拽到此处，或 <strong>点击上传</strong>",
                    model_label: "AI模型:",
                    model_hq: "ISNet (最高画质)",
                    model_std: "U2Net (标准)",
                    model_portrait: "U2Net (人像优化)",
                    model_fast: "Silueta (极速)",
                    remove_bg_btn: "一键抠图",
                    upgrade_btn: "升级专业版",
                    has_license: "已有许可证？在此输入",
                    modal_license_title: "输入许可证密钥",
                    modal_license_desc: "请粘贴您购买后收到的密钥。",
                    cancel: "取消",
                    activate: "激活",
                    modal_payment_title: "🎉 支付成功！",
                    modal_payment_desc: "感谢您的升级！下方是您的许可证密钥。它已自动保存，但请复制并妥善保管。",
                    copy: "复制",
                    close: "关闭",
                    result_original: "原图",
                    result_final: "抠图结果",
                    brush_size: "画笔大小",
                    brush_erase: "擦除",
                    brush_restore: "恢复",
                    brush_undo: "撤销",
                    download_btn: "下载"
                },
                hi: {
                    loading_label: "बैकग्राउंड हटाया जा रहा है…",
                    loading_sub: "इसमें कुछ सेकंड लग सकते हैं",
                    subtitle: "आसान। तेज़। बेहतरीन काम।",
                    upload_text: "यहां फोटो छोड़ें या <strong>अपलोड करने के लिए क्लिक करें</strong>",
                    model_label: "AI मॉडल:",
                    model_hq: "ISNet (हाई क्वालिटी)",
                    model_std: "U2Net (स्टैंडर्ड)",
                    model_portrait: "U2Net (पोर्ट्रेट)",
                    model_fast: "Silueta (फास्ट)",
                    remove_bg_btn: "बैकग्राउंड हटाएं",
                    upgrade_btn: "प्रो में अपग्रेड करें",
                    has_license: "पहले से लाइसेंस है? यहां डालें",
                    modal_license_title: "लाइसेंस की दर्ज करें",
                    modal_license_desc: "खरीदने के बाद मिली की (Key) को यहां पेस्ट करें।",
                    cancel: "रद्द करें",
                    activate: "एक्टिवेट करें",
                    modal_payment_title: "🎉 पेमेंट सफल!",
                    modal_payment_desc: "अपग्रेड करने के लिए धन्यवाद! आपकी लाइसेंस की नीचे है। यह ऑटोमैटिक रूप से सेव हो गई है, लेकिन कृपया इसे कॉपी करके सुरक्षित रखें।",
                    copy: "कॉपी",
                    close: "बंद करें",
                    result_original: "ओरिजिनल",
                    result_final: "रिजल्ट",
                    brush_size: "ब्रश का आकार",
                    brush_erase: "मिटाएं",
                    brush_restore: "वापस लाएं",
                    brush_undo: "अंडू (Undo)",
                    download_btn: "डाउनलोड"
                },
                pt: {
                    loading_label: "Removendo fundo…",
                    loading_sub: "Isso pode levar alguns segundos",
                    subtitle: "Simples. Rápido. Funciona.",
                    upload_text: "Arraste a imagem aqui ou <strong>clique para enviar</strong>",
                    model_label: "Modelo:",
                    model_hq: "ISNet (Alta Qualidade)",
                    model_std: "U2Net (Padrão)",
                    model_portrait: "U2Net (Retratos)",
                    model_fast: "Silueta (Rápido)",
                    remove_bg_btn: "Remover Fundo",
                    upgrade_btn: "Atualizar para Pro",
                    has_license: "Já tem licença? Insira aqui",
                    modal_license_title: "Insira a Chave da Licença",
                    modal_license_desc: "Cole aqui a chave que você recebeu após a compra.",
                    cancel: "Cancelar",
                    activate: "Ativar",
                    modal_payment_title: "🎉 Pagamento Aprovado!",
                    modal_payment_desc: "Obrigado por atualizar! Sua Chave de Licença está abaixo. Ela foi salva automaticamente, mas copie-a para segurança.",
                    copy: "Copiar",
                    close: "Fechar",
                    result_original: "Original",
                    result_final: "Resultado",
                    brush_size: "Tamanho do Pincel",
                    brush_erase: "Apagar",
                    brush_restore: "Restaurar",
                    brush_undo: "Desfazer",
                    download_btn: "Baixar"
                }
            };

            // Language logic
            const langSelectBtn = document.getElementById('langSelectBtn');
            const langOptionsBox = document.getElementById('langOptions');
            const customOptions = document.querySelectorAll('.custom-option');

            langSelectBtn.addEventListener('click', (e) => {
                langOptionsBox.classList.toggle('open');
                e.stopPropagation();
            });

            document.addEventListener('click', () => {
                langOptionsBox.classList.remove('open');
            });
            
            // Set language via UI
            function setLanguage(lang) {
                if (!translations[lang]) lang = 'en';
                const dict = translations[lang];
                document.documentElement.lang = lang;
                
                document.querySelectorAll('[data-i18n]').forEach(el => {
                    const key = el.getAttribute('data-i18n');
                    if (dict[key]) {
                        el.innerHTML = dict[key];
                    }
                });
                
                // Update dropdown text
                const activeOption = document.querySelector(`.custom-option[data-value="${lang}"]`);
                if (activeOption) {
                    langSelectBtn.innerHTML = activeOption.innerHTML;
                }
                localStorage.setItem('clearcut_lang', lang);
            }

            // Init language on load
            const savedLang = localStorage.getItem('clearcut_lang') || 'en';
            setLanguage(savedLang);

            customOptions.forEach(opt => {
                opt.addEventListener('click', (e) => {
                    setLanguage(e.target.getAttribute('data-value'));
                });
            });

            const dropZone = document.getElementById('dropZone');
            const fileInput = document.getElementById('fileInput');
            const removeBgBtn = document.getElementById('removeBgBtn');
            const preview = document.getElementById('preview');
            const resultImg = document.getElementById('resultImg');
            const resultContainer = document.getElementById('resultContainer');
            const resultActions = document.getElementById('resultActions');
            const loadingFullscreen = document.getElementById('loadingFullscreen');
            const downloadBtn = document.getElementById('downloadBtn');
            const brushToolbar = document.getElementById('brushToolbar');
            const brushSizeInput = document.getElementById('brushSize');
            const brushSizeVal = document.getElementById('brushSizeVal');
            const undoBtn = document.getElementById('undoBtn');
            const eraseBtn = document.getElementById('eraseBtn');
            const restoreBtn = document.getElementById('restoreBtn');
            const modeBadge = document.getElementById('modeBadge');
            const eraserCanvas = document.getElementById('eraserCanvas');
            const canvasWrapper = document.getElementById('canvasWrapper');
            const modelSelect = document.getElementById('modelSelect');
            const ctx = eraserCanvas.getContext('2d');

            // License & usage UI
            const usageBar = document.getElementById('usageBar');
            const upgradeBtn = document.getElementById('upgradeBtn');
            const licenseLink = document.getElementById('licenseLink');
            const licenseModal = document.getElementById('licenseModal');
            const licenseInput = document.getElementById('licenseInput');
            const licenseMsg = document.getElementById('licenseMsg');
            const licenseCancel = document.getElementById('licenseCancel');
            const licenseSubmit = document.getElementById('licenseSubmit');

            let currentFile = null;
            let resultBlobUrl = null;
            let originalSourceImage = null;
            let originalSourceCanvas = null;
            let bgRemovedImageData = null;
            let brushMode = 'erase';
            let isDrawing = false;
            let lastPos = null;
            let history = [];

            // --- License key from LocalStorage ---
            function getSavedLicense() {
                return localStorage.getItem('clearcut_license') || '';
            }
            function saveLicense(key) {
                localStorage.setItem('clearcut_license', key);
            }
            function getLicenseHeaders() {
                const key = getSavedLicense();
                return key ? { 'X-License-Key': key } : {};
            }

            // --- Usage status ---
            async function updateUsageUI() {
                try {
                    const resp = await fetch('/usage-status', { headers: getLicenseHeaders() });
                    const data = await resp.json();
                    if (data.is_pro) {
                        usageBar.innerHTML = '\u2713 Pro \u2014 Unlimited access';
                        usageBar.className = 'usage-bar pro';
                        upgradeBtn.classList.add('hidden');
                        licenseLink.classList.add('hidden');
                    } else {
                        const left = data.limit - data.used;
                        usageBar.innerHTML = `Free: <span class="uses-left">${left} / ${data.limit}</span> uses left today`;
                        usageBar.className = 'usage-bar';
                        upgradeBtn.classList.remove('hidden');
                        licenseLink.classList.remove('hidden');
                    }
                } catch(e) {}
            }
            updateUsageUI();

            // --- Upgrade button ---
            upgradeBtn.addEventListener('click', async () => {
                const oldText = upgradeBtn.textContent;
                upgradeBtn.textContent = "Loading...";
                upgradeBtn.disabled = true;

                try {
                    const resp = await fetch('/create-checkout', { method: 'POST' });
                    const data = await resp.json();
                    if (data.url) {
                        // Reverting to window.open due to white screen issue with top.location
                        window.open(data.url, '_blank');
                    } else {
                        console.error("Backend error:", data);
                        alert(`Stripe Checkout Error: ${data.error || 'Unknown error'}`);
                    }
                } catch(e) {
                    console.error("Network error:", e);
                    alert(`Network or Server Error: ${e.message}`);
                } finally {
                    upgradeBtn.textContent = oldText;
                    upgradeBtn.disabled = false;
                }
            });

            // --- Check for checkout success in URL ---
            const urlParams = new URLSearchParams(window.location.search);
            const checkoutStatus = urlParams.get('checkout');
            
            // --- Success modal logic ---
            const successModal = document.getElementById('successModal');
            const successLicenseInput = document.getElementById('successLicenseInput');
            const copyLicenseBtn = document.getElementById('copyLicenseBtn');
            const successCloseBtn = document.getElementById('successCloseBtn');

            if (copyLicenseBtn) {
                copyLicenseBtn.addEventListener('click', () => {
                    successLicenseInput.select();
                    document.execCommand('copy');
                    const oldText = copyLicenseBtn.textContent;
                    copyLicenseBtn.textContent = 'Copied!';
                    setTimeout(() => { copyLicenseBtn.textContent = oldText; }, 2000);
                });
            }
            if (successCloseBtn) {
                successCloseBtn.addEventListener('click', () => {
                    successModal.classList.remove('active');
                });
            }

            if (checkoutStatus === 'success') {
                const sessionId = urlParams.get('session_id');
                if (sessionId) {
                    fetch(`/get-checkout-license?session_id=${sessionId}`)
                        .then(r => r.json())
                        .then(data => {
                            if (data.license_key) {
                                saveLicense(data.license_key);
                                updateUsageUI();
                                // Show custom modal instead of alert
                                successLicenseInput.value = data.license_key;
                                successModal.classList.add('active');
                            } else {
                                alert("Payment successful, but could not display license key automatically. Please check your email.");
                            }
                            window.history.replaceState({}, document.title, window.location.pathname);
                        })
                        .catch(e => {
                            console.error("License fetch error", e);
                            window.history.replaceState({}, document.title, window.location.pathname);
                        });
                }
            } else if (checkoutStatus === 'cancel') {
                alert("Payment was cancelled.");
                window.history.replaceState({}, document.title, window.location.pathname);
            }

            // --- License modal ---
            licenseLink.addEventListener('click', () => {
                licenseModal.classList.add('active');
                licenseInput.value = '';
                licenseMsg.classList.add('hidden');
                licenseInput.focus();
            });
            licenseCancel.addEventListener('click', () => {
                licenseModal.classList.remove('active');
            });
            licenseModal.addEventListener('click', (e) => {
                if (e.target === licenseModal) licenseModal.classList.remove('active');
            });
            licenseSubmit.addEventListener('click', async () => {
                const key = licenseInput.value.trim().toUpperCase();
                if (!key) return;
                licenseMsg.classList.add('hidden');
                try {
                    const resp = await fetch('/verify-license', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ license_key: key })
                    });
                    const data = await resp.json();
                    if (data.valid) {
                        saveLicense(key);
                        licenseMsg.textContent = 'License activated! Unlimited access unlocked.';
                        licenseMsg.className = 'modal-msg success';
                        licenseMsg.classList.remove('hidden');
                        setTimeout(() => {
                            licenseModal.classList.remove('active');
                            updateUsageUI();
                        }, 1500);
                    } else {
                        licenseMsg.textContent = 'Invalid or expired license key.';
                        licenseMsg.className = 'modal-msg error';
                        licenseMsg.classList.remove('hidden');
                    }
                } catch(e) {
                    licenseMsg.textContent = 'Verification failed. Try again.';
                    licenseMsg.className = 'modal-msg error';
                    licenseMsg.classList.remove('hidden');
                }
            });

            // --- Custom cursors via SVG data URIs ---
            function makeBrushCursor(size) {
                const displaySize = Math.max(size, 12);
                const half = displaySize / 2;
                const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${displaySize}" height="${displaySize}" viewBox="0 0 ${displaySize} ${displaySize}">
                    <circle cx="${half}" cy="${half}" r="${half - 1}" fill="rgba(239,68,68,0.25)" stroke="#ef4444" stroke-width="1.5"/>
                </svg>`;
                return `url('data:image/svg+xml;utf8,${encodeURIComponent(svg)}') ${half} ${half}, crosshair`;
            }

            function makeWandCursor() {
                const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">
                    <line x1="4" y1="28" x2="20" y2="12" stroke="#8b5cf6" stroke-width="2.5" stroke-linecap="round"/>
                    <polygon points="20,12 24,8 28,4 26,10 22,14" fill="#a855f7"/>
                    <circle cx="26" cy="4" r="2" fill="#fbbf24"/>
                    <line x1="24" y1="1" x2="24" y2="7" stroke="#fbbf24" stroke-width="1"/>
                    <line x1="21" y1="4" x2="27" y2="4" stroke="#fbbf24" stroke-width="1"/>
                    <line x1="29" y1="7" x2="30" y2="10" stroke="#fbbf24" stroke-width="0.8"/>
                    <line x1="22" y1="1" x2="21" y2="3" stroke="#fbbf24" stroke-width="0.8"/>
                </svg>`;
                return `url('data:image/svg+xml;utf8,${encodeURIComponent(svg)}') 4 28, crosshair`;
            }

            function updateCursor() {
                if (!brushToolbar.classList.contains('active')) {
                    eraserCanvas.style.cursor = 'default';
                    return;
                }
                if (brushMode === 'erase') {
                    const displaySize = Math.min(parseInt(brushSizeInput.value), 40);
                    eraserCanvas.style.cursor = makeBrushCursor(displaySize);
                } else {
                    eraserCanvas.style.cursor = makeWandCursor();
                }
            }

            // --- Drag & drop ---
            dropZone.addEventListener('dragover', e => {
                e.preventDefault();
                dropZone.classList.add('drag-over');
            });
            dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
            dropZone.addEventListener('drop', e => {
                e.preventDefault();
                dropZone.classList.remove('drag-over');
                if (e.dataTransfer.files.length) {
                    fileInput.files = e.dataTransfer.files;
                    handleFile(e.dataTransfer.files[0]);
                }
            });

            fileInput.addEventListener('change', () => {
                if (fileInput.files[0]) handleFile(fileInput.files[0]);
            });

            function handleFile(file) {
                currentFile = file;
                const url = URL.createObjectURL(file);
                preview.src = url;

                // Load original image into an HTMLImageElement for restore brush
                const img = new Image();
                img.onload = () => { originalSourceImage = img; };
                img.src = url;

                resultContainer.classList.remove('hidden');
                resultImg.src = '';
                eraserCanvas.width = 0;
                eraserCanvas.height = 0;
                resultActions.style.display = 'none';
                brushToolbar.classList.remove('active');
                brushMode = 'erase';
                removeBgBtn.disabled = false;
                history = [];
                bgRemovedImageData = null;
            }

            // --- Remove BG ---
            removeBgBtn.addEventListener('click', async () => {
                if (!currentFile) return;
                removeBgBtn.disabled = true;
                loadingFullscreen.classList.add('active');

                try {
                    const formData = new FormData();
                    formData.append('file', currentFile);
                    formData.append('model', modelSelect.value);

                    const resp = await fetch('/remove-bg', {
                        method: 'POST',
                        body: formData,
                        headers: getLicenseHeaders()
                    });

                    if (resp.status === 429) {
                        const data = await resp.json();
                        alert(data.error || 'Daily limit reached. Upgrade to Pro!');
                        return;
                    }
                    if (!resp.ok) throw new Error('Error');

                    const blob = await resp.blob();
                    if (resultBlobUrl) URL.revokeObjectURL(resultBlobUrl);
                    resultBlobUrl = URL.createObjectURL(blob);
                    resultImg.src = resultBlobUrl;

                    resultImg.onload = () => {
                        setupCanvas();
                        resultActions.style.display = 'flex';
                    };

                    updateUsageUI();
                } catch (err) {
                    alert('Failed to remove background. Please try again.');
                } finally {
                    loadingFullscreen.classList.remove('active');
                    removeBgBtn.disabled = false;
                }
            });

            // --- Canvas Setup ---
            function setupCanvas() {
                const img = resultImg;
                const w = img.naturalWidth;
                const h = img.naturalHeight;
                eraserCanvas.width = w;
                eraserCanvas.height = h;
                eraserCanvas.style.width = img.width + 'px';
                eraserCanvas.style.height = img.height + 'px';
                ctx.clearRect(0, 0, w, h);
                ctx.drawImage(img, 0, 0, w, h);

                // Save BG-removed result for reference
                bgRemovedImageData = ctx.getImageData(0, 0, w, h);

                // Cache original source image at result size for fast restore
                if (originalSourceImage) {
                    originalSourceCanvas = document.createElement('canvas');
                    originalSourceCanvas.width = w;
                    originalSourceCanvas.height = h;
                    const tmpCtx = originalSourceCanvas.getContext('2d');
                    tmpCtx.drawImage(originalSourceImage, 0, 0, w, h);
                }

                // Show brush toolbar
                brushToolbar.classList.add('active');
                eraserCanvas.style.cursor = 'crosshair';
                updateCursor();

                history = [];
                saveHistory();
                resultImg.style.visibility = 'hidden';
            }



            // --- Erase / Restore mode toggle ---
            eraseBtn.addEventListener('click', () => {
                brushMode = 'erase';
                eraseBtn.classList.add('active-mode');
                restoreBtn.classList.remove('active-mode');
                modeBadge.textContent = 'Erase';
                modeBadge.className = 'mode-badge erase';
                updateCursor();
            });

            restoreBtn.addEventListener('click', () => {
                brushMode = 'restore';
                restoreBtn.classList.add('active-mode');
                eraseBtn.classList.remove('active-mode');
                modeBadge.textContent = 'Restore';
                modeBadge.className = 'mode-badge restore';
                updateCursor();
            });

            brushSizeInput.addEventListener('input', () => {
                brushSizeVal.textContent = brushSizeInput.value;
                updateCursor();
            });

            // --- Drawing ---
            function getCanvasPos(e) {
                const rect = eraserCanvas.getBoundingClientRect();
                const scaleX = eraserCanvas.width / rect.width;
                const scaleY = eraserCanvas.height / rect.height;
                const clientX = e.touches ? e.touches[0].clientX : e.clientX;
                const clientY = e.touches ? e.touches[0].clientY : e.clientY;
                return {
                    x: (clientX - rect.left) * scaleX,
                    y: (clientY - rect.top) * scaleY
                };
            }

            function isBrushActive() {
                return brushToolbar.classList.contains('active');
            }

            // Interpolate points for smooth strokes
            function interpolatePoints(p1, p2, spacing) {
                const points = [];
                const dx = p2.x - p1.x;
                const dy = p2.y - p1.y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                const steps = Math.max(Math.floor(dist / spacing), 1);
                for (let i = 0; i <= steps; i++) {
                    const t = i / steps;
                    points.push({ x: p1.x + dx * t, y: p1.y + dy * t });
                }
                return points;
            }

            function brushStroke(pos) {
                const radius = parseInt(brushSizeInput.value);
                const spacing = Math.max(radius * 0.3, 2);

                // Get points to draw (interpolated for smoothness)
                let points;
                if (lastPos) {
                    points = interpolatePoints(lastPos, pos, spacing);
                } else {
                    points = [pos];
                }
                lastPos = pos;

                if (brushMode === 'erase') {
                    ctx.globalCompositeOperation = 'destination-out';
                    ctx.lineWidth = radius * 2;
                    ctx.lineCap = 'round';
                    ctx.lineJoin = 'round';
                    ctx.beginPath();
                    ctx.moveTo(points[0].x, points[0].y);
                    for (let i = 1; i < points.length; i++) {
                        ctx.lineTo(points[i].x, points[i].y);
                    }
                    ctx.stroke();
                    ctx.globalCompositeOperation = 'source-over';

                } else if (brushMode === 'restore' && originalSourceCanvas) {
                    // Use clip + drawImage for fast restore
                    ctx.save();
                    ctx.beginPath();
                    for (const p of points) {
                        ctx.moveTo(p.x + radius, p.y);
                        ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
                    }
                    ctx.clip();
                    ctx.drawImage(originalSourceCanvas, 0, 0);
                    ctx.restore();
                }
            }

            function startDraw(e) {
                if (!isBrushActive()) return;
                e.preventDefault();
                isDrawing = true;
                lastPos = null;
                brushStroke(getCanvasPos(e));
            }

            function draw(e) {
                if (!isDrawing || !isBrushActive()) return;
                e.preventDefault();
                brushStroke(getCanvasPos(e));
            }

            function endDraw() {
                if (!isDrawing) return;
                isDrawing = false;
                lastPos = null;
                saveHistory();
            }

            eraserCanvas.addEventListener('mousedown', startDraw);
            eraserCanvas.addEventListener('mousemove', draw);
            eraserCanvas.addEventListener('mouseup', endDraw);
            eraserCanvas.addEventListener('mouseleave', endDraw);
            eraserCanvas.addEventListener('touchstart', startDraw, { passive: false });
            eraserCanvas.addEventListener('touchmove', draw, { passive: false });
            eraserCanvas.addEventListener('touchend', endDraw);

            // --- Undo ---
            function saveHistory() {
                if (history.length > 30) history.shift();
                history.push(ctx.getImageData(0, 0, eraserCanvas.width, eraserCanvas.height));
            }

            undoBtn.addEventListener('click', () => {
                if (history.length <= 1) return;
                history.pop();
                const prev = history[history.length - 1];
                ctx.putImageData(prev, 0, 0);
            });

            // --- Download ---
            downloadBtn.addEventListener('click', () => {
                const link = document.createElement('a');
                if (eraserCanvas.width > 0 && eraserCanvas.height > 0) {
                    link.href = eraserCanvas.toDataURL('image/png');
                } else {
                    link.href = resultBlobUrl;
                }
                link.download = 'removed_bg.png';
                link.click();
            });

            // Resize observer
            const resizeObserver = new ResizeObserver(() => {
                if (resultImg.width > 0) {
                    eraserCanvas.style.width = resultImg.width + 'px';
                    eraserCanvas.style.height = resultImg.height + 'px';
                }
            });
            resizeObserver.observe(resultImg);
        })();
        </script>
    </body>
    </html>
    """


@app.post("/remove-bg")
async def remove_bg(
    request: Request,
    file: UploadFile = File(...),
    model: str = Form("isnet-general-use"),
    x_license_key: str = Header(None, alias="X-License-Key"),
):
    ip = request.client.host

    # Check usage limits
    status = can_use(ip, x_license_key)
    if not status["allowed"]:
        return JSONResponse(
            status_code=429,
            content={"error": "Daily limit reached. Upgrade to Pro for unlimited access."}
        )

    input_data = await file.read()

    allowed_models = ["isnet-general-use", "u2net", "u2net_human_seg", "silueta"]
    if model not in allowed_models:
        model = "isnet-general-use"

    sess = new_session(model)
    output_data = remove(input_data, session=sess)

    # Record usage for free users
    if not status["is_pro"]:
        record_usage(ip)

    return StreamingResponse(
        io.BytesIO(output_data),
        media_type="image/png"
    )


@app.get("/usage-status")
async def usage_status(
    request: Request,
    x_license_key: str = Header(None, alias="X-License-Key"),
):
    ip = request.client.host
    status = can_use(ip, x_license_key)
    return status


@app.post("/verify-license")
async def verify_license_endpoint(request: Request):
    body = await request.json()
    key = body.get("license_key", "")
    valid = verify_license(key)
    return {"valid": valid, "license_key": key}


@app.post("/record-access")
async def record_access(request: Request):
    """Ping GAS webhook to record page access."""
    ip = request.client.host
    user_agent = request.headers.get("user-agent", "unknown")
    
    from stripe_handler import GAS_WEBHOOK_URL
    if GAS_WEBHOOK_URL:
        import urllib.request
        import json
        import threading
        
        def ping_gas():
            try:
                data = json.dumps({
                    "type": "access",
                    "ip": ip,
                    "user_agent": user_agent
                }).encode("utf-8")
                
                req = urllib.request.Request(
                    GAS_WEBHOOK_URL, 
                    data=data, 
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                urllib.request.urlopen(req, timeout=5)
            except Exception as e:
                print(f"[ClearCut] Failed to record access to GAS: {e}")
                
        # Run in background to not block page load
        threading.Thread(target=ping_gas, daemon=True).start()
        
    return {"status": "ok"}


@app.post("/create-checkout")
async def create_checkout(request: Request):
    try:
        from stripe_handler import create_checkout_session
        from license import generate_license
        
        # Pre-generate the license key to link it with the session
        pending_license_key = generate_license()
        
        base_url = str(request.base_url).rstrip("/")
        url = create_checkout_session(
            success_url=f"{base_url}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base_url}/?checkout=cancel",
            client_reference_id=pending_license_key
        )
        return {"url": url}
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        print(f"[ClearCut] create_checkout error: {err_msg}")
        return JSONResponse(status_code=500, content={"error": str(e), "trace": err_msg})


@app.get("/get-checkout-license")
async def get_checkout_license(session_id: str):
    """Retrieve the license key attached to a completed checkout session."""
    import stripe
    import os
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == "paid":
            return {"license_key": session.client_reference_id}
        else:
            return {"error": "Payment not completed"}
    except Exception as e:
        return {"error": str(e)}


@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    try:
        from stripe_handler import handle_webhook
        payload = await request.body()
        sig = request.headers.get("stripe-signature", "")
        result = handle_webhook(payload, sig)
        return result
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.get("/debug")
async def debug_endpoint(request: Request):
    """Simple endpoint to verify the server is running and accessible"""
    return {
        "status": "ok",
        "client_host": request.client.host if request.client else "unknown",
        "headers": dict(request.headers),
        "env_keys": list(os.environ.keys())
    }


# Dev/test helper: manually generate a license
@app.post("/generate-test-license")
async def generate_test_license(request: Request):
    body = await request.json()
    email = body.get("email", "test@example.com")
    key = create_license(email)
    print(f"[ClearCut] Test license generated: {key} for {email}")
    return {"license_key": key, "email": email}