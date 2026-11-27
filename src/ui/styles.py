import base64
from datetime import datetime
import io
from urllib.parse import quote

import streamlit as st

try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

CATEGORIAS_UI = [
    ("bebidas", "🧃 Bebidas"),
    ("carne", "🥩 Carne"),
    ("charcutaria", "🥓 Charcutaria"),
    ("fruta", "🍎 Fruta"),
    ("laticinios", "🥛 Laticínios"),
    ("mercearia", "🛒 Mercearia"),
    ("padaria", "🥖 Padaria"),
    ("pescado", "🐟 Pescado"),
]

CORES_DECISAO = {
    "Prateleira (Normal/Campanha)": "#52606D",
    "Desc. Validade (ESL)": "#1E6F8C",
    "Sacos Surpresa": "#C88A2E",
    "Cozinha Interna": "#8B3A7B",
    "Doação (Caridade)": "#3E8E41",
    "Doação (Ração Animal)": "#CC6633",
    "Desperdício (Lixo)": "#B8433E",
}


def injetar_css_global() -> None:
    st.markdown("""
    <style>
        .kpi-card {
            background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 16px;
            text-align: center;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
        }
        .kpi-title {
            font-size: 12px;
            color: #64748b;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.4px;
            margin-bottom: 4px;
        }
        .kpi-value {
            font-size: 26px;
            color: #0f172a;
            font-weight: 800;
        }
        .kpi-sub {
            font-size: 11px;
            color: #64748b;
            margin-top: 2px;
        }
        .esl-bezel {
            background: #1e293b;
            padding: 7px;
            border-radius: 10px;
            box-shadow: 0 6px 16px rgba(15, 23, 42, 0.14);
            max-width: 360px;
            margin: 0 auto 8px auto;
        }
        .esl-screen {
            background: #e5e7eb;
            border-radius: 5px;
            padding: 11px 12px;
            color: #0f172a;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            min-height: 190px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            border: 1px solid #cbd5e1;
        }
        .esl-header {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            border-bottom: 1.5px solid #cbd5e1;
            padding-bottom: 5px;
            margin-bottom: 6px;
        }
        .esl-prod-name {
            font-size: 15.5px;
            font-weight: 800;
            color: #090d16;
            line-height: 1.15;
            margin: 0;
        }
        .esl-gtin {
            font-size: 9.5px;
            font-weight: 600;
            color: #475569;
            font-family: 'JetBrains Mono', monospace;
            margin-left: 6px;
            white-space: nowrap;
        }
        .esl-middle {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 6px;
            min-height: 36px;
        }
        .esl-pum {
            font-size: 10px;
            font-weight: 700;
            color: #334155;
            text-transform: uppercase;
        }
        .esl-pvp-clean {
            font-size: 14px;
            font-weight: 700;
            color: #1e293b;
        }
        .esl-strike-wrap {
            position: relative;
            display: inline-block;
            font-size: 13.5px;
            font-weight: 700;
            color: #334155;
        }
        .esl-strike-wrap::after {
            content: "";
            position: absolute;
            left: -2px;
            right: -2px;
            top: 50%;
            border-top: 2px solid #dc2626;
            transform: rotate(-10deg);
        }
        .esl-folheto-box {
            text-align: right;
        }
        .esl-folheto-pct {
            font-size: 15px;
            font-weight: 800;
            color: #0f172a;
        }
        .esl-folheto-price {
            font-size: 16px;
            font-weight: 800;
            color: #0f172a;
        }
        .esl-folheto-dates {
            font-size: 9px;
            font-weight: 600;
            color: #475569;
            margin-top: 1px;
        }
        .esl-footer {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 8px;
            padding-top: 2px;
        }
        .esl-qr {
            width: 44px;
            height: 44px;
            background: #ffffff;
            padding: 2px;
            border-radius: 3px;
            border: 1px solid #94a3b8;
            flex-shrink: 0;
        }
        .esl-promo-group {
            margin-left: auto;
            display: flex;
            align-items: flex-end;
            gap: 7px;
        }
        .esl-discount-badge {
            font-size: 28px;
            font-weight: 900;
            color: #0369a1;
            line-height: 0.95;
            letter-spacing: -0.8px;
        }
        .esl-price-right {
            text-align: right;
        }
        .esl-big-price {
            font-size: 26px;
            font-weight: 900;
            color: #090d16;
            line-height: 1;
        }
        .esl-folheto-main-price {
            font-size: 22px;
            font-weight: 800;
            color: #090d16;
            line-height: 1;
        }
        .esl-unit-tag {
            font-size: 11px;
            font-weight: 800;
            color: #1e293b;
            text-transform: uppercase;
        }
        .esl-validade-bar {
            margin-top: 6px;
            padding-top: 4px;
            border-top: 1px dashed #94a3b8;
            text-align: right;
            font-size: 10.5px;
            font-weight: 700;
            color: #0369a1;
        }
        .esl-extra-lotes {
            margin-top: 5px;
            padding: 4px 6px;
            background: #dbeafe;
            border-radius: 4px;
            border-left: 3px solid #0369a1;
            font-size: 10px;
            color: #0f172a;
        }
        .esl-extra-lote-row {
            display: flex;
            justify-content: space-between;
            font-weight: 700;
            margin-top: 2px;
        }
        .esl-saco-stock {
            font-size: 10.5px;
            font-weight: 800;
            color: #047857;
            background: #d1fae5;
            padding: 2px 7px;
            border-radius: 4px;
            border: 1px solid #6ee7b7;
        }
        .st-key-btn_repor_dia button {
            background-color: rgba(28, 131, 225, 0.18) !important;
            border: 1px solid rgba(61, 157, 243, 0.45) !important;
            color: inherit !important;
            font-weight: 600 !important;
        }
        .st-key-btn_repor_dia button:hover {
            background-color: rgba(28, 131, 225, 0.30) !important;
            border-color: rgba(61, 157, 243, 0.75) !important;
        }
        .resumo-quant-wrap {
            border: 1px solid rgba(128, 128, 128, 0.28);
            border-radius: 8px;
            overflow-x: auto;
            background: var(--background-color);
        }
        .resumo-quant-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13.5px;
        }
        .resumo-quant-table th {
            background: var(--secondary-background-color);
            color: var(--text-color);
            font-weight: 600;
            padding: 9px 11px;
            border-bottom: 1px solid rgba(128, 128, 128, 0.28);
            white-space: nowrap;
        }
        .resumo-quant-table td {
            padding: 8px 11px;
            border-bottom: 1px solid rgba(128, 128, 128, 0.16);
            color: var(--text-color);
        }
        .resumo-quant-table tr:last-child td {
            border-bottom: none;
        }
        .resumo-quant-table th.col-left,
        .resumo-quant-table td.col-left {
            text-align: left;
        }
        .resumo-quant-table th.col-right,
        .resumo-quant-table td.col-right,
        .stTable td:not(:first-child),
        .stTable th:not(:first-child) {
            text-align: right !important;
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
        }
        .ag-right-aligned-header .ag-header-cell-label {
            justify-content: flex-end !important;
        }
        .rag-origem-banner {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 14px;
            border-radius: 8px;
            margin: 14px 0 10px 0;
            font-weight: 700;
            font-size: 14px;
            letter-spacing: 0.2px;
        }
        .rag-origem-regra {
            background: rgba(14, 165, 233, 0.14);
            border-left: 4px solid #0ea5e9;
            color: var(--text-color);
        }
        .rag-origem-sql {
            background: rgba(245, 158, 11, 0.14);
            border-left: 4px solid #f59e0b;
            color: var(--text-color);
        }
        .rag-origem-count {
            font-size: 12px;
            font-weight: 600;
            opacity: 0.8;
        }
        .rag-notebook {
            column-count: 2;
            column-gap: 26px;
            column-rule: 1px dashed rgba(128, 128, 128, 0.32);
            padding: 12px 14px;
            border: 1px solid rgba(128, 128, 128, 0.22);
            border-radius: 10px;
            background: color-mix(in srgb, var(--secondary-background-color) 55%, var(--background-color));
            margin-bottom: 10px;
        }
        @media (max-width: 768px) {
            .rag-notebook {
                column-count: 1;
            }
        }
        .rag-cat-header {
            break-after: avoid;
            page-break-after: avoid;
            font-size: 11.5px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.6px;
            color: var(--text-color);
            opacity: 0.78;
            border-bottom: 1px solid rgba(128, 128, 128, 0.28);
            padding-bottom: 3px;
            margin: 10px 0 8px 0;
        }
        .rag-cat-header:first-child {
            margin-top: 0;
        }
        .rag-card {
            break-inside: avoid;
            page-break-inside: avoid;
            background: var(--background-color);
            border: 1px solid rgba(128, 128, 128, 0.20);
            border-radius: 7px;
            padding: 9px 11px;
            margin-bottom: 9px;
        }
        .rag-card-title {
            font-size: 12.5px;
            font-weight: 700;
            color: var(--text-color);
            margin-bottom: 4px;
            line-height: 1.3;
        }
        .rag-card-body {
            font-size: 12.2px;
            line-height: 1.48;
            color: var(--text-color);
            opacity: 0.88;
            text-align: justify;
        }
        .ts-info-wrapper {
            position: relative;
            display: block;
            margin-bottom: 14px;
            cursor: help;
        }
        .ts-info-box {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 8px;
            padding: 13px 16px;
            border-radius: 8px;
            background: rgba(28, 131, 225, 0.12);
            border: 1px solid rgba(28, 131, 225, 0.28);
            color: var(--text-color);
            font-size: 14.5px;
        }
        .ts-info-hint {
            font-size: 12px;
            opacity: 0.72;
            font-weight: 500;
        }
.ts-tooltip-card {
            position: absolute;
            top: calc(100% + 8px);
            left: 0;
            z-index: 999999;
            width: min(680px, 92vw);
            padding: 14px 16px;
            border-radius: 10px;
            background-color: #ffffff;
            background-color: light-dark(#ffffff, #1e293b);
            color: #0f172a;
            color: light-dark(#0f172a, #f8fafc);
            border: 1px solid #cbd5e1;
            border-color: light-dark(#cbd5e1, #475569);
            box-shadow: 0 12px 28px rgba(0, 0, 0, 0.22);
            opacity: 0;
            visibility: hidden;
            pointer-events: none;
            transform: translateY(-4px);
            transition: opacity 0.18s ease, transform 0.18s ease, visibility 0.18s ease;
        }
        .ts-info-wrapper:hover .ts-tooltip-card,
        .ts-info-wrapper:focus-within .ts-tooltip-card {
            opacity: 1;
            visibility: visible;
            transform: translateY(0);
        }
        .ts-formula-box {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-family: 'Cambria Math', 'Times New Roman', Georgia, serif;
            font-size: 16px;
            font-weight: 700;
            padding: 6px 14px;
            border-radius: 7px;
            background-color: #e0f2fe;
            background-color: light-dark(#e0f2fe, #0f172a);
            border: 1px solid #7dd3fc;
            border-color: light-dark(#7dd3fc, #38bdf8);
            margin-bottom: 10px;
        }
        .ts-frac {
            display: inline-flex;
            flex-direction: column;
            align-items: center;
            line-height: 1.15;
            font-size: 14px;
        }
        .ts-frac-num {
            border-bottom: 1.5px solid currentColor;
            padding: 0 6px 2px 6px;
        }
        .ts-frac-den {
            padding: 2px 6px 0 6px;
        }
        .ts-var-list {
            margin: 0;
            padding-left: 18px;
            font-size: 13px;
            line-height: 1.5;
        }
        .ts-var-list li {
            margin-bottom: 4px;
        }
        .ts-var-list li:last-child {
            margin-bottom: 0;
        }
    </style>
    """, unsafe_allow_html=True)


def formatar_data_pt(data_iso: str) -> str:
    try:
        return datetime.strptime(data_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return data_iso


@st.cache_data(show_spinner=False)
def gerar_qr_src(texto: str) -> str:
    if HAS_QRCODE:
        qr = qrcode.QRCode(box_size=3, border=1)
        qr.add_data(texto)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"
    return f"https://api.qrserver.com/v1/create-qr-code/?size=80x80&data={quote(texto)}"