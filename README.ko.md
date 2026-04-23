# GhostWallet — [gate.report](https://gate.report)

[English](README.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md) · **한국어** · [Русский](README.ru.md) · [Deutsch](README.de.md)

[![status](https://img.shields.io/badge/status-v0.2-blue)]()
[![tests](https://img.shields.io/badge/tests-23%2F24_passing-brightgreen)]()
[![python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![license](https://img.shields.io/badge/license-Apache_2.0-green)]()
[![deps](https://img.shields.io/badge/runtime_deps-zero-green)]()

> **Gate는 무엇을 할지 결정하지 않습니다. 무엇이 일어나도록 허용될지를 결정합니다.**
>
> *3줄로 지갑을 감싸세요. GhostWallet가 나쁜 트랜잭션을 차단합니다.*

**GhostWallet**는 봇의 의도와 온체인 트랜잭션 사이에 있는 결정론적 집행 레이어입니다. 자율 거래 / 민팅 / DeFi 에이전트와 털린 지갑 사이에 자리잡는 서킷 브레이커입니다.

## 대상 사용자

- 트랜잭션에 서명하는 **자율 에이전트**를 운영하는 분 (DeFi, 민팅, NFT 바닥가, 아비트러지 봇)
- 프로덕션에서 **`eth_account` + `web3.py`**를 사용하며 어딘가 불안한 곳에 메모리상의 개인키를 두고 있는 분
- 프롬프트 인젝션 지갑 털이에 대한 이야기를 읽고 *"내게 이런 일이 일어날 수 없다는 것을 어떻게 증명할까"*라고 생각한 분
- **결정론적이고 LLM이 아닌 제어 레이어**를 원하는 분 —— 모델을 크리티컬 패스에 절대 두지 않습니다

## 상태

v0.2 —— 순수 Python 코어, 오프라인, 런타임 의존성 없음. `pip install 'ghostgate[web3]'`를 통해 실제 `eth_account` + `web3.py` 어댑터 제공. **23/24 테스트 통과** (`eth_account`가 설치되지 않은 경우 1개 자동 스킵).

v0.2는 우리가 수요를 검증하는 동안 **무료입니다.** 충분한 운영자들이 실제로 지불할 의사가 있다고 알려주면, 유료 버전 v1.0은 **$79 / wallet / year**로 서명된 오프라인 라이선스와 함께 출시됩니다. 폰 홈 없음, 지연 시간 없음, 클라우드 의존성 없음 —— 절대로.

## 왜 존재하는가

자율 지갑 봇은 매번 같은 몇 가지 방식으로 실패합니다:

- 모델이 스왑을 환각하여 사기 토큰으로 자금을 보냄
- 오염된 입력(Discord 스크랩, 트윗, RAG 문서)이 악성 컨트랙트에 대한 무제한 ERC-20 승인을 트리거함
- 가스 급등과 재시도 루프가 30초 안에 지갑을 비움
- 플래시 크래시 공황 매도가 바닥을 찍음 —— 위기 상황에서 봇을 제어하는 것이 없었기 때문

이 모두가 *제어* 문제이지 모델 문제가 아닙니다. 프롬프트로는 빠져나올 수 없습니다. 해결책은 에이전트의 의도와 서명자 사이에 결정론적 레이어를 두는 것입니다. 그 레이어는 의도가 규칙을 위반했을 때 "아니요"라고 말하고 —— 상황이 능동적으로 침해된 것처럼 보일 때 지갑 전체를 동결합니다.

이것이 GhostWallet입니다.

## 무엇을 하는가

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

정책 통과 없이는 서명도 없습니다. 서명자는 체인을 건너뛴 어떤 코드 경로에서도 도달할 수 없습니다.

## 30초 예제

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

완전히 실행 가능한 버전: [`examples/broken_bot.py`](examples/broken_bot.py).

## 정책 프리미티브

모든 내장 항목은 `ghostgate.policies`에 있습니다:

| 정책 | 결과 | 용도 |
|---|---|---|
| `max_value_per_tx(max_wei)` | deny | 단일 트랜잭션에 대한 하드 캡 |
| `contract_allowlist({...})` | deny | 지정된 대상지만 허용 |
| `contract_denylist({...})` | **freeze** | 알려진 악성 주소 = 킬 스위치 |
| `rate_limit(n, window_s)`   | **freeze** | 버스트 감지 |
| `spend_cap(max_wei, window_s)` | deny | 롤링 윈도우 지출 한도 |

커스텀 규칙은 단순 callable입니다:

```python
def only_business_hours(intent, state):
    import time
    hour_utc = time.gmtime().tm_hour
    if not (13 <= hour_utc <= 21):  # 9am-5pm EST
        return Decision("deny", "outside trading hours", "business_hours")
    return None
```

두 가지 결과가 중요합니다:

- **`deny`** —— 이 트랜잭션은 차단되지만 지갑은 사용 가능한 상태로 유지됩니다
- **`freeze`** —— 사람이 `wallet.unfreeze()`를 호출할 때까지 *모든* 향후 전송에 대해 지갑이 잠깁니다

시도 자체가 침해의 증거일 때는 `freeze`를 사용합니다. 일상적인 비즈니스 제약에는 `deny`를 사용합니다.

## 킬 스위치

```python
wallet.freeze("operator panic button")  # manual
wallet.state.frozen                     # -> True
wallet.unfreeze()                       # explicit release
```

동결된 지갑은 정책 체인이 실행되기도 전에 모든 전송을 `WalletFrozen`으로 거부합니다.

## 감사 추적

모든 시도 —— 승인, 거부 또는 동결 —— 가 기록됩니다.

```python
for entry in wallet.audit.entries():
    print(entry.decision.outcome, entry.intent.to, entry.decision.reason)

wallet.audit.approved()   # tuple of records
wallet.audit.denied()
wallet.audit.frozen()
```

위 30초 예제 이후의 샘플 출력:

```
approved 0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D  all policies passed
frozen   0xDeadBeef00000000000000000000000000000000  attempted send to denylisted address
frozen   0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D  wallet frozen at 2026-04-22T04:57:10Z
```

레코드는 `entry.to_dict()`를 통해 JSON 직렬화 가능하여 내보낼 수 있습니다 —— SIEM으로 스트리밍하거나, SQLite에 추가하거나, `gate-compliance` / `ghostseal`과 같은 해시 체인 감사 싱크에 발행할 수 있습니다.

## 설치

아직 PyPI에 없습니다. 소스에서:

```bash
git clone https://github.com/adam-scott-thomas/GhostGate.git
cd GhostGate
pip install -e .               # core: zero runtime deps
pip install -e '.[dev]'        # + pytest
pip install -e '.[web3]'       # + eth_account + web3.py (production adapters)
pytest                         # 23 passing, 1 skipped unless web3 extras installed
python -m ghostgate.examples.broken_bot
```

### 실제 어댑터 사용

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

어댑터 레이어는 덕 타이핑입니다 —— `LocalAccount`나 `Web3`처럼 동작하는 무엇이든 작동합니다. 테스트용 가짜와 미래의 드롭인 호환 서명자도 포함됩니다. `pip install 'ghostgate[web3]'`는 편의일 뿐 필수가 아닙니다.

## 가격

| 등급 | 가격 | 지갑 | 기능 |
|---|---|---|---|
| **Solo** | **$79 / wallet / year** | 1 | 모든 v1 정책, 오프라인, SaaS 없음 |
| Pro *(planned)* | $149 / yr | 5 | 커스텀 규칙, 감사 내보내기, 우선 패치 |
| Desk *(planned)* | $299+ / yr | 25+ | 팀 라이선스, SOC2 증거 번들, 전화번호 |

라이선스는 내장된 공개 키로 오프라인 검증되는 서명된 토큰이 될 것입니다 —— 폰 홈 없음, 트랜잭션 경로에 지연 시간 추가 없음, 클라우드 의존성 없음. v0.2는 라이선스를 강제하지 않습니다. 강제 집행은 실제 수요를 확인한 후 v1.0에서 출시됩니다.

## 로드맵

| 버전 | 출시 항목 | 상태 |
|---|---|---|
| **v0.1** | 코어 지갑, 5개 정책, 감사 로그, 동결 래치, broken-bot 데모 | ✅ done |
| **v0.2** | `[web3]` extras 아래의 `eth_account` + `web3.py` 어댑터 | ✅ done |
| v0.3 | 콜데이터 패턴 매처 (`approve(max_uint256)`, `setApprovalForAll` 등 플래그) | planned |
| v0.4 | SQLite를 통한 영구 상태; `gate-compliance` 감사 싱크 어댑터 | planned |
| v0.5 | YAML / `gate-policy` 구성에서 정책 로더 | planned |
| v1.0 | 서명된 오프라인 라이선스 + 유료 등급 | 실수요 이후 |
| v1.x | pyo3 / maturin을 통한 Rust 핫 패스 | 강화 단계 |

로드맵의 모든 것은 실제 사용자 피드백에 따릅니다. 콜데이터 패턴 매칭을 요청하는 사람이 없고 세 명이 Solana를 요청한다면, Solana가 줄을 앞당깁니다.

## Gate 생태계에 어떻게 어울리는가

GhostWallet는 **Maelstrom Gate** 거버넌스 표준의 지갑 보호 배포입니다 —— 암호 서명자에 적용된 동일한 사고 모델: 의도는 감사 추적과 함께 결정론적 정책 체인을 통해 흐릅니다.

GhostWallet는 다른 어떤 Gate 패키지에 대해서도 **하드 의존성 없이** 자체 완결성을 유지합니다. 감사 싱크와 정책 로더는 프로토콜이므로, `gate-policy`, `gate-compliance` 등이 지갑 자체를 건드리지 않고 플러그인할 수 있습니다. GhostWallet를 영원히 독립 실행형으로 운영하거나, 준비가 되면 더 큰 에이전트 거버넌스 스택에 구성할 수 있습니다.

## 이것이 아닌 것

- 지갑이 아닙니다 (지갑을 감쌉니다)
- 봇이 아닙니다 (봇을 차단합니다)
- AI 레이어가 아닙니다 (의도적으로 결정론적입니다 —— 모델을 크리티컬 패스에 절대 두지 않습니다)
- 대시보드 우선 제품이 아닙니다 (가시성은 감사 추적의 결과이지 목적이 아닙니다)

그것은 한 가지입니다: **무엇이 일어나도록 허용될지를 결정하는 제어 레이어.**

## 피드백

v0.2는 누군가가 이것에 지갑당 연 $79를 지불할 의사가 있는지 알아보는 단계입니다. 로드맵의 모든 결정은 실제 운영자들이 요청하는 것에 따라 결정됩니다.

- **자율 지갑 봇을 운영 중이신가요?** 어떤 공격 벡터가 밤잠을 설치게 하는지 알려주는 이슈를 열어주세요 —— 그것이 다음에 출시됩니다.
- **원하는 정책이 없나요?** 이슈 + 코드 스케치 환영합니다. 커스텀 정책은 `Decision`을 반환하는 단순한 callable입니다 —— 좋은 테스트가 있는 PR은 빠르게 머지됩니다.
- **유료 등급을 원하시나요?** 크게 말해주세요. 라이선스 강제는 충분한 운영자들이 그렇게 말할 때까지 출시되지 않습니다.

## 라이선스

Apache-2.0.
