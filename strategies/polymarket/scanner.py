"""
Polymarket Scanner — busca mercados ativos com edge potencial.

Usa py-clob-client (API síncrona) via asyncio.run_in_executor para não bloquear
o event loop. Retorna mercados candidatos ordenados por volume decrescente.

Cache em disco:
  Os candidatos filtrados são salvos em state/polymarket_candidates.json com
  timestamp. Na reinicialização, o cache é reutilizado enquanto não expirar
  (padrão: 4h, configurável via candidates_cache_ttl_minutes). Isso evita as
  centenas de requisições HTTP a cada restart.
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

log = logging.getLogger("polymarket.scanner")

try:
    from py_clob_client.client import ClobClient
    _CLOB_AVAILABLE = True
except ImportError:
    _CLOB_AVAILABLE = False
    log.warning("py-clob-client não instalado — PolymarketScanner desabilitado")

CLOB_HOST = "https://clob.polymarket.com"
_MAX_CANDIDATES = 20  # máximo de mercados passados ao modelo por ciclo
_CACHE_FILE = Path(__file__).resolve().parent.parent.parent / "state" / "polymarket_candidates.json"


class PolymarketScanner:
    """
    Busca mercados ativos no Polymarket com volume > min_volume_usd.
    Filtra por categorias configuradas e data de resolução futura.
    Retorna lista de mercados candidatos para o ProbabilityModel.

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

        self._client: "ClobClient | None" = None
        if _CLOB_AVAILABLE:
            self._client = ClobClient(host=CLOB_HOST)
            log.info("PolymarketScanner pronto (host=%s, cache_ttl=%dmin)", CLOB_HOST, self._cache_ttl // 60)

        # Cache em memória
        self._cached_candidates: list[dict] = []
        self._cache_timestamp: float = 0.0
        self._disk_cache_loaded: bool = False  # flag: leitura do disco já tentada?

        # Sinaliza parada para _fetch_markets (roda em thread, não pode ser cancelado por asyncio)
        self._stop_event = threading.Event()

    async def get_candidates(self) -> list[dict]:
        """
        Retorna lista de mercados candidatos (do cache ou buscando na API).

        Campos retornados:
          - question, description, market_price, volume_usd, end_date,
            category, condition_id, token_yes_id, token_no_id
        """
        if not _CLOB_AVAILABLE or self._client is None:
            log.warning("py-clob-client indisponível — retornando lista vazia")
            return []

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

        # Cache expirado ou ausente → busca na API
        log.info("Scanner: cache expirado ou ausente — buscando mercados na CLOB API...")
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
            # Em caso de falha, retorna cache expirado se disponível
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
    # Fetch síncrono (executado em thread pool)
    # ─────────────────────────────────────────────

    def _fetch_markets(self) -> list[dict]:
        """Paginação completa da CLOB API + filtragem.

        Inclui delay entre páginas (evita rate limit) e retry com backoff
        em caso de erro transiente (a API corta conexão após muitos requests seguidos).
        """
        all_markets: list[dict] = []
        next_cursor: str | None = None
        page = 0
        _PAGE_DELAY = 0.3        # segundos entre páginas
        _MAX_RETRIES = 3         # retries por página com erro
        _RETRY_BASE_DELAY = 5.0  # backoff: 5s, 10s, 20s

        while not self._stop_event.is_set():
            # Delay entre páginas para evitar rate limit
            if page > 0:
                time.sleep(_PAGE_DELAY)

            resp = None
            for retry in range(_MAX_RETRIES):
                if self._stop_event.is_set():
                    break
                try:
                    if next_cursor:
                        resp = self._client.get_markets(next_cursor=next_cursor)
                    else:
                        resp = self._client.get_markets()
                    break  # sucesso
                except Exception as exc:
                    wait = _RETRY_BASE_DELAY * (2 ** retry)
                    log.warning(
                        "CLOB get_markets erro (página %d, tentativa %d/%d): %s — retry em %.0fs",
                        page, retry + 1, _MAX_RETRIES, exc, wait,
                    )
                    if retry < _MAX_RETRIES - 1:
                        # Espera com checagem de stop a cada segundo
                        for _ in range(int(wait)):
                            if self._stop_event.is_set():
                                break
                            time.sleep(1)
                    else:
                        log.error(
                            "CLOB get_markets: falha após %d tentativas na página %d — "
                            "retornando %d mercados coletados até agora",
                            _MAX_RETRIES, page, len(all_markets),
                        )

            if resp is None:
                break  # todas as retries falharam ou stop sinalizado

            # Resposta pode ser lista direta ou dict paginado
            if isinstance(resp, list):
                all_markets.extend(resp)
                break
            else:
                data = resp.get("data", [])
                all_markets.extend(data)
                next_cursor = resp.get("next_cursor")
                if not next_cursor or next_cursor in ("LTE=", ""):
                    break

            page += 1
            if page % 50 == 0:
                log.info("Scanner: %d páginas processadas (%d mercados)...", page, len(all_markets))

        return self._filter_and_format(all_markets)

    def _filter_and_format(self, raw_markets: list[dict]) -> list[dict]:
        """Aplica filtros de estado/data/preço e normaliza campos.

        Nota sobre volume: o endpoint /markets do CLOB API não retorna dados de
        volume por mercado. O filtro min_volume_usd só é aplicado quando o campo
        está presente na resposta; do contrário, o mercado é aceito.

        Nota sobre categoria: a CLOB API retorna o campo `category` diretamente
        (string) além de `tags`. Se nenhum bater com a lista configurada, o
        mercado ainda é aceito (categorias servem apenas como preferência).
        """
        now = datetime.now(timezone.utc)
        candidates: list[dict] = []

        for m in raw_markets:
            try:
                # ── Ativo e não fechado (campos presentes no objeto de mercado) ─
                if m.get("active") is False or m.get("closed") is True:
                    continue

                # ── Volume (opcional: CLOB API frequentemente não retorna) ─────
                volume = float(
                    m.get("volume") or m.get("volumeNum") or m.get("volume24hr") or 0
                )
                if self.min_volume > 0 and volume > 0 and volume < self.min_volume:
                    continue  # Filtra só quando o campo existe e está abaixo do mínimo

                # ── Categoria (melhor esforço: `category` direto ou via tags) ──
                category = str(m.get("category") or "").lower()
                if not category:
                    tags = m.get("tags") or []
                    if tags and isinstance(tags, list):
                        first = tags[0]
                        category = (
                            first.get("label", "") if isinstance(first, dict) else str(first)
                        ).lower()

                # Filtra por categoria apenas se a API retornou uma e não bate
                if self.categories and category and category not in self.categories:
                    continue

                # ── Data de resolução ────────────────────────────────────────
                end_date_str = (
                    m.get("end_date_iso")
                    or m.get("endDateIso")
                    or m.get("end_date")
                    or ""
                )
                if end_date_str:
                    try:
                        end_dt = datetime.fromisoformat(
                            end_date_str.replace("Z", "+00:00")
                        )
                        if end_dt <= now:
                            continue  # Mercado já encerrado
                    except ValueError:
                        pass

                # ── Tokens YES / NO ──────────────────────────────────────────
                tokens: list[dict] = m.get("tokens") or []
                token_yes = next(
                    (t for t in tokens if str(t.get("outcome", "")).upper() == "YES"),
                    None,
                )
                token_no = next(
                    (t for t in tokens if str(t.get("outcome", "")).upper() == "NO"),
                    None,
                )
                if not token_yes:
                    continue

                market_price = float(token_yes.get("price", 0) or 0)
                if not (0.02 <= market_price <= 0.98):
                    continue  # Já resolvido ou sem preço significativo

                candidates.append({
                    "question":     m.get("question", ""),
                    "description":  m.get("description", ""),
                    "market_price": market_price,
                    "volume_usd":   volume,
                    "end_date":     end_date_str,
                    "category":     category,
                    "condition_id": m.get("condition_id", ""),
                    "token_yes_id": token_yes.get("token_id", ""),
                    "token_no_id":  token_no.get("token_id", "") if token_no else "",
                })

            except Exception as exc:
                log.debug("Erro ao processar mercado: %s", exc)

        candidates.sort(key=lambda x: x["volume_usd"], reverse=True)
        log.info(
            "Scanner: %d/%d mercados passaram nos filtros (volume/categoria/data/preço)",
            len(candidates), len(raw_markets),
        )
        return candidates[:_MAX_CANDIDATES]

    def stop(self) -> None:
        """Sinaliza parada para _fetch_markets (encerra loop de paginação na próxima iteração)."""
        self._stop_event.set()
        log.info("Scanner: parada sinalizada")

    def get_last_price_sync(self, token_id: str) -> float | None:
        """Preço atual de um token (síncrono, usar via run_in_executor)."""
        if not self._client or not token_id:
            return None
        try:
            result = self._client.get_last_trade_price(token_id)
            price = result.get("price") if isinstance(result, dict) else result
            return float(price) if price is not None else None
        except Exception as exc:
            log.debug("get_last_price(%s): %s", token_id, exc)
            return None
