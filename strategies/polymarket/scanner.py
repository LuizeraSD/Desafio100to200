"""
Polymarket Scanner — busca mercados ativos com edge potencial.

Usa a Gamma Markets API (https://gamma-api.polymarket.com/markets) para buscar
mercados já filtrados server-side (active, volume mínimo, não fechados).
Isso reduz de ~340k mercados paginados via CLOB para ~100-500 resultados úteis.

O CLOB client (py-clob-client) ainda é usado para:
  - get_last_trade_price() → atualização de P&L das posições abertas

Cache em disco:
  Os candidatos filtrados são salvos em state/polymarket_candidates.json com
  timestamp. Na reinicialização, o cache é reutilizado enquanto não expirar
  (padrão: 4h, configurável via candidates_cache_ttl_minutes).
"""
import asyncio
import json
import logging
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

log = logging.getLogger("polymarket.scanner")

try:
    from py_clob_client.client import ClobClient
    _CLOB_AVAILABLE = True
except ImportError:
    _CLOB_AVAILABLE = False
    log.warning("py-clob-client não instalado — get_last_price indisponível")

CLOB_HOST = "https://clob.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"
_MAX_CANDIDATES = 20  # máximo de mercados passados ao modelo por ciclo
_CACHE_FILE = Path(__file__).resolve().parent.parent.parent / "state" / "polymarket_candidates.json"


class PolymarketScanner:
    """
    Busca mercados ativos no Polymarket com volume > min_volume_usd.
    Usa Gamma Markets API (filtros server-side) em vez de paginar CLOB.

    Cache em disco (state/polymarket_candidates.json):
      - Válido por `candidates_cache_ttl_minutes` (padrão: 240 = 4h)
      - Carregado automaticamente na inicialização
      - Re-fetch só ocorre quando o TTL expira
    """

    def __init__(self, config: dict):
        self.cfg = config
        self.min_volume = float(config.get("min_volume_usd", 50_000))
        self.categories: set[str] = set(c.lower() for c in config.get("categories", []))
        self._cache_ttl = int(config.get("candidates_cache_ttl_minutes", 240)) * 60

        # CLOB client apenas para get_last_trade_price (P&L)
        self._client: "ClobClient | None" = None
        if _CLOB_AVAILABLE:
            self._client = ClobClient(host=CLOB_HOST)

        log.info(
            "PolymarketScanner pronto (Gamma API, min_vol=$%.0f, cache_ttl=%dmin)",
            self.min_volume, self._cache_ttl // 60,
        )

        # Cache em memória
        self._cached_candidates: list[dict] = []
        self._cache_timestamp: float = 0.0
        self._disk_cache_loaded: bool = False

        # Sinaliza parada para _fetch_markets (roda em thread)
        self._stop_event = threading.Event()

    async def get_candidates(self) -> list[dict]:
        """
        Retorna lista de mercados candidatos (do cache ou buscando na API).

        Campos retornados:
          - question, description, market_price, volume_usd, end_date,
            category, condition_id, token_yes_id, token_no_id
        """
        now = time.time()

        # Carrega cache do disco apenas na primeira chamada
        if not self._disk_cache_loaded:
            self._disk_cache_loaded = True
            self._load_disk_cache()

        # Retorna cache se ainda válido
        if self._cached_candidates and (now - self._cache_timestamp) < self._cache_ttl:
            age_min = (now - self._cache_timestamp) / 60
            log.info(
                "Scanner: cache válido — %d candidatos (age=%.0fmin, ttl=%dmin)",
                len(self._cached_candidates), age_min, self._cache_ttl // 60,
            )
            return self._cached_candidates

        # Cache expirado ou ausente → busca na Gamma API
        log.info("Scanner: cache expirado ou ausente — buscando mercados na Gamma API...")
        loop = asyncio.get_event_loop()
        try:
            candidates = await loop.run_in_executor(None, self._fetch_markets)
            self._cached_candidates = candidates
            self._cache_timestamp = time.time()
            self._save_disk_cache()
            log.info("Scanner: %d mercados candidatos encontrados e cacheados", len(candidates))
            return candidates
        except Exception as exc:
            log.error("Erro ao buscar mercados Polymarket: %s", exc)
            if self._cached_candidates:
                log.warning(
                    "Scanner: retornando cache expirado como fallback (%d candidatos)",
                    len(self._cached_candidates),
                )
                return self._cached_candidates
            return []

    # ─────────────────────────────────────────────
    # Cache em disco
    # ─────────────────────────────────────────────

    def _load_disk_cache(self) -> None:
        """Carrega candidatos salvos do disco (state/polymarket_candidates.json)."""
        if not _CACHE_FILE.exists():
            return
        try:
            with open(_CACHE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            self._cached_candidates = data.get("candidates", [])
            self._cache_timestamp = float(data.get("timestamp", 0.0))
            age_min = (time.time() - self._cache_timestamp) / 60
            log.info(
                "Scanner: cache carregado do disco — %d candidatos (age=%.0fmin)",
                len(self._cached_candidates), age_min,
            )
        except Exception as exc:
            log.warning("Scanner: erro ao carregar cache do disco: %s", exc)
            self._cached_candidates = []
            self._cache_timestamp = 0.0

    def _save_disk_cache(self) -> None:
        """Salva candidatos filtrados em disco de forma atômica."""
        try:
            _CACHE_FILE.parent.mkdir(exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=_CACHE_FILE.parent, suffix=".tmp", text=True)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(
                        {"timestamp": self._cache_timestamp, "candidates": self._cached_candidates},
                        f, indent=2, ensure_ascii=False,
                    )
            except Exception:
                os.unlink(tmp_path)
                raise
            os.replace(tmp_path, _CACHE_FILE)
            log.debug("Scanner: cache salvo em disco (%s)", _CACHE_FILE)
        except Exception as exc:
            log.warning("Scanner: erro ao salvar cache em disco: %s", exc)

    # ─────────────────────────────────────────────
    # Fetch via Gamma Markets API (executado em thread pool)
    # ─────────────────────────────────────────────

    def _fetch_markets(self) -> list[dict]:
        """Busca mercados ativos via Gamma API com filtros server-side.

        Em vez de paginar 340k+ mercados via CLOB, a Gamma API permite:
          - active=true, closed=false  → só mercados abertos
          - volume_num_min             → filtra volume server-side
          - order=volume, ascending=false → já ordenado por volume

        Resultado: ~2-5 requests HTTP em vez de ~340+.
        """
        all_markets: list[dict] = []
        offset = 0
        limit = 100  # resultados por página
        _MAX_PAGES = 10  # segurança: máximo 1000 mercados
        _REQUEST_TIMEOUT = 30.0

        for page in range(_MAX_PAGES):
            if self._stop_event.is_set():
                break

            params = {
                "active": "true",
                "closed": "false",
                "archived": "false",
                "limit": str(limit),
                "offset": str(offset),
                "order": "volume",
                "ascending": "false",
            }
            # Filtra volume server-side quando possível
            if self.min_volume > 0:
                params["volume_num_min"] = str(int(self.min_volume))

            try:
                resp = httpx.get(
                    f"{GAMMA_API}/markets",
                    params=params,
                    timeout=_REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                log.error("Gamma API erro (página %d): %s", page, exc)
                break

            if not data or not isinstance(data, list):
                break

            all_markets.extend(data)
            log.info(
                "Scanner: página %d — %d mercados recebidos (total: %d)",
                page, len(data), len(all_markets),
            )

            # Menos resultados que o limit → última página
            if len(data) < limit:
                break

            offset += limit

            # Delay entre páginas
            if not self._stop_event.is_set():
                time.sleep(0.3)

        return self._filter_and_format(all_markets)

    def _filter_and_format(self, raw_markets: list[dict]) -> list[dict]:
        """Filtragem local complementar (preço, data, tokens).

        A maioria dos filtros pesados (active, volume) já foi aplicada
        server-side pela Gamma API. Aqui só validamos campos obrigatórios
        e formatamos para o modelo.

        Schema da Gamma API (campos relevantes):
          - conditionId: str (hex)
          - question, description: str
          - outcomePrices: JSON string '["0.493", "0.507"]' → [YES_price, NO_price]
          - clobTokenIds: JSON string '["token_yes_id", "token_no_id"]'
          - outcomes: JSON string '["Yes", "No"]'
          - volumeNum: float, endDateIso: str, endDate: str (ISO 8601)
        """
        now = datetime.now(timezone.utc)
        candidates: list[dict] = []

        for m in raw_markets:
            try:
                # ── Volume ───────────────────────────────────────────────
                volume = float(m.get("volumeNum") or m.get("volume") or 0)

                # ── Categoria ────────────────────────────────────────────
                category = str(m.get("category") or "").lower()
                if not category:
                    tags = m.get("tags") or []
                    if tags and isinstance(tags, list):
                        first = tags[0]
                        category = (
                            first.get("label", "") if isinstance(first, dict) else str(first)
                        ).lower()

                if self.categories and category and category not in self.categories:
                    continue

                # ── Data de resolução ────────────────────────────────────
                end_date_str = m.get("endDate") or m.get("endDateIso") or ""
                if end_date_str:
                    try:
                        end_dt = datetime.fromisoformat(
                            end_date_str.replace("Z", "+00:00")
                        )
                        if end_dt <= now:
                            continue
                    except ValueError:
                        pass

                # ── Preços YES/NO (Gamma: outcomePrices como JSON string) ─
                prices_raw = m.get("outcomePrices") or "[]"
                if isinstance(prices_raw, str):
                    prices = json.loads(prices_raw)
                else:
                    prices = prices_raw
                if not prices or len(prices) < 2:
                    continue

                market_price = float(prices[0])  # YES price
                if not (0.02 <= market_price <= 0.98):
                    continue

                # ── Token IDs (Gamma: clobTokenIds como JSON string) ─────
                tokens_raw = m.get("clobTokenIds") or "[]"
                if isinstance(tokens_raw, str):
                    token_ids = json.loads(tokens_raw)
                else:
                    token_ids = tokens_raw
                if not token_ids or len(token_ids) < 2:
                    continue

                token_yes_id = token_ids[0]
                token_no_id = token_ids[1]

                # ── Condition ID ─────────────────────────────────────────
                condition_id = m.get("conditionId") or m.get("condition_id") or ""
                if not condition_id:
                    continue

                # ── Aceitando ordens? ────────────────────────────────────
                if m.get("enableOrderBook") is False or m.get("acceptingOrders") is False:
                    continue

                candidates.append({
                    "question":     m.get("question", ""),
                    "description":  m.get("description", ""),
                    "market_price": market_price,
                    "volume_usd":   volume,
                    "end_date":     end_date_str,
                    "category":     category,
                    "condition_id": condition_id,
                    "token_yes_id": token_yes_id,
                    "token_no_id":  token_no_id,
                })

            except Exception as exc:
                log.debug("Erro ao processar mercado: %s", exc)

        candidates.sort(key=lambda x: x["volume_usd"], reverse=True)
        log.info(
            "Scanner: %d/%d mercados passaram nos filtros",
            len(candidates), len(raw_markets),
        )
        return candidates[:_MAX_CANDIDATES]

    def stop(self) -> None:
        """Sinaliza parada para _fetch_markets."""
        self._stop_event.set()
        log.info("Scanner: parada sinalizada")

    def get_last_price_sync(self, token_id: str) -> float | None:
        """Preço atual de um token via CLOB (síncrono, usar via run_in_executor)."""
        if not self._client or not token_id:
            return None
        try:
            result = self._client.get_last_trade_price(token_id)
            price = result.get("price") if isinstance(result, dict) else result
            return float(price) if price is not None else None
        except Exception as exc:
            log.debug("get_last_price(%s): %s", token_id, exc)
            return None
