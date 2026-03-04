from py_clob_client.client import ClobClient

HOST = "https://clob.polymarket.com"
CHAIN_ID = 137
PRIVATE_KEY = "<sua-chave-privada>"

client = ClobClient(HOST, key=PRIVATE_KEY, chain_id=CHAIN_ID)
api_creds = client.create_or_derive_api_creds()

print("API Key:", api_creds.api_key)
print("Secret:", api_creds.api_secret)
print("Passphrase:", api_creds.api_passphrase)