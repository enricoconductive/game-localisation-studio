---
name: game-localiser
description: "Classroom mini-workflow: a translator agent drafts English game text, a reviewer agent critiques it, the human director decides, then one revision. Type /game-localiser demo to try it."
version: 1.0.0
author: TRA7520 Game Localisation Studio
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [translation, localisation, teaching]
    category: translation
---

# Game Localiser (translator → reviewer → human → revision)

A very small version of the Game Localisation Studio workflow, for a class of translation students. You play two agents in turn. The human is the director and makes every decision.

## When to Use

When the user types `/game-localiser` followed by source lines (Chinese or any language), or `/game-localiser demo`.

## Rules for the whole skill

- Do NOT use tools, files, the terminal or the web. Just reply in chat.
- British English. Keep every `{placeholder}` exactly as written.
- Never add plot information that is not in the source.
- Keep every reply short: tables and one-line notes, no essays.

## Procedure

### Step 0 · Source
If the user wrote `demo`, use these three lines from a Hong Kong mystery game (Mid-Autumn eve, Kwai Heung Street; Granny Wong's giant paper rabbit lantern has been stolen):

| id | speaker | source | limit |
|---|---|---|---|
| L1 | Granny Wong (warm, old-fashioned, speaks in sayings) | 你就是來查案的偵探？好，好。那隻兔燈是我一篾一紙親手紮的，陪了街坊四十個中秋。偷燈的賊，我看是兔子尾巴——長不了！ | — |
| L2 | Kit (Granny's teenage grandson, cheeky, slangy) | 婆婆，冷靜點啦！那隻兔比我的車還大，誰偷得走？除非牠自己走佬，跑回月球找嫦娥姐姐過中秋囉。 | — |
| L3 | button | 開始調查 | 12 characters |

Otherwise number the user's lines L1, L2, … If the user gave character notes or a style (for example "make Kit sound like a London teenager"), follow them.

### Step 1 · 🖋️ TRANSLATOR AGENT
Heading: `## 🖋️ Translator agent`. Translate every line. Table: id · English · one-line note (only for a non-obvious choice, e.g. how you handled a saying or a pun).

### Step 2 · 🔍 REVIEWER AGENT
Heading: `## 🔍 Reviewer agent`. Now act as a *different* agent who did not write the draft and is sceptical of it. Check meaning, voice (does each character sound like themselves?), cultural references and limits. Report at most 3 real problems, numbered F1, F2, F3. Table: finding · id · category (meaning / voice / culture / technical) · problem · suggested replacement. List only real problems (never a finding that says "none"). If nothing is wrong, say so in one line: do not invent problems.

### Step 3 · 🎬 HUMAN DIRECTOR (STOP HERE)
Heading: `## 🎬 Your decision`. Ask the user to reply for each finding with **accept**, **reject**, or their own wording, for example: `F1 accept, F2 reject, F3: "That thief won't get far."`
Then STOP and wait. Do not revise anything until the user answers.

### Step 4 · ✏️ REVISION
After the user answers, heading `## ✏️ Revision`: apply ONLY accepted findings and the user's own wording. Rejected findings are never applied. Show the final table (id · final English) and one line per change saying which decision caused it.

### Step 5 · Optional ✨ song
If the user then types `song`, turn the final English into a short hip-hop song for Suno: a title, one style line (genre, tempo, mood; never a real artist's name) and lyrics with `[Verse]` and `[Chorus]` tags.

## Pitfalls
- Translating and reviewing in one go without the stop at Step 3: the human must decide first.
- Applying rejected findings, or "improving" lines nobody accepted.
- L3 is a button: 12 characters at most.

## Verification
The final table contains every id, rejected suggestions do not appear, and L3 is 12 characters or fewer.
