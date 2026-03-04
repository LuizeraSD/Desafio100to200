"""
Polymarket Setup — configura allowances e verifica saldo USDC.e.

Executar UMA VEZ antes de usar o bot em live mode:
  python scripts/polymarket_setup.py

O script:
  1. Conecta à rede Polygon via RPC público (com fallback)
  2. Verifica saldo USDC.e da carteira
  3. Aprova os contratos CLOB Exchange para gastar USDC.e e Conditional Tokens
  4. Mostra o endereço proxy (funder) se aplicável

Variáveis de ambiente necessárias (.env):
  POLY_PRIVATE_KEY  — private key da carteira Polygon (hex, com ou sem 0x)

Referência: https://gist.github.com/poly-rodr/44313920481de58d5a3f6d1f8226bd5e
"""
import os
import re
import sys
import time
from pathlib import Path

# Adiciona raiz do projeto ao path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv()

try:
    from web3 import Web3
    from web3.middleware import ExtraDataToPOAMiddleware
except ImportError:
    print("❌ web3 não instalado. Execute:")
    print("   pip install web3")
    sys.exit(1)

# ── Endereços dos contratos Polymarket na Polygon ────────────────────────────
USDC_E = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC.e (bridged)
CTF    = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"  # Conditional Token Framework
# Exchange contracts que precisam de allowance
EXCHANGE          = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
NEG_RISK_EXCHANGE = "0xC5d563A36AE78145C45a50134d48A1215220f80a"
NEG_RISK_ADAPTER  = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"

RPC_URLS = [
    os.getenv("POLYGON_RPC_URL", "").strip(),
    "https://polygon-rpc.com",
    "https://rpc.ankr.com/polygon",
    "https://1rpc.io/matic",
]
RPC_URLS = [u for u in RPC_URLS if u]  # remove vazios
CHAIN_ID = 137

# ABIs mínimos para approve e setApprovalForAll
ERC20_APPROVE_ABI = [
    {
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

ERC1155_APPROVAL_ABI = [
    {
        "inputs": [
            {"name": "operator", "type": "address"},
            {"name": "approved", "type": "bool"},
        ],
        "name": "setApprovalForAll",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "account", "type": "address"},
            {"name": "operator", "type": "address"},
        ],
        "name": "isApprovedForAll",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
]

MAX_UINT256 = 2**256 - 1

# ── Helpers com retry e fallback ─────────────────────────────────────────────


def create_w3(rpc_url: str) -> Web3:
    """Cria instância Web3 com middleware POA."""
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def connect_best_rpc(pub_key: str) -> tuple:
    """
    Conecta ao RPC que retorna o nonce mais alto (= mais atualizado).
    Resolve o problema de RPCs stale que retornam nonce 0.
    """
    best_w3 = None
    best_nonce = -1
    best_url = ""

    for rpc_url in RPC_URLS:
        try:
            w3 = create_w3(rpc_url)
            if not w3.is_connected():
                continue
            n_latest = w3.eth.get_transaction_count(pub_key, "latest")
            try:
                n_pending = w3.eth.get_transaction_count(pub_key, "pending")
            except Exception:
                n_pending = n_latest
            nonce = max(n_latest, n_pending)
            print(f"   RPC {rpc_url}: nonce={nonce} (latest={n_latest}, pending={n_pending})")
            if nonce > best_nonce:
                best_nonce = nonce
                best_w3 = w3
                best_url = rpc_url
        except Exception as e:
            print(f"   ⚠ RPC {rpc_url}: {e}")
            continue

    if best_w3 is None:
        print("❌ Não foi possível conectar a nenhum RPC Polygon")
        sys.exit(1)

    return best_w3, best_url


def rpc_call_with_retry(fn, max_retries=4, base_delay=3.0):
    """
    Executa uma chamada RPC com retry e backoff exponencial.
    Lida com 429 Too Many Requests e erros transientes.
    """
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            err_str = str(e)
            is_retryable = (
                "429" in err_str
                or "Too Many" in err_str
                or "timeout" in err_str.lower()
                or "connection" in err_str.lower()
            )
            if is_retryable and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"   ⏳ Rate limited, aguardando {delay:.0f}s... (tentativa {attempt + 1}/{max_retries})")
                time.sleep(delay)
                continue
            raise


def poll_receipt(w3, tx_hash, timeout=180):
    """Poll para receipt com backoff, tolerante a 429."""
    deadline = time.time() + timeout
    delay = 3.0
    while time.time() < deadline:
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            if receipt is not None:
                return receipt
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "Too Many" in err_str:
                delay = min(delay * 2, 20)  # backoff até 20s
            # TransactionNotFound é normal, só esperar
        time.sleep(delay)
    return None


def safe_get_nonce(w3, pub_key, delay=2.0):
    """Tenta pegar nonce com retry e backoff."""
    for attempt in range(5):
        try:
            if delay > 0:
                time.sleep(delay)
            n1 = w3.eth.get_transaction_count(pub_key, "latest")
            try:
                n2 = w3.eth.get_transaction_count(pub_key, "pending")
            except Exception:
                n2 = n1
            return max(n1, n2)
        except Exception:
            delay = delay * 2
            continue
    return 0


def send_tx_robust(w3, contract_fn, pub_key, private_key, nonce, label):
    """
    Envia transação com retry, tratamento de nonce e rate limit.
    Retorna (success: bool, new_nonce: int).
    """
    for attempt in range(3):
        try:
            gas_price = rpc_call_with_retry(lambda: w3.eth.gas_price)
            gas_price = max(gas_price * 2, 50_000_000_000)  # min 50 gwei

            tx = contract_fn.build_transaction({
                "chainId": CHAIN_ID,
                "from": pub_key,
                "nonce": nonce,
                "gas": 100_000,
                "gasPrice": gas_price,
            })
            signed = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = rpc_call_with_retry(
                lambda s=signed: w3.eth.send_raw_transaction(s.raw_transaction)
            )
            print(f"   ⏳ tx enviada: {tx_hash.hex()}")
            print(f"   Aguardando confirmação (até 3 min)...")

            # Poll receipt com retry manual (evita crash por 429 no polling)
            receipt = poll_receipt(w3, tx_hash, timeout=180)
            if receipt and receipt["status"] == 1:
                print(f"   ✅ Confirmado no bloco {receipt['blockNumber']}")
                return True, nonce + 1
            elif receipt:
                print(f"   ❌ Tx revertida no bloco {receipt['blockNumber']}")
                return False, nonce + 1
            else:
                # Timeout mas tx pode ter sido minerada — atualizar nonce
                print(f"   ⚠ Timeout aguardando receipt. Tx pode ainda ser minerada.")
                time.sleep(5)
                new_nonce = safe_get_nonce(w3, pub_key)
                if new_nonce > nonce:
                    print(f"   ✅ Nonce avançou ({nonce} → {new_nonce}), tx provavelmente confirmada")
                    return True, new_nonce
                return False, nonce

        except Exception as e:
            err_str = str(e)
            if "nonce too low" in err_str:
                # Extrair nonce correto da mensagem de erro
                match = re.search(r"next nonce (\d+)", err_str)
                if match:
                    correct_nonce = int(match.group(1))
                    print(f"   ⚠ Nonce corrigido: {nonce} → {correct_nonce}")
                    nonce = correct_nonce
                    time.sleep(2)
                    continue
                else:
                    new_nonce = safe_get_nonce(w3, pub_key)
                    print(f"   ⚠ Nonce atualizado: {nonce} → {new_nonce}")
                    nonce = new_nonce
                    continue
            elif "already known" in err_str or "replacement" in err_str:
                print(f"   ⚠ Tx já conhecida pela rede, aguardando...")
                time.sleep(10)
                new_nonce = safe_get_nonce(w3, pub_key)
                return True, new_nonce
            else:
                print(f"   ❌ Erro (tentativa {attempt + 1}/3): {e}")
                if attempt < 2:
                    time.sleep(5)
                    continue
                return False, nonce

    return False, nonce


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    private_key = os.getenv("POLY_PRIVATE_KEY", "").strip()
    if not private_key:
        print("❌ POLY_PRIVATE_KEY não configurada no .env")
        sys.exit(1)

    if not private_key.startswith("0x"):
        private_key = "0x" + private_key

    # ── Derivar endereço antes de conectar ───────────────────────────────────
    temp_w3 = Web3()
    account = temp_w3.eth.account.from_key(private_key)
    pub_key = account.address

    # ── Conectar ao melhor RPC (nonce mais alto) ─────────────────────────────
    print("🔍 Testando RPCs disponíveis...")
    w3, rpc_url = connect_best_rpc(pub_key)
    print(f"✅ RPC selecionado: {rpc_url}")
    print(f"✅ Carteira: {pub_key}")

    # ── Verificar saldo ──────────────────────────────────────────────────────
    matic_bal = rpc_call_with_retry(lambda: w3.eth.get_balance(pub_key))
    matic_eth = w3.from_wei(matic_bal, "ether")
    print(f"   POL/MATIC: {matic_eth:.4f}")

    usdc_contract = w3.eth.contract(address=USDC_E, abi=ERC20_APPROVE_ABI)
    usdc_bal = rpc_call_with_retry(lambda: usdc_contract.functions.balanceOf(pub_key).call())
    usdc_human = usdc_bal / 1e6  # USDC.e tem 6 decimais
    print(f"   USDC.e: ${usdc_human:.2f}")

    if matic_eth < 0.01:
        print("⚠ Saldo POL/MATIC baixo — precisa de gas para aprovar transações")
        print("  Envie ao menos 0.1 MATIC para esta carteira")

    if usdc_human < 1:
        print("⚠ Saldo USDC.e baixo — precisa de USDC.e para fazer apostas")
        print("  Deposite USDC.e (Polygon) nesta carteira")

    if matic_eth < 0.005:
        print("\n!! Sem POL/MATIC para gas. Envie ao menos 0.5 POL para:")
        print(f"   {pub_key}")
        print("   (rede Polygon, não Ethereum)")
        print("\nAbortando — execute novamente após depositar POL.")
        sys.exit(1)

    # ── Verificar e configurar allowances ────────────────────────────────────
    targets = {
        "Exchange": EXCHANGE,
        "NegRiskExchange": NEG_RISK_EXCHANGE,
        "NegRiskAdapter": NEG_RISK_ADAPTER,
    }

    ctf_contract = w3.eth.contract(address=CTF, abi=ERC1155_APPROVAL_ABI)
    nonce = safe_get_nonce(w3, pub_key, delay=0.5)
    print(f"   Nonce atual: {nonce}")
    txs_sent = 0
    tx_errors = 0

    for label, target in targets.items():
        # ── USDC.e allowance ─────────────────────────────────────────────
        try:
            current_allowance = rpc_call_with_retry(
                lambda t=target: usdc_contract.functions.allowance(pub_key, t).call()
            )
        except Exception as e:
            print(f"⚠ Não foi possível verificar allowance USDC.e → {label}: {e}")
            current_allowance = 0

        if current_allowance >= MAX_UINT256 // 2:
            print(f"✅ USDC.e → {label}: allowance já configurado")
        else:
            print(f"🔄 USDC.e → {label}: configurando allowance...")
            contract_fn = usdc_contract.functions.approve(target, MAX_UINT256)
            success, nonce = send_tx_robust(w3, contract_fn, pub_key, private_key, nonce, f"USDC.e→{label}")
            if success:
                txs_sent += 1
            else:
                tx_errors += 1
            # Delay entre transações para evitar rate limit
            time.sleep(3)

        # ── CTF (Conditional Token) approval ─────────────────────────────
        try:
            is_approved = rpc_call_with_retry(
                lambda t=target: ctf_contract.functions.isApprovedForAll(pub_key, t).call()
            )
        except Exception as e:
            print(f"⚠ Não foi possível verificar approval CTF → {label}: {e}")
            is_approved = False

        if is_approved:
            print(f"✅ CTF → {label}: approval já configurado")
        else:
            print(f"🔄 CTF → {label}: configurando approval...")
            contract_fn = ctf_contract.functions.setApprovalForAll(target, True)
            success, nonce = send_tx_robust(w3, contract_fn, pub_key, private_key, nonce, f"CTF→{label}")
            if success:
                txs_sent += 1
            else:
                tx_errors += 1
            # Delay entre transações para evitar rate limit
            time.sleep(3)

    # ── Resumo ───────────────────────────────────────────────────────────────
    print(f"\n{'─' * 50}")
    if tx_errors > 0:
        print(f"⚠ {tx_errors} transação(ões) falharam — execute novamente para completar")
    if txs_sent == 0 and tx_errors == 0:
        print("✅ Todas as allowances já estavam configuradas!")
    elif txs_sent > 0:
        print(f"✅ {txs_sent} transação(ões) de allowance enviadas com sucesso")

    print(f"\nCarteira: {pub_key}")
    print(f"USDC.e: ${usdc_human:.2f}")
    print(f"\nVariáveis para .env:")
    print(f"  POLY_PRIVATE_KEY=<sua chave privada aqui>")
    print(f"\nSe sua conta Polymarket usa proxy wallet (criada via email/browser),")
    print(f"adicione também ao .env:")
    print(f"  POLY_FUNDER=<endereço_proxy_polymarket>")
    print(f"  POLY_SIGNATURE_TYPE=1  (Magic/email) ou 2 (browser wallet)")
    print(f"\nPara descobrir o endereço proxy, veja o campo 'Proxy address'")
    print(f"em https://polymarket.com/settings ao conectar com sua carteira.")


if __name__ == "__main__":
    main()
