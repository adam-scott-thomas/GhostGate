# GhostGate — [gate.report](https://gate.report)

[English](README.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · **Русский** · [Deutsch](README.de.md)

[![status](https://img.shields.io/badge/status-v0.2-blue)]()
[![tests](https://img.shields.io/badge/tests-23%2F24_passing-brightgreen)]()
[![python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![license](https://img.shields.io/badge/license-Apache_2.0-green)]()
[![deps](https://img.shields.io/badge/runtime_deps-zero-green)]()

> **Gate не решает, что делать. Он решает, что разрешено.**
>
> *Оберните ваш кошелёк в 3 строки. GhostGate останавливает плохие транзакции.*

**GhostGate** — это детерминированный слой принуждения между намерением бота и транзакцией в блокчейне. Это аварийный выключатель между вашим автономным агентом для торговли / минтинга / DeFi и опустошённым кошельком.

## Для кого это

- Вы запускаете **автономный агент**, подписывающий транзакции (DeFi, минтинг, полы NFT, арбитражные боты)
- У вас в продакшене **`eth_account` + `web3.py`** и приватный ключ где-то в памяти, в страшноватом месте
- Вы читали про опустошение кошельков через prompt-injection и подумали: *«как бы мне доказать, что со мной такого не случится»*
- Вам нужен **детерминированный контрольный слой без LLM** — никаких моделей в критическом пути, никогда

## Статус

v0.2 — чисто Python-ядро, оффлайн, нулевые runtime-зависимости. Реальные адаптеры `eth_account` + `web3.py` через `pip install 'ghostgate[web3]'`. **23/24 тестов зелёные** (1 автоматически пропускается, если `eth_account` не установлен).

v0.2 **бесплатна, пока мы проверяем спрос.** Платная v1.0 выйдет с подписанной оффлайн-лицензией по цене **$79 / wallet / year**, когда достаточно операторов скажут нам, что они реально готовы платить. Никаких phone-home, никакой задержки, никакой облачной зависимости — никогда.

## Зачем это существует

Автономные кошельковые боты отказывают одними и теми же несколькими способами:

- Модель галлюцинирует своп и отправляет средства на скам-токен
- Отравленный ввод (парсинг Discord, твит, RAG-документ) запускает безлимитное одобрение ERC-20 на вредоносный контракт
- Скачок газа плюс цикл повтора опустошают кошелёк за 30 секунд
- Паническая распродажа на флэш-крэше на самом дне, потому что ничто не сдерживало бота в кризисе

Каждая из этих ситуаций — проблема *контроля*, а не модели. Промптами от этого не уйти. Решение — детерминированный слой между намерением агента и подписчиком, который говорит «нет», когда намерение нарушает правила — и замораживает весь кошелёк, когда всё выглядит активно скомпрометированным.

Это и есть GhostGate.

## Что он делает

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

Нет прохождения политик — нет подписи. Подписчик недостижим из любого пути кода, который обошёл цепочку.

## Пример на 30 секунд

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

Полная запускаемая версия: [`examples/broken_bot.py`](examples/broken_bot.py).

## Примитивы политик

Все встроенные живут в `ghostgate.policies`:

| Политика | Результат | Применение |
|---|---|---|
| `max_value_per_tx(max_wei)` | deny | Жёсткий лимит на одну транзакцию |
| `contract_allowlist({...})` | deny | Разрешены только указанные адресаты |
| `contract_denylist({...})` | **freeze** | Известный вредоносный адрес = аварийный выключатель |
| `rate_limit(n, window_s)`   | **freeze** | Обнаружение всплесков |
| `spend_cap(max_wei, window_s)` | deny | Лимит расходов в скользящем окне |

Пользовательские правила — это просто вызываемые объекты:

```python
def only_business_hours(intent, state):
    import time
    hour_utc = time.gmtime().tm_hour
    if not (13 <= hour_utc <= 21):  # 9am-5pm EST
        return Decision("deny", "outside trading hours", "business_hours")
    return None
```

Важны два исхода:

- **`deny`** — эта одна транзакция блокируется, кошелёк остаётся работоспособным
- **`freeze`** — кошелёк заблокирован от *всех* будущих отправок, пока человек не вызовет `wallet.unfreeze()`

Используйте `freeze`, когда сама попытка является доказательством компрометации. Используйте `deny` для рутинных бизнес-ограничений.

## Аварийный выключатель

```python
wallet.freeze("operator panic button")  # manual
wallet.state.frozen                     # -> True
wallet.unfreeze()                       # explicit release
```

Замороженный кошелёк отклоняет каждую отправку с `WalletFrozen` ещё до того, как запустится цепочка политик.

## Журнал аудита

Каждая попытка — одобренная, отклонённая или замороженная — записывается.

```python
for entry in wallet.audit.entries():
    print(entry.decision.outcome, entry.intent.to, entry.decision.reason)

wallet.audit.approved()   # tuple of records
wallet.audit.denied()
wallet.audit.frozen()
```

Пример вывода после приведённого выше 30-секундного примера:

```
approved 0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D  all policies passed
frozen   0xDeadBeef00000000000000000000000000000000  attempted send to denylisted address
frozen   0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D  wallet frozen at 2026-04-22T04:57:10Z
```

Записи сериализуются в JSON через `entry.to_dict()` для экспорта — стримьте их в ваш SIEM, добавляйте в SQLite или публикуйте в приёмник аудита с хеш-цепочкой, такой как `gate-compliance` / `ghostseal`.

## Установка

Ещё не в PyPI. Из исходников:

```bash
git clone https://github.com/adam-scott-thomas/GhostGate.git
cd GhostGate
pip install -e .               # core: zero runtime deps
pip install -e '.[dev]'        # + pytest
pip install -e '.[web3]'       # + eth_account + web3.py (production adapters)
pytest                         # 23 passing, 1 skipped unless web3 extras installed
python -m ghostgate.examples.broken_bot
```

### Использование реальных адаптеров

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

Слой адаптеров использует утиную типизацию — всё, что ведёт себя как `LocalAccount` или `Web3`, работает, включая тестовые заглушки и любой будущий drop-in-совместимый подписчик. `pip install 'ghostgate[web3]'` — это удобство, а не требование.

## Цены

| Уровень | Цена | Кошельков | Функции |
|---|---|---|---|
| **Solo** | **$79 / wallet / year** | 1 | Все политики v1, оффлайн, без SaaS |
| Pro *(planned)* | $149 / yr | 5 | Пользовательские правила, экспорт аудита, приоритетные патчи |
| Desk *(planned)* | $299+ / yr | 25+ | Командная лицензия, пакет доказательств SOC2, номер телефона |

Лицензия будет подписанным токеном, проверяемым оффлайн по встроенному публичному ключу — никаких phone-home, никакой задержки в пути транзакции, никакой облачной зависимости. v0.2 не принуждает к лицензии; принуждение выйдет в v1.0 после того, как мы увидим реальный спрос.

## Дорожная карта

| Версия | Поставляет | Статус |
|---|---|---|
| **v0.1** | Ядро кошелька, 5 политик, журнал аудита, защёлка заморозки, broken-bot демо | ✅ done |
| **v0.2** | Адаптеры `eth_account` + `web3.py` под extras `[web3]` | ✅ done |
| v0.3 | Сопоставление паттернов calldata (флажки для `approve(max_uint256)`, `setApprovalForAll` и т. д.) | planned |
| v0.4 | Постоянное состояние через SQLite; адаптер приёмника аудита `gate-compliance` | planned |
| v0.5 | Загрузчик политик из YAML / конфига `gate-policy` | planned |
| v1.0 | Подписанная оффлайн-лицензия + платный уровень | после реального спроса |
| v1.x | Rust hot path через pyo3 / maturin | этап усиления |

Всё в дорожной карте подчиняется реальной обратной связи пользователей. Если никто не просит сопоставление паттернов calldata, а три человека просят Solana — Solana прыгает в очередь вперёд.

## Как он вписывается в экосистему Gate

GhostGate — это развёртывание стандарта управления **Maelstrom Gate** для защиты кошелька — та же ментальная модель, применённая к крипто-подписчику: намерения проходят через детерминированную цепочку политик с журналом аудита.

GhostGate остаётся самодостаточным с **нулевыми жёсткими зависимостями** от любых других пакетов Gate. Приёмник аудита и загрузчик политик — это протоколы, так что `gate-policy`, `gate-compliance` и другие могут подключаться, не касаясь самого кошелька. Вы можете запускать GhostGate автономно всегда или встраивать его в более крупный стек управления агентами, когда будете готовы.

## Чем это НЕ является

- Не кошелёк (он его оборачивает)
- Не бот (он его ограничивает)
- Не AI-слой (он намеренно детерминированный — никакой модели в критическом пути, никогда)
- Не продукт с приоритетом на дашборд (видимость — это следствие журнала аудита, а не цель)

Это одна вещь: **контрольный слой, который решает, что разрешено.**

## Обратная связь

v0.2 — это момент, когда мы узнаем, готов ли хоть кто-то платить $79/wallet/year за это. Каждое решение в дорожной карте определяется тем, что просят реальные операторы.

- **Запускаете автономного кошелькового бота?** Откройте issue, рассказав, какой вектор атаки не даёт вам спать по ночам — именно это поставим следующим.
- **Нашли политику, которую хотели бы иметь, а её нет?** Issue + набросок кода приветствуются. Пользовательские политики — это просто callable, возвращающий `Decision` — PR с хорошими тестами мёржатся быстро.
- **Хотите платный уровень?** Скажите об этом громко. Принуждение к лицензии не выйдет, пока достаточно операторов не скажут этого.

## Лицензия

Apache-2.0.
