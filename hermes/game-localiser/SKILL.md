---
name: game-localiser
description: "Classroom multi-agent workflow: you (the producer) spawn a translator subagent and a separate reviewer subagent with delegate_task, the human director decides, then a reviser subagent applies only the accepted changes. Type /game-localiser demo to try it."
version: 2.0.0
author: TRA7520 Game Localisation Studio
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [translation, localisation, teaching, multi-agent]
    category: translation
---

# Game Localiser (producer → translator agent → reviewer agent → human → reviser agent)

A very small version of the Game Localisation Studio workflow, for a class of translation students.

You are the **producer**. You do NOT translate or review yourself. The translation and the review are each done by a **separate subagent** spawned with `delegate_task`. Each subagent has its own isolated context: it sees only what you pass it in `context`. The human is the **director** and makes every decision.

## When to Use

When the user types `/game-localiser` followed by source lines (Chinese or any language), or `/game-localiser demo`.

## Rules for the whole skill

- The only tool you use is `delegate_task`, with ONE task per call. No terminal, files, web or memory.
- Spawn the agents one after another, never in parallel: the reviewer needs the translator's finished draft.
- Every subagent's `context` must say: "Do not use any tools. Reply only with the table asked for." Subagents know nothing of this chat, so pass them everything they need.
- After you dispatch a subagent, write one line (e.g. `🖋️ Translator agent is working…`) and END YOUR TURN. Its result comes back as a new message; then continue with the next step.
- British English. Keep every `{placeholder}` exactly as written. Never add plot information that is not in the source.
- Keep your own messages short: tables and one-line notes.

## Procedure

### Step 0 · Source
If the user wrote `demo`, use these three lines from a Hong Kong mystery game (Mid-Autumn eve, Kwai Heung Street; Granny Wong's giant paper rabbit lantern has been stolen):

| id | speaker | source | limit |
|---|---|---|---|
| L1 | Granny Wong (warm, old-fashioned, speaks in sayings) | 你就是來查案的偵探？好，好。那隻兔燈是我一篾一紙親手紮的，陪了街坊四十個中秋。偷燈的賊，我看是兔子尾巴——長不了！ | — |
| L2 | Kit (Granny's teenage grandson, cheeky, slangy) | 婆婆，冷靜點啦！那隻兔比我的車還大，誰偷得走？除非牠自己走佬，跑回月球找嫦娥姐姐過中秋囉。 | — |
| L3 | button | 開始調查 | 12 characters |

Otherwise number the user's lines L1, L2, … and keep any character notes or style the user gave (for example "make Kit sound like a London teenager").

### Step 1 · 🖋️ Spawn the TRANSLATOR AGENT
Call `delegate_task` with one task:
- goal: "You are a professional game translator. Translate every line into natural British English that keeps each character's voice."
- context: the game setting, the source table (id · speaker and character note · source · limit), the user's style notes, the rules above, and the output format: a table `id · English · note` (a note only for a non-obvious choice, e.g. a saying or a pun).

When it returns, show its table under the heading `## 🖋️ Translator agent (subagent 1)`.

### Step 2 · 🔍 Spawn the REVIEWER AGENT
Call `delegate_task` with one NEW task. The reviewer must not see the translator's notes or reasoning: pass ONLY the game setting, the source table and the English column of the draft.
- goal: "You are a sceptical localisation reviewer. You did not write this draft. Find its real problems."
- context: the setting, source table, English draft, the rules above, and: "Check meaning, voice (does each character sound like themselves?), cultural references and limits. Report at most 3 real problems as a table `finding · id · category (meaning / voice / culture / technical) · problem · suggested replacement`, numbered F1, F2, F3. Never write a finding that says 'none'. If nothing is wrong, say so in one line."

When it returns, show its table under the heading `## 🔍 Reviewer agent (subagent 2)`, then add one line: "The reviewer saw only the source and the English, not the translator's notes."

### Step 3 · 🎬 HUMAN DIRECTOR (STOP HERE)
Heading: `## 🎬 Your decision`. Ask the user to reply for each finding with **accept**, **reject**, or their own wording, for example: `F1 accept, F2 reject, F3: "That thief won't get far."`
Then STOP and wait. Spawn nothing until the user answers.

### Step 4 · ✏️ Spawn the REVISER AGENT
After the user answers, call `delegate_task` with one NEW task:
- goal: "Apply the director's decisions to this translation. Change nothing else."
- context: the source table, the English draft, each finding with the director's decision (accept / reject / own wording), and: "Apply ONLY accepted findings and the director's own wording. Never apply rejected findings. Return a table `id · final English` and one line per change saying which decision caused it. If the director's own wording drops source meaning, apply it anyway and add a one-line warning."

When it returns, show its result under the heading `## ✏️ Reviser agent (subagent 3)`. Then check it yourself: every id is present, no rejected suggestion appears, every limit is respected. Say in one line whether the check passed.

### Step 5 · Optional ✨ song
If the user then types `song`, you (the producer) turn the final English into a short hip-hop song for Suno: a title, one style line (genre, tempo, mood; never a real artist's name) and lyrics with `[Verse]` and `[Chorus]` tags. No subagent needed.

## Pitfalls
- Translating or reviewing yourself instead of spawning a subagent.
- Spawning the reviewer in the same call as the translator (it would have no draft to review).
- Passing the translator's notes to the reviewer: the review must be independent.
- Spawning the reviser before the human has answered.
- L3 is a button: 12 characters at most.

## Verification
Three separate subagents ran (translator, reviewer, reviser). The final table contains every id, rejected suggestions do not appear, and L3 is 12 characters or fewer.
