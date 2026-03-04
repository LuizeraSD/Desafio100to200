"""
Orchestrator principal — loop central do Desafio $100→$200.
Coordena as 4 estratégias, aplica circuit breakers e rebalanceia diariamente.

Estratégias:
  Perna 1: Grid Bot (Bybit Futures) — $30 — ✅ implementado
  Perna 2: Forex Breakout (IC Markets MT5 EA) — $25 — ✅ implementado (MQL5)
  Perna 3: Polymarket Model (Claude API) — $25 — ✅ implementado
  Perna 4: Momentum Scalper (Bybit Futures) — $20 — ✅ implementado

Nota: Grid Bot migrado de Binance → Bybit (Binance Futures geo-bloqueada no Brasil).
      Grid + Momentum compartilham a mesma instância ccxt.bybit.

Variável de ambiente:
  PAPER_TRADE=true  → usa PaperExchange (simula ordens, preços reais da exchange)
  PAPER_TRADE=false → usa exchanges reais (padrão)

Execução:
  python orchestrator/main.py    (a partir da raiz do projeto)
  python -m orchestrator.main    (alternativa equivalente)
"""
import sys
from pathlib import Path

# Garante que a raiz do projeto está no sys.path quando executado diretamente
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import importlib.util
import logging
import os
import signal
import socket
import sys
from datetime import datetime, timezone

import aiohttp
import ccxt.async_support as ccxt
import yaml
from dotenv import load_dotenv

from orchestrator.notifier import TelegramNotifier
from orchestrator.portfolio import Portfolio
from orchestrator.risk_manager import RiskManager
from strategies.grid_bot.engine import GridBot
from strategies.momentum.executor import MomentumScalper
from strategies.paper_exchange import PaperExchange
from strategies.polymarket.executor import PolymarketModel
from strategies.state_manager import save_state

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("orchestrator")

TICK_INTERVAL    = 60   # segundos
REBALANCE_HOUR_UTC = 23
PAPER_TRADE = os.getenv("PAPER_TRADE", "false").lower() == "true"


def _load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _is_rebalance_time() -> bool:
    now = datetime.now(timezone.utc)
    return now.hour == REBALANCE_HOUR_UTC and now.minute < 2


def _make_connector() -> aiohttp.TCPConnector:
    """
    ThreadedResolver: usa loop.run_in_executor + socket.getaddrinfo (OS DNS).
    Evita o c-ares/aiodns (DefaultResolver com aiodns instalado = AsyncResolver)
    que falha em certos ambientes Windows.
    """
    return aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())


async def _init_exchange(ex: ccxt.Exchange, label: str) -> None:
    """Injeta sessão aiohttp com ThreadedResolver na exchange ccxt."""
    ex.session = aiohttp.ClientSession(connector=_make_connector())
    log.info("%s: sessão aiohttp configurada (ThreadedResolver)", label)


async def _load_markets_with_retry(ex: ccxt.Exchange, label: str) -> bool:
    """
    Carrega mercados com backoff exponencial.
    Retorna True em caso de sucesso, False em caso de falha permanente.
    Nunca lança exceção — o orquestrador decide o que fazer com a perna afetada.

    Falhas permanentes (HTTP 451 geo-bloqueio, PermissionDenied) falham na 1ª tentativa
    sem aguardar os delays — não faz sentido retentar erros de jurisdição.
    """
    delays = [30, 60, 120, 300]
    for attempt, delay in enumerate(delays + [None], start=1):
        try:
            log.info("%s: carregando mercados (tentativa %d)...", label, attempt)
            await ex.load_markets()
            log.info("%s: %d símbolos carregados", label, len(ex.markets))
            return True
        except ccxt.AuthenticationError as exc:
            # API key inválida, IP não permitido, ou sem permissão — permanente
            log.error(
                "%s: autenticação falhou (key/IP/permissão): %s",
                label, exc,
            )
            return False
        except (ccxt.NetworkError, ccxt.ExchangeNotAvailable) as exc:
            # Verifica se é geo-bloqueio disfarçado de erro de rede (ex: Binance HTTP 451)
            err_str = str(exc)
            if "451" in err_str or "restricted location" in err_str.lower():
                log.error(
                    "%s: geo-bloqueio detectado (HTTP 451) — exchange indisponível nesta região: %s",
                    label, exc,
                )
                return False
            if delay is None:
                log.error(
                    "%s: falha após %d tentativas — perna será desabilitada: %s",
                    label, attempt - 1, exc,
                )
                return False
            log.warning(
                "%s: erro de conexão (tentativa %d/%d): %s — aguardando %ds...",
                label, attempt, len(delays), exc, delay,
            )
            await asyncio.sleep(delay)
        except ccxt.ExchangeError as exc:
            # Qualquer outro erro da exchange (rate limit, manutenção, etc.)
            log.error(
                "%s: erro de exchange não recuperável: %s", label, exc,
            )
            return False
    return False  # nunca alcançado, mas satisfaz o type checker


# ─────────────────────────────────────────────────────────────────────────────
# Diagnóstico de rede (executado uma vez na inicialização)
# ─────────────────────────────────────────────────────────────────────────────

async def _run_network_diag() -> None:
    log.info("── Diagnóstico de rede ──")
    log.info("aiohttp versão: %s", aiohttp.__version__)
    log.info("aiodns instalado: %s", importlib.util.find_spec("aiodns") is not None)

    # DNS síncrono (pilha OS)
    try:
        addrs = socket.getaddrinfo("api.bybit.com", 443, proto=socket.IPPROTO_TCP)
        log.info("socket.getaddrinfo OK → %s", [a[4][0] for a in addrs])
    except OSError as exc:
        log.error("socket.getaddrinfo FALHOU: %s", exc)

    # DNS asyncio (loop.getaddrinfo, também usa pilha Windows)
    try:
        loop = asyncio.get_event_loop()
        addrs_async = await loop.getaddrinfo(
            "api.bybit.com", 443, proto=socket.IPPROTO_TCP
        )
        log.info("loop.getaddrinfo OK → %s", [a[4][0] for a in addrs_async])
    except OSError as exc:
        log.error("loop.getaddrinfo FALHOU: %s", exc)

    # HTTP com ThreadedResolver (sem ccxt)
    try:
        async with aiohttp.ClientSession(connector=_make_connector()) as s:
            async with s.get(
                "https://api.bybit.com/v5/market/time",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                log.info("aiohttp ThreadedResolver ping OK → HTTP %d", r.status)
    except Exception as exc:
        log.error("aiohttp ThreadedResolver ping FALHOU: %s — %s", type(exc).__name__, exc)

    log.info("── Fim do diagnóstico ──")


# ─────────────────────────────────────────────────────────────────────────────
# Validação de credenciais (executado uma vez na inicialização)
# ─────────────────────────────────────────────────────────────────────────────

async def _validate_credentials(
    bybit_ex: ccxt.Exchange,
    paper_trade: bool,
) -> None:
    """
    Valida credenciais das APIs no boot e loga ✅/⚠/❌ por serviço.

    Camadas de validação:
      1. Presença da variável de ambiente
      2. Formato básico da key (quando aplicável)
      3. Chamada autenticada leve à exchange (apenas em live)

    Nunca aborta a inicialização — informa e deixa o operador decidir.
    Em paper trading só valida variáveis obrigatórias (ANTHROPIC_API_KEY).
    Em live trading testa autenticação real na Bybit.
    """
    log.info("── Validação de credenciais ──")
    issues: list[str] = []  # coleta erros para notificar via Telegram depois

    # ── Anthropic API (obrigatória em ambos os modos) ─────────────────────────
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not anthropic_key:
        msg = "ANTHROPIC_API_KEY ausente — Polymarket Model não funcionará"
        log.error("❌ %s", msg)
        issues.append(msg)
    elif not anthropic_key.startswith("sk-ant-"):
        msg = "ANTHROPIC_API_KEY com formato inválido (esperado: sk-ant-...)"
        log.warning("⚠ %s", msg)
        issues.append(msg)
    else:
        log.info("✅ ANTHROPIC_API_KEY presente (formato ok)")

    # ── Telegram (opcional mas recomendado) ───────────────────────────────────
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    tg_chat  = os.getenv("TELEGRAM_CHAT_ID",   "").strip()
    if tg_token and tg_chat:
        log.info("✅ Telegram configurado (BOT_TOKEN + CHAT_ID presentes)")
    elif tg_token and not tg_chat:
        log.warning("⚠ TELEGRAM_CHAT_ID ausente — notificações desabilitadas")
    elif tg_chat and not tg_token:
        log.warning("⚠ TELEGRAM_BOT_TOKEN ausente — notificações desabilitadas")
    else:
        log.info("ℹ Telegram não configurado — monitoramento apenas via logs")

    # ── Keys de exchange (Bybit para Grid Bot + Momentum) ────────────────────
    exchange_keys = {
        "BYBIT_API_KEY":   "Grid Bot + Momentum (Bybit)",
        "BYBIT_SECRET":    "Grid Bot + Momentum (Bybit)",
    }
    poly_keys = {
        "POLY_API_KEY":    "Polymarket CLOB",
        "POLY_SECRET":     "Polymarket CLOB",
        "POLY_PASSPHRASE": "Polymarket CLOB",
    }

    if paper_trade:
        # Em paper: warnings para keys faltando (bot funciona sem elas)
        for key, desc in {**exchange_keys, **poly_keys}.items():
            if not os.getenv(key, "").strip():
                log.warning(
                    "⚠ %s ausente — %s rodará em paper (ok para testes)", key, desc
                )
    else:
        # Em live: erros para keys faltando
        for key, desc in {**exchange_keys, **poly_keys}.items():
            if not os.getenv(key, "").strip():
                msg = f"{key} ausente — {desc} não operará em live"
                log.error("❌ %s", msg)
                issues.append(msg)
            else:
                log.info("✅ %s presente", key)

        # ── Teste de autenticação real: Bybit Futures ─────────────────────────
        bybit_key = os.getenv("BYBIT_API_KEY", "").strip()
        if bybit_key:
            try:
                await bybit_ex.fetch_balance(params={"type": "future"})
                log.info("✅ Bybit Futures auth OK (balance acessível)")
            except ccxt.AuthenticationError as exc:
                msg = f"Bybit auth FALHOU: key inválida ou sem permissão ({exc})"
                log.error("❌ %s", msg)
                issues.append(msg)
            except ccxt.ExchangeError as exc:
                msg = f"Bybit auth FALHOU: {exc}"
                log.error("❌ %s", msg)
                issues.append(msg)
            except Exception as exc:
                log.warning("⚠ Bybit auth: erro inesperado (%s): %s", type(exc).__name__, exc)

    log.info("── Fim da validação (%d problema(s) encontrado(s)) ──", len(issues))
    return issues  # retorna lista para notificar via Telegram


# ─────────────────────────────────────────────────────────────────────────────
# Verificação de saldo mínimo (executado uma vez na inicialização)
# ─────────────────────────────────────────────────────────────────────────────

async def _check_balances(
    bybit_ex: ccxt.Exchange,
    paper_trade: bool,
    bybit_ok: bool,
    grid_alloc: float,
    momentum_alloc: float,
) -> list[str]:
    """
    Verifica saldo USDT livre na Bybit e compara com a alocação total (Grid + Momentum).

    Apenas em live mode — em paper mode o saldo real não importa.
    Só verifica se a exchange conseguiu carregar mercados (bybit_ok).

    Níveis de alerta:
      ✅  saldo >= alocação total              → operação normal
      ⚠   0 < saldo < alocação                → posições serão proporcionalmente menores
      ❌  saldo = $0 (conta vazia ou errada)   → exchange não conseguirá abrir posições

    Nunca aborta a inicialização — retorna lista para notificar o operador.
    Nota: Polymarket (USDC on-chain) não é verificado aqui — requer chave privada
    Polygon, não suportada pelo CLOB API key.
    """
    if paper_trade:
        log.info("Saldo: paper mode — verificação ignorada")
        return []

    log.info("── Verificação de saldo ──")
    issues: list[str] = []

    total_bybit_alloc = grid_alloc + momentum_alloc

    if not bybit_ok:
        log.info("Bybit: exchange inacessível — saldo não verificado")
    elif not os.getenv("BYBIT_API_KEY", "").strip():
        pass  # key ausente — já reportado em _validate_credentials
    else:
        try:
            bal = await bybit_ex.fetch_balance(params={"type": "future"})
            usdt_free = float(bal.get("USDT", {}).get("free") or 0)

            if usdt_free >= total_bybit_alloc:
                log.info(
                    "✅ Bybit Futures: $%.2f USDT livre (alocação total: $%.2f — Grid $%.2f + Momentum $%.2f)",
                    usdt_free, total_bybit_alloc, grid_alloc, momentum_alloc,
                )
            elif usdt_free > 0:
                msg = (
                    f"Bybit Futures: saldo ${usdt_free:.2f} < alocação total ${total_bybit_alloc:.2f}"
                    f" (Grid ${grid_alloc:.2f} + Momentum ${momentum_alloc:.2f})"
                    " — posições serão proporcionalmente menores"
                )
                log.warning("⚠ %s", msg)
                issues.append(msg)
            else:
                msg = f"Bybit Futures: saldo USDT $0.00 — não conseguirá abrir posições"
                log.error("❌ %s", msg)
                issues.append(msg)

        except ccxt.AuthenticationError:
            pass  # já reportado em _validate_credentials
        except Exception as exc:
            log.warning(
                "⚠ Bybit: erro ao verificar saldo: %s — %s", type(exc).__name__, exc
            )

    log.info("── Fim da verificação de saldo (%d problema(s)) ──", len(issues))
    return issues


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    notify     = TelegramNotifier()
    portfolio  = Portfolio(initial=100.0)
    risk       = RiskManager(max_drawdown=0.40, daily_target=0.15)
    stop_event = asyncio.Event()  # sinaliza parada de emergência (Telegram /stop)
    emergency_stop = False  # True = fechar tudo; False = shutdown gracioso

    mode_label = "PAPER TRADING" if PAPER_TRADE else "LIVE"
    log.info("Modo: %s", mode_label)

    # ── Sinais de encerramento (SIGTERM/SIGHUP no Linux/Docker) ──────────────
    # Windows não suporta add_signal_handler — usa apenas KeyboardInterrupt.
    if sys.platform != "win32":
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGHUP):
            loop.add_signal_handler(sig, stop_event.set)
        log.info("Handlers SIGTERM/SIGHUP registrados")

    await _run_network_diag()

    # ── Bybit Futures (Grid Bot + Momentum Scalper) ───────────────────────────
    # Ambas as pernas crypto compartilham a mesma instância ccxt.bybit.
    # Grid Bot migrado de Binance → Bybit (Binance Futures geo-bloqueada no Brasil).
    bybit_key    = (os.getenv("BYBIT_API_KEY") or "").strip() or None
    bybit_secret = (os.getenv("BYBIT_SECRET")  or "").strip() or None
    bybit_real = ccxt.bybit({
        "apiKey":          bybit_key,
        "secret":          bybit_secret,
        "options":         {"defaultType": "future"},
        "enableRateLimit": True,
    })
    await _init_exchange(bybit_real, "Bybit")
    bybit_ok = await _load_markets_with_retry(bybit_real, "Bybit")

    bybit = PaperExchange(bybit_real, label="Bybit") if PAPER_TRADE else bybit_real

    # ── Perna 1: Grid Bot (Bybit Futures) ─────────────────────────────────────
    grid_cfg = _load_config("strategies/grid_bot/config.yaml")
    grid_bot  = GridBot(grid_cfg, bybit, allocation=30.0, paper_trade=PAPER_TRADE)
    grid_bot.notify = notify.send
    if not bybit_ok:
        grid_bot.disable()
        log.error("Grid Bot desabilitado — Bybit inacessível nesta região/rede")

    # ── Perna 4: Momentum Scalper (Bybit Futures) ─────────────────────────────
    mom_cfg  = _load_config("strategies/momentum/config.yaml")
    momentum = MomentumScalper(mom_cfg, bybit, allocation=20.0, paper_trade=PAPER_TRADE)
    if not bybit_ok:
        momentum.disable()
        log.error("Momentum Scalper desabilitado — Bybit inacessível nesta região/rede")

    # ── Perna 3: Polymarket (Claude API + CLOB) ───────────────────────────────
    poly_cfg  = _load_config("strategies/polymarket/config.yaml")
    polymarket = PolymarketModel(poly_cfg, allocation=25.0, paper_trade=PAPER_TRADE)

    # ── Validação de credenciais + saldo mínimo ───────────────────────────────
    cred_issues = await _validate_credentials(bybit_real, PAPER_TRADE)
    balance_issues = await _check_balances(
        bybit_real, PAPER_TRADE,
        bybit_ok,
        grid_bot.allocation, momentum.allocation,
    )

    # ── Estratégias ativas ────────────────────────────────────────────────────
    # Perna 2 (Forex EA) roda direto no MetaTrader 5 — sem instância Python.
    strategies = [grid_bot, momentum, polymarket]

    # ── Telegram command handler (background) ────────────────────────────────
    tg_task = asyncio.create_task(
        notify.start_commands(portfolio, strategies, stop_event)
    )

    prefix = "[PAPER] " if PAPER_TRADE else ""

    active_legs = []
    if grid_bot.active:
        active_legs.append("Grid Bot")
    if momentum.active:
        active_legs.append("Momentum")
    if polymarket.active:
        active_legs.append("Polymarket")
    active_legs.append("Forex EA (MT5)")

    disabled_text = ""
    if not bybit_ok:
        disabled_text += "\n⛔ Grid Bot + Momentum desabilitados (Bybit inacessível)"

    all_issues = cred_issues + balance_issues
    issues_text = (
        "\n⚠ Problemas detectados:\n" + "\n".join(f"• {i}" for i in all_issues)
        if all_issues else ""
    )
    await notify.send(
        f"{prefix}🚀 Orchestrator iniciado\n"
        f"Modo: {mode_label}\n"
        f"Pernas ativas: {' | '.join(active_legs)}\n"
        f"Comandos: /status /pnl /stop"
        f"{disabled_text}"
        f"{issues_text}"
    )

    log.info("Iniciando loop principal (tick a cada %ds)", TICK_INTERVAL)

    try:
        while not stop_event.is_set():
            for strat in strategies:
                if not strat.active:
                    continue

                status = await strat.tick()
                portfolio.update(strat.id, status)
                paper_tag = "[PAPER] " if status.paper_trade else ""
                log.info(
                    "%s%s | P&L=%.4f | ordens=%d",
                    paper_tag, strat.id, status.total_pnl, status.open_orders,
                )

                # Circuit breaker individual
                if risk.should_stop(strat, status):
                    await strat.close_all()
                    strat.disable()
                    await notify.alert(
                        f"{prefix}⛔ {strat.id} desligado (circuit breaker)\n"
                        f"P&L: {status.total_pnl:+.2f} | Alloc: {status.allocation:.2f}"
                    )
                    risk.redistribute(portfolio, strat)

            # Meta atingida
            if portfolio.total_value >= 200:
                await notify.alert(
                    f"{prefix}🎯 META ATINGIDA! Portfólio: ${portfolio.total_value:.2f}\n"
                    "Iniciando fechamento gradual das posições..."
                )

            # Stop global: -50%
            if portfolio.drawdown > 0.50:
                await notify.alert(
                    f"{prefix}🚨 DRAWDOWN GLOBAL 50% — parando tudo!\n"
                    f"Portfólio: ${portfolio.total_value:.2f}"
                )
                emergency_stop = True
                stop_event.set()
                break

            # Rebalanceamento diário às 23:00 UTC
            if _is_rebalance_time():
                await notify.daily_report(portfolio)
                new_allocs = portfolio.rebalance()
                for strat in strategies:
                    if strat.id in new_allocs:
                        await strat.resize(new_allocs[strat.id])
                log.info(
                    "Rebalanceamento: %s",
                    {k: f"${v:.2f}" for k, v in new_allocs.items()},
                )

            # Persiste estado do portfólio para o dashboard
            portfolio.record_snapshot()
            save_state("portfolio", portfolio.to_state_dict(PAPER_TRADE))

            await asyncio.sleep(TICK_INTERVAL)

    except KeyboardInterrupt:
        log.info("Interrompido pelo usuário (Ctrl+C) — shutdown gracioso")
    finally:
        # Verificar se /stop foi acionado (parada de emergência via Telegram)
        if stop_event.is_set():
            emergency_stop = True

        if emergency_stop:
            # EMERGÊNCIA: fecha todas as posições e limpa estado
            log.info("🛑 Parada de emergência — fechando todas as posições...")
            close_tasks = [s.close_all() for s in strategies if s.active]
            await asyncio.gather(*close_tasks, return_exceptions=True)
            await notify.send(
                f"{prefix}🛑 Orchestrator PARADO (emergência)\n"
                "Todas as posições foram fechadas e estado limpo."
            )
        else:
            # GRACIOSO: salva estado SEM fechar posições
            log.info("🔄 Shutdown gracioso — salvando estado (posições permanecem abertas)...")
            shutdown_tasks = [s.shutdown() for s in strategies]
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)
            await notify.send(
                f"{prefix}🔄 Orchestrator encerrado (shutdown gracioso)\n"
                "Posições permanecem abertas — serão recuperadas no próximo boot."
            )

        # Persiste snapshot final do portfólio
        portfolio.record_snapshot()
        save_state("portfolio", portfolio.to_state_dict(PAPER_TRADE))

        await notify.stop_commands()
        tg_task.cancel()

        await bybit_real.close()
        log.info("Orchestrator encerrado (estado salvo, posições intactas)")


if __name__ == "__main__":
    asyncio.run(main())
