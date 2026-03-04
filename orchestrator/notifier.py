"""
Telegram Notifier — alertas, relatórios diários e comandos de controle.

Comandos suportados (quando configurado com token + chat_id):
  /status  → resumo do portfólio e status de cada estratégia
  /pnl     → P&L detalhado por perna
  /stop    → sinaliza parada de emergência (seta stop_event)

Uso em main.py:
  notify = TelegramNotifier()
  await notify.start_commands(portfolio, strategies, stop_event)
  # → roda bot polling como task em background
"""
import asyncio
import logging
import os

log = logging.getLogger("notifier")


class TelegramNotifier:
    def __init__(self):
        self.token   = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or None
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID",   "").strip() or None
        self._bot    = None
        self._app    = None   # telegram.ext.Application (command handler)

        if self.token and self.chat_id:
            try:
                from telegram import Bot
                self._bot = Bot(token=self.token)
                log.info("Telegram bot configurado (chat_id=%s)", self.chat_id)
            except ImportError:
                log.warning("python-telegram-bot não instalado — notificações desabilitadas")
        else:
            log.warning(
                "TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não configurados — "
                "notificações desabilitadas"
            )

    # ─────────────────────────────────────────────
    # Envio de mensagens
    # ─────────────────────────────────────────────

    async def send(self, message: str) -> None:
        """Envia mensagem de texto. Loga localmente se bot não configurado."""
        if not self._bot:
            log.info("[NOTIFY] %s", message)
            return
        try:
            await self._bot.send_message(chat_id=self.chat_id, text=message)
        except Exception as exc:
            log.error("Erro ao enviar Telegram: %s", exc)

    async def alert(self, message: str) -> None:
        await self.send(f"🚨 {message}")

    async def daily_report(self, portfolio) -> None:
        await self.send(f"📊 Relatório Diário\n{portfolio.summary()}")

    # ─────────────────────────────────────────────
    # Comandos de controle (/status, /pnl, /stop)
    # ─────────────────────────────────────────────

    async def start_commands(
        self,
        portfolio,
        strategies: list,
        stop_event: asyncio.Event,
    ) -> None:
        """
        Inicia o bot polling em background com handlers de comando.
        Deve ser chamado como asyncio.create_task(notify.start_commands(...)).
        Não bloqueia — retorna imediatamente após configurar o Application.
        """
        if not self.token:
            log.info("Comandos Telegram desabilitados (token não configurado)")
            return

        try:
            from telegram.ext import Application, CommandHandler
        except ImportError:
            log.warning("python-telegram-bot não instalado — comandos desabilitados")
            return

        app = Application.builder().token(self.token).build()
        self._app = app

        # ── /status ───────────────────────────────
        async def cmd_status(update, context):
            if str(update.effective_chat.id) != self.chat_id:
                return
            lines = [portfolio.summary(), ""]
            for s in strategies:
                active = "✅" if s.active else "⛔"
                mode   = "[PAPER]" if s.paper_trade else "[LIVE]"
                lines.append(f"{active} {mode} {s.id} | alloc=${s.allocation:.2f}")
            await update.message.reply_text("\n".join(lines))

        # ── /pnl ──────────────────────────────────
        async def cmd_pnl(update, context):
            if str(update.effective_chat.id) != self.chat_id:
                return
            lines = [
                f"💰 P&L Total: {portfolio.total_pnl:+.2f}",
                f"   Portfólio: ${portfolio.total_value:.2f}",
                f"   Drawdown:  {portfolio.drawdown:.1%}",
                "",
            ]
            for sid, snap in portfolio._snapshots.items():
                lines.append(
                    f"  {sid}: {snap.total_pnl:+.2f}"
                    f" (real={snap.pnl_realized:+.2f}"
                    f" unreal={snap.pnl_unrealized:+.2f})"
                )
            await update.message.reply_text("\n".join(lines))

        # ── /stop ─────────────────────────────────
        async def cmd_stop(update, context):
            if str(update.effective_chat.id) != self.chat_id:
                return
            await update.message.reply_text(
                "🛑 Parada de emergência solicitada via Telegram.\n"
                "Fechando todas as posições..."
            )
            log.warning("Parada solicitada via Telegram (/stop)")
            stop_event.set()

        app.add_handler(CommandHandler("status", cmd_status))
        app.add_handler(CommandHandler("pnl",    cmd_pnl))
        app.add_handler(CommandHandler("stop",   cmd_stop))

        # Inicia polling em background (não-bloqueante para o event loop)
        try:
            await app.initialize()
            await app.start()
            await app.updater.start_polling(drop_pending_updates=True)
            log.info("Telegram command polling iniciado (/status /pnl /stop)")
        except Exception as exc:
            log.error("Erro ao iniciar Telegram polling: %s", exc)

    async def stop_commands(self) -> None:
        """Para o bot polling graciosamente."""
        if self._app is None:
            return
        try:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        except Exception as exc:
            log.debug("Erro ao parar Telegram polling: %s", exc)
