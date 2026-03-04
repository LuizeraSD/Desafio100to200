"""
Dashboard Streamlit — monitoramento em tempo real do portfólio.

Lê state/portfolio.json (escrito pelo orchestrator a cada tick) e atualiza
automaticamente a cada 30 segundos.

Rodar:
  streamlit run dashboard/app.py   (a partir da raiz do projeto)
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

# ── Garante que a raiz do projeto está no sys.path ────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STATE_DIR   = ROOT / "state"
PORTFOLIO_F = STATE_DIR / "portfolio.json"
MOMENTUM_F  = STATE_DIR / "momentum.json"
POLY_F      = STATE_DIR / "polymarket.json"

GOAL        = 200.0
INITIAL     = 100.0
REFRESH_MS  = 30_000  # 30 segundos

# ── Configuração da página ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="Desafio $100→$200",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Auto-refresh ──────────────────────────────────────────────────────────────
# st.rerun() nativo do Streamlit ≥ 1.28 via fragment com run_every
# Fallback: botão manual de refresh no topo
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _pnl_color(value: float) -> str:
    return "green" if value >= 0 else "red"


def _fmt_pnl(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}${value:.2f}"


# ── Autenticação básica (opcional via DASHBOARD_PASSWORD) ────────────────────
_dashboard_pwd = os.getenv("DASHBOARD_PASSWORD", "").strip()
if _dashboard_pwd:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        st.title("🎯 Desafio $100 → $200")
        pwd = st.text_input("Senha de acesso", type="password")
        if st.button("Entrar"):
            if pwd == _dashboard_pwd:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
        st.stop()

# ── Layout ────────────────────────────────────────────────────────────────────

st.title("🎯 Desafio $100 → $200 | Dashboard")

portfolio = _load_json(PORTFOLIO_F)

# ─── Header: sem dados ────────────────────────────────────────────────────────
if portfolio is None:
    st.warning(
        "⏳ Orchestrator ainda não iniciado — aguardando `state/portfolio.json`.\n\n"
        "Rode: `python orchestrator/main.py`"
    )
    col_r, _ = st.columns([1, 4])
    if col_r.button("🔄 Verificar novamente"):
        st.rerun()
    st.stop()

# ─── Dados do portfólio ───────────────────────────────────────────────────────
total_value  = portfolio.get("total_value", INITIAL)
total_pnl    = portfolio.get("total_pnl", 0.0)
drawdown     = portfolio.get("drawdown", 0.0)
paper_trade  = portfolio.get("paper_trade", True)
last_update  = portfolio.get("last_update_str", "—")
strategies   = portfolio.get("strategies", {})
equity_hist  = portfolio.get("equity_history", [])
progress     = min(total_value / GOAL, 1.0)

mode_tag = "🧪 PAPER TRADING" if paper_trade else "⚡ LIVE"

# ─── Linha de status ─────────────────────────────────────────────────────────
col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 2])

col1.metric(
    label="Portfólio",
    value=f"${total_value:.2f}",
    delta=_fmt_pnl(total_pnl),
    delta_color="normal",
)
col2.metric(
    label="P&L Total",
    value=_fmt_pnl(total_pnl),
    delta=f"{total_pnl / INITIAL * 100:+.1f}%",
    delta_color="normal",
)
col3.metric(
    label="Progresso para $200",
    value=f"{progress * 100:.1f}%",
    delta=f"faltam ${max(GOAL - total_value, 0):.2f}",
    delta_color="off",
)
col4.metric(
    label="Drawdown",
    value=f"{drawdown * 100:.2f}%",
    delta_color="inverse",
)
col5.metric(label="Modo", value=mode_tag)

st.progress(progress)
st.caption(f"Atualizado: {last_update} · Próximo refresh em ~30s")

# ─── Cards de estratégias ─────────────────────────────────────────────────────
st.divider()
st.subheader("Pernas")

STRATEGY_META = {
    "grid_bot":  {"nome": "Grid Bot",          "exchange": "Binance Futures", "emoji": "◈"},
    "momentum":  {"nome": "Momentum Scalper",  "exchange": "Bybit Futures",   "emoji": "⚡"},
    "polymarket":{"nome": "Polymarket Model",  "exchange": "Polymarket CLOB", "emoji": "🎲"},
}

cols = st.columns(4)

# Pernas Python
for i, (sid, meta) in enumerate(STRATEGY_META.items()):
    s = strategies.get(sid, {})
    active      = s.get("active", False)
    allocation  = s.get("allocation", 0.0)
    total_pnl_s = s.get("total_pnl", 0.0)
    open_orders = s.get("open_orders", 0)
    is_paper    = s.get("paper_trade", True)

    status_icon = "✅ Ativo" if active else "⛔ Parado"
    paper_icon  = " [PAPER]" if is_paper else ""

    with cols[i]:
        st.markdown(f"**{meta['emoji']} {meta['nome']}**")
        st.caption(f"{meta['exchange']}{paper_icon}")
        st.metric(
            label="P&L",
            value=_fmt_pnl(total_pnl_s),
            delta=f"{total_pnl_s / allocation * 100:+.1f}%" if allocation > 0 else "—",
            delta_color="normal",
        )
        st.write(f"Alocação: **${allocation:.2f}**")
        label = "Ordens" if sid == "grid_bot" else ("Trades" if sid == "momentum" else "Posições")
        st.write(f"{label}: **{open_orders}**")
        st.write(f"Status: {status_icon}")

# Forex (MT5 — independente do Python)
with cols[3]:
    st.markdown("**🌐 Forex Breakout**")
    st.caption("IC Markets MT5 (EA)")
    st.write("Alloc: **$25**")
    st.write("Pares: GBP/USD + EUR/JPY")
    st.write("Status: 🔌 MT5 independente")
    st.caption("Monitorar direto no terminal MT5")

# ─── Curva de equity ─────────────────────────────────────────────────────────
st.divider()
st.subheader("Curva de Capital")

if equity_hist:
    df_eq = pd.DataFrame(equity_hist)
    df_eq["timestamp"] = pd.to_datetime(df_eq["timestamp"], unit="s", utc=True)
    df_eq = df_eq.set_index("timestamp").rename(columns={"value": "Portfólio ($)"})

    # Linha de meta
    df_eq["Meta $200"] = GOAL

    st.line_chart(df_eq, color=["#00cc66", "#ff4444"])
    st.caption(
        f"Pontos: {len(equity_hist)} | "
        f"Mín: ${df_eq['Portfólio ($)'].min():.2f} | "
        f"Máx: ${df_eq['Portfólio ($)'].max():.2f}"
    )
else:
    st.info("Curva de capital ainda sem dados — aguardando ticks do orchestrator.")

# ─── Posições abertas ─────────────────────────────────────────────────────────
st.divider()
col_left, col_right = st.columns(2)

# Polymarket
with col_left:
    st.subheader("🎲 Posições Polymarket")
    poly_state = _load_json(POLY_F)
    poly_positions = []
    if poly_state:
        for cid, pos in poly_state.get("positions", {}).items():
            if not pos.get("closed", True):
                poly_positions.append({
                    "Pergunta":   pos.get("question", "")[:60],
                    "Direção":    pos.get("direction", ""),
                    "Entrada":    f"{pos.get('entry_price', 0) * 100:.1f}%",
                    "Valor":      f"${pos.get('amount_usd', 0):.2f}",
                    "P&L":        f"{_fmt_pnl(pos.get('pnl', 0))}",
                })

    if poly_positions:
        st.dataframe(pd.DataFrame(poly_positions), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma posição aberta no momento.")

# Momentum
with col_right:
    st.subheader("⚡ Trades Momentum")
    mom_state = _load_json(MOMENTUM_F)
    mom_trades = []
    if mom_state:
        for sym, trade in mom_state.get("trades", {}).items():
            if not trade.get("closed", True):
                mom_trades.append({
                    "Símbolo":  sym,
                    "Entrada":  f"${trade.get('entry_price', 0):.4f}",
                    "TP":       f"${trade.get('tp_price', 0):.4f}",
                    "SL":       f"${trade.get('sl_price', 0):.4f}",
                    "Trail":    f"${trade.get('trailing_stop', 0):.4f}",
                    "P&L":      f"{_fmt_pnl(trade.get('pnl', 0))}",
                })

    if mom_trades:
        st.dataframe(pd.DataFrame(mom_trades), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum trade aberto no momento.")

# ─── Rodapé com botão de refresh ──────────────────────────────────────────────
st.divider()
col_btn, col_info = st.columns([1, 5])
if col_btn.button("🔄 Atualizar agora"):
    st.rerun()
col_info.caption(
    "O dashboard atualiza automaticamente a cada 30s. "
    "Para forçar atualização clique no botão acima ou recarregue a página."
)

# ─── Auto-refresh via meta tag ────────────────────────────────────────────────
# Injeta meta refresh HTML para recarregar a página automaticamente
st.markdown(
    f'<meta http-equiv="refresh" content="{REFRESH_MS // 1000}">',
    unsafe_allow_html=True,
)
