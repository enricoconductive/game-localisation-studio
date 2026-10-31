# Student guide: Game Localisation Studio v0.3

You and your partner direct a small team of AI agents that localises a Hong Kong mystery game, *The Lantern Mystery* (燈籠之謎), from Chinese into English, and then you play your translation in the browser. You never edit Python: everything is buttons, sliders and text boxes, and your work is saved after every action.

> **You are the localisation director. The agents are collaborators, not authorities.**

---

## 1. Open the notebook and make your own copy

1. Click the **Open in Colab** badge on the course GitHub page. The notebook opens in Google Colab.
2. Colab may warn that the notebook was not written by Google. Click **Run anyway**.
3. Choose **File → Save a copy in Drive**, then work in your copy (it opens in a new tab).
4. Run **⚙️ Step 0 · Set up the studio**: click ▶ and wait about 20 seconds. A green box saying **The studio is ready** appears.
   If Step 0 says **The studio could not be downloaded automatically**, your instructor gives you `studio_bundle.zip`. Either click **Upload bundle** and choose it, or drag it into the Files panel (📁 folder icon on the left) and run Step 0 again (it says "Could not download from GitHub — using studio_bundle.zip from the Files panel.").
5. Run each **▶ Show Section …** cell as you reach it. (*Runtime → Run all* also works.)

Work in **one notebook per pair**. The person whose screen you are both looking at does the clicking.

Mission 1 takes about 80 minutes, including setup. The advanced missions (2–4) take about 35–40 minutes each: you are already connected, so skip Section 1 and start at Section 2.

## 2. Add your API key safely (Colab Secrets)

You start in **Replay Mode**, which needs no key (see section 9). If your instructor has given you a key for a live AI:

1. Click the **key icon 🔑** in Colab's left sidebar, then **Add new secret**.
2. **Name:** use exactly the name for your provider (copy it from the box in Section 1):

   | Provider | Secret name |
   |---|---|
   | Claude (Anthropic) | `ANTHROPIC_API_KEY` |
   | HKBU GenAI | `HKBU_API_KEY` |
   | Hugging Face | `HF_TOKEN` |

3. **Value:** paste the key. Switch on **Notebook access**.
4. In Section 1 choose the **Provider** and **Model**, click **Load my key**, then **Test connection**.

**Never** paste a key into a code cell, a text box, the instructions, a comment, a chat or an email. The studio refuses to save or export anything that looks like a key, with the message "This text contains your API key — remove it from the …". (If Colab Secrets is not available, a hidden **Key:** box appears above the buttons. Use that box only.)

The status bar shows **Live requests this session: n / 40**. This counts every live request in this notebook session, across all missions; it is not reset by **Load my key**, by changing provider or by starting a new mission. Replay requests are free and never counted.

## 3. The six sections, one per stage

| Section | What you do | Main button |
|---|---|---|
| **1 · Connect** | Choose Replay Mode or a live AI. | **Load my key** → **Test connection** (or **Use Replay instead**) |
| **2 · Choose your mission** | Pick a mission (start with **Mission 1 — The Lantern Mystery (Introductory)**; the names match the game) and an **English variant**. Read the source strings. Open **Scene**, **Characters**, **Intended meanings** and **Glossary**. | **Start this mission** |
| **3 · Configure your agents** | Set up the translator (preset, sliders, instructions) and the reviewer (what it checks, how strict it is). | **Show full prompt** |
| **4 · Run the agents** | Run the baseline, the translator and the reviewer. Change the prompt, run again and compare. | **2 · Run translator** |
| **5 · Human Director** | Decide on every reviewer suggestion, add project rules, send feedback, edit, approve. | **Approve final translation** |
| **6 · Test and export** | Write your reflection, play your translation, export the three files to hand in. | **▶ Play my translation in the game**, **Export all three files** |

## 4. Two roles, and when to swap

| Role | What you do |
|---|---|
| 🎬 **AI Director** | Configures the agents, decides which changes are made, approves the final translation. |
| 🔍 **Quality Evaluator** | Challenges the outputs, finds errors and argues for better alternatives. |

The notebook tells you when to swap with an orange **🔁 Swap roles now** box:

- after Section 2 (before you configure the agents);
- after Section 4 (before the Human Director step);
- after Section 6 (before the next mission).

Each time you swap, change **Who is deciding:** in the status bar, so every decision in the log is recorded under the right role.

## 5. Writing better agent instructions

The translator's **instructions** box is a prompt. Five tips:

1. **Name the audience and the effect.** "International players of a light-hearted mystery should smile at Kit's jokes."
2. **Describe each voice with features the agent can copy:** sentence length, vocabulary, idioms, slang, how a character addresses others.
3. **Repeat the hard constraints and say what to do when they bite.** "Buttons: one or two words, within the limit; if it does not fit, drop the article, not the verb."
4. **Say what not to do.** "Do not explain cultural references inside dialogue. Do not add plot details."
5. **Change one thing at a time**, so you can tell which change caused which difference.

| ✅ Good | ❌ Poor |
|---|---|
| "Granny Wong speaks like a proud, sharp-tongued elder: short sentences, an old proverb where the source has one, never slang. Kit is 17: contractions, casual slang, short bursts. They must never sound alike." | "Make the characters sound good and add some fun." (Nothing the agent can check, and it invites invented content.) |

**Show full prompt** shows exactly what the model receives. Editing the preview box changes nothing: edit the instructions and settings above it.

## 6. The key activity: change the prompt, run again, compare, explain

1. In Section 3, pick a preset: **Faithful**, **Balanced** or **Creative**. A preset only sets the visible sliders and the instructions, so open **What the presets change** to see the differences.
2. In Section 4, click **1 · Baseline (one-shot)**. This is a deliberately minimal prompt with no context, so you can see what your agents add.
3. Click **2 · Run translator**. Every run becomes a new version.
4. Go back to Section 3. Change **one** thing (another preset, a slider, a line of your instructions) and click **2 · Run translator** again.
5. In the **Compare runs** tab (it opens by itself after your second translator run), choose **Run A:** and **Run B:**, then click **Compare A and B**. Changed strings are highlighted, and the prompt differences are shown under **Prompt changes (A → B)**.
6. **Explain it to each other:** *What in the prompt caused these differences?* Note your answer; it is useful for your reflection.

Each run shows how many requests it will make. In Replay Mode the requests are simulated, free and not counted.

## 7. Judging the reviewer's findings

Click **3 · Run reviewer**. Each finding is labelled **Suggestion — you decide**. **The reviewer is not always right.** Some suggestions are wrong or debatable, on purpose.

The message under the buttons tells you what happened:

- "The reviewer made N suggestion(s): decide in Section 5.": decide on each one.
- "The reviewer checked N string(s) and found no problems.": nothing to decide; look for what it missed yourself.
- "Review skipped: no string has changed since the last review…": no request was sent. Edit strings or run a revision first.
- "⚠️ The reviewer sent N finding(s), but none could be used…": this does **not** mean the translation is fine. Run the reviewer again, or switch to Replay Mode.

For every finding in Section 5, choose one:

| Button | Use it when… |
|---|---|
| **Accept** | the problem is real and the suggested string is good. |
| **Reject** | the problem is not real, or the fix makes things worse. Your disagreement is recorded. |
| **Use my wording** | you want a different string. The box starts with the reviewer's suggestion: edit it (or replace it completely), then click. |

Before you decide, the Quality Evaluator checks:

- **Is the issue real?** Read the source, the context and the intended meaning.
- **Does the suggestion break a rule?** Count the characters of buttons, check that every `{placeholder}` is kept exactly, check line breaks, and check the **REQUIRED** glossary terms.
- **Does it flatten a voice?** Does Kit still sound like Kit, and Granny like Granny?
- **Do linked strings still match?** For example a riddle, its answer button and the reaction to it.

Always write *why* in the comment box: your comments are the evidence of your judgement.

The **Technical checks** tab (automatic checks) is separate from the reviewer: **MUST FIX** items block approval; **CHECK** items are warnings. For example, a string that "has a space (or an invisible space-like character) at the start or end, or a double space" is a CHECK item: retype the start and end of the string.

## 8. Rules, revision, approval and export

Section 5 has five tabs, worked from left to right: **a · Decide** → **b · Rules** → **c · Revise** → **d · Final edits** → **e · Approve**. The result of every button appears just below the tabs. Under them, the collapsible **History and decision log** panel holds the version history and the decision log. In Sections 4–6, long tables scroll inside their own box, so the buttons stay where they are.

- **Add rule** (in **b · Rules**) for anything the agents should always follow, for example "Kit always calls Granny Wong 'Granny'." This is **project memory**: the rule is added to your agents' future prompts. The AI model itself is not retrained.
- **Send accepted feedback** (in **c · Revise**). Only strings with **accepted** findings are re-sent. Your own wording (**Use my wording**) is applied directly, with no AI request, and rejected suggestions are never applied. You can then click **Review again (optional)**.
- **Edit the final translation yourself** in **d · Final edits**, then click **Save edits as new version**. Save your edits before running other steps.
- **Version history** (in **History and decision log**): use **Compare with current** or **Restore version** if a change made things worse.
- **Approve final translation** (in **e · Approve**) when you are satisfied. Any later change revokes the approval, so approve again. Then click **Download progress** (the studio reminds you): your autosave lives only in this Colab runtime.
- **Export** in Section 6: **Export all three files** gives you:
  - `game_translation_en.json`, the file you play in the game;
  - `agent_settings.json`, your models, prompts, settings and rules (no keys);
  - `workflow_report.html`, the full record of your work, for your instructor.

  Export is blocked until the translation is approved and has no MUST FIX problems. The message says **download started** when Colab started the download. If nothing downloads: open the Files panel (📁 folder icon on the left) → `exports` → your mission's folder (for example `intro`) → **⋮** next to the file → **Download**. Every file is saved there, even when the message says "use the Files panel to download it". Every mission's files have the same names, so your browser may add "(1)" to a second download; rename them (for example `TeamLantern_intro_workflow_report.html`). After exporting, click **Download progress** too.

  **Chrome asks "Download multiple files?"** (a small download icon at the right of the address bar) when you click **Export all three files**: choose **Allow**. If you clicked **Block**, Chrome blocks every later download from Colab until you click that icon and choose **Always allow**; until then, use the Files panel as above.

## 9. Test your translation in the game

1. After **Approve final translation**, click **▶ Play my translation in the game** in Section 6. The game opens in a new tab with your approved translation already loaded. (Before approval, Section 6 says "Approve in Section 5 first.")
2. Link not working? Open the game (<https://enricoconductive.github.io/game-localisation-studio/game/>), click **Import student JSON** and choose your exported `game_translation_en.json`. (Or click **Paste JSON**, paste the file's contents and click **Check and apply**.)
3. The game switches **Dialogue language** to **Student's imported English** by itself. Choose your mission and play both endings.
4. To compare, switch **Dialogue language** to **Original Chinese** or **Reference English**. The reference is *one possible solution*, not the answer key.
5. **Interface** switches the menus between **English** and **繁體中文**. **Reset to 中文** clears your imported file.

If the game says **This file was not applied**, read the **Must fix** list, fix the strings in the notebook, approve and export again. Reloading the page clears an imported file, so import it again after a reload. Checks about `source` or `locale` ("The file does not say where the translation came from…", "The 'locale' should be one of…") mean the file was edited by hand: use the file the studio exported.

## 10. If the live AI fails

Every error message ends with the same advice: you can always continue in Replay Mode.

| You see | What to do |
|---|---|
| "…service is busy — many classmates are using the service at once." | **Wait 30 seconds** and try again, or click **Switch to Replay**. |
| "…key was not accepted." | **Check your key:** the secret name is exact, the whole key is pasted, **Notebook access** is on. Click **Load my key** again. |
| "…account has no credit left…" | Tell your instructor, and click **Switch to Replay**. |
| "…did not answer within 45 seconds." | Try again once. If it happens again, click **Switch to Replay**. |
| "You have used all 40 live requests allowed for this exercise." | Click **Switch to Replay** and carry on. |
| "The translator reply was cut off because it was too long…" | Ask for short notes in the instructions, then try again, or click **Switch to Replay**. Nothing was changed. |
| "⚠️ Only part of this step worked. …" | The strings that worked are kept; the others keep their previous text. Run the step again. |
| "Autosave failed: …" (also in the status bar) | Read the reason, fix it (for example remove a key you pasted), then click **Download progress**. |

**About Replay Mode.** Replay shows outputs prepared by the course team, always labelled **REPLAY MODE — simulated outputs, not live AI** It needs no key or internet. It does **not** respond to your own prompt edits: it has one prepared output per preset (Faithful, Balanced, Creative), so in Replay compare runs by switching presets. Your edits are still saved in your prompt and report. All prepared English is British: if you chose American or International English, the studio reminds you that "Replay text is British English; live agents follow your choice."

## 11. Disconnected, behind, or changing computer

Use the **🆘 If you get stuck** box at the bottom of the notebook.

- **Colab disconnected, but the runtime is still there?** Run Step 0 again, then click **Resume my saved session**. Your work is autosaved after every action, in this Colab runtime (`/content`).
- **Colab reset the whole runtime** (after a long break, for example)? The autosave is lost with it. Use your downloaded progress file: **Choose file**, then **Resume from file**. So click **Download progress** in the status bar **before every break**, after approving and after exporting.
- **Nothing downloaded** after **Download progress** or an export? The file is saved anyway: open the Files panel (📁 folder icon on the left) → `exports` (progress files) or `exports` → your mission's folder (exports) → **⋮** next to the file → **Download**. Allow downloads from colab.research.google.com if your browser asks.
- **Changing computer, or handing over to your partner?** Click **Download progress file**. On the other computer, choose the file with **Choose file**, then click **Resume from file**.
- **Behind the class?** In **Checkpoint:** choose one of the Mission 1 checkpoints ("Catch up: agents already run", "Catch up: review done", "Catch up: revision done") and click **Load checkpoint**. Your previous work is kept as a backup.
- **Mission in a mess?** **Reset this mission** asks you to confirm, and keeps a backup copy.

## 12. Reflection

Before you export, answer this together in Section 6 and click **Save reflection (goes in your report)**:

> **What did your agents get wrong, what did you change, and why was the final result better?**

Good answers are specific. Name a string id, quote the before and after, and say which prompt change, decision or rule made the difference. If a change did *not* help, say so; that is a valid finding too.
