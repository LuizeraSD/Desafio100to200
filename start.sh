#!/bin/bash
# start.sh — entrypoint do container Docker
#
# Inicia o orchestrator em background e o Streamlit em foreground.
# Se o Streamlit morrer, o container encerra e o Digital Ocean reinicia.
# O orchestrator é filho deste processo e encerra junto.

set -e

PORT=${PORT:-8501}
LOG_DIR=/app/logs
mkdir -p "$LOG_DIR"

echo "[start.sh] Iniciando orchestrator em background..."
python -u orchestrator/main.py 2>&1 | tee "$LOG_DIR/orchestrator.log" &
ORCH_PID=$!
echo "[start.sh] Orchestrator PID=$ORCH_PID"

# Aguarda um momento para o orchestrator inicializar antes do dashboard
sleep 5

echo "[start.sh] Iniciando Streamlit na porta $PORT..."
exec streamlit run dashboard/app.py \
    --server.port "$PORT" \
    --server.headless true \
    --server.address "0.0.0.0" \
    --server.enableCORS false \
    --server.enableXsrfProtection false
