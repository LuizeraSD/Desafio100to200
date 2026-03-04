"""
StateManager — persistência atômica de estado JSON por estratégia.

Cada estratégia salva seu estado em state/<id>.json após cada mudança
relevante (abertura de grid, fill, novo trade, aposta).

Escrita atômica: escreve em arquivo temporário → renomeia.
Isso garante que um crash no meio da escrita nunca corrumpe o arquivo anterior.

Semântica de ciclo de vida:
  - save_state()  : chamado após qualquer mudança de estado
  - load_state()  : chamado na inicialização para retomar
  - clear_state() : chamado após close_all() intencional (circuit breaker, meta atingida)
                    Sinaliza que o próximo restart deve começar do zero.

Reconectar vs. limpar:
  - Se o arquivo existe → bot crashou → tentar recuperar
  - Se o arquivo não existe → encerramento limpo → começar do zero
"""
import json
import logging
import os
import tempfile
from pathlib import Path

log = logging.getLogger("state_manager")

STATE_DIR = Path(__file__).resolve().parent.parent / "state"


def save_state(strategy_id: str, data: dict) -> None:
    """Salva estado em JSON de forma atômica (write + rename)."""
    STATE_DIR.mkdir(exist_ok=True)
    target = STATE_DIR / f"{strategy_id}.json"
    try:
        fd, tmp_path = tempfile.mkstemp(dir=STATE_DIR, suffix=".tmp", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            os.unlink(tmp_path)
            raise
        os.replace(tmp_path, target)
    except Exception as exc:
        log.error("Erro ao salvar estado '%s': %s", strategy_id, exc)


def load_state(strategy_id: str) -> dict | None:
    """
    Carrega estado salvo. Retorna None se não existir ou estiver corrompido.
    None = bot foi encerrado corretamente (ou primeira execução).
    """
    path = STATE_DIR / f"{strategy_id}.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log.warning(
            "Estado corrompido para '%s' (%s) — ignorando e começando do zero",
            strategy_id, exc,
        )
        return None


def clear_state(strategy_id: str) -> None:
    """
    Remove arquivo de estado após encerramento limpo.
    O próximo restart saberá que deve iniciar do zero.
    """
    path = STATE_DIR / f"{strategy_id}.json"
    if path.exists():
        try:
            path.unlink()
            log.debug("Estado '%s' removido (encerramento limpo)", strategy_id)
        except Exception as exc:
            log.warning("Erro ao remover estado '%s': %s", strategy_id, exc)
