# Decisions

Why `SPEC.md` says what it says. `SPEC.md` holds the conclusions; this file holds the reasons and the alternatives that lost.

**Format going forward.** One entry per change to `SPEC.md`, newest at the bottom of its section:

```
### YYYY-MM-DD — <short title>  (commit <hash>)
- Changed: <section or rule ids>, added / changed / removed
- Why: <the reason, in one or two sentences>
- Rejected: <what else was considered and why not>  (omit if nothing)
```

The commit hash is the commit that changed `SPEC.md`; the entry is written in the following commit. Rule ids are append-only, so a hash plus rule ids locates a change exactly.

The entries below were backfilled on 2026-10-03 from the spec review log (2026-09-16 to 2026-10-03, spec v0.2 → v1). They cite spec versions instead of hashes, because the history lives in a different repository.

---

## Scope and goals

### 2026-09-18 — Goals split into ablation-tested points and shared items  (spec v0.2)
- Changed: Goals, Ablation Design.
- Why: the original goal list had seven points to "verify by ablation", but three of them (context assembly, evaluation and observability, comparison under non-determinism) exist in every variant and have no toggle. Only a capability that can be turned off can be tested by ablation. The four that can (decision loop, tool interface, multi-agent handoffs, memory) map to V1, V2, V3; the rest are shared requirements of all variants.
- Rejected: keeping one flat list. Accepted residue: decision loop and tool interface share the single V1 toggle, so they are not tested separately.

### 2026-09-18 — Two-week limit means build plus run, machine 24/7  (spec v0.2)
- Changed: Non-goals.
- Why: the original wording ("the whole project … no more than two weeks") would have made Claude Code schedule design and analysis into the same budget. The author's intent is calendar time from first line of code to the four batches finished, not including corpus work or writing.

### 2026-09-19 — Demo is two full transcripts per variant in the report; no replay  (spec v0.2)
- Changed: Definition of Done; Recovery, forks, and replay.
- Why: "a fun demo" had no checkable artifact. A live run takes tens of minutes per game, so the demo material is the transcripts pasted into the report. Replay from checkpoints was dropped as unneeded.

### 2026-09-27 — M0 (hand-played trial) removed; forbidden words moved into corpus entries  (spec v0.3)
- Changed: Milestones (M0 removed), Corpus and Cards.
- Why: one person cannot play a guessing game against themselves, so M0 could not produce the calibration it promised. The schema decisions it was meant to make now happen in M1. Forbidden words are a property of an entry, so they belong in the corpus rather than being added at card time.
- Also removed: the per-card difficulty field. Difficulty differences between cards are absorbed by the per-card paired comparison, so the field had no reader.

### 2026-09-27 — Project name "Don't Say Oyster"  (spec v0.3; repo spelling fixed 2026-09-30)
- Why: Taboo's core rule is "don't say the word"; 蚵仔煎 (oyster omelet) stands in for the Taiwanese-snack theme. Chosen over "Xiaochi" for memorability as an article title. Repository name is `Dont-Say-Oyster`.

## Game rules

### 2026-09-19 — The Describer's answers to questions skip the Challenger; at most three questions per game  (spec v0.2; now R12, R16)
- Why: the Challenger only sees the card and the description, not the Guesser's question, so it cannot judge whether "yes" leads to the answer. Letting answers through unjudged while capping questions keeps the Challenger's job well-defined and bounds how much un-judged information the Guesser can extract.
- Rejected: showing the Challenger the question too (widens its context and its job for no gain in the V1→V2 comparison).

### 2026-09-19 — Rejected descriptions are visible only to the Describer  (spec v0.2; State schema)
- Why: if the Guesser also saw rejected descriptions, a V2 Guesser would receive more text per round than a V1 Guesser, and the V1→V2 difference would mix "more information" with "has a Challenger". The Guesser-visible description row is therefore filled by the program only after the Challenger passes or a forced pass.

### 2026-09-19 — The Challenger's reason is passed back to the Describer  (spec v0.2; now R30)
- Why: the Challenger's criterion is "leads to the answer and not to a distractor", so a fail reason carries information ("also sounds like X"). Withholding it would make the Describer's retry blind.

### 2026-09-19 — A question may not contain any name; program sends it back, max two, third is a Guesser violation  (spec v0.2; now R17)
- Why: a question containing a candidate name is a free guess ("is it 蚵仔煎?"), and a rational Guesser would spend all its questions that way, breaking the round-count metric. Checking only the current card's name leaves a shotgun loophole (ask about many names at once). Not checking at all would make V0 (no candidate list) and V1+ (candidate list from lookups) behave differently for reasons unrelated to the tool.
- Narrowed 2026-09-27: after the language split, the English-name check covers only the current card and its distractors, because English dish names are ordinary food phrases ("rice noodles", "fried chicken") and checking all three hundred would block legitimate questions.

### 2026-09-19 — Oracle matching rules  (spec v0.2; now R22)
- Why: "contains a name" and "answer is in the list" had no definition, and oracle noise feeds straight into the main metric. Fixed: NFKC, strip spaces and punctuation, lowercase, Simplified→Traditional; Chinese lists by substring; English lists by whole word or phrase with word boundaries; the guess must equal an entry; no fuzzy matching.

### 2026-09-19 — Sentence limit and no-repeat are prompt constraints only  (spec v0.2; now R8)
- Why: there is no good program test for "the same description", and the sentence count is not worth a hard check. Both stay in the prompt as the only exceptions to program-side validation.

### 2026-09-24 — Guesser is forced to guess by schema, not by retry  (spec v0.3; node G)
- Why: after three questions, and in round ten, the Guesser may only return the guess schema. Constrained decoding guarantees this; no retry loop is needed.

### 2026-09-24 — Separate structured-output call after the tool loop; sixth lookup blocked  (spec v0.3; now R43, R47)
- Why: mixing tool calls and the final structured answer in one call is unreliable on local models through Ollama. The tool loop runs first (at most five lookups), then one separate call returns the question or guess. On the sixth attempt the program blocks the tool and forces that call.

### 2026-09-26/27 — Language split: names Chinese, dialogue English  (spec v0.3; now R3–R8, R20–R22)
- Why: the report is for English readers, so descriptions, questions, answers, verdicts and memory summaries are English; the corpus and the answers stay Chinese because that is what the snacks are called. Consequences: forbidden words and attributes are English; each entry carries English names used only for program checks and never accepted as answers; a non-Chinese guess counts as wrong and uses a round; the program checks for Chinese characters (not "CJK", which would count Japanese and Korean). Retry policies: Describer Chinese → sent back, max two, third is a violation (R11); Challenger Chinese reason → asked once, then a fixed message (R40).
- Rejected: all-Chinese (hard for the target readers), all-English (names would need romanization and the oracle would lose precision).

## Corpus and cards

### 2026-09-19 — Corpus is "about three hundred", counted in M1; near-duplicates become aliases  (spec v0.2)
- Why: "at least three hundred" had no source, and padding to a number would force in regional variants that weaken both the oracle's exact match and the Challenger's "does not point to another answer" criterion.

### 2026-09-24 — Distractors: up to five official names per card, picked for the Challenger  (spec v0.3; now R34, R35)
- Why: the Challenger (9B, 4K context) cannot be given the whole corpus to judge "does not point to another answer". Instead each card carries up to five distractors, and the criterion becomes "leads to the official name or an alias, and not to any distractor". The author reviews every pick.
- Rejected: giving the Challenger the corpus; giving it the card's attributes instead of names.

### 2026-09-30 — Distractors are picked by an LLM, reviewed by the author  (spec v1)
- Changed: Corpus and Cards, State schema, M1 (previously "the program picks by shared attribute values").
- Why: a program can only count shared attribute values; with a thin attribute set (location is the only fixed field) that yields useless distractors (a night-market stall next to bubble tea). An LLM judges semantic confusability. This is a one-time M1 step with author review, so the LLM's non-determinism does not touch the experiment.
- Rejected: program shortlist plus manual pick (extra step for little gain).

### 2026-09-30 — Program selects and builds the forty cards by a criterion decided in M1; card order fixed in M1 and shared by all batches  (spec v1)
- Why: the card set and order are controlled variables for the per-card comparison, so they are decided once, written into the batch manifests, and never changed between variants.

## Agents and models

### 2026-09-18 — Models are starting points; M5 settles them  (spec v0.2)
- Why: the pairing (Gemma 4:26B Guesser, Qwen 3.8:27B Describer, GLM-4:9B Challenger) had no stated justification, and the Challenger, the hardest judging job, was given the smallest model. Rather than argue on paper, M5 runs real games, checks ten Challenger verdicts by hand, and swaps models if needed; a changed model also reruns the M2 checks. Quantization is part of the model tag, so M5 settles it with the model.
- Also: M2 must check that tool calling works for the Guesser's model on Ollama (Gemma family historically had no tools template) and that structured output works for all three.

### 2026-09-18 — Temperature 0.7, provisional, same for all roles and variants  (spec v0.2)
- Why: >0 is needed for variation; "same value everywhere" makes it a controlled variable. The original claim that 0.7 "falls within all three models' recommended ranges" was deleted as unsourced. M5 may change it.

### 2026-09-19 — num_ctx 16K / 8K / 4K; warning at 90%  (spec v0.2)
- Why: Ollama's default context is small and silently truncates. Ten rounds of history plus lookup results plus memory can exceed it, which would make V3 fail quietly. The warning is checked in M4 and M6.

### 2026-09-19 — Latency means end-to-end delay, including thinking  (spec v0.2; Metrics)
- Why: "thinking time" could be read as Ollama's eval_duration or as thinking-token time; the three readings differ a lot. The metric is wall-clock from prompt sent to full response received.

### 2026-09-25 — Jev (TypeSafe AI) rejected as the Challenger  (no spec change)
- Why: Jev's documentation says its primary training language is English with lower CJK accuracy, and the card names are Chinese. It also emits no text, so the fail reason fed back to the Describer would have to be program-composed. Do not re-propose English-first cloud classifiers for the Challenger.

## Memory (V3)

### 2026-09-20 — Cross-game memory lives in per-role JSON files numbered by game; no LangGraph checkpointer  (spec v0.2; Architecture)
- Why: a batch is forty independent commands, one per game, so LangGraph State does not survive between games. Files are read into State at game start and written back after node H. In-memory checkpointing gives no crash recovery, so it is not used at all; recovery reruns the crashed game from the last memory file (V3) or skips cards that already have a JSONL record (V0–V2).
- Rejected: LangGraph Store; running forty games in one thread; fork-and-rerun from a card checkpoint (impossible for V3, whose game n depends on memory from games 1..n−1; also unnecessary because the same command takes a different variant argument).

### 2026-09-20 — Node H: two model calls per game write the memory  (spec v0.2; now Full flow of one game)
- Why: the memory definition required a per-game summary from the Describer and the Guesser, but the V3 flow ended at F with no node that wrote memory. H makes it explicit and makes the extra cost visible in the batch time estimate.

### 2026-09-20 — Disclosure and Write rules  (spec v0.2; Cross-game memory definition)
- Why: without them, the Guesser's best use of memory would be "exclude answers already seen", and the V2→V3 difference would measure an exclusion list rather than memory management. So the program tells each role only who won; it never tells the Guesser the answer or aliases; the Guesser's memory may contain strategies only.

### 2026-09-21 — Memory size: latest five entries in full plus one rolling summary  (spec v0.2)
- Why: "a rolling summary with a cap" had no number. The cap is count-based (five), which is easy to implement and to inspect; the summary's token count is a logged metric so drift is visible.

### 2026-09-24 — Check rule on memory output; failure keeps the previous file  (spec v0.3)
- Why: the Guesser's English summary could leak the answer or an English name in prose. The program checks both roles' output for Chinese characters and the Guesser's for the answer, aliases, and English names; two redos, then that game is not written and the previous file is copied forward.

## Evaluation

### 2026-09-18 — Per-card pairing of neighboring variants; count discordant cards; one-sided binomial; credibility = 1 − p; threshold 0.95; forty cards  (spec v0.2–v0.3)
- Why: a hit rate over forty games carries about ±8 percentage points of error by itself, so totals cannot separate variant from luck. Pairing by card removes card difficulty. With forty cards there are usually eight to twelve discordant cards and 0.95 needs about 8:1, so credibility is reported for reference and the reading is "who wins more". One hundred twenty cards would give real power but triple the batch time.
- Rejected: comparing totals; first-half vs second-half comparison for V3 (different cards, standard error about ±16 points, weaker than what the spec already refused); every-pair comparison (only neighbors are meaningful in an ablation chain).

### 2026-09-18 — Optional second V2 run as the ruler for luck  (spec v0.2)
- Why: the number of discordant cards between two runs of the same variant shows how many cards pure noise flips. A variant only gets credit when its winning margin beats that ruler. If there is no time for the second run, only "who wins" and credibility are reported, with no causal claim.

### 2026-09-19 — V3 judged by the V2↔V3 paired difference laid out in game order  (spec v0.2)
- Why: if memory helps, later games should lean toward V3; the V2 side absorbs card difficulty, so no split into halves is needed.

### 2026-09-19 — Confidence score gets a calibration chart per variant  (spec v0.2)
- Why: the Guesser was asked to output a confidence score that no metric used. Plotting confidence against correctness gives the "comparison under non-determinism" item a concrete output.

### 2026-09-19 — Batch time estimate added; thinking on/off decided in M5  (spec v0.2; Implementation)
- Why: there was no estimate at all. With 27B-class models at 10–15 tok/s and prefill at 150–300 tok/s, four batches take roughly 25–60 hours with thinking off and 95–250 hours with it on for the Describer and Guesser, so thinking is a budget decision, not a default.

## Process

### 2026-09-28 — Spec rewritten in English with numbered rules and one unified flow  (spec v0.4–v0.6)
- Why: the Chinese v0.3 had four near-duplicate per-variant flow descriptions and no stable way to cite a rule. v0.4 translated it line by line (Opus, with a glossary), a structure review (Fable) found 18 duplicate groups, v0.5 merged the flows into one node table plus a Mermaid diagram and numbered the rules R1–R50, each step verified by an independent Sonnet pass against an inventory of every rule sentence in the Chinese original (257 items).

### 2026-09-30 — Milestones rewritten as bullet lists ending in "Done when"  (spec v1)
- Why: the prose milestones disagreed with the spec body in 25 places (missing node G, three retry loops instead of four, program vs LLM for distractors, "every chart" undefined, M8 comparing all pairs). Each milestone now lists its work items and one observable exit condition.

### 2026-10-03 — Tickets: lite ticket format, one file per milestone, written just in time  (no spec change)
- Why: a `- [ ] M2.3` checklist inside the spec was rejected as unreadable; a full ticket file in the style of the author's earlier project Clearway (Preamble, Table of Contents) duplicates design reasons that already live in `SPEC.md`. The lite format keeps Goal & exit criterion (with Real/Absent), How to use these tickets, and the tickets themselves (Produces, Consumes, Detail, Acceptance, Out of scope, Depends on). Tickets for milestone n are written only after milestone n−1 is done, because the project's uncertainty is concentrated in M2 (tool calling, three resident models, structured output) and detailed M3–M8 tickets written now would mostly be rewritten. One ticket is one commit and does one thing.
- Rejected: all eight ticket files up front; tickets inside `SPEC.md`.
