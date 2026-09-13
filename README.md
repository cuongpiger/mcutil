# Introduction
- My personal package for Python

## API service

A FastAPI service for fetching current crypto prices from Binance.

### Install

```bash
pip install -r requirements.txt
```

### Run

```bash
uvicorn mcutil.api.app:app --reload
```

### Usage

```bash
# Fetch the current price of Bitcoin
curl http://127.0.0.1:8000/price/BTCUSDT
# {"symbol":"BTCUSDT","price":"77294.00000000"}

# Lowercase is accepted
curl http://127.0.0.1:8000/price/ethusdt
```

### Account management

Create a new account by POSTing a JSON body with the owner's name, sex
(`male`, `female`, or `other`), and starting balance:

```bash
curl -X POST http://127.0.0.1:8000/accounts \
  -H "Content-Type: application/json" \
  -d '{"name":"Alice","sex":"female","balance":5000.0}'
# {"id":1,"name":"Alice","sex":"female","balance":5000.0}
```

Fetch an existing account by its ID:

```bash
curl http://127.0.0.1:8000/accounts/1
# {"id":1,"name":"Alice","sex":"female","balance":5000.0}

# An unknown ID returns 404
curl http://127.0.0.1:8000/accounts/999
# {"detail":"Account not found."}
```

### Tests

```bash
pip install -r requirements-dev.txt
pytest
```
