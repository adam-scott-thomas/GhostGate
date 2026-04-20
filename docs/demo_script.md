# 30-Second Broken-Bot Demo — Shot List

**Goal**: A single take, one terminal window, one narrator line, one visible result.
No animations. No music. No logos. The output is the product.

**Total runtime**: 30 seconds (hard cap — anything longer loses Twitter/Farcaster)

**Record with**: OBS Studio, 1080p, 30fps, terminal font >= 18pt, dark background.

---

## Prep (do this once before recording)

1. Open a fresh terminal window in `D:\lost_marbles\gate-wallet\`.
2. Maximize the window. Increase font size so code is readable on mobile.
3. Clear the scrollback: `cls` (Windows) or `clear` (bash).
4. Have this command ready to paste: `PYTHONPATH=. python examples/broken_bot.py`
5. Start recording. Give yourself 2 seconds of silent terminal before speaking.

---

## The script (read this verbatim)

> *"This is a trading bot with a wallet.*
>
> *It just got prompt-injected by a poisoned tweet.*
>
> *Watch what happens when Gate is in the middle."*

**[paste the command and hit enter]**

**[let the output scroll — takes under a second]**

> *"Three legit swaps. One drain attempt — blocked. Five panic retries — all dead on arrival. The wallet is frozen until a human unfreezes it.*
>
> *Wrap your wallet in three lines. Gate stops bad transactions.*
>
> *Gate dot report."*

**[stop recording]**

---

## On-screen text overlays (add in post)

| Timestamp | Text | Position |
|---|---|---|
| 0:00 | `gate.report` | top-right, small, mono |
| 0:12 | `BLOCKED` appears next to the drain line | inline |
| 0:20 | `5/5 retries blocked by kill switch` | highlight |
| 0:28 | `gate.report — wrap your wallet in 3 lines` | centered lower third |

---

## Alternative 15-second cut (for Twitter)

Use only phases 1 and 2. Cut the audit dump at the end. Script:

> *"Trading bot. Gets prompt-injected mid-run. Tries to drain to a scam address.*
>
> *Gate stops it cold. Wallet frozen. Zero funds lost.*
>
> *gate.report"*

---

## What NOT to do

- No hero shots of the terminal with rotating gradients. The product is the deny.
- No AI voiceover. Record your own voice, one take, slightly tired is fine.
- No "before Gate / after Gate" split screen. Boring and misleading.
- No mention of pricing, tiers, SOC2, compliance, or the broader Gate ecosystem.
  That's for the landing page. The video has one job: make someone type
  `pip install ghostgate`.

---

## After recording

1. Upload as MP4 (H.264, AAC audio) — not GIF. Gifs kill quality and limit length.
2. Host it three places:
   - GitHub README (at the top, above the code block)
   - `gate.report` landing page (between hero and "how")
   - Twitter / Farcaster / Reddit as the lead media in each post
3. Thumbnail: the frame where `>>> BLOCKED` first appears.
