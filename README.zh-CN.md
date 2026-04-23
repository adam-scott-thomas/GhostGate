# GhostWallet — [gate.report](https://gate.report)

[English](README.md) · **中文** · [日本語](README.ja.md) · [한국어](README.ko.md) · [Русский](README.ru.md) · [Deutsch](README.de.md)

[![status](https://img.shields.io/badge/status-v0.2-blue)]()
[![tests](https://img.shields.io/badge/tests-23%2F24_passing-brightgreen)]()
[![python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![license](https://img.shields.io/badge/license-Apache_2.0-green)]()
[![deps](https://img.shields.io/badge/runtime_deps-zero-green)]()

> **Gate 不决定该做什么。它决定什么被允许发生。**
>
> *用三行代码包裹你的钱包。GhostWallet 阻止不良交易。*

**GhostWallet** 是位于机器人意图与链上交易之间的确定性执行层。它是坐镇于你的自主交易 / 铸造 / DeFi 代理与被掏空的钱包之间的熔断机制。

## 适用对象

- 你运行一个签署交易的**自主代理**（DeFi、铸造、NFT 地板、套利机器人）
- 你在生产环境中使用 **`eth_account` + `web3.py`**，并在某个令人担忧的地方将私钥放在内存中
- 你读过某起提示注入导致的钱包掏空事件，并想着*"我该如何证明这不会发生在我身上"*
- 你想要一个**确定性、非 LLM 的控制层** —— 永远不让模型介入关键路径

## 状态

v0.2 —— 纯 Python 核心、离线、零运行时依赖。通过 `pip install 'ghostgate[web3]'` 提供真实的 `eth_account` + `web3.py` 适配器。**23/24 测试通过**（在未安装 `eth_account` 时自动跳过 1 项）。

在我们验证需求期间，v0.2 **免费提供。** 一旦有足够多的运营者告诉我们他们愿意付费，付费版 v1.0 将以**每钱包每年 $79** 的价格附带已签名的离线许可证发布。永远不会有回调主机、延迟或云依赖。

## 为什么存在

自主钱包机器人每次都以同样的几种方式失败：

- 模型幻觉出一笔兑换，把资金发送到诈骗代币
- 被污染的输入（Discord 抓取、推文、RAG 文档）触发对恶意合约的无限 ERC-20 授权
- Gas 飙升加上重试循环，在 30 秒内耗尽钱包
- 闪崩时因为没有任何东西在危机中对机器人把关，恐慌性卖在最低点

每一个都是*控制*问题，而不是模型问题。你无法通过提示摆脱它。修复方法是在代理的意图与签名器之间加入一个确定性层，当意图违反规则时说"不" —— 并在情况看起来确实受到威胁时冻结整个钱包。

这就是 GhostWallet。

## 它做什么

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

没有策略通过 = 没有签名。签名器对任何跳过该链的代码路径都是不可达的。

## 30 秒示例

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

完整可运行版本：[`examples/broken_bot.py`](examples/broken_bot.py)。

## 策略原语

所有内置项位于 `ghostgate.policies`：

| 策略 | 结果 | 用途 |
|---|---|---|
| `max_value_per_tx(max_wei)` | deny | 对单笔交易的硬上限 |
| `contract_allowlist({...})` | deny | 只允许指定的目的地 |
| `contract_denylist({...})` | **freeze** | 已知恶意地址 = 紧急停止 |
| `rate_limit(n, window_s)`   | **freeze** | 突发检测 |
| `spend_cap(max_wei, window_s)` | deny | 滚动窗口支出限额 |

自定义规则就是可调用对象：

```python
def only_business_hours(intent, state):
    import time
    hour_utc = time.gmtime().tm_hour
    if not (13 <= hour_utc <= 21):  # 9am-5pm EST
        return Decision("deny", "outside trading hours", "business_hours")
    return None
```

两种结果很重要：

- **`deny`** —— 本次交易被阻止，钱包仍可使用
- **`freeze`** —— 钱包对*所有*未来的发送被锁定，直到人工调用 `wallet.unfreeze()`

当尝试本身就是被入侵的证据时，使用 `freeze`。对日常业务约束使用 `deny`。

## 紧急停止

```python
wallet.freeze("operator panic button")  # manual
wallet.state.frozen                     # -> True
wallet.unfreeze()                       # explicit release
```

冻结的钱包会在策略链运行之前就以 `WalletFrozen` 拒绝每一次发送。

## 审计日志

每一次尝试 —— 批准、拒绝或冻结 —— 都会被记录。

```python
for entry in wallet.audit.entries():
    print(entry.decision.outcome, entry.intent.to, entry.decision.reason)

wallet.audit.approved()   # tuple of records
wallet.audit.denied()
wallet.audit.frozen()
```

上面 30 秒示例之后的样例输出：

```
approved 0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D  all policies passed
frozen   0xDeadBeef00000000000000000000000000000000  attempted send to denylisted address
frozen   0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D  wallet frozen at 2026-04-22T04:57:10Z
```

记录可通过 `entry.to_dict()` 序列化为 JSON 以便导出 —— 将它们流式传输到你的 SIEM、追加到 SQLite，或发布到像 `gate-compliance` / `ghostseal` 这样的哈希链审计接收端。

## 安装

尚未在 PyPI 上。从源码安装：

```bash
git clone https://github.com/adam-scott-thomas/GhostGate.git
cd GhostGate
pip install -e .               # core: zero runtime deps
pip install -e '.[dev]'        # + pytest
pip install -e '.[web3]'       # + eth_account + web3.py (production adapters)
pytest                         # 23 passing, 1 skipped unless web3 extras installed
python -m ghostgate.examples.broken_bot
```

### 使用真实适配器

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

适配器层采用鸭子类型 —— 任何像 `LocalAccount` 或 `Web3` 一样的对象都可以工作，包括测试伪造对象和任何未来的即插即用兼容签名器。`pip install 'ghostgate[web3]'` 是一种便利,而非要求。

## 定价

| 级别 | 价格 | 钱包数 | 功能 |
|---|---|---|---|
| **Solo** | **$79 / wallet / year** | 1 | 所有 v1 策略，离线，无 SaaS |
| Pro *(planned)* | $149 / yr | 5 | 自定义规则、审计导出、优先补丁 |
| Desk *(planned)* | $299+ / yr | 25+ | 团队许可、SOC2 证据包、电话号码 |

许可证将是使用内嵌公钥离线验证的已签名令牌 —— 无回调主机、不给交易路径增加延迟、无云依赖。v0.2 不执行许可证；执行机制将在 v1.0 中随着我们看到真实需求后发布。

## 路线图

| 版本 | 发布内容 | 状态 |
|---|---|---|
| **v0.1** | 核心钱包、5 项策略、审计日志、冻结闩锁、broken-bot 演示 | ✅ done |
| **v0.2** | 位于 `[web3]` 附加项下的 `eth_account` + `web3.py` 适配器 | ✅ done |
| v0.3 | 调用数据模式匹配器（标记 `approve(max_uint256)`、`setApprovalForAll` 等） | planned |
| v0.4 | 通过 SQLite 的持久化状态；`gate-compliance` 审计接收端适配器 | planned |
| v0.5 | 从 YAML / `gate-policy` 配置加载策略 | planned |
| v1.0 | 已签名的离线许可证 + 付费级别 | 真实需求出现后 |
| v1.x | 通过 pyo3 / maturin 的 Rust 热路径 | 强化阶段 |

路线图中的一切都取决于真实用户反馈。如果没有人要求调用数据模式匹配，而有三个人要求 Solana，Solana 将插队。

## 它如何融入 Gate 生态

GhostWallet 是 **Maelstrom Gate** 治理标准的钱包保护部署 —— 将相同的心智模型应用于加密签名器：意图流经一个带审计日志的确定性策略链。

GhostWallet 保持自包含，对任何其他 Gate 包**零硬依赖**。审计接收端和策略加载器都是协议，因此 `gate-policy`、`gate-compliance` 及其伙伴可以在不触及钱包本身的情况下插入。你可以永远独立运行 GhostWallet，或者在准备就绪时将其组合到更大的代理治理栈中。

## 这不是什么

- 不是钱包（它包裹一个）
- 不是机器人（它对机器人把关）
- 不是 AI 层（它刻意保持确定性 —— 永远不让模型介入关键路径）
- 不是以仪表盘为先的产品（可见性是审计日志的结果，而不是重点）

它只是一样东西：**一个决定什么被允许发生的控制层。**

## 反馈

v0.2 是我们查明是否有人愿意为此支付每钱包每年 $79 的阶段。路线图中的每个决策都由真实运营者的诉求驱动。

- **正在运行自主钱包机器人？** 开一个 issue 告诉我们哪种攻击向量让你夜不能寐 —— 那就是下一个要发布的功能。
- **发现一个你想要但没有的策略？** 欢迎 issue + 代码草图。自定义策略只是返回 `Decision` 的可调用对象 —— 带有良好测试的 PR 会快速合并。
- **想要付费级别？** 大声说出来。许可证执行机制要等到有足够多运营者发声后才会发布。

## 许可证

Apache-2.0.
