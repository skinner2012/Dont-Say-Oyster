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

### 2026-10-17 — Both scripts to Simplified; English items match plurals and ignore punctuation; a mixed-script guess is Chinese  (commit cfdaa8a)
- Changed: R5, R17, R22, changed.
- Why: M1 left three Open questions. s2tw cannot tell 面 from 麵 or 干 from 乾 outside its phrase table, so a guess in one spelling missed the other; converting both sides to Simplified (opencc t2s) folds every variant to one form, and the corpus scan after the change found no cross-entry collision. Forbidden words and English names are stored singular, so "oysters" passed the Describer check; an item now also matches its plural (s or es). 107 of the 622 English names carry a hyphen or apostrophe (tang-a-bi-ko, Pig's blood cake), and a writer may drop or change them, so the English path removes apostrophes and turns other punctuation into spaces, keeping word boundaries so a hyphen cannot glue a forbidden word to its neighbour. "In Chinese" is defined as containing at least one Chinese character, so aliases such as 雪Q餅 are valid guesses. R17 now says the question check uses the R22 English rule.
- Rejected: s2tw plus a hand-kept fold table for 面/麵 and 干/乾 (a second list to maintain); storing both singular and plural forms in the corpus (doubles every list); removing all English punctuation (turns oyster-omelet into one word, so the whole-word match misses); "no Latin letters" as the Chinese test (would reject 雪Q餅 and QQ蛋).

### 2026-10-17 — Node C checks names before Chinese characters; send-backs are per output asked for  (commit 7e9f9cb)
- Changed: R11, changed; Full flow of one game (C row, Transitions), changed.
- Why: a description holding a card's Chinese name satisfied both R11 ("contains Chinese characters, not a violation, send back") and R21 ("contains a name, a violation"), and the spec did not say which ran first. The name check now runs first: saying a name is a loss whatever the script, and otherwise R21's official name and aliases could never fire, since any Chinese text would be sent back before it. "At most two times" had no unit; it is now per description or answer the program asks for, the natural reading of "send it back to rewrite", the same shape as R17 (per question) and R40 (per verdict), and still bounded: at most three descriptions and one answer per round, three tries each.
- Rejected: the Chinese check first (makes R21's Chinese names dead text); two send-backs per round across rejects (mixes the Challenger's penalty with the language penalty and leaves a twice-rejected Describer no room to fix a slip).

### 2026-10-17 — Node E: an invalid-question retry repeats only the structured call; one lookup is one tool call; invalid questions leave no trace in State  (commit bbd5b8d)
- Changed: R17, R43, R50, changed; State schema (Earlier guesses and questions), changed; Full flow of one game (E row and diagram), changed.
- Why: three gaps the M2 tickets could not close. The E row said "Invalid question → E retry" without saying whether the retry re-entered the tool loop; repeating only the structured call [R47] keeps R43's five lookups per round a real cap and makes a retry cheap. R43 counted "times" without saying what one was; a reply from the Guesser's model can carry several tool calls, so one lookup is now one search-tool call, counted in order, and calls past the fifth are not run, which keeps the V1 metric "lookups per round" equal to corpus hits. The row "Earlier guesses and questions" is read by the Describer, who never saw an invalid question, so it holds guesses and valid questions only; the Guesser sees the fixed message in its retry prompt, and the attempt number [R26] and the JSONL record (M4) keep the invalid questions for the metrics.
- Rejected: rerunning all of E on a retry (up to five more lookups per invalid question, and a lookup budget shared across retries that the spec would have to define); one reply as one lookup (a reply could carry ten calls); writing invalid questions into State with a flag (both role prompts would have to explain it).

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

### 2026-10-07 — Attribute fields decided  (commit 5fbf77b)
- Changed: Corpus and Cards (Attributes), added: six fields (Dish type, Main ingredients, Cooking method, Flavor, Physical form, Occasion), each with a closed value list, required or optional, a value count, and boundary definitions. [R44], changed: points to the list and adds the filter rule. State schema (Attributes on the card), changed: the Guesser sees attributes as filters [R44] and in results [R45]. M1, changed: "location is fixed so far" removed.
- Why: the fields are the Guesser's search filters [R44]. A filter helps only if the Guesser can infer the value from a three-to-four-sentence English description and draws the same boundary as the corpus labeler; one disagreement drops the right entry from the results and shows up in the V1 recall metric. So each field is something descriptions reveal, each vague value has a boundary rule, no value appears in two fields, and value counts are capped so a labeler working through three hundred entries cannot tag everything. Within a field the filter accepts any given value, so the Guesser can hedge across a fuzzy boundary; across fields all must hold. Values and coverage notes were added wherever a required field had no honest value for a common snack (tea eggs, bubble tea, dumplings, pineapple cake, tofu pudding, grass jelly, aiyu, sugarcane juice, almond tea): Egg, Tea, Milk, Herbs, Boiled, Baked, Set, No Cooking. The attributes also reach the search results [R45] and the M1 distractor prompt (T6).
- Rejected: location, the one field SPEC v1 called sure (most snacks are no longer tied to a region, so it would filter almost nothing; author). Portability (rarely revealed by a description; most snacks are both Grab-and-Go and Dine-In; Drinkable and Boxed repeated other fields). Values that repeated another field: Braised as a flavor; Thickened Soup and Chilled as cooking methods; Soup, Beverage, and Souvenir as satiety levels; Herbal as a flavor beside the Herbs ingredient; Drink as a Physical form value beside Dish type Drink (now Smooth Drink). Values with no boundary an LLM could hold across three hundred entries: Main Meal and Staple, Side Dish (against Snack), Solid (against Dry), Viscous (against Thickened), Rich and Creamy, Refreshing, Lunch and Dinner as occasions, Late Night, Gifting. Separate Beans and Seeds values (peanut and almond have no clear side); Soy was split out instead, since tofu has a crisp boundary. Physical form values on a second axis (filled, wrapped, skewered), which a one-value field cannot hold alongside sauced or dry.

### 2026-10-07 — The author's corpus review covers attributes  (commit 6400cdb)
- Changed: Corpus and Cards (the author's review of every entry), changed: the review also checks that the attributes follow the definitions in Attributes.
- Why: the attributes are the Guesser's search filters [R44], so a wrong value drops the right entry from the results. T5 already reviewed attributes against the list, but the spec sentence named only aliases, English names, and forbidden words (a finding of the cross-reference check on 5fbf77b).

### 2026-10-08 — Corpus format is a JSON Schema file validated by the loader  (commit 160da07)
- Changed: Implementation (Data and persistence), changed: the corpus file's format is `data/corpus/schema.json`, and the loader validates the corpus against it.
- Why: the corpus is generated outside the repo, so one file must serve both as the format handed to the external LLM and as the loader's rule; two copies would drift. The file encodes the Corpus and Cards fields and attribute values; every attribute is an array, one-value fields included, so the loader and the [R44] filter handle one shape. Two rules it cannot express stay in the loader: no two entries share an official name; no alias equals its entry's official name.
- Rejected: key names recorded only in the T3 ticket (no single source); hand-coded loader rules with the schema as documentation only (drift); `$defs`/`$ref` (each definition used once); dropping the full `physical_form` enum in favour of the if/then/else alone (the enum is the readable value list for the external LLM and gives clearer validation errors).

### 2026-10-09 — Meal, Snack, and drink cooking-method boundaries settled  (commit f1fdc15)
- Changed: Corpus and Cards (Attributes), changed: Meal is "filling enough to be eaten on its own as a meal, at any time of day" (was "as lunch or dinner"); Snack is "any other mainly savory food"; added: a drink the stall boils itself is Boiled, a pressed, blended, or assembled drink is No Cooking.
- Why: the four labelling edge cases deferred from the T2 audit (F8) must be settled before the corpus is labelled, or the labeler's rules and the reviewer's would differ. Meal by time of day excluded breakfast mains by the letter; the test the author uses is whether it makes a meal on its own. Snack with "mainly" lets Flavor list both Sweet and Savory for 潤餅 or 蚵仔煎 without a conflict; Dessert stays "sweet food" because a dessert is always sweet. No Cooking's example "(drinks)" made boiled drinks ambiguous against "the step that gives the dish its character". No Flavor rule: an item with no taste a first-time eater would notice is not a snack and is not in the corpus.
- Rejected: a default Savory for bland items; a breakfast rule and a sweet-savory rule as separate lines (both covered by the rewritten definitions); dropping Dessert into Flavor (loses a coarse one-value filter the Guesser can infer from a description).

### 2026-10-08 — Each name belongs to one corpus entry  (commit f0152cf)
- Changed: Corpus and Cards, added: no name is the official name or an alias of more than one entry, and no alias repeats its own entry's official name, compared after normalization [R22]. `data/corpus/schema.json` description, changed: states the loader's check of this rule on exact strings and points to the normalized rule. BACKLOG M2.20 added. Supersedes the two loader rules listed in the 160da07 entry.
- Why: [R20] counts a guess as correct when it equals an official name or alias after normalization, so a name held by two entries would let a guess of one snack count as correct for another, and [R35] cannot be judged when a card and a distractor share a name. Found in the author's review of the T3 loader; the loader enforces the rule on exact strings now (db7f4ee), and M2.20 adds the normalized comparison once the M2.5 helpers exist.
- Rejected: exact strings as the whole rule (R20 matches after normalization, so 凤梨酥 and 鳳梨酥 would both pass); the normalized check in M1 (pulls M2.5 forward into the open [R22] 面/麵 question; a hit in M2 costs a corpus correction and a T8 rerun, recorded in M2.20, and is unlikely for a hand-reviewed Traditional corpus); the rule only in the schema description (SPEC.md is the only authority).

### 2026-10-11 — Attribute values added and boundaries settled from labelling the corpus  (commit 476155b)
- Changed: Corpus and Cards (Attributes), added: values Sugar and Sweeteners (Main ingredients), Smoked and Dried (Cooking method), Bitter (Flavor), and Ice Pop (Physical form), each with a definition; a rule that an item sold in several versions is labelled by its most common version, with both listed when two are about equally common and the field allows more than one value; an Occasion preamble (only associations that are culturally established and specific to the dish); lines for offal and blood (by animal), Other Meat (animals without their own value), pickled and preserved vegetables (Vegetables), and candies made from syrup the maker boils (No Cooking). Changed: Meal (substantial enough and commonly eaten on its own, need not be balanced; supersedes the wording quoted in the f1fdc15 entry); Noodles (kneaded, cut, or extruded strips; wok-scraped batter is Rice); Starch (body or defining texture, not a thickener or fried coating; carrot and daikon join Root Vegetables); Herbs (adds mugwort, cudweed, roselle, ginger); Braised and Boiled (split on whether the liquid is soy-sauce-based); No Cooking (drinks dropped from its examples and left to the drink line; wraps and sandwiches added); Spicy (adds ginger heat); Fermented (smell or taste); Dry and Sauced (a substantial sauce, dressing, or seasoned oil against a dipping sauce on the side); Thick Soup (broth or sweet soup, thickened with starch or flour); Breakfast (commonly eaten for breakfast, or a breakfast-shop staple); Festival (a specific festival, holiday, or life-cycle ritual). `data/corpus/schema.json`, changed: the five values added to their enums, and Ice Pop to the non-Drink branch of `physical_form`.
- Why: labelling the 366 imported entries (T4) left 193 calls the definitions could not settle, and the author resolved them one by one. Some common snacks had no honest value (smoked goose, jerky, bitter tea, bagged ices, brown-sugar shaved ice), the same reason Egg, Tea, Milk, and Herbs were added in the 5fbf77b entry. The rest were boundaries a labeler and the reviewer would draw differently; under [R44] a missing or wrong value drops the right entry from the Guesser's results. The several-versions rule is a tiebreak for every field, not the sweet-savory line the f1fdc15 entry rejected. 冬粉, which T2 F8 called Noodles "only by a stretch", now fits the Noodles line plainly (extruded strips). Fable's review of the change found five wording faults, fixed before commit (No Cooking listing drinks against the drink line; candies of plain syrup left out; Thick Soup naming only broth; Breakfast "sold at breakfast shops" against the preamble; "tastes mainly of them" readable as any sweet dish).
- Rejected: a multi-valued Physical form for dry noodles tossed in sauce (Sauced was redefined instead); a Puffing method for 爆米香 (one item, so the value would give the answer away; Baked); finer splits of Vegetables or Other Meat (author); Fable's other findings: blended ice eaten with a spoon, a tie between two equally common versions in a one-value field, Dried against Baked, Drink against Dessert for sweet liquids, and the name Ice Pop (boundaries a labeler can hold, or low risk; author).

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

### 2026-10-03 — SPEC v1 settled  (commit cef7f39)
- Why: the spec review (v0.2 → v1) is finished and M1 starts from this version. Every later `SPEC.md` change gets its own entry citing its commit hash.

### 2026-10-07 — Directory structure settled  (commit 4b7f362)
- Changed: Implementation (Repo), changed.
- Why: T1 (6becd4f) committed the layout, so "not worked out yet" was no longer true (T1 audit finding F2). The committed directories are the record; SPEC.md points to them instead of listing them.
- Rejected: listing the directories in SPEC.md, because SPEC wins over code and every folder move would become a spec change.

### 2026-10-07 — First code commit; two-week limit starts  (no spec change)
- Why: CLAUDE.md, Start here, step 4. The Non-goals two-week limit counts from the first code commit, 6becd4f (T1), dated 2026-10-07.

### 2026-10-16 — M1 (Corpus) done  (no spec change)
- Why: the M1 Done when holds: the corpus (342 entries, 338f56b) and the forty cards (645fc01) load without error, every entry (T5) and every distractor (T8) was reviewed by the author, and the four manifests carry the same card order. Tickets T1–T8 in `docs/tasks/M1-corpus.md`, 62 commits on `m1-corpus`, fast-forwarded into `main` (the author prefers no merge commits; CLAUDE.md updated in the next commit). The three Open questions in that file ([R22] 面/麵 and 干/乾, plurals; [R5] "in Chinese") were answered in chat and become the first `SPEC.md` changes after the merge.
