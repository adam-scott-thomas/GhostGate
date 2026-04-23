# GhostGate — [gate.report](https://gate.report)

[English](README.md) · [中文](README.zh-CN.md) · **日本語** · [한국어](README.ko.md) · [Русский](README.ru.md) · [Deutsch](README.de.md)

[![status](https://img.shields.io/badge/status-v0.2-blue)]()
[![tests](https://img.shields.io/badge/tests-23%2F24_passing-brightgreen)]()
[![python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![license](https://img.shields.io/badge/license-Apache_2.0-green)]()
[![deps](https://img.shields.io/badge/runtime_deps-zero-green)]()

> **Gate は何をするかを決めません。何が起こることを許可するかを決めます。**
>
> *ウォレットを 3 行でラップ。GhostGate は悪い取引を止めます。*

**GhostGate** は、ボットの意図とオンチェーン取引の間に位置する決定論的な実施レイヤーです。自律的な取引 / ミント / DeFi エージェントと、空になったウォレットとの間に座るサーキットブレーカーです。

## 対象者

- 取引に署名する**自律エージェント**を運用している方（DeFi、ミント、NFT フロア、アービトラージボット）
- 本番で **`eth_account` + `web3.py`** を使用し、どこか不安な場所でメモリ内に秘密鍵を保持している方
- プロンプトインジェクションによるウォレット枯渇について読み、*「自分には起こり得ないとどう証明するか」*と考えた方
- **決定論的で LLM ではない制御レイヤー**が欲しい方 —— モデルはクリティカルパスに決して入れません

## ステータス

v0.2 —— 純粋な Python コア、オフライン、ランタイム依存ゼロ。`pip install 'ghostgate[web3]'` で本物の `eth_account` + `web3.py` アダプターが利用可能。**23/24 テストが green**（`eth_account` がインストールされていない場合 1 つが自動スキップ）。

v0.2 は**需要を検証する間、無料です。**十分な数のオペレーターが実際に支払うと伝えてくれた時点で、有料版 v1.0 は**$79 / wallet / year** で署名されたオフラインライセンスとともに出荷されます。フォンホームなし、レイテンシなし、クラウド依存なし —— 永久に。

## なぜ存在するのか

自律型ウォレットボットは、毎回同じような数種類の方法で失敗します：

- モデルがスワップをハルシネーションし、詐欺トークンに資金を送信する
- 汚染された入力（Discord スクレイピング、ツイート、RAG ドキュメント）が悪意あるコントラクトへの無制限の ERC-20 承認をトリガーする
- ガス急騰とリトライループが 30 秒でウォレットを空にする
- フラッシュクラッシュのパニック売りで底値を踏む —— 危機時にボットをゲートするものが何もなかったため

これらはすべて *制御* の問題であり、モデルの問題ではありません。プロンプトで抜け出すことはできません。修正方法は、エージェントの意図とサイナーの間に決定論的なレイヤーを入れることです。そのレイヤーは、意図がルールに違反したときに「ノー」と言い、状況が能動的に侵害されているように見えるときはウォレット全体を凍結します。

それが GhostGate です。

## 何をするのか

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

ポリシーパスがなければ、署名もありません。サイナーは、チェーンをスキップしたコードパスから一切到達できません。

## 30 秒の例

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

完全に実行可能なバージョン：[`examples/broken_bot.py`](examples/broken_bot.py)。

## ポリシープリミティブ

すべての組み込みは `ghostgate.policies` にあります：

| ポリシー | 結果 | 用途 |
|---|---|---|
| `max_value_per_tx(max_wei)` | deny | 単一取引のハードキャップ |
| `contract_allowlist({...})` | deny | 指定された宛先のみ許可 |
| `contract_denylist({...})` | **freeze** | 既知の悪意あるアドレス = キルスイッチ |
| `rate_limit(n, window_s)`   | **freeze** | バースト検知 |
| `spend_cap(max_wei, window_s)` | deny | ローリングウィンドウ支出上限 |

カスタムルールは単なる callable です：

```python
def only_business_hours(intent, state):
    import time
    hour_utc = time.gmtime().tm_hour
    if not (13 <= hour_utc <= 21):  # 9am-5pm EST
        return Decision("deny", "outside trading hours", "business_hours")
    return None
```

2 つの結果が重要です：

- **`deny`** —— この 1 取引はブロックされ、ウォレットは使用可能なまま
- **`freeze`** —— ウォレットは、人間が `wallet.unfreeze()` を呼び出すまで*すべての*今後の送信に対してロックされる

試行自体が侵害の証拠である場合は `freeze` を使用してください。通常のビジネス制約には `deny` を使用してください。

## キルスイッチ

```python
wallet.freeze("operator panic button")  # manual
wallet.state.frozen                     # -> True
wallet.unfreeze()                       # explicit release
```

凍結されたウォレットは、ポリシーチェーンが実行される前にすべての送信を `WalletFrozen` で拒否します。

## 監査証跡

すべての試行 —— 承認、拒否、または凍結 —— は記録されます。

```python
for entry in wallet.audit.entries():
    print(entry.decision.outcome, entry.intent.to, entry.decision.reason)

wallet.audit.approved()   # tuple of records
wallet.audit.denied()
wallet.audit.frozen()
```

上記の 30 秒の例の後のサンプル出力：

```
approved 0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D  all policies passed
frozen   0xDeadBeef00000000000000000000000000000000  attempted send to denylisted address
frozen   0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D  wallet frozen at 2026-04-22T04:57:10Z
```

レコードは `entry.to_dict()` 経由で JSON シリアライズ可能でエクスポートできます —— SIEM にストリーム、SQLite に追記、または `gate-compliance` / `ghostseal` のようなハッシュチェーン監査シンクに発行できます。

## インストール

まだ PyPI にはありません。ソースから：

```bash
git clone https://github.com/adam-scott-thomas/GhostGate.git
cd GhostGate
pip install -e .               # core: zero runtime deps
pip install -e '.[dev]'        # + pytest
pip install -e '.[web3]'       # + eth_account + web3.py (production adapters)
pytest                         # 23 passing, 1 skipped unless web3 extras installed
python -m ghostgate.examples.broken_bot
```

### 本物のアダプターを使う

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

アダプターレイヤーはダックタイピングです —— `LocalAccount` や `Web3` のようにふるまうものは何でも動作します。テスト用フェイクや将来のドロップイン互換サイナーも含まれます。`pip install 'ghostgate[web3]'` は便利であって必須ではありません。

## 価格

| ティア | 価格 | ウォレット数 | 機能 |
|---|---|---|---|
| **Solo** | **$79 / wallet / year** | 1 | すべての v1 ポリシー、オフライン、SaaS なし |
| Pro *(planned)* | $149 / yr | 5 | カスタムルール、監査エクスポート、優先パッチ |
| Desk *(planned)* | $299+ / yr | 25+ | チームライセンス、SOC2 エビデンスバンドル、電話番号 |

ライセンスは、組み込みの公開鍵でオフライン検証される署名付きトークンになります —— フォンホームなし、トランザクションパスへのレイテンシ追加なし、クラウド依存なし。v0.2 はライセンスを強制しません。強制は、実際の需要が見えてから v1.0 で出荷されます。

## ロードマップ

| バージョン | 出荷内容 | ステータス |
|---|---|---|
| **v0.1** | コアウォレット、5 ポリシー、監査ログ、フリーズラッチ、broken-bot デモ | ✅ done |
| **v0.2** | `[web3]` extras 下の `eth_account` + `web3.py` アダプター | ✅ done |
| v0.3 | コールデータパターンマッチャー（`approve(max_uint256)`、`setApprovalForAll` 等をフラグ） | planned |
| v0.4 | SQLite による永続状態；`gate-compliance` 監査シンクアダプター | planned |
| v0.5 | YAML / `gate-policy` 設定からのポリシーローダー | planned |
| v1.0 | 署名付きオフラインライセンス + 有料ティア | 実需要後 |
| v1.x | pyo3 / maturin 経由の Rust ホットパス | 強化フェーズ |

ロードマップのすべては実際のユーザーフィードバックに依存します。もし誰もコールデータパターンマッチングを求めず、3 人が Solana を求めたら、Solana が列に割り込みます。

## Gate エコシステムへのフィット

GhostGate は **Maelstrom Gate** ガバナンス標準のウォレット保護デプロイです —— 暗号サイナーに適用された同じメンタルモデル：意図は監査証跡とともに決定論的なポリシーチェーンを流れます。

GhostGate は他のどの Gate パッケージに対しても**ハード依存ゼロ**で自己完結を維持します。監査シンクとポリシーローダーはプロトコルなので、`gate-policy`、`gate-compliance`、およびその仲間たちは、ウォレット自体に触れることなくプラグインできます。GhostGate をずっとスタンドアロンで実行することも、準備ができたらより大きなエージェントガバナンススタックに組み込むこともできます。

## これは何ではないか

- ウォレットではありません（それをラップします）
- ボットではありません（それをゲートします）
- AI レイヤーではありません（意図的に決定論的です —— モデルはクリティカルパスに決して入れません）
- ダッシュボードファーストのプロダクトではありません（可視性は監査証跡の結果であって、目的ではありません）

それは 1 つのものです：**何が起こることを許可するかを決める制御レイヤー。**

## フィードバック

v0.2 は、このために $79/wallet/year を支払う人がいるかどうかを見極めるところです。ロードマップのすべての決定は、実際のオペレーターが求めるものによって駆動されます。

- **自律型ウォレットボットを運用中ですか？** どの攻撃ベクターが夜も眠れなくさせるかを教える issue をオープンしてください —— それが次に出荷されます。
- **欲しいポリシーがそこにないと気づきましたか？** issue + コードスケッチ歓迎。カスタムポリシーは `Decision` を返す単なる callable です —— 良いテストを持つ PR は素早くマージされます。
- **有料ティアが欲しいですか？** 大きな声で言ってください。ライセンス強制は十分なオペレーターがそう言うまで出荷されません。

## ライセンス

Apache-2.0.
