# M1 — Corpus

## Goal & exit criterion

See `SPEC.md`, Milestones, M1. Do not copy the bullets here; they go stale.

**Exit criterion:** Done when the corpus and the forty cards load into the program without error, every entry and every distractor has been reviewed by me, and the four batch manifests carry the same card order.

- **Real:** a reviewed corpus of about three hundred Taiwanese snacks, forty reviewed cards with distractors, and four batch manifests sharing one card order, all loaded and checked by the program.
- **Absent:** no models for the game, no game flow, no Oracle checks (M2); the manifests carry no models, num_ctx, temperature, or thinking on/off yet (M4–M5).

## How to use these tickets

T1 and T2 can run in parallel (T2 is the author's `SPEC.md` change). T3 follows both. Then the work runs on two tracks: the corpus track T4 → T5 (T5 is the author's hand review) and the code track T6 → T7. T8 joins them and closes the milestone. T6 and T7 each carry author decisions marked "author fills in"; they are not dispatched until those are filled in. T2, T4, T5, and T8 need the author (in T8 an agent runs the commands); the rest are an implementer's. Any commit may be made by an agent with the author's approval. One ticket, one commit; Status updates, audit fixes, and the `DECISIONS.md` entry after a spec change are their own small commits.

## Tickets

### T1 — Repo layout and dev toolchain
- **Status:** done 6becd4f
- **Produces:** a uv project on Python 3.13 or later (`pyproject.toml`, `uv.lock`), the committed directory structure, the chosen test runner, linter, type checker, and Simplified-to-Traditional converter, and a `## Commands` section appended to `CLAUDE.md` with the lint, type-check, and test commands.
- **Consumes:** —
- **Detail:**
  - From BACKLOG M1.1. `SPEC.md` Implementation (Language and runtime, Repo).
  - The layout must give a place to each of these, because later tickets refer to them as "from T1": the Python package, tests and test fixtures, the corpus file, the card files (the selection, the distractor file, the cards file), prompts, and one directory per batch (V0–V3) holding its manifest; BACKLOG M7.1 writes each batch's JSONL records next to its manifest. The committed directories are the record of the layout (a `.gitkeep` where one is still empty).
  - The dev toolchain is pre-approved (`CLAUDE.md`, Rules of engagement); versions are pinned in `uv.lock`. LangChain, LangGraph, and Phoenix are not added here; the first ticket that imports one adds it.
  - The converter is chosen and installed now and first used in M2 [R22]; one smoke test calls it so the test run is not empty.
  - After this commit, the date of the first code commit goes into `docs/DECISIONS.md` as its own doc commit (`CLAUDE.md`, Start here, step 4).
- **Acceptance:** the commit contains a directory for each location named in Detail (package, tests, test fixtures, corpus, cards, prompts, and four batch directories V0–V3); inside the repo, `uv run python --version` prints 3.13 or later; the lint, type-check, and test commands in the new `## Commands` section each exit 0; the test run includes one test that converts a Simplified Chinese string to Traditional.
- **Out of scope:** any data file or schema (T3); LangChain, LangGraph, Phoenix, or any model client (T6); CI; a README.
- **Depends on:** —

### T2 — Attribute fields in SPEC.md
- **Status:** done 5fbf77b
- **Produces:** the attribute field list, written into `SPEC.md` Corpus and Cards: for each field, its name, its allowed values (a closed list), how many values it takes, and whether every entry must have it.
- **Consumes:** —
- **Detail:**
  - From BACKLOG M1.2. The list lives in `SPEC.md`, not in a separate file, unless it grows too large for it (author, 2026-10-03).
  - A spec change: the author edits; the review, the cross-reference check, and the `DECISIONS.md` entry follow `CLAUDE.md`, Delegation (Changing `SPEC.md`). The cross-reference check also names any later BACKLOG item the list affects; that patch goes in the same commit as the spec change.
  - The fields are the search tool's filter fields [R44].
- **Acceptance:** a commit changes `SPEC.md` Corpus and Cards so it lists every attribute field, each with its allowed values, how many values it takes, and whether it is required; the next commit adds a `docs/DECISIONS.md` entry citing that commit's hash.
- **Out of scope:** the schema code (T3); the distractor model and prompt (T6); the card-selection and ordering criteria (T7); any other part of `SPEC.md`.
- **Depends on:** —

### T3 — Corpus schema and loader
- **Status:** done db7f4ee (schema e73d81a, by the author)
- **Produces:** the corpus schema `data/corpus/schema.json` (designed and settled by the author, e73d81a) and a loader in the package that validates the corpus JSON file against it and reads it into typed entries; an entry point that loads a corpus file and prints its entry count; good and bad fixtures.
- **Consumes:** the attribute fields in `SPEC.md` from T2; the package and fixture locations from T1.
- **Detail:**
  - From BACKLOG M1.3. The schema is the author's: designed and settled by the author (e73d81a, 2026-10-08) and named as the corpus format in `SPEC.md` Implementation (Data and persistence); it fixes entry fields, key names, and attribute values. The loader does not change it; from e73d81a on, a change to it is a spec change.
  - The loader validates every entry against the schema with the `jsonschema` package (approved by the author 2026-10-08; pinned in `uv.lock`) and turns each validation error into an error, not a warning, naming the entry (its index, and its official name when present) and the failing field. The schema covers: an unknown or missing field; an empty official name; an empty English names list; a value outside its allowed values; too many or too few values in an attribute; a value repeated within one attribute; an empty or repeated string in aliases, English names, or forbidden words; a value of the wrong type; a drink Physical form exactly when Dish type is Drink (both ways: a drink form without Dish type Drink, and Dish type Drink without a drink form).
  - The loader checks in code what the schema cannot: two entries with the same official name, since distractors are looked up by official name [R17]; an alias equal to its entry's official name (author, 2026-10-08); a name (official name or alias) held by two entries, since a guess of one would count as correct for the other [R20] (author, 2026-10-08). Names are compared as exact strings; normalization [R22] is M2's.
  - The empty official name and English names checks are the part of BACKLOG M1.4 that lands here (split with T4).
  - Empty aliases and empty forbidden words are allowed (author, 2026-10-03; changing this is a spec change).
  - No per-field language checks here; the Chinese-character detector is M2's (BACKLOG M2.5).
  - Fixtures: a hand-written three-entry corpus, plus one bad fixture per error above.
- **Acceptance:** the test command passes: the three-entry fixture loads into three typed entries; each bad fixture fails with an error naming the entry and the field; the entry point prints the count 3 for the good fixture; `data/corpus/schema.json` is unchanged by the loader commit.
- **Out of scope:** changing `data/corpus/schema.json` after e73d81a (a spec change); bringing in the real corpus (T4); cards, card ids, and distractors (T6, T7); normalization and name checks (M2); the search tool (M2).
- **Depends on:** T1, T2

### T4 — Bring in the corpus
- **Status:** todo
- **Produces:** the corpus JSON file at the corpus location from T1, aiming for about three hundred entries.
- **Consumes:** the attribute fields from T2; the schema (`data/corpus/schema.json`), loader, and entry point from T3.
- **Detail:**
  - From BACKLOG M1.4, split: the non-empty checks are in T3, the file arrives here. What an entry holds and how the official name is chosen: `SPEC.md` Corpus and Cards.
  - The corpus is generated outside this repo, and which LLM generated it is not recorded (author, 2026-10-03); this ticket brings the file in.
  - Accepted by the record it leaves, not by the quality of the entries; the author reviews them in T5.
  - Only mechanical fixes so the loader accepts the file (JSON syntax, field names, anything the schema rejects); content corrections belong to T5.
- **Acceptance:** the T3 entry point loads the committed corpus file without error and prints its entry count (the count is recorded, not gated: `SPEC.md` Corpus and Cards says "aiming for").
- **Out of scope:** content corrections (T5); schema changes (if the file needs a field the schema lacks, stop and raise it under Open questions); distractors (T6–T8).
- **Depends on:** T3

### T5 — Review every corpus entry
- **Status:** todo
- **Produces:** the corrected corpus file, every entry reviewed by the author.
- **Consumes:** the corpus file from T4; the entry point from T3.
- **Detail:**
  - From BACKLOG M1.5 and M1.6, merged: one review of one file; the backlog's 1–150 / 151–300 split was only for size. The author may review over several sittings and commits once.
  - What to check against each official name: `SPEC.md` Corpus and Cards; attributes also against the T2 list.
  - Attribute edge cases left to this review (author, 2026-10-07): which Flavor an item with no clear taste gets; which Dish type a breakfast main gets (Occasion: Breakfast still finds it); the Dish type of an item both sweet and savory; whether a boiled or brewed drink is Boiled or No Cooking.
  - The author's ticket. An agent may run the entry point after edits; it does not change entries.
- **Acceptance:** the author approves the reviewed corpus file and it is committed (if the review changed nothing, the T4 commit stands and the Status names it); the T3 entry point loads the file at that commit without error.
- **Out of scope:** schema changes (stop and raise them under Open questions); card selection and distractors (T7, T8).
- **Depends on:** T4

### T6 — Distractor picker
- **Status:** todo
- **Produces:** the distractor prompt file at the prompts location from T1, and a pick command that reads the corpus and a list of official names (a JSON array) and writes the distractor file; a re-pick option on that command for named official names.
- **Consumes:** the schema and loader from T3; the prompts and card-file locations from T1.
- **Detail:**
  - From BACKLOG M1.7 and M1.8 (the code and the re-pick); the live run and the review are T8. Merged because the prompt is useless without the code that sends it, and the code cannot be tested without a prompt. Re-pick is here because it touches only this ticket's file (author, 2026-10-03).
  - **Model** (author fills in before dispatch): _model and version, local or cloud._ A cloud model needs a provider package, which is not pre-approved (`CLAUDE.md`, Rules of engagement); the author's approval is written here with the model. Keys come from `.env`.
  - **Prompt** (author fills in before dispatch): _what makes another entry confusable with this card_ (`SPEC.md` Corpus and Cards, Distractors; [R35]). The implementer puts it in the prompt file as written.
  - Each prompt carries the card's entry and every other entry's official name, English names, and attributes. If that does not fit the model's context, stop and raise it under Open questions.
  - The program keeps a pick only if it equals the official name of another entry (exact string), drops duplicates, keeps the first five valid picks, and lists every other pick as dropped with its reason. Zero valid picks is allowed.
  - The distractor file holds, for each official name, numbered rounds of kept and dropped picks, and one current distractor list: the list the author reviews and may edit by hand, and the list T7 builds the cards from. A pick round sets the current list to that round's kept picks.
  - Re-pick: given official names, the command runs a new round for those names only and replaces their current lists; every other name, including the author's hand edits, stays unchanged; an unknown name is an error. A full run starts a fresh distractor file.
  - This ticket also provides the distractor file's loader; T7 reads the file only through it, so the file's shape is defined in one place.
  - This ticket adds the model client package (LangChain's, pre-approved, or the cloud provider package approved above). The LLM call sits behind one function so tests feed scripted replies.
- **Acceptance:** the prompt file exists at the prompts location; the test command passes on a fixture corpus of at least eight entries with scripted replies: a reply naming the card itself, a name not in the corpus, a duplicate, and seven valid names gives a current list of the first five valid names and every other pick as dropped with its reason; an empty reply gives an empty current list; after a hand edit to one name's current list, re-picking a different name with a different scripted reply changes only that name's current list, leaves the hand edit and every other name's rounds unchanged, and gives the re-picked name rounds 1 and 2; re-picking an unknown name exits non-zero.
- **Out of scope:** selecting the forty names and building cards (T7); running on the real corpus (T8); retrying the LLM automatically after bad picks.
- **Depends on:** T3

### T7 — Card selection, card builder, and batch manifests
- **Status:** todo
- **Produces:** a select command that writes the forty official names chosen by the selection criterion below (the selection, a JSON array, the input of the T6 pick command); a build command that reads the corpus, the selection, and the distractor file and writes the cards file and the four batch manifests, ordered by the ordering criterion below; a card loader; a manifest check; and a data test that loads the committed corpus, cards file, and manifests.
- **Consumes:** the loader from T3; the distractor file loader from T6; the card-file and batch locations from T1.
- **Detail:**
  - From BACKLOG M1.9 (the criterion and the program that selects the forty), M1.10, and M1.11 (the order and writing the manifests); all three are split with T8, which runs the commands and holds the review. Merged because select and build are two ends of one pipeline over one input, and the card loader and data test are how its output is checked.
  - **Selection criterion** (author fills in before dispatch): _how forty entries are chosen from the reviewed corpus._
  - **Ordering criterion** (author fills in before dispatch): _the order of the forty cards, shared by all four variants._
  - Both criteria are stated so a program can apply them to the corpus file (`SPEC.md` Milestones, M1: "have the corresponding program"); a criterion that uses randomness names its seed.
  - Card fields: `SPEC.md` Corpus and Cards and State schema (the card rows, Card id) [R1], [R9]. Distractors are each name's current list from the distractor file; every other card field except the card id is copied from its corpus entry. The cards file is never edited by hand; it is rebuilt.
  - Card id: a string, unique, the same on every run over the same corpus, and not derived from the card's position in the order (the order lives in the manifests).
  - The card loader raises an error on: a card count other than forty; a missing field; a duplicate card id; more than five distractors; a duplicate distractor on one card; a distractor that is not the official name of another corpus entry (the English-name lookup in [R17] needs it).
  - Manifests: one JSON file per variant V0–V3, each in its batch directory, holding the variant, the cards file path, and the forty card ids in order. Models, num_ctx, temperature, and thinking on/off are left out; later milestones add them (author, 2026-10-03).
  - The manifest check is a function over manifest and cards paths; it fails when the four manifests' orders differ or do not list exactly the cards file's ids.
  - The data test (author, 2026-10-03, instead of a separate check command) runs in the normal test command, so every later commit that touches these files is checked. Its corpus part loads the committed corpus and skips only while the corpus file is absent (before T4). Its card part loads the cards file and runs the manifest check on the committed manifests; it skips only while the cards file and all four manifests are absent (before T8), and fails if some are present and some are not.
  - Tests run select and build on a generated fixture corpus, shaped so both criteria apply to it, with a fixture distractor file.
- **Acceptance:** the test command passes on a fixture corpus of at least forty-one entries: select writes forty names and a second run writes the same names; build writes forty cards with every field, distractors equal to the fixture's current lists, and four manifests listing the same forty ids in the same order; a second build gives the same ids in the same order; the manifest check fails on fixture files where one manifest's order is changed and where a card is removed; the card loader fails on each error listed in Detail; the data test's card part reports a skip, with its reason, while the card files are absent, and fails when only some of them are present.
- **Out of scope:** the live run on the real corpus and the distractor review (T8); models, num_ctx, temperature, and thinking on/off in the manifests (M4–M5); the batch script (M7).
- **Depends on:** T3, T6

### T8 — Build the forty cards and review every distractor
- **Status:** todo
- **Produces:** the committed selection, distractor file, cards file, and four manifests, built from the reviewed corpus, with every distractor on the forty cards reviewed by the author.
- **Consumes:** the reviewed corpus from T5; the pick command from T6; the select and build commands and the data test from T7.
- **Detail:**
  - From BACKLOG M1.8, M1.9, and M1.10 (the run) and M1.11 (the review).
  - Order: an agent runs select, then pick on the selection. After the review starts, only re-pick is used: a full pick run starts a fresh distractor file and discards the author's edits. The author reviews every name's current list in the distractor file and fixes a wrong one by editing it (removing, replacing, or adding; the author picks the final set) or by re-pick, after which only the re-picked names need another look. Then the agent runs build.
  - One commit, because unreviewed distractors must never be committed as if they were final. The distractor file keeps every round, so the author's changes are the difference between each name's latest round and its current list.
  - Card ids and order are not edited by hand; changing them means changing a T7 criterion and rerunning from select.
  - A live run: accepted by the record, not by the quality of the picks.
- **Acceptance:** one commit, made with the author's approval, adds the selection, the distractor file, the cards file, and the four manifests; the corpus file is unchanged since the commit named in T5's Status (`git diff` is empty); rerunning build on the committed files leaves `git diff` empty; the test command passes and its output reports both parts of the T7 data test as passed, not skipped. This is the M1 exit check.
- **Out of scope:** corpus corrections found during the review (raise under Open questions; changing the corpus after T5 means rerunning this ticket); hand edits to the cards file; models, num_ctx, temperature, and thinking on/off in the manifests (M4–M5).
- **Depends on:** T5, T7

## Open questions for the author

- [R22]: s2tw cannot tell 面 from 麵 outside its phrase table; 面线, 大肠面线, 猪肠面线, 鸭肉面线 all convert to 面線 and miss the Traditional 麵線 names. Raised in T1 F1; decide before M2 tickets (M2.5, M2.20).

## Audit findings

- T1 F1: converter smoke test used s2t (面→麪), breaking [R22] for 麵 names; fixed fb7ed56 (s2tw).
- T1 F2: SPEC.md Implementation (Repo) still called the layout undecided; fixed 4b7f362 (author).
- T1 F3: commit scope "repo" was not a module or doc; fixed by amending before push to 6becd4f (author approved 2026-10-07).
- T2 F1: Main ingredients had no honest value for grass jelly, aiyu, sugarcane juice, almond tea, or sesame paste (Fable, blocking); fixed before commit in 5fbf77b (author).
- T2 F2: "Drink" was a value in both Dish type and Physical form (Fable); fixed before commit in 5fbf77b, renamed Smooth Drink (author).
- T2 F3: Tea had no definition, so herbal teas could land in Tea (Fable re-check); fixed before commit in 5fbf77b (author).
- T2 F4: the spec change made T2's Detail ("Location is fixed") and Acceptance ("location included") false and left T3's loader errors incomplete (Sonnet, Fable); fixed c1da680.
- T2 F5: the author's corpus review sentence in SPEC.md omitted attributes (Sonnet); fixed 6400cdb (author).
- T2 F6: [R44] does not say how keywords combine with the filters or with each other (Sonnet, Fable; predates T2); deferred to BACKLOG M2.15 (author, 2026-10-07), recorded c1da680.
- T2 F7: attribute values with spaces may not work as enum strings in Ollama tool schemas (Fable); deferred to BACKLOG M2.15 (author, 2026-10-07), recorded c1da680.
- T2 F8: attribute labelling edge cases (Flavor for bland items, breakfast mains, sweet-and-savory items, Boiled vs No Cooking for drinks) (Fable); deferred to T5 (author, 2026-10-07), recorded c1da680. 冬粉 fitting Noodles only by a stretch: no change, not a snack in its own right (author).
- T2 F9: BACKLOG M1.2 still says location is fixed (Sonnet); no change, the M1 block is no longer maintained (BACKLOG line 9; author approved c1da680 without it).
