# GhostWallet — [gate.report](https://gate.report)

[English](README.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Русский](README.ru.md) · **Deutsch**

[![status](https://img.shields.io/badge/status-v0.2-blue)]()
[![tests](https://img.shields.io/badge/tests-23%2F24_passing-brightgreen)]()
[![python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![license](https://img.shields.io/badge/license-Apache_2.0-green)]()
[![deps](https://img.shields.io/badge/runtime_deps-zero-green)]()

> **Gate entscheidet nicht, was zu tun ist. Es entscheidet, was geschehen darf.**
>
> *Wickle deine Wallet in 3 Zeilen ein. GhostWallet stoppt schlechte Transaktionen.*

**GhostWallet** ist die deterministische Durchsetzungsschicht zwischen der Absicht eines Bots und einer On-Chain-Transaktion. Es ist der Circuit Breaker zwischen deinem autonomen Trading- / Minting- / DeFi-Agenten und einer leergeräumten Wallet.

## Für wen das ist

- Du betreibst einen **autonomen Agenten**, der Transaktionen signiert (DeFi, Minting, NFT-Floors, Arbitrage-Bots)
- Du hast **`eth_account` + `web3.py`** in Produktion und einen Private Key irgendwo unheimlich im Speicher
- Du hast über eine Prompt-Injection-Wallet-Drainage gelesen und gedacht: *„Wie würde ich beweisen, dass mir das nicht passieren kann?"*
- Du willst eine **deterministische, Nicht-LLM-Kontrollschicht** — niemals ein Modell im kritischen Pfad

## Status

v0.2 — reiner Python-Kern, offline, null Laufzeitabhängigkeiten. Echte `eth_account` + `web3.py`-Adapter über `pip install 'ghostgate[web3]'`. **23/24 Tests grün** (1 wird automatisch übersprungen, wenn `eth_account` nicht installiert ist).

v0.2 ist **kostenlos, solange wir die Nachfrage validieren.** Die bezahlte v1.0 liefert eine signierte Offline-Lizenz für **$79 / wallet / year**, sobald genug Betreiber uns sagen, dass sie tatsächlich bezahlen würden. Kein Phone-home, keine Latenz, keine Cloud-Abhängigkeit — niemals.

## Warum es existiert

Autonome Wallet-Bots fallen jedes Mal auf dieselben paar Arten aus:

- Das Modell halluziniert einen Swap und sendet Mittel an einen Scam-Token
- Eine vergiftete Eingabe (Discord-Scrape, Tweet, RAG-Dokument) löst eine unbegrenzte ERC-20-Freigabe an einen bösartigen Vertrag aus
- Gas-Spike plus Retry-Schleife leeren die Wallet in 30 Sekunden
- Flash-Crash-Panikverkauf am Boden, weil nichts den Bot in einer Krise gestoppt hat

Jedes einzelne davon ist ein *Kontroll*-Problem, kein Modell-Problem. Man kann sich nicht herausprompten. Die Lösung ist eine deterministische Schicht zwischen der Absicht des Agenten und dem Signer, die „nein" sagt, wenn die Absicht die Regeln bricht — und die gesamte Wallet einfriert, wenn die Dinge aktiv kompromittiert aussehen.

Das ist GhostWallet.

## Was es macht

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

Kein Policy-Pass = keine Signatur. Der Signer ist aus keinem Codepfad erreichbar, der die Kette übersprungen hat.

## 30-Sekunden-Beispiel

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

Vollständig lauffähige Version: [`examples/broken_bot.py`](examples/broken_bot.py).

## Policy-Primitive

Alle eingebauten leben in `ghostgate.policies`:

| Policy | Ergebnis | Einsatz |
|---|---|---|
| `max_value_per_tx(max_wei)` | deny | Harte Obergrenze für eine einzelne Transaktion |
| `contract_allowlist({...})` | deny | Nur benannte Ziele erlaubt |
| `contract_denylist({...})` | **freeze** | Bekanntermaßen schlechte Adresse = Not-Aus |
| `rate_limit(n, window_s)`   | **freeze** | Burst-Erkennung |
| `spend_cap(max_wei, window_s)` | deny | Ausgabenlimit im rollierenden Fenster |

Eigene Regeln sind einfach Callables:

```python
def only_business_hours(intent, state):
    import time
    hour_utc = time.gmtime().tm_hour
    if not (13 <= hour_utc <= 21):  # 9am-5pm EST
        return Decision("deny", "outside trading hours", "business_hours")
    return None
```

Zwei Ergebnisse sind wichtig:

- **`deny`** — diese eine Transaktion wird blockiert, die Wallet bleibt nutzbar
- **`freeze`** — die Wallet ist gegen *alle* zukünftigen Sends gesperrt, bis ein Mensch `wallet.unfreeze()` aufruft

Verwende `freeze`, wenn der Versuch selbst schon Beweis für eine Kompromittierung ist. Verwende `deny` für routinemäßige Geschäftsbeschränkungen.

## Kill Switch

```python
wallet.freeze("operator panic button")  # manual
wallet.state.frozen                     # -> True
wallet.unfreeze()                       # explicit release
```

Eine eingefrorene Wallet lehnt jeden Send mit `WalletFrozen` ab, bevor die Policy-Chain überhaupt läuft.

## Audit-Trail

Jeder Versuch — genehmigt, abgelehnt oder eingefroren — wird aufgezeichnet.

```python
for entry in wallet.audit.entries():
    print(entry.decision.outcome, entry.intent.to, entry.decision.reason)

wallet.audit.approved()   # tuple of records
wallet.audit.denied()
wallet.audit.frozen()
```

Beispielausgabe nach dem obigen 30-Sekunden-Beispiel:

```
approved 0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D  all policies passed
frozen   0xDeadBeef00000000000000000000000000000000  attempted send to denylisted address
frozen   0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D  wallet frozen at 2026-04-22T04:57:10Z
```

Datensätze sind über `entry.to_dict()` JSON-serialisierbar für den Export — streame sie in dein SIEM, hänge sie an SQLite an oder veröffentliche sie in einer hash-verketteten Audit-Senke wie `gate-compliance` / `ghostseal`.

## Installation

Noch nicht auf PyPI. Aus den Quellen:

```bash
git clone https://github.com/adam-scott-thomas/GhostGate.git
cd GhostGate
pip install -e .               # core: zero runtime deps
pip install -e '.[dev]'        # + pytest
pip install -e '.[web3]'       # + eth_account + web3.py (production adapters)
pytest                         # 23 passing, 1 skipped unless web3 extras installed
python -m ghostgate.examples.broken_bot
```

### Die echten Adapter verwenden

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

Die Adapter-Schicht ist duck-typed — alles, was sich wie ein `LocalAccount` oder `Web3` verhält, funktioniert, einschließlich Test-Fakes und jedem zukünftigen drop-in-kompatiblen Signer. `pip install 'ghostgate[web3]'` ist eine Bequemlichkeit, keine Anforderung.

## Preise

| Stufe | Preis | Wallets | Features |
|---|---|---|---|
| **Solo** | **$79 / wallet / year** | 1 | Alle v1-Policies, offline, kein SaaS |
| Pro *(planned)* | $149 / yr | 5 | Eigene Regeln, Audit-Export, priorisierte Patches |
| Desk *(planned)* | $299+ / yr | 25+ | Team-Lizenz, SOC2-Evidenzpaket, Telefonnummer |

Die Lizenz wird ein signiertes Token sein, das offline mit einem eingebetteten öffentlichen Schlüssel verifiziert wird — kein Phone-home, keine zusätzliche Latenz im Transaktionspfad, keine Cloud-Abhängigkeit. v0.2 erzwingt keine Lizenz; die Durchsetzung kommt in v1.0, nachdem wir echte Nachfrage sehen.

## Roadmap

| Version | Liefert | Status |
|---|---|---|
| **v0.1** | Core Wallet, 5 Policies, Audit-Log, Freeze-Latch, broken-bot Demo | ✅ done |
| **v0.2** | `eth_account` + `web3.py`-Adapter unter `[web3]`-Extras | ✅ done |
| v0.3 | Calldata-Pattern-Matcher (markiert `approve(max_uint256)`, `setApprovalForAll` usw.) | planned |
| v0.4 | Persistenter Zustand via SQLite; `gate-compliance`-Audit-Senken-Adapter | planned |
| v0.5 | Policy-Loader aus YAML / `gate-policy`-Konfig | planned |
| v1.0 | Signierte Offline-Lizenz + bezahlte Stufe | nach echter Nachfrage |
| v1.x | Rust-Hot-Path via pyo3 / maturin | Härtungsphase |

Alles in der Roadmap unterliegt echtem Nutzer-Feedback. Wenn niemand Calldata-Pattern-Matching verlangt, aber drei Leute Solana verlangen, drängelt sich Solana in die Warteschlange vor.

## Wie es ins Gate-Ökosystem passt

GhostWallet ist die Wallet-Schutz-Deployment des **Maelstrom Gate**-Governance-Standards — dasselbe mentale Modell, angewandt auf einen Krypto-Signer: Absichten fließen durch eine deterministische Policy-Chain mit Audit-Trail.

GhostWallet bleibt eigenständig mit **null harten Abhängigkeiten** von anderen Gate-Paketen. Die Audit-Senke und der Policy-Loader sind Protokolle, sodass `gate-policy`, `gate-compliance` und Freunde sich einstecken lassen, ohne die Wallet selbst zu berühren. Du kannst GhostWallet für immer standalone fahren oder es in einen größeren Agent-Governance-Stack einbauen, wenn du bereit bist.

## Was das NICHT ist

- Keine Wallet (es wickelt eine ein)
- Kein Bot (es gated einen)
- Keine AI-Schicht (es ist absichtlich deterministisch — niemals ein Modell im kritischen Pfad)
- Kein Dashboard-First-Produkt (Sichtbarkeit ist eine Folge des Audit-Trails, nicht der Zweck)

Es ist eine Sache: **eine Kontrollschicht, die entscheidet, was geschehen darf.**

## Feedback

v0.2 ist der Punkt, an dem wir herausfinden, ob jemand $79/wallet/year dafür zahlen will. Jede Entscheidung in der Roadmap wird davon getrieben, was echte Betreiber fragen.

- **Betreibst du einen autonomen Wallet-Bot?** Öffne ein Issue und sag uns, welcher Angriffsvektor dich nachts nicht schlafen lässt — genau das kommt als Nächstes.
- **Eine Policy gefunden, die du willst, die aber nicht da ist?** Issue + Code-Skizze willkommen. Eigene Policies sind einfach Callables, die eine `Decision` zurückgeben — PRs mit guten Tests werden schnell gemerged.
- **Willst du eine bezahlte Stufe?** Sag es laut. Die Lizenzdurchsetzung kommt erst, wenn genug Betreiber das sagen.

## Lizenz

Apache-2.0.
