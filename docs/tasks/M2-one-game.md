# M2 — Build the code needed to run one game, based on the V2 spec

## Goal & exit criterion

See `SPEC.md`, Milestones, M2. Do not copy the bullets here; they go stale.

**Exit criterion:** Done when one V2 game reaches F.

- **Real:** the three local models checked on Ollama (resident together, structured output, tool calling with a separate structured call), and the code that plays one V2 game from one command: nodes A–G, the Guesser's search tool and tool loop, the four retry loops, and the Oracle checks, ending in one live game recorded here.
- **Absent:** no Phoenix tracing (M3); no variant argument, Challenger or lookup toggle, or JSONL record (M4); models, temperature, and thinking on/off are not settled and not written into the manifests (M5); no cross-game memory, node H, or memory-file argument (M6); no batch script or metrics (M7).

## How to use these tickets

T1 → T2 → T3 are the three model checks, the project's biggest risk, and run first, in that order; each is a live check accepted by the record it leaves. A failure in any of them (the three models do not stay resident together, a model returns no parsed structured output, or the Guesser's model makes no tool call or its separate structured call does not parse) is a `SPEC.md` gap (Implementation, Models), escalated to the author before T4 and the node tickets proceed. T4 follows T3. T5 does not need a model and can run beside T1–T3; T6 and T7 follow T5, T11 follows T3 and T5, and T8 follows T7. Then the node tickets: T9 (needs T4, T7, T8), T10 (needs T4, T5, T8), and T12 (needs T3, T4, T7, T8, T11), all three beside each other. T13 (needs T8, T9, T10, T12) joins them; T14 (needs T1, T6, T13), the live game, closes the milestone. T14 carries decisions marked "author fills in" (T1's were filled in on 2026-10-18); a ticket is not dispatched until those are filled in, nor while an Open question it names is unanswered. T6's corpus correction is committed (5ba08c6), and its schema description text is the author's; T9, T10, and T12 are not dispatched until the author has written their prompt files (the role prompt and its fixed message), and each is accepted only when its approval line is filled in after a live trial; in T1–T3 and T14 an agent runs the commands. One ticket, one commit; a live record written into this file after a code commit, Status updates, audit fixes, and the `DECISIONS.md` entry after a spec change are their own small commits.

## Tickets

### T1 — Three models resident in Ollama at once
- **Status:** todo
- **Produces:** the Ollama tags for the three roles, written into this Detail, and the record of a residency check: the three models loaded together at their num_ctx with `OLLAMA_MAX_LOADED_MODELS=3`.
- **Consumes:** —
- **Detail:**
  - From BACKLOG M2.1. `SPEC.md` Implementation (Models); Milestones, M2.
  - **Tags** (author, 2026-10-18; the tag fixes the quantization, which `CLAUDE.md` Rules of engagement requires pinned): Guesser (Gemma 4 26B) `gemma4:26b-a4b-it-q4_K_M`; Describer (Qwen 3.8 27B) `qwen3.8:27b-q4_K_M`; Challenger (Gemma 4 12B) `gemma4:12b-it-q4_K_M` (author, 2026-10-18; was `glm4:9b-chat-q4_K_M`). num_ctx 16K / 8K / 4K are read as 16384 / 8192 / 4096 (author, 2026-10-18).
  - No code. An agent pulls the three tags, runs the Ollama server with `OLLAMA_MAX_LOADED_MODELS=3` (from a shell, or with `launchctl setenv` for the menu-bar app; the record says which), loads each model with one request to the Ollama API that sets `options.num_ctx` and a `keep_alive` long enough for the check, then runs `ollama ps` while all three are loaded.
  - The record, written into this Detail: the date; `ollama --version`; the `ollama list` lines for the three tags (their IDs pin the weights); the full `ollama ps` output (name, size, processor, until, and the context each was loaded with: the CONTEXT column, or `/api/ps` if this version prints none); the memory macOS reports as free at that moment.
  - If `ollama ps` does not list all three at once, or a context differs from the requested num_ctx, stop and escalate (How to use these tickets). A processor column other than 100% GPU is recorded and raised under Open questions; it does not fail the check by itself.
  - **Record** (2026-10-18; superseded on 2026-10-18 by Record 2, because the Challenger changed):
    - Server: from a shell, `OLLAMA_MAX_LOADED_MODELS=3 ollama serve`, with the menu-bar app quit; the server config line in its log reads `OLLAMA_MAX_LOADED_MODELS:3` and `OLLAMA_NUM_PARALLEL:1`.
    - Loads: one `/api/generate` request per model with an empty prompt, `keep_alive` `30m`, and `options.num_ctx` 16384, 8192, 4096, in the order Guesser, Describer, Challenger.
    - `ollama --version`: `ollama version is 0.40.6`
    - `ollama list`, the three tags:
      ```
      NAME                        ID              SIZE      MODIFIED
      glm4:9b-chat-q4_K_M         f17dc1ac3c7c    6.3 GB    About a minute ago
      qwen3.8:27b-q4_K_M          25b843619e94    17 GB     5 minutes ago
      gemma4:26b-a4b-it-q4_K_M    5571076f3d70    17 GB     14 minutes ago
      ```
    - `ollama ps` at 17:23:47 PDT, with all three loaded:
      ```
      NAME                        ID              SIZE      PROCESSOR    CONTEXT    RUNNER      UNTIL
      glm4:9b-chat-q4_K_M         f17dc1ac3c7c    6.2 GB    100% GPU     4096       llamacpp    29 minutes from now
      qwen3.8:27b-q4_K_M          25b843619e94    16 GB     100% GPU     8192       llamacpp    29 minutes from now
      gemma4:26b-a4b-it-q4_K_M    5571076f3d70    1.5 GB    100% GPU     16384      llamacpp    29 minutes from now
      ```
    - Free memory at that moment: `memory_pressure` reports "System-wide memory free percentage: 31%"; `vm_stat` (16384-byte pages) reports 6127 free, 636327 inactive, 12884 speculative, 2790551 wired.
    - The 1.5 GB for the Guesser's model is not its loaded size: Q16.
  - **Record 2** (2026-10-18), with the Challenger `gemma4:12b-it-q4_K_M`:
    - Server: the same shell server as the first Record, still running: `OLLAMA_MAX_LOADED_MODELS=3 ollama serve`, with the menu-bar app quit; its config line reads `OLLAMA_MAX_LOADED_MODELS:3` and `OLLAMA_NUM_PARALLEL:1`.
    - Loads: from nothing loaded, one `/api/generate` request per model with an empty prompt, `keep_alive` `30m`, and `options.num_ctx` 16384, 8192, 4096, in the order Guesser, Describer, Challenger.
    - `ollama --version`: `ollama version is 0.40.6`
    - `ollama list`, the three tags:
      ```
      NAME                        ID              SIZE      MODIFIED
      gemma4:12b-it-q4_K_M        6114515d63c1    8.0 GB    24 seconds ago
      qwen3.8:27b-q4_K_M          25b843619e94    17 GB     About an hour ago
      gemma4:26b-a4b-it-q4_K_M    5571076f3d70    17 GB     About an hour ago
      ```
    - `ollama ps` at 18:20:06 PDT, with all three loaded:
      ```
      NAME                        ID              SIZE      PROCESSOR    CONTEXT    RUNNER      UNTIL
      gemma4:12b-it-q4_K_M        6114515d63c1    678 MB    100% GPU     4096       llamacpp    29 minutes from now
      qwen3.8:27b-q4_K_M          25b843619e94    16 GB     100% GPU     8192       llamacpp    29 minutes from now
      gemma4:26b-a4b-it-q4_K_M    5571076f3d70    1.5 GB    100% GPU     16384      llamacpp    29 minutes from now
      ```
    - Free memory at that moment: `memory_pressure` reports "System-wide memory free percentage: 26%"; `vm_stat` (16384-byte pages) reports 7065 free, 551012 inactive, 5150 speculative, 2958754 wired.
    - The 678 MB and 1.5 GB for the two Gemma models are not their loaded sizes: Q16.
- **Acceptance:** this Detail holds the three tags (filled in by the author) and the record above, and the recorded `ollama ps` output lists all three tags loaded at the same time with contexts 16384, 8192, and 4096.
- **Out of scope:** any Python code or dependency (T2); structured output and tool calling (T2, T3); trying other models or settling them (M5); writing the tags into the manifests (M5).
- **Depends on:** —

### T2 — Structured-output check on the three models
- **Status:** todo
- **Produces:** a check command `check-models` (`src/dont_say_oyster/model_checks.py`, a console script like M1's) whose `structured` subcommand sends each role's model structured-output requests through LangChain's Ollama integration and prints, per model and thinking setting, how many replies parsed; its tests; and the record of one run with the T1 tags, written into this Detail.
- **Consumes:** the tags and num_ctx from T1; `python-dotenv` and the `.env` convention from M1.
- **Detail:**
  - From BACKLOG M2.2. `SPEC.md` Milestones, M2. The command and its run are one ticket because the command exists to leave this record and to be rerun when a model changes (`SPEC.md` Milestones, M5).
  - Adds `langchain-ollama` (pre-approved: `CLAUDE.md` Rules of engagement; LangChain is named in `SPEC.md`), pinned in `uv.lock`. The Ollama endpoint comes from `.env`.
  - Each model gets a schema shaped like its role's output: the Describer, one text field [R32]; the Challenger, a verdict and an optional reason [R39], [R40] (a reason on a pass is dropped [R40]); the Guesser, a question or a guess with a confidence score [R48]. These are check schemas; the nodes define their own (T9, T10, T12).
  - Settings: temperature 0.7 (`SPEC.md` Implementation, Temperature policy) and each model at its T1 num_ctx. Each check runs `--repeat` times (default 5). The Describer and Guesser models run with thinking off and on (M5 decides which is used); the Challenger with thinking off (`SPEC.md` Implementation, Batch time estimate).
  - The subcommand also sends one prompt twice to the Guesser's model and prints the prompt token count Ollama reports each time. A lower second count means Ollama reports only the tokens it did not reuse from its cache; T4 needs to know this for the token count and the num_ctx warning.
  - The model call sits behind one callable the command takes as an argument (M1's `Ask` pattern in `distractors.py`), so tests feed scripted replies.
  - The record, written into this Detail: the date, the command line, and for each model and thinking setting the parsed count out of the repeats, the latency of each call, one parsed object, and the raw text of every reply that did not parse; the two prompt token counts.
- **Acceptance:** the test command passes: with scripted replies, a reply that fits the schema counts as parsed; a malformed one counts as not parsed and its raw text is printed; the command exits non-zero when some check has no parsed reply. This Detail holds the record of one live run with the T1 tags, and every model has at least one parsed reply under every thinking setting it was run with (otherwise escalate, How to use these tickets).
- **Out of scope:** the model-call wrapper the nodes use (T4); tool calling (T3); the role prompts (T9, T10, T12); changing models or choosing thinking on/off (M5); Phoenix (M3).
- **Depends on:** T1

### T3 — Tool-calling check on the Guesser's model
- **Status:** todo
- **Produces:** a `tools` subcommand of `check-models` that binds a stand-in search tool to the Guesser's model, runs the tool call the model makes, then makes a separate structured-output call for a guess [R47]; its tests; and the record of one run, written into this Detail.
- **Consumes:** the check command and `langchain-ollama` from T2; the Guesser tag from T1; the attribute value lists in `data/corpus/schema.json` (M1).
- **Detail:**
  - From BACKLOG M2.3, and the enum part of BACKLOG M2.15 (split with T11): the question deferred from M1 (T2 F7, author, 2026-10-07), whether attribute values with spaces ("Sugar and Sweeteners", "No Cooking", "Drink with Add-ins") work as enum strings in an Ollama tool schema, is answered by this run; T11 uses the answer.
  - The stand-in tool has the input shape of [R44]: optional filters on main_ingredients, cooking_method, and physical_form, each an enum of that field's values in `data/corpus/schema.json`, and an optional keyword list. It returns a fixed two-entry result and does not search (T11).
  - The prompt gives a short English description whose natural filters include values with spaces (for example a sweet drink with chewy add-ins).
  - One run: a call with the tool bound; if the model makes a tool call, the program runs the stand-in and sends the result back; then a second, separate call with no tool bound and a guess schema (guess and confidence [R48]). Repeats and thinking settings as in T2, Guesser model only.
  - The record, written into this Detail: for each thinking setting, how many runs made a tool call, the arguments verbatim as the model sent them, whether each enum value equals a listed value exactly, and how many separate guess calls parsed. Enum values that come back altered (case, spacing, a value not in the list) are the T2 F7 answer and go under Open questions for the author to decide the tool-schema shape before T11.
- **Acceptance:** the test command passes with scripted replies: a scripted tool call is run and its result sent back; the guess call is made with no tool bound (asserted on the request); an argument value not in its enum is reported. This Detail holds the record of one live run, and in it the Guesser's model made at least one tool call and at least one following separate guess call parsed under each thinking setting (otherwise escalate, How to use these tickets).
- **Out of scope:** the real search tool and its filter and keyword rules (T11); the lookup limit and the tool loop (T12); the wrapper (T4); the Describer and Challenger models, which use no tools [R31], [R38].
- **Depends on:** T2

### T4 — Model-call wrapper
- **Status:** todo
- **Produces:** `src/dont_say_oyster/llm.py`: one call path every role uses for a plain-text, a structured-output, or a tool-bound call, with model, num_ctx, temperature, and thinking on/off given as arguments, returning the output with latency, token count, and attempt number [R26]; the num_ctx warning; tests.
- **Consumes:** `langchain-ollama` from T2 and T2's record of the reported prompt token count; the tool-binding pattern checked in T3.
- **Detail:**
  - From BACKLOG M2.4. [R26]; `SPEC.md` Implementation (Models, Temperature policy); Metrics (Latency).
  - Latency is the wall time around the one call, thinking included. Token count keeps the input and output counts Ollama reports, apart. The warning (`SPEC.md` Implementation, Models) goes through `logging` at WARNING, naming the role, the prompt tokens, and num_ctx; it needs the prompt's full size, so if T2's record shows the reported count drops on a cached prefix, stop and raise it under Open questions instead of choosing another count.
  - The attempt number is an argument; what it counts is the caller's rule [R26] (T9, T10, T12).
  - No automatic retries: one wrapper call is one request to Ollama (`CLAUDE.md`, Auditing a ticket: a retried call is one call in the log but two in latency). A connection error, or a structured reply that does not parse, raises the wrapper's own error; the game stops on it (`SPEC.md` Recovery, forks, and replay, Model errors; T13).
  - Tests inject a scripted chat model (a LangChain fake chat model carrying usage metadata); no Ollama.
- **Acceptance:** the test command passes: a scripted plain, structured, and tool-bound call each return the output with a latency, input and output token counts, and the attempt number passed in (3 in, 3 out); a scripted reply with 901 prompt tokens at num_ctx 1000 logs one warning and one with 900 logs none; the chat client is built with the model, num_ctx, temperature, and thinking setting passed in (asserted on the client's fields); a structured reply that does not parse, and a scripted connection error, each raise the wrapper's error after exactly one request.
- **Out of scope:** role prompts and nodes (T9, T10, T12); Phoenix spans (M3); writing token counts or latency to a record (M4); choosing thinking on/off or temperature (M5); retrying on errors.
- **Depends on:** T3

### T5 — Name-check helpers
- **Status:** todo
- **Produces:** `src/dont_say_oyster/matching.py` (named after `SPEC.md` [R22], Matching rules; author, 2026-10-17): the normalization [R22], Chinese contains and equals, English whole-word-or-phrase contains, and a Chinese-character detector; their tests; the converter smoke test moved to the conversion [R22] names.
- **Consumes:** the converter (`opencc-python-reimplemented`) and `tests/test_converter.py` from M1.
- **Detail:**
  - From BACKLOG M2.5, on the [R22] and [R5] wording in `SPEC.md`, not the BACKLOG text.
  - `tests/test_converter.py` checks `s2tw` today; it moves to `t2s`, since nothing else uses `s2tw`.
  - Chinese characters (`SPEC.md` Glossary): code points of the Unicode Han script (the CJK ideograph blocks, their extensions, and the compatibility ideographs); kana, hangul, bopomofo, and full-width punctuation are not. Punctuation in the normalization: Unicode category P; spaces: whitespace and category Z. Apostrophes in the English rule [R22]: U+0027 and U+2019; every other category P character becomes a space.
  - The helpers are pure functions over strings and string lists and know nothing of cards (T7).
- **Acceptance:** the test command passes with cases for: full-width letters and digits equal their half-width forms; a Traditional text matches a Simplified list entry and the reverse (麵線 and 面线; 烤牡蠣 and 烤牡蛎); 豆干 and 豆乾 normalize to the same string; spaces and punctuation are ignored ("蚵仔 煎！" equals 蚵仔煎); contains is a substring match and equals is not; an English item matches with its case changed and as a phrase with its spaces ("grilled oyster" in "Is it a Grilled Oyster?"); "oysters" is caught by oyster and "peaches" by peach; an item inside a longer word does not match ("raw" in "drawn", "egg" in "eggplant"); the item tang-a-bi-ko is found in "is it tang a bi ko" and in "TANG-A-BI-KO"; the item "Pig's blood cake" is found in "pigs blood cake", in "pig’s blood cake" (U+2019), and in "Pig's Blood Cake"; the item oyster is found in "an oyster-omelet stall"; the item "Oyster Omelet" is found in "oyster-omelet"; full-width "ＯＹＳＴＥＲ" is found by oyster; "grilled   oyster" (three spaces) is found by "grilled oyster"; the detector finds 雪Q餅 and 蚵, and not "QQ", すし, 김밥, ㄅ, or "，"; the converter test converts with `t2s`.
- **Out of scope:** Oracle checks on cards (T7); the loader's name check (T6); keyword matching in the search tool (T11); fuzzy matching ([R22]).
- **Depends on:** M1

### T6 — Normalized name check in the corpus loader
- **Status:** todo
- **Produces:** the corpus loader's name check compares names after the T5 normalization and rejects a name that is empty after it; fixtures; the schema's description text updated by the author.
- **Consumes:** the normalization from T5; `load_corpus` and its exact-string name check in `src/dont_say_oyster/corpus.py` (M1).
- **Detail:**
  - From BACKLOG M2.20 (with M1's T3 F2, deferred to it on 2026-10-08). `SPEC.md` Corpus and Cards (the name rule), [R20], [R21], [R22]. Separate from T5 because a hit on the committed corpus means a corpus correction, and because the schema wording is the author's.
  - The description in `data/corpus/schema.json` says the loader compares exact strings; the new text is a spec change and the author's only part of this ticket, in its own commit (as the schema was in M1).
  - Known hit, found with `t2s` while writing this file: 滷豆干 (a card) has the alias 滷豆乾, equal to its official name after normalization. Corpus correction (author, 2026-10-17, committed 5ba08c6 before this ticket, the way M1's 338f56b did): the aliases 滷豆乾 and 大溪豆乾 were removed (大溪豆干 kept) and the card rebuilt; the data test (which reselects and rebuilds the cards from the committed corpus) is green on it.
  - Error lines keep M1's form: the entry, the field, and for a shared name the other entry.
- **Acceptance:** the test command passes: fixture corpora fail, naming both entries, for a cross-entry pair equal only after full-width conversion, only after space removal, and only after Traditional-to-Simplified conversion (鳳梨酥 and 凤梨酥); a fixture fails for an alias equal to its own official name only after normalization, and for a name made only of spaces and punctuation; M1's good fixture still loads; the data test passes on the committed corpus (5ba08c6 or later) at the loader commit; `data/corpus/schema.json` no longer says "exact strings", changed in a commit by the author.
- **Out of scope:** further corpus corrections (raise them under Open questions); English-name uniqueness (no `SPEC.md` rule asks for it); any other schema change; the Oracle (T7).
- **Depends on:** T5

### T7 — Oracle checks on guesses, Describer output, and questions
- **Status:** todo
- **Produces:** `src/dont_say_oyster/oracle.py`: a guess check (right or not, which name it matched, and whether it is in Chinese) [R20], [R5]; a Describer check that returns what it found [R21]; a question check that returns why a question is invalid [R17]; tests on a committed card.
- **Consumes:** the helpers from T5; `Card`, `load_cards`, and `load_corpus` from M1; the committed cards and corpus.
- **Detail:**
  - From BACKLOG M2.6 and M2.7. Merged: three pure functions over one card on the same helpers, in one module with shared test fixtures; together they are the Oracle's name checks.
  - Cards carry the distractors' Chinese official names only; the question check looks up their English names in the corpus by official name [R17].
  - The checks only report; send-backs, violations, rounds, and counters are the nodes' (T8–T10, T12).
- **Acceptance:** the test command passes on the committed card 烤蚵仔 (`card-5ed17f8f`) and the committed corpus. Guess: 烤蚵仔 is right as the official name; 烤牡蛎 is right as the alias 烤牡蠣; 烤蚵仔好吃 and 蚵仔煎 are wrong; "kao o-a" is wrong and not in Chinese; 雪Q餅 is wrong and in Chinese. Describer: "Grilled Oyster" (an English name, case changed), "oysters" (the forbidden word oyster), "charcoal", and 烤生蠔 (an alias) are each reported; "drawn on the street" passes. Question: one containing 蚵 is invalid (Chinese); "Is it grilled oysters?" is invalid (the card's English name, plural); "Is it like an oyster omelet?" is invalid (the English name of the distractor 蚵仔煎, found in the corpus); "Is it o-a-tsian?", "is it o a tsian", and "Is it o‐a‐tsian?" (U+2010 hyphens) are each invalid (蚵仔煎's English name o-a-tsian); "Does it have oysters?" and "Is it sold at night markets?" are valid.
- **Out of scope:** routing, send-backs, and counters (T8–T10, T12); the loader (T6); the search tool (T11).
- **Depends on:** T5

### T8 — Game State and the program nodes A, G, and F
- **Status:** todo
- **Produces:** `src/dont_say_oyster/state.py` (the LangGraph State with every non-memory row of the State schema) and `src/dont_say_oyster/program_nodes.py` with node A (draw the given card into State), node G, and node F; tests.
- **Consumes:** `Card` and `load_cards` from M1; the guess check from T7.
- **Detail:**
  - From BACKLOG M2.8, M2.10, M2.18, and the node A part of M2.9 (its command part is T13, split). Merged: State has no behaviour of its own, and A, G, and F are program nodes that only read and write State, each a few lines; none is testable without State.
  - Adds `langgraph` (pre-approved: `CLAUDE.md` Rules of engagement; named in `SPEC.md`), pinned in `uv.lock`.
  - Rows: `SPEC.md` State schema without the two memory rows (M6); counters [R25]. Program-only fields that the table does not list are allowed where a loop needs them (the send-back counts of [R11], [R17], [R40]; the attempt number of the output being asked for [R26]; whether the Describer owes a description or an answer; G's guess-only flag) and are marked as such in the code.
  - G: the G row of Full flow of one game, [R14]–[R16]; it also zeroes the reject and lookup counters, which the State schema scopes to the round.
  - F: the F row and [R23], using T7's guess check; it records which name a right guess matched (`SPEC.md` Metrics, "official answer or an alias").
- **Acceptance:** the test command passes: node A given a card id from the committed cards file returns a State in which every row listed in Detail is present with its type and the card rows equal the card; an unknown card id raises an error naming it; G from round 0 gives round 1 and zeroes reject and lookup counters set to 2 and 4; G sets guess-only in round 10, and in round 5 after three questions, and not in round 9 after two questions. F on card 烤蚵仔: the guess 烤牡蠣 gives "Guesser wins" with the alias recorded; a wrong guess in round 10 and a non-Chinese guess in round 10 each give "Guesser loses"; a Guesser violation gives "Guesser loses"; a Describer violation gives "Guesser wins"; a wrong guess in round 3 and a non-Chinese guess in round 4 give no result and route to G.
- **Out of scope:** the graph and its edges (T13); the one-game command (T13); nodes B, D, E (T9, T10, T12); the memory rows and F → H (M6); the JSONL record (M4).
- **Depends on:** T7

### T9 — Node B (Describer) and node C with the Chinese send-back loop
- **Status:** todo
- **Produces:** `src/dont_say_oyster/describer.py` (node B and its prompt builder, which reads `prompts/describer.txt`); node C and its routing in `program_nodes.py`; tests; the prompt approval line in this Detail.
- **Consumes:** the wrapper (T4); the Describer check (T7) and the Chinese-character detector (T5); State and G (T8); the prompt file written by the author, `prompts/describer.txt`, which also holds the [R11] fixed message.
- **Detail:**
  - From BACKLOG M2.11 and M2.12. Merged: C's loop sends output back to B, so the loop cannot be tested without both, and B's output goes nowhere but C.
  - Prompt: the Describer's items in Information isolation, without cross-game memory (M6); its content per [R3], [R18], [R19], [R28], [R30], [R33]; no tools [R31]. The reply is plain text, the description or the answer [R32]; the wrapper adds the rest [R26].
  - B is asked for an answer when the Guesser's latest output is a valid question, otherwise for a description [R10], [R29].
  - When an answer reaches E, C also appends it to the earlier descriptions and answers row (State schema: the program writes it; the Describer and Guesser read it [R33], [R50]); T10 does the same for a description on a pass or forced pass.
  - The prompt and the fixed message are the author's (author, 2026-10-17). The implementer wires the file in and runs one live trial on a committed card with the T1 Describer tag; the author approves or edits the file, and the committed file is the author's; the trial outputs are not committed. M4–M5 tune them.
  - **Prompt approval** (written when it happens): Prompt approved by the author on `…` after a trial on card `…`.
  - C: [R11], [R12], [R21], and the C row of Full flow of one game. In M2 a description always goes to D (the V0–V1 edge is M4). The [R11] send-back count and the [R26] attempt number restart whenever B is asked for a new output (from G, or from D after a reject, T10), never on C's send-back.
  - Isolation test: a State whose every row holds a distinct sentinel string; the built prompt holds the sentinels of the Describer's items and none of the others.
- **Acceptance:** the test command passes with scripted Describer replies on card 烤蚵仔: the isolation test; with a fail verdict and two rejected descriptions with their reasons in State, the prompt holds the verdict's reason [R30] and both rejected descriptions with their reasons; after a valid question the prompt asks for an answer; Chinese, Chinese, then a clean description reaches D with the round counter unchanged, the fixed message in the second and third prompts, and attempt numbers 1, 2, 3; after a reject whose description had already used two send-backs (reject counter 1), the new description asked for is sent back twice more and then reaches D, so each output asked for gets its own two send-backs, with attempt numbers 1, 2, 3 again; a description holding 烤牡蠣 (an alias) reaches F as a Describer violation after one Describer call, with no send-back; a description holding 蚵仔煎 (a distractor, not an [R21] name) is sent back; Chinese three times reaches F as a Describer violation; a description with "oysters" reaches F as a Describer violation; a clean answer to a question reaches E without calling D, with the Guesser's description-or-answer row filled and the answer appended to earlier descriptions and answers; every reply carries latency, token count, and attempt number. This Detail's prompt approval line holds a date and a committed card id.
- **Out of scope:** writing or editing the prompt or the fixed message (the author's); node D and the reject loop (T10); node E (T12); the graph (T13); cross-game memory in the prompt (M6); checking sentence count or repetition [R8].
- **Depends on:** T4, T7, T8

### T10 — Node D (Challenger) and the reject loop
- **Status:** todo
- **Produces:** `src/dont_say_oyster/challenger.py` (node D and its prompt builder, which reads `prompts/challenger.txt`); D's routing with the reject loop; tests; the prompt approval line in this Detail.
- **Consumes:** the wrapper (T4); the Chinese-character detector (T5); State and the description row a scripted B leaves in it (T8); the prompt file written by the author, `prompts/challenger.txt`, which also holds the [R40] fixed message and the wording of the [R40] re-ask.
- **Detail:**
  - From BACKLOG M2.13 and M2.14. Merged: the reject loop is D's routing back to B, so neither is testable alone. The loop is tested on State alone, with a scripted description in the row D reads: D writes the verdict with its reason and the rejected description with its reason, and names B as the route; that the next Describer prompt then holds them is T9's test ([R30]), so this ticket does not need T9 and runs beside it.
  - Prompt: the Challenger's items in Information isolation; judging rule [R35]; [R4], [R34], [R36]–[R38], [R41]. Structured output: verdict and optional reason [R39], [R40]; the [R40] re-ask is a second structured call with the same schema, recorded as its own call with its own latency, token count, and attempt number 2 [R26]; the verdict row keeps the first call's latency, token count, and attempt number, since the verdict is the first call's, and takes only the reason from the re-ask (a ticket-level reading; `SPEC.md` does not say which call's fields the row carries). Prompt as in T9, with the T1 Challenger tag.
  - **Prompt approval** (written when it happens): Prompt approved by the author on `…` after a trial on card `…`.
  - Rejects, forced passes, and their counters: [R13], [R25], and the D row of Full flow of one game.
  - On a pass or a forced pass the program fills the row the Guesser reads (State schema, the note under the table) and appends the description to the earlier descriptions and answers row; a rejected description goes only to the earlier rejected descriptions row, with its fail reason (State schema).
- **Acceptance:** the test command passes with scripted replies on card 烤蚵仔: the isolation test (the official name, aliases, distractors, and the description only); a pass reaches E with the description in the Guesser's row and appended to earlier descriptions and answers; a fail then a pass routes to B once with the verdict row holding the fail and its reason, the earlier rejected descriptions row holding the description with its reason, the reject counter 1, the round counter unchanged, then routes to E; three fails reach E as a forced pass with the forced pass counter 1, the reject counter 2, the round counter unchanged, the third description in the Guesser's row, the earlier rejected descriptions row holding the first two with their reasons, and earlier descriptions and answers holding only the third; a fail whose reason has Chinese, then an English reason, keeps the English reason after one re-ask, the re-ask carrying attempt number 2 and the verdict row the first call's latency, token count, and attempt number 1; Chinese twice gives the fixed message as the reason with the verdict fail kept; a fail whose reason has Chinese, then a re-ask reply carrying the verdict pass and an English reason, leaves the verdict fail with that English reason, routes to B, and raises the reject counter to 1; a pass whose reason has Chinese makes one Challenger call and reaches E with no reason in the verdict row. This Detail's prompt approval line holds a date and a committed card id.
- **Out of scope:** writing or editing the prompt or the fixed message (the author's); node E (T12); the graph (T13); the Challenger toggle for V0–V1 (M4); whether rejects are reasonable, or changing the Challenger model (M5).
- **Depends on:** T4, T5, T8

### T11 — Search tool
- **Status:** todo
- **Produces:** `src/dont_say_oyster/search.py`: the search tool with its typed input schema [R44] and output [R45], [R46], as a plain function and its LangChain tool; the model-facing field and value descriptions; tests.
- **Consumes:** `load_corpus` and `CorpusEntry` from M1; the value lists in `data/corpus/schema.json`; T3's record on enum values with spaces; T5's English matching.
- **Detail:**
  - From BACKLOG M2.15 (its enum question was checked live in T3, split). `SPEC.md` Corpus and Cards (Attributes), [R44]–[R46]; Goals (Tool interface).
  - The six filter fields are the six attribute fields, dish_type, main_ingredients, cooking_method, flavor, physical_form, occasion, each an optional list of its values, read from `data/corpus/schema.json` so the two cannot drift. Each field and value is described to the model by its definition in `SPEC.md` Corpus and Cards; that text sits in one model-facing file, `prompts/search_tool.json`, and costs Guesser tokens.
  - Filters and keywords: [R44], with keywords matched by T5's English matching (M1 T2 F6, deferred to this milestone, is settled there). Values with spaces follow T3's record (M1 T2 F7); if T3 found them altered, the schema shape follows the author's answer under Open questions.
  - Results come in corpus file order. A call the schema rejects (a value outside its field's list, or a call with neither filter nor keyword [R44]) is not searched; the LangChain tool returns the validation message as its result instead of raising (`SPEC.md` Recovery, forks, and replay, Model errors). Counting lookups is node E's (T12).
- **Acceptance:** the test command passes on a fixture corpus: a filter-only query; two values in one field (either passes); two fields (both must pass); a filter on occasion, where some entries have no value (those do not pass); a filter plus a keyword returns only entries that pass both; two keywords return entries matching either; a keyword matches a whole word or its plural and not a substring ("noodle" finds an entry named "Rice Noodles"; "noodles" does not find one named "Rice Noodle", since the keyword is the item [R44]; "rice" does not find an entry whose only English name holds "price"); a call with no filter and no keyword returns the validation message and no entries; a query with more than ten matches returns the first ten in corpus order and says there are more; each result holds exactly the official name, aliases, English names, and attributes (no forbidden words); a value not in its field's list returns the validation message as the result, with no entries and no search; the tool's JSON schema lists each field's values exactly as `data/corpus/schema.json` does.
- **Out of scope:** the lookup limit and the tool loop (T12); the Guesser prompt (T12); ranking or fuzzy matching; the lookup toggle for V0 (M4); lookup spans (M3); recall metrics (M7).
- **Depends on:** T3, T5

### T12 — Node E (Guesser): tool loop, structured call, and invalid-question loop
- **Status:** todo
- **Produces:** `src/dont_say_oyster/guesser.py` (node E and its prompt builder, which reads `prompts/guesser.txt`); E's routing; tests; the prompt approval line in this Detail.
- **Consumes:** the wrapper (T4) and the tool-calling pattern checked in T3; the question check (T7); State and G's guess-only flag (T8); the search tool (T11); the prompt file written by the author, `prompts/guesser.txt`, which also holds the [R17] fixed message.
- **Detail:**
  - From BACKLOG M2.16 and M2.17. Merged: one node; the tool loop ends in the structured call, and the invalid-question loop repeats that call [R17].
  - Prompt: the Guesser's items in Information isolation [R42], without cross-game memory (M6); content per [R5], [R16], [R17], [R49], [R50]. Prompt as in T9, with the T1 Guesser tag.
  - **Prompt approval** (written when it happens): Prompt approved by the author on `…` after a trial on card `…`.
  - Tool loop: [R43], [R49]; calls with the search tool bound until the model stops calling it or the limit is reached; lookups and results go into State. Counting: [R43]; a call not run gets a fixed tool result saying lookups are blocked (its text in `prompts/guesser.txt`; a ticket-level reading, since `SPEC.md` says only that the program blocks the call and every tool call in the message history needs a result). Tool-loop calls carry the attempt number of the output being asked for, 1 on the first try [R26]; the structured call carries the same number. A call the schema rejects gets T11's validation message as its result (`SPEC.md` Recovery, forks, and replay, Model errors).
  - Structured call: [R47], [R48], with no tool bound; its schema is question-or-guess, or guess only when G set the flag [R16]. Invalid questions: [R17]; the earlier guesses and questions row: State schema. Attempt number: [R26].
  - A guess goes to F, which decides right or wrong (T8).
- **Acceptance:** the test command passes with scripted replies on card 烤蚵仔 and the committed corpus: the isolation test (sentinels as in T9); two lookups and then none give two results in State, the lookup counter 2, then one structured call made with no tool bound; six lookup requests in a row run five, do not run the sixth, leave the lookup counter at 5, and the structured call follows; after three lookups, one reply carrying three tool calls runs the first two, gives the third the blocked result without searching, leaves the lookup counter at 5, and the structured call follows; a tool call with a value outside its field's list, and a tool call with no filter and no keyword, each count as one lookup and their result in State is the validation message [R44]; a guess with confidence 0.8 reaches F and is written to earlier guesses and questions; a valid question raises the question counter by one, is written there, and reaches G; "Is it like an oyster omelet?" twice, then a valid question, raises the question counter once, leaves the round counter unchanged, puts the fixed message in both retry prompts, makes no tool-bound call after the first invalid question (asserted on the scripted model's requests), writes neither invalid question to earlier guesses and questions, gives the structured calls attempt numbers 1, 2, 3, and reaches G; E run again for the next round makes its first structured call with attempt number 1; three invalid questions reach F as a Guesser violation with the question counter unchanged; with the guess-only flag set, the structured call's schema has no question; every call carries latency and token count, and every call its attempt number: the tool-loop calls and the structured call of one try carry the same number, 1 on the first try and 2 on the first retry. This Detail's prompt approval line holds a date and a committed card id.
- **Out of scope:** writing or editing the prompt or the fixed message (the author's); F's outcome (T8); the graph (T13); cross-game memory (M6); the lookup toggle for V0 (M4); lookup spans (M3); recall metrics (M7).
- **Depends on:** T3, T4, T7, T8, T11

### T13 — V2 graph and the one-game command
- **Status:** todo
- **Produces:** `src/dont_say_oyster/graph.py` (A, G, B, C, D, E, and F in one LangGraph graph with the V2 transitions) and the one-game command `play-game` (`src/dont_say_oyster/play.py`, console script); tests that play whole games with scripted model outputs.
- **Consumes:** nodes and State from T8–T10 and T12; the search tool (T11); the wrapper (T4); the cards, corpus, and their loaders from M1.
- **Detail:**
  - From BACKLOG M2.19 (the wiring; the live game is T14, split) and the command part of M2.9 (node A is T8, split). Merged: the command only builds the graph and runs it on one card, and the graph is tested end to end through the command.
  - Transitions: Full flow of one game, the V2 column; with no variant argument, C → D always (M4 adds the toggles).
  - Parameters: `SPEC.md` Implementation (Commands) without the variant (M4) and the memory file (M6): model and num_ctx per role, the cards path, the card id, the corpus path, the output path, temperature, and thinking on/off per role (M5 decides it per role). The Ollama endpoint comes from `.env`.
  - Output: until the JSONL record (M4), the command writes the final State as one JSON file to the output path and prints the outcome and the round, question, reject, and forced pass counts. num_ctx warnings (T4) go to stderr. A model error (T4) stops the game (`SPEC.md` Recovery, forks, and replay, Model errors): the command exits non-zero and writes no output file.
  - The command sets LangGraph's recursion limit explicitly from the worst case (every loop at its maximum in every round: two [R11] send-backs for each description or answer asked for, two rejects and a forced pass, two [R17] retries of the structured call only), with a comment showing the computation, and never relies on the default: langgraph 1.2.16 defaults to 10007 steps (`LANGGRAPH_DEFAULT_RECURSION_LIMIT`), earlier versions to 25, below a ten-round V2 game.
  - Tests inject scripted models through `main` (M1's `Ask` pattern); no Ollama.
- **Acceptance:** the test command passes with scripted outputs on card 烤蚵仔: a right guess in round 1 gives "Guesser wins" and an output file holding the final State; a game that passes through a Chinese send-back, one reject, a question and its answer (no Challenger call for the answer), and a wrong guess before a right guess gives "Guesser wins" with counters equal to the scripted path; a forbidden word in round 2 gives a Describer violation; three invalid questions give a Guesser violation; ten rounds of wrong guesses give "Guesser loses" with the round counter at 10 and no eleventh round; a scripted worst-case game (in each of ten rounds: three descriptions each sent back twice, two rejects then a forced pass, and a wrong guess, preceded in rounds 1–9 by two invalid questions) reaches F as "Guesser loses" without hitting the recursion limit; a scripted connection error from the Challenger in round 2 exits non-zero and writes no output file; an unknown card id exits non-zero without a model call; `play-game --help` lists every parameter in Detail.
- **Out of scope:** the live game (T14); the variant argument and toggles (M4); the JSONL record (M4); Phoenix (M3); the memory-file argument (M6); the batch script (M7).
- **Depends on:** T8, T9, T10, T12

### T14 — One live V2 game
- **Status:** todo
- **Produces:** the record of one V2 game on the three local models that reaches F, written into this Detail.
- **Consumes:** the tags and num_ctx from T1; `play-game` from T13; the committed cards and corpus (5ba08c6 or later).
- **Detail:**
  - From BACKLOG M2.19 (the run; the wiring is T13, split). This is the M2 exit check.
  - **Settings** (author fills in at dispatch): the card id; thinking on/off per role. Temperature 0.7 and num_ctx from T1.
  - An agent runs the command. A run stopped by a model error writes no output file and is rerun as a crash (`SPEC.md` Recovery, forks, and replay, Model errors); a run stopped by a code error is debugged by the session (`CLAUDE.md`, Delegation), fixed as an audit finding of the ticket that owns the code, and rerun; every run is recorded, not only the last.
  - The record, written into this Detail: the date; the command line; `ollama --version` and the three tags with their IDs; the card; for each run, the outcome or the error, and the round, question, reject, and forced pass counts; wall time; any num_ctx warning; where the output file was written. The output file is not committed (the JSONL record is M4).
  - A live run: accepted by the record, not by who wins or by the quality of the descriptions.
- **Acceptance:** this Detail holds the record of a run made with the T1 tags at their num_ctx and temperature 0.7 whose output file holds a game result that is one of the four F outcomes; the test command passes at the commit the run used.
- **Out of scope:** tuning prompts, models, temperature, or thinking (M4–M5); games in V0, V1, or more cards (M4); Phoenix (M3); the JSONL record (M4).
- **Depends on:** T1, T6, T13

## Open questions for the author

Q1–Q10 and Q12–Q15 were answered on 2026-10-17: Q9 by the author in chat (the author writes the prompts and fixed messages); the rest in SPEC.md commits cfdaa8a (Q1, Q2), 7e9f9cb (Q3, Q12), bbd5b8d (Q4, Q5, Q15), a76f200 (Q13, Q14), 5705e5f (Q6, Q7), 4948881 (Q8, Q10).

Q11 (the 滷豆干 aliases 滷豆乾 and 大溪豆乾, equal to other names of the entry under `t2s`) was answered by the author on 2026-10-17 and fixed in 5ba08c6, recorded in T6.

Q16, Q17, and Q18 are open; none blocks T2 (author, 2026-10-18).

- **Q16** (T1, 2026-10-18): Ollama 0.40.6 reports `gemma4:26b-a4b-it-q4_K_M` at 1.5 GB in `ollama ps` (1540850973 bytes for `size` and `size_vram` in `/api/ps`), loaded alone or with the other two. The model is fully loaded: before loading, llama.cpp projects 17043 MiB on the GPU in the server log (model 16001, context 720, compute 322); 31/31 layers are offloaded; and wired memory rose by about 17.9 GiB when it was loaded alone. The weights are the tag's: the blob re-hashed on disk gives `7121486771cb…`, the model digest in the manifest, and the ID `5571076f3d70…` equals the sha256 of the registry's manifest for the tag. The fit checks for the two loads after it were limited by system free memory (`system_limited=true`, 30.0 and 12.3 GiB available), not by the GPU figure. Only the Gemma load logs "detected Ollama-format gemma4 GGUF; applying compatibility fixes"; the cause is not confirmed. The under-count also feeds Ollama's own scheduler: the server log shows its GPU-available figure falling from 51.8 to 50.4 GiB when this model loaded, so the fit decisions for the two later loads rested on system free memory (`system_limited=true`, 30.0 and 12.3 GiB), not on the GPU figure; where that limit is not binding (M5 and M7 batch runs), a fourth model could be admitted on the wrong figure. For the author: whether to recheck this when the Gemma tag or the Ollama version changes (M5). On the rerun with the Challenger `gemma4:12b-it-q4_K_M` (Record 2), the 12B shows the same anomaly, 678 MB in `ollama ps` (678869072 bytes in `/api/ps`) against the 7693 MiB llama.cpp projects, without logging the compatibility-fixes line.
- **Q17** (T1, 2026-10-18): the server config reads `OLLAMA_FLASH_ATTENTION:false`, yet Ollama started each llama-server with `--flash-attn auto` and all three logged "Flash Attention enabled". Flash attention changes memory use and can change outputs slightly. For the author: whether M5 pins it. On the rerun (Record 2), the 12B's runner also started with `--flash-attn auto` and logged "Flash Attention enabled".
- **Q18** (T1, 2026-10-18; for the author to decide in M5): four informal checks, outside T1's record, asked Gemma 4 12B, Gemma 4 26B, Qwen 3.5 9B, and Qwen 3.8 27B in Chinese what ten Taiwanese snacks are, one request per snack with thinking off. The author's rough grading put the first three at about 52%, 55%, and 43% correct and Qwen 3.8 at about 43% (its worst misses: 烤蚵仔 described as battered and pan-fried, as 蚵仔煎 is, and 阿給 placed in 台南), with errors that are specific and invented rather than vague (Qwen 3.5 9B: 阿給 as fried octopus pizza, 棺材板 traced to 高雄的阿宗麵線, 杏仁茶 with no almond). This matters because knowledge of the dishes, not Chinese, is what the Challenger [R35] and the Describer need, and no model tested in the 9B–27B class knows them well; a Describer that states a wrong cooking method or region sends the Guesser's filters [R44] after the wrong entries, which the V1 recall split (`SPEC.md` Experiment plan) records as "not found". The check of ten fail verdicts in M5 (`SPEC.md` Milestones, M5) is where this is judged on real games.

## Audit findings

