"""
Polymarket Model — usa Claude API para estimar probabilidades de eventos.

Usa o cliente AsyncAnthropic do SDK anthropic para chamadas não-bloqueantes.
Edge = |estimated_prob - market_price|.
Só recomenda aposta quando edge > min_edge_pct E confiança não é baixa.
"""
import logging
import re

log = logging.getLogger("polymarket.model")

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False
    log.warning("anthropic SDK não instalado — ProbabilityModel desabilitado")

_MODEL_ID = "claude-opus-4-6"

_SYSTEM_PROMPT = """\
Você é um analista especializado em mercados de previsão (prediction markets).
Sua tarefa é estimar a probabilidade real de um evento ocorrer com base em:
1. O histórico base (base rate) do tipo de evento
2. Dados contextuais fornecidos
3. Raciocínio bayesiano rigoroso

Responda SEMPRE e APENAS no formato exato abaixo (sem texto extra antes ou depois):

PROBABILIDADE: XX%
CONFIANÇA: alta|média|baixa
RACIOCÍNIO: <2-3 frases concisas>

Onde XX é um número inteiro de 1 a 99.
Use "baixa" quando os dados são insuficientes para fazer uma estimativa confiável.\
"""


class ProbabilityModel:
    """
    Estima probabilidade de um mercado Polymarket via Claude API.
    Retorna recomendação de aposta com edge calculado.
    """

    def __init__(self, config: dict):
        self.cfg = config
        self.min_edge = config.get("min_edge_pct", 12) / 100.0
        self._client: "anthropic.AsyncAnthropic | None" = None

        if _ANTHROPIC_AVAILABLE:
            self._client = anthropic.AsyncAnthropic()
            log.info("ProbabilityModel pronto (model=%s, min_edge=%.0f%%)",
                     _MODEL_ID, self.min_edge * 100)

    async def estimate(self, market: dict) -> dict:
        """
        Analisa um mercado e retorna recomendação de aposta.

        Returns:
            estimated_prob : float  — probabilidade estimada de YES (0.0–1.0)
            market_price   : float  — preço atual do mercado (0.0–1.0)
            edge           : float  — estimated_prob - market_price (negativo → apostar NO)
            abs_edge       : float  — |edge|
            direction      : str    — "YES" | "NO"
            reasoning      : str    — raciocínio do modelo
            confidence     : str    — "alta" | "média" | "baixa"
            should_bet     : bool   — True se edge >= min_edge E confiança != baixa
        """
        if not _ANTHROPIC_AVAILABLE or self._client is None:
            return self._no_bet(market, "anthropic SDK indisponível")

        market_price = float(market.get("market_price", 0.5))
        question = market.get("question", "")
        description = market.get("description", "") or ""
        end_date = market.get("end_date", "N/A")
        volume = market.get("volume_usd", 0)
        category = market.get("category", "")

        prompt = (
            f"Analise este mercado de previsão:\n\n"
            f"PERGUNTA: {question}\n"
            f"DESCRIÇÃO: {description[:400] or 'Não disponível'}\n"
            f"CATEGORIA: {category}\n"
            f"DATA DE RESOLUÇÃO: {end_date}\n"
            f"VOLUME: ${volume:,.0f}\n"
            f"PREÇO DE MERCADO (prob. implícita YES): {market_price:.1%}\n\n"
            f"Estime a probabilidade real de YES. Considere se o mercado está "
            f"subestimando ou superestimando o evento. Use base rates históricos."
        )

        try:
            response = await self._client.messages.create(
                model=_MODEL_ID,
                max_tokens=300,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            return self._parse_response(text, market_price, market)
        except Exception as exc:
            log.error("Erro na chamada Claude API (market=%s): %s",
                      question[:40], exc)
            return self._no_bet(market, f"Erro API: {exc}")

    # ─────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────

    def _parse_response(self, text: str, market_price: float, market: dict) -> dict:
        """Extrai probabilidade e recomendação do texto da resposta."""
        # PROBABILIDADE: XX%
        prob_match = re.search(
            r"PROBABILIDADE:\s*(\d+(?:\.\d+)?)\s*%", text, re.IGNORECASE
        )
        if not prob_match:
            log.warning("Não foi possível parsear probabilidade: %s", text[:120])
            return self._no_bet(market, "parse error")

        estimated_prob = float(prob_match.group(1)) / 100.0
        estimated_prob = max(0.01, min(0.99, estimated_prob))

        # CONFIANÇA: alta|média|baixa
        conf_match = re.search(
            r"CONFIANÇA:\s*(alta|m[eé]dia|baixa)", text, re.IGNORECASE
        )
        confidence = conf_match.group(1).lower() if conf_match else "baixa"
        if confidence == "media":
            confidence = "média"

        # RACIOCÍNIO: ...
        reasoning_match = re.search(
            r"RACIOC[IÍ]NIO:\s*(.+)", text, re.DOTALL | re.IGNORECASE
        )
        reasoning = (
            reasoning_match.group(1).strip()[:400]
            if reasoning_match
            else text[:200]
        )

        # Cálculo do edge
        edge = estimated_prob - market_price          # >0 → YES, <0 → NO
        abs_edge = abs(edge)
        direction = "YES" if edge >= 0 else "NO"

        # Recomendação: precisa de edge suficiente E confiança aceitável
        should_bet = abs_edge >= self.min_edge and confidence != "baixa"

        if should_bet:
            log.info(
                "Edge encontrado: '%s' | est=%.1f%% mkt=%.1f%% edge=%.1f%% dir=%s conf=%s",
                market.get("question", "")[:55],
                estimated_prob * 100, market_price * 100,
                abs_edge * 100, direction, confidence,
            )
        else:
            log.debug(
                "Sem edge: '%s' | est=%.1f%% mkt=%.1f%% edge=%.1f%% conf=%s",
                market.get("question", "")[:55],
                estimated_prob * 100, market_price * 100,
                abs_edge * 100, confidence,
            )

        return {
            "estimated_prob": estimated_prob,
            "market_price":   market_price,
            "edge":           edge,
            "abs_edge":       abs_edge,
            "direction":      direction,
            "reasoning":      reasoning,
            "confidence":     confidence,
            "should_bet":     should_bet,
        }

    def _no_bet(self, market: dict, reason: str) -> dict:
        price = float(market.get("market_price", 0.5))
        return {
            "estimated_prob": price,
            "market_price":   price,
            "edge":           0.0,
            "abs_edge":       0.0,
            "direction":      "NO",
            "reasoning":      reason,
            "confidence":     "baixa",
            "should_bet":     False,
        }
