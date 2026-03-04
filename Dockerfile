FROM python:3.11-slim

WORKDIR /app

# Build deps (gcc para compilar extensões C do ccxt/pandas)
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

# Python deps primeiro — aproveita cache de layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código da aplicação
COPY . .

# Garante que os diretórios existem
# (o volume DO sobrescreve /app/state/ em runtime, mas o mkdir não prejudica)
RUN mkdir -p /app/state /app/logs

RUN chmod +x /app/start.sh

EXPOSE 8501

CMD ["/app/start.sh"]
