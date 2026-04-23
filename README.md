# GhostGate — [gate.report](https://gate.report)

**English** · [中文](README.zh-CN.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Русский](README.ru.md) · [Deutsch](README.de.md)

[![status](https://img.shields.io/badge/status-v0.2-blue)]()
[![tests](https://img.shields.io/badge/tests-23%2F24_passing-brightgreen)]()
[![python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![license](https://img.shields.io/badge/license-Apache_2.0-green)]()
[![deps](https://img.shields.io/badge/runtime_deps-zero-green)]()

> **Gate doesn't decide what to do. It decides what is allowed to happen.**
>
> *Wrap your wallet in 3 lines. GhostGate stops bad transactions.*

**GhostGate** is the deterministic enforcement layer between a bot's intent
and an on-chain transaction. It is the circuit breaker that sits between
your autonomous trading / minting / DeFi agent and a drained wallet.

## Who this is for

- You run an **autonomous agent** that signs transactions (DeFi, minting, NFT floors, arb bots)
- You have **`eth_account` + `web3.py`** in production and a private key in memory somewhere scary
- You've read about a prompt-injection wallet drain and thought *"how would I prove that can't happen to me"*
- You want a **deterministic, non-LLM control layer** — no model in the critical path, ever

## Status

v0.2 — pure-Python core, offline, zero runtime deps. Real `eth_account` +
`web3.py` adapters via `pip install 'ghostgate[web3]'`. **23/24 tests green**
(1 auto-skipped when `eth_account` isn't installed).

v0.2 is **free while we validate demand.** Paid v1.0 ships a signed offline
license at **$79 / wallet / year** once enough operators tell us they'd
actually pay for it. No phone-home, no latency, no cloud dependency — ever.

## Why this exists

Autonomous wallet bots fail in the same handful of ways every time:

- Model hallucinates a swap and sends funds to a scam token
- A poisoned input (Discord scrape, tweet, RAG doc) triggers an unlimited
  ERC-20 approval to a malicious contract
- Gas spike plus retry loop drains the wallet in 30 seconds
- Flash crash panic-sells the bottom because nothing was gating the bot in
  a crisis

Every one of these is a *control* problem, not a model problem. You can't
prompt your way out of it. The fix is a deterministic layer between the
agent's intent and the signer that says "no" when the intent breaks the
rules — and freezes the whole wallet when things look actively compromised.

That's GhostGate.

## What it does

```
                +--------+
                |  BOT   |
                +---+----+
                    | send(to, value, data)
                    v
             +---------------+
             |  GatedWallet  |
             +---+-----------+
                 | 1. kill-switch check
                 | 2. policy chain (first non-approve wins)
                 | 3. audit record
                 | 4. sign only if approved
                 | 5. broadcast via RPC
                 v
            +-----------+
            |  Chain    |
            +-----------+
```

No policy pass = no signature. The signer is never reachable from any code
path that skipped the chain.

## 30-second example

```python
from ghostgate import (
    GatedWallet, MockSigner, MockRPC, policies,
    TxDenied, WalletFrozen,
)

UNISWAP = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
SCAM    = "0xDeadBeef00000000000000000000000000000000"

wallet = GatedWallet(
    signer=MockSigner(),  # replace with EthAccountSigner in prod
    rpc=MockRPC(),        # replace with Web3RPC in prod
    policies=[
        policies.contract_denylist({SCAM}),
        policies.contract_allowlist({UNISWAP}),
        policies.max_value_per_tx(max_wei=10**17),          # 0.1 ETH
        policies.rate_limit(max_sends=5, window_seconds=60),
        policies.spend_cap(max_wei=10**18, window_seconds=3600),
    ],
)

# Normal bot behavior -- fine.
wallet.send(UNISWAP, value_wei=10**16)

# Bot gets prompt-injected and tries to drain.
try:
    wallet.send(SCAM, value_wei=10**18)
except WalletFrozen as e:
    print("stopped:", e)     # -> stopped: attempted send to denylisted address ...

# Wallet is now locked. Every subsequent send raises WalletFrozen
# until a human calls wallet.unfreeze().
```

Full runnable version: [`examples/broken_bot.py`](examples/broken_bot.py).

## Policy primitives

All built-ins live in `ghostgate.policies`:

| Policy | Outcome | Use |
|---|---|---|
| `max_value_per_tx(max_wei)` | deny | Hard cap on a single transaction |
| `contract_allowlist({...})` | deny | Only named destinations allowed |
| `contract_denylist({...})` | **freeze** | Known-bad address = kill switch |
| `rate_limit(n, window_s)`   | **freeze** | Burst detection |
| `spend_cap(max_wei, window_s)` | deny | Rolling window spend limit |

Custom rules are just callables:

```python
def only_business_hours(intent, state):
    import time
    hour_utc = time.gmtime().tm_hour
    if not (13 <= hour_utc <= 21):  # 9am-5pm EST
        return Decision("deny", "outside trading hours", "business_hours")
    return None
```

Two outcomes matter:

- **`deny`** — this one transaction is blocked, the wallet stays usable
- **`freeze`** — the wallet is locked against *all* future sends until a
  human calls `wallet.unfreeze()`

Use `freeze` when the attempt itself is evidence of compromise. Use `deny`
for routine business constraints.

## Kill switch

```python
wallet.freeze("operator panic button")  # manual
wallet.state.frozen                     # -> True
wallet.unfreeze()                       # explicit release
```

A frozen wallet rejects every send with `WalletFrozen` before the policy
chain even runs.

## Audit trail

Every attempt — approved, denied, or frozen — is recorded.

```python
for entry in wallet.audit.entries():
    print(entry.decision.outcome, entry.intent.to, entry.decision.reason)

wallet.audit.approved()   # tuple of records
wallet.audit.denied()
wallet.audit.frozen()
```

Sample output after the 30-second example above:

```
approved 0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D  all policies passed
frozen   0xDeadBeef00000000000000000000000000000000  attempted send to denylisted address
frozen   0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D  wallet frozen at 2026-04-22T04:57:10Z
```

Records are JSON-serializable via `entry.to_dict()` for export — stream them to
your SIEM, append to SQLite, or publish to a hash-chained audit sink like
`gate-compliance` / `ghostseal`.

## Install

Not on PyPI yet. From source:

```bash
git clone https://github.com/adam-scott-thomas/GhostGate.git
cd GhostGate
pip install -e .               # core: zero runtime deps
pip install -e '.[dev]'        # + pytest
pip install -e '.[web3]'       # + eth_account + web3.py (production adapters)
pytest                         # 23 passing, 1 skipped unless web3 extras installed
python -m ghostgate.examples.broken_bot
```

### Using the real adapters

```python
import os
from eth_account import Account
from web3 import Web3

from ghostgate import GatedWallet, policies
from ghostgate.adapters import EthAccountSigner, Web3RPC

account = Account.from_key(os.environ["PRIVATE_KEY"])
w3 = Web3(Web3.HTTPProvider(os.environ["RPC_URL"]))

wallet = GatedWallet(
    signer=EthAccountSigner(account),
    rpc=Web3RPC(w3),
    policies=[
        policies.contract_allowlist({UNISWAP}),
        policies.max_value_per_tx(max_wei=10**17),
        policies.rate_limit(max_sends=10, window_seconds=60),
    ],
)

wallet.send(UNISWAP, value_wei=10**16)  # routes through policy chain
```

The adapter layer is duck-typed — anything quacking like a
`LocalAccount` or `Web3` works, including test fakes and any future
drop-in-compatible signer. `pip install 'ghostgate[web3]'` is a
convenience, not a requirement.

## Pricing

| Tier | Price | Wallets | Features |
|---|---|---|---|
| **Solo** | **$79 / wallet / year** | 1 | All v1 policies, offline, no SaaS |
| Pro *(planned)* | $149 / yr | 5 | Custom rules, audit export, priority patches |
| Desk *(planned)* | $299+ / yr | 25+ | Team license, SOC2 evidence bundle, phone number |

License will be a signed token verified offline with an embedded public
key — no phone-home, no latency added to the tx path, no cloud dependency.
v0.2 does not enforce a license; enforcement ships in v1.0 after we see
real demand.

## Roadmap

| Version | Ships | Status |
|---|---|---|
| **v0.1** | Core wallet, 5 policies, audit log, freeze latch, broken-bot demo | ✅ done |
| **v0.2** | `eth_account` + `web3.py` adapters under `[web3]` extras | ✅ done |
| v0.3 | Calldata pattern matcher (flag `approve(max_uint256)`, `setApprovalForAll`, etc.) | planned |
| v0.4 | Persistent state via SQLite; `gate-compliance` audit-sink adapter | planned |
| v0.5 | Policy loader from YAML / `gate-policy` config | planned |
| v1.0 | Signed offline license + paid tier | after real demand |
| v1.x | Rust hot path via pyo3 / maturin | hardening pass |

Everything in the roadmap is subject to real user feedback. If nobody
asks for calldata pattern matching but three people ask for Solana,
Solana jumps the queue.

## How it fits the Gate ecosystem

GhostGate is the wallet-protection deployment of the **Maelstrom Gate**
governance standard — the same mental model applied to a crypto signer:
intents flow through a deterministic policy chain with an audit trail.

GhostGate stays self-contained with **zero hard deps** on any other Gate
package. The audit sink and policy loader are protocols, so `gate-policy`,
`gate-compliance`, and friends can plug in without touching the wallet
itself. You can run GhostGate stand-alone forever, or compose it into a
larger agent-governance stack when you're ready.

## What this is NOT

- Not a wallet (it wraps one)
- Not a bot (it gates one)
- Not an AI layer (it's deterministic on purpose — no model in the
  critical path, ever)
- Not a dashboard-first product (visibility is a consequence of the audit
  trail, not the point)

It is one thing: **a control layer that decides what is allowed to happen.**

## Feedback

v0.2 is where we find out whether anyone wants to pay $79/wallet/year for
this. Every decision in the roadmap is driven by what real operators ask for.

- **Running an autonomous wallet bot?** Open an issue telling us which
  attack vector keeps you up at night — that's what ships next.
- **Found a policy you'd want that isn't there?** Issue + code sketch
  welcome. Custom policies are just callables returning a `Decision` — PRs
  with good tests get merged fast.
- **Want a paid tier?** Say so loudly. The license enforcement doesn't
  ship until enough operators do.

## License

Apache-2.0.
