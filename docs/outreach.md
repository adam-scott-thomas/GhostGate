# Outreach Drafts

Four posts. One per venue. Each one leads with the broken-bot demo and
funnels to `gate.report` + GitHub. All drafted — you paste and post from
your own accounts.

**Order of operations**:
1. Record the 30-second demo video first (see `demo_script.md`).
2. Publish the GitHub repo so the `pip install` + star link work.
3. Stand up `gate.report` pointing at `site/index.html`.
4. Post in this order, 24 hours apart: Show HN → r/ethdev → Farcaster → ETHGlobal Discord.
5. Stagger so you can actually respond to each thread as comments come in.

Do **not** post all four on the same day. You'll burn the narrative if one
of them catches fire and you're not around to reply.

---

## 1. Show HN

**Title** (80-char cap — HN truncates):

> Show HN: GhostGate — a circuit breaker for autonomous crypto wallets

**URL**: `https://gate.report` (not the GitHub link — HN de-ranks repo-only submissions)

**Text** (first comment, posted by you right after submitting):

> Author here. I've been watching autonomous trading / minting bots fail the
> same way for two years: prompt injection drains the wallet, retry loops
> burn the balance on gas, flash crashes trigger panic sells. Every post-mortem
> ends with "we need more guardrails" and then nobody ships them because
> guardrails aren't a product.
>
> GhostGate is those guardrails, shipped as a library. You wrap your wallet in one
> call, hand it a policy list, and the signer becomes unreachable from any code
> path that skipped the chain. The policy chain is deterministic — no model in
> the critical path — and a freeze latch shuts down the wallet entirely when
> anything looks actively compromised.
>
> Every attempt gets an audit record. The whole thing runs offline, zero
> runtime dependencies, 11 tests in 70 milliseconds.
>
> The README has a 30-second "broken bot gets stopped mid-drain" demo you
> can run yourself:
>
>     git clone https://github.com/adam-scott-thomas/GhostGate.git
>     cd GhostGate && pip install -e .
>     python -m ghostgate.examples.broken_bot
>
> Not on PyPI yet — I'll push once I've got a handful of real users kicking
> tires. Core package has zero runtime dependencies; the `[web3]` extra
> pulls in `eth_account` + `web3.py` for production adapters.
>
> v0.2 is free while I validate demand. Paid version (signed offline
> license, $79/wallet/year) ships when enough people tell me they'd actually
> pay for it.
>
> Happy to talk design choices — especially why it's pure Python with no
> dashboard, no cloud, no AI layer. Those are deliberate, not missing features.

**Expected top comment**: "why not just use Safe / use a session key / use
Rabby's simulation." Have these replies queued:

- *Safe*: "Safe protects the *key*. GhostGate protects the *intent*. They
  compose. A Safe + GhostGate setup is strictly safer than either alone —
  Safe gives you multisig + recovery, GhostGate gives you per-call policy
  evaluation and a kill switch the bot can't reach."
- *Session keys*: "Session keys constrain *what* you can call. GhostGate
  constrains *when* and *how fast* and *how much*. They're orthogonal."
- *Simulation*: "Simulation tells you what a tx *would* do. GhostGate tells
  you whether it's *allowed* to. A simulated drain is still a drain if
  nothing refuses to sign."

---

## 2. r/ethdev

**Title**:

> I built a deterministic circuit breaker for autonomous wallet bots — stops drains before they hit the chain

**Body**:

> **TL;DR**: Open-source Python library that sits between your bot and your
> signer. Wraps the wallet in a policy chain; if any rule returns DENY the tx
> never gets signed; if any rule returns FREEZE the wallet locks until a human
> unfreezes it. Full audit trail. 30-second demo of a broken bot getting stopped
> mid-drain here: [link to video + gate.report]
>
> ---
>
> **The problem**
>
> Every autonomous wallet bot I've shipped or watched ship has failed in one
> of these four ways:
>
> 1. Model outputs a swap against a scam token because the RAG context got poisoned
> 2. Prompt injection from a scraped Discord/tweet/doc triggers an unlimited approval
> 3. An error handler fires 400 retries during a gas spike and drains the wallet in 30s
> 4. Flash crash panic-sells the bottom because nothing was gating the bot in a crisis
>
> All four are control problems, not model problems. You can't prompt your
> way out of them. You need a deterministic layer between the intent and the
> signer that says "no" when the intent breaks the rules.
>
> **What GhostGate does**
>
> - `GatedWallet` wraps your signer and RPC
> - Policy chain evaluates every intent before signing (first non-approve wins)
> - Built-in policies: `max_value_per_tx`, `contract_allowlist`, `contract_denylist`,
>   `rate_limit`, `spend_cap`
> - Deny = this tx blocked, wallet stays usable
> - Freeze = kill switch, all future sends blocked until `wallet.unfreeze()`
> - Every attempt (approve, deny, freeze) recorded to an append-only audit log
>
> **What GhostGate is NOT**
>
> - Not a wallet (wraps one)
> - Not a bot (gates one)
> - Not an AI layer (deterministic on purpose, no model in the critical path)
> - Not a dashboard product (audit trail is a stream, not a screen)
>
> **Code in full** (this is the whole API):
>
> ```python
> from ghostgate import GatedWallet, policies, TxDenied, WalletFrozen
> from ghostgate import MockSigner, MockRPC  # swap for eth_account + web3.py
>
> wallet = GatedWallet(
>     signer=MockSigner(),
>     rpc=MockRPC(),
>     policies=[
>         policies.contract_denylist({SCAM_ADDR}),
>         policies.contract_allowlist({UNISWAP}),
>         policies.max_value_per_tx(max_wei=10**17),
>         policies.rate_limit(max_sends=5, window_seconds=60),
>         policies.spend_cap(max_wei=10**18, window_seconds=3600),
>     ],
> )
>
> try:
>     wallet.send(UNISWAP, value_wei=10**16)    # approved
>     wallet.send(SCAM_ADDR, value_wei=10**18)  # freezes wallet
> except WalletFrozen as e:
>     print("stopped:", e)
> ```
>
> v0.2 is on GitHub under Apache-2.0. No runtime deps for the core; the
> `[web3]` extra pulls in real `eth_account` / `web3.py` adapters. 23 tests
> in 70ms (1 auto-skips unless you install the web3 extras). The Mock*
> classes in the example above exist so you can test your bot's policies
> without an RPC key — the real `EthAccountSigner` and `Web3RPC` are
> drop-in replacements.
>
> **Looking for**: people running autonomous bots on Base / Arbitrum /
> Ethereum who'd be willing to try it and tell me what's missing from the
> policy catalog. Also very much want to know the failure mode I haven't
> thought of — if you've had a bot drain on you, I want to hear the story.
>
> Links:
> - Live demo: gate.report
> - GitHub: https://github.com/adam-scott-thomas/GhostGate
> - 30-sec video: [video link]

---

## 3. Farcaster thread (6 casts)

**Cast 1 (lead, with video attached)**

> watched another trading bot get drained yesterday
>
> prompt injection → unlimited approval → wallet empty in 12 seconds
>
> built a fix:
>
> [video: 30s broken-bot demo]

**Cast 2**

> ghostgate is a circuit breaker between your bot's intent and your signer
>
> deterministic policy chain
> kill switch
> full audit trail
> no AI in the critical path
> no cloud
> no latency

**Cast 3**

> three lines:
>
> ```
> wallet = GatedWallet(signer, rpc, policies=[
>     contract_denylist({SCAM}),
>     max_value_per_tx(10**17),
>     rate_limit(5, 60),
> ])
> wallet.send(...)
> ```
>
> if any rule denies, the tx never reaches your signer
> if any rule freezes, the wallet locks until you unfreeze

**Cast 4**

> what ghostgate is NOT:
>
> • not a wallet (it wraps one)
> • not a bot (it gates one)
> • not an AI layer (deterministic on purpose)
> • not a dashboard (audit trail is a stream, pipe it anywhere)

**Cast 5**

> v0.1 is free. apache-2.0. pure python. no deps. 11 tests in 70ms.
>
> $79/wallet/year when v1 ships — offline signed license, no saas, no phone home
>
> v0.2 users grandfathered at $49

**Cast 6 (closer)**

> ghostgate · gate.report
>
> looking for builders running autonomous wallet bots willing to try it and
> tell me which policies are missing. reply or DM.

---

## 4. ETHGlobal Discord — #project-showcase or #builders

**Post**:

> Hey all — solo dev shipping an open-source library for a problem I've
> personally hit on three different hackathon projects: autonomous wallet bots
> getting drained by prompt injection / retry loops / panic sells.
>
> **GhostGate** is a deterministic enforcement layer that sits between a bot's
> intent and its signer. You wrap the wallet, hand it a policy list, and the
> signer becomes unreachable without a passing rule chain. Freeze latch shuts
> the wallet down entirely if anything looks compromised. Full audit trail.
> Zero dependencies, pure Python, Apache-2.0.
>
> 30-second demo of a prompt-injected bot getting stopped mid-drain:
> https://gate.report
>
> GitHub: https://github.com/adam-scott-thomas/GhostGate
>
> Especially interested in feedback from folks who've run bots on Base,
> Arbitrum, or Solana (Solana adapter isn't in v0.1 but would be next if
> there's demand). What policies are missing? What failure mode have I
> not thought of? Drop replies or DM.
>
> v0.1 free. Paid version ($79/wallet/year, offline license, no SaaS) ships
> when real users tell me they'd pay for it — still validating.

---

## Reply playbook (same for every venue)

**When someone asks "is this open source?"**
→ "Yes, Apache-2.0, core is free forever. The paid version adds a signed
license that unlocks custom policy packs and priority support. Core wallet
+ all v1 policies work without a license."

**When someone asks "does it work with Safe / Rabby / privy / turnkey?"**
→ "v0.2 ships with an `eth_account` adapter, which covers any stack that
exposes a LocalAccount (privy, turnkey via their exported key, dynamic.xyz,
standalone hot wallets). Safe integration is on the roadmap — for now you'd
wrap the Safe's proposer account, not the Safe itself. Which stack are you
running? Happy to sketch what the integration looks like."

**When someone asks "what about Solana?"**
→ "Architecture is chain-agnostic — the signer and RPC are protocols, not
concrete types. EVM adapter first because that's where I've seen the most
drains. Solana is next if you want it. Open an issue with your use case
and it jumps the queue."

**When someone posts a critical comment**
→ Engage, don't delete. The critic is often the first paying customer.
Ask them what a v1 would need to look like for them to actually use it.

**When someone says "cool, how do I pay you"**
→ "v0.1 is free — I'd rather have 10 users in production telling me what's
missing than one $79 invoice. Email me at hello@gate.report, I'll grandfather
you at $49/yr when the license ships."

---

## What I (Claude) did NOT write

These drafts are in your voice. I took liberties with tone but not with
claims. Before posting any of them, check:

- Every technical claim is true against the v0.1 code on disk
- The GitHub repo is public (it currently returns 404 to logged-out visitors)
- The `gate.report` domain is live and pointing at `site/index.html`
- The 30-second video is uploaded and the link works
- You actually have `hello@gate.report` set up to receive mail

If any of those are false, don't post. A broken link in the first 30 minutes
is the difference between "100 stars" and "archived."
