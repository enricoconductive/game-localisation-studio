# Hermes mini version: `/game-localiser`

A very small version of the studio workflow for the [Hermes Desktop](https://hermes-agent.nousresearch.com/desktop) app: translator agent → reviewer agent → **you decide** → one revision → optional song for Suno.

## 1. Connect a model (Hermes Desktop → Settings → Providers)

- **HKBU GenAI:** choose **Custom endpoint**.
  - Base URL: `https://genai.hkbu.edu.hk/api/v1`
  - API key: your own HKBU key
  - Model: `deepseek-v4-flash-0731`
- **Anthropic:** choose **Anthropic** and paste your own key.

Never paste a key into the chat.

## 2. Install the skill (one command, in a terminal)

```bash
hermes skills install https://raw.githubusercontent.com/enricoconductive/game-localisation-studio/main/hermes/game-localiser/SKILL.md --category translation --yes
```

Then restart Hermes Desktop (or start a new chat).

## 3. Use it

In a new chat, type:

```
/game-localiser demo
```

Reply to the reviewer's findings, for example `F1 accept, F2 reject, F3: "That thief won't get far."`. When the final table appears, type `song` for Suno lyrics.

Use your own lines instead of `demo`: `/game-localiser` followed by the source text, one line each.
