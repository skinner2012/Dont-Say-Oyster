# M6 — run records (appendix to M6-cross-game-memory.md)

This file holds the transcripts, memory entries, and per-call tables of T6's seven V3 games, which `docs/tasks/M6-cross-game-memory.md` T6 summarises game by game; the record files, stderr files, memory files, and server log under `runs/` are not committed. The record-validation command is in `docs/tasks/M5-models-temperature.md`, How to use these tickets, and the memory-file command in T6's "Each game"; the per-game blocks, the memory files, the prompt check, and the num_ctx table are in T6's Detail.

## T6

- How each game was read (2026-11-04, after the loop's `DONE`; every figure by throwaway scripts in the session scratchpad, not in the repo): the record from `runs/m6-t6/v3-game<n>.jsonl`; the card from `data/cards/cards.json`; the trace as in `docs/tasks/M4-end-to-end.md` T4, How each run was read: `get_client().api.observations.get_many(session_id="m6-t6", is_root_observation=True, ...)` gave the session's seven roots, one per card, then `get_many(trace_id=..., fields="core,basic,time,io,metadata,model,usage,metrics", expand_metadata="round,role,attempt,kind,call,node")` each trace, following the cursor; generation spans are type `GENERATION`, sorted by start time and compared with the record's `calls` as a multiset of (round, role, attempt, kind), with input and output tokens, and position by position with the span's `langgraph_node` metadata against the call's node. Loads and evictions from `runs/m5/ollama-server.log` (the shell server, pid 78720, Ollama 0.40.8, no restart), window 10:02:00–11:21:00 PST (lines 123923–144824): a `starting llama-server` line names the model by its blob (27B `f5f1dd89…`, 26B `71214867…`, 12B `bb722270…`, from `ollama show --modelfile`), and a call has a load inside when that line's time falls between its generation span's start and end. In the window: 139 `POST "/api/chat"` lines (the seven records' 139 calls) and 14 `POST "/api/generate"` lines (the memory token counts), all status 200; no `truncated = 1`.
- Settings (each record's `settings`, the same in all seven): Describer `qwen3.8:27b-q4_K_M`, num_ctx 16384, thinking "medium", keep_alive -1; Challenger `gemma4:12b-it-q4_K_M`, 4096, thinking false, keep_alive 0; Guesser `gemma4:26b-a4b-it-q4_K_M`, 16384, thinking false, keep_alive -1; temperature 0.7.
- Every call of the seven games is attempt 1; no output was sent back [R11], [R17], [R40]; no violation; every game a right guess; both roles' `redos` 0, `written` true, and `failed` empty in every game.

### Game 1 — card-753f27f6 (筒仔米糕)

- Card (from `data/cards/cards.json`): official name 筒仔米糕; aliases 米糕; English names Steamed Sticky Rice Cake, Tube rice pudding, tang-a-bi-ko, Tong Zai Mi Gao; forbidden words glutinous, sticky, tube, steamed, rice, pork; distractors 油飯, 肉粽, 碗粿, 竹筒飯, 糯米腸.
- Record `runs/m6-t6/v3-game1.jsonl`: 1 line, `1 line(s) valid`; `variant` V3, `result` right guess, `matched_name` 米糕, `counters` rounds 6, questions 3, forced passes 0; 51 calls (Challenger 4: 4 D `structured`; Describer 8: 7 B `text`, 1 H `structured`; Guesser 39: 6 E `structured`, 32 E `tools`, 1 H `structured`), attempts {1: 51}; 4 verdicts (fail 1, pass 3); 1 rejected description; 0 sent-back outputs; 26 lookups (success 26); `memory.game` 1.
- Trace: id `2183409c429b5a0862015bdc4f409fb2`, name `card-753f27f6`, session `m6-t6`, root span 10:02:00.481–10:18:21.094 PST; 134 observations, all session `m6-t6`, levels DEFAULT 134. Node and router spans: B 7, C 7, D 4, E 6, F 3, G 6, H 1, LangGraph 1, route_after_d 4, route_after_e 6, route_c 7, route_f 3, A 1. Tool spans: 26, equal to the record's 26 lookups. Generation spans: 51, equal to the record's `calls` length 51; H generation spans 2 (the record's H calls 2); the multiset of (round, role, attempt, kind) equals the record's (True), with input and output tokens (True); in start-time order each span's (round, role, attempt, kind, tokens, `langgraph_node`) equals the call of the same ordinal (True); span latency within 0.001 s of the record's.
- Loads and evictions (`runs/m5/ollama-server.log`, lines timestamped inside the trace's root span): 6 `starting llama-server` lines: 12B at 10:04:44 (call 2), 12B at 10:07:43 (call 4), 12B at 10:11:45 (call 25), 26B at 10:11:52 (call 26), 12B at 10:15:58 (call 42), 26B at 10:16:06 (call 43); 2 `evicting` lines: 10:11:45.559 (predicted 7.1 GiB, system_free 8.2 GiB), then the 12B load at 10:11:45.799 (call 25) with loaded runners 2, and the next load of another model the 26B at 10:11:52.210 (call 26, loaded runners 2); 10:15:58.605 (predicted 7.1 GiB, system_free 6.8 GiB), then the 12B load at 10:15:58.809 (call 42) with loaded runners 2, and the next load of another model the 26B at 10:16:06.106 (call 43, loaded runners 2). Every load falls inside one call's generation span (the table's last column); an `evicting` line does not name the model it evicts. No `truncated = 1` line in the whole run window.
- Transcript:
  - Round 1 (description):
    - Description 1, verdict **fail** (ordinal 2), rejected: "It is a soft, chewy cylindrical treat made from a white grain flour batter, cooked inside a hollow bamboo stalk over boiling water. The top is drenched in a glossy, sweet-savory soy-based sauce with a bit of braised meat. Street vendors in Taiwan sell it from a cart, pulling the bamboo cylinder to reveal the pale, dense interior. The texture is dense and yielding, almost like a mochi, while the salty-sweet sauce on top adds a rich umami contrast." Reason: "The description of a bamboo cylinder with a sweet-savory sauce and meat is too similar to a bamboo rice dish, as it doesn't sufficiently emphasize that the interior is a solid batter rather than whole grains."
    - Description 2, verdict **pass** (ordinal 4): "It is a dense, smooth batter—no individual grains visible—that solidifies into a uniform pale cylinder inside a hollow bamboo piece boiled in water. The top is ladled with a thick, glossy sweet-savory sauce and a chunk of braised meat. Street vendors in Taiwan serve it from a cart, sliding the bamboo piece out to reveal the seamless, custard-like interior. The texture is dense and yielding, almost like a thick paste, while the salty-sweet topping provides a rich umami contrast."
    - Lookup 1 `search` {cooking_method: Boiled; flavor: Sweet, Savory; keywords: bamboo} → 竹筍湯 (1; `more_results` false)
    - Lookup 2 `search` {keywords: bamboo} → 竹筒飯, 烤茭白筍, 竹筍湯 (3; `more_results` false)
    - Lookup 3 `search` {keywords: custard} → 糕渣 (1; `more_results` false)
    - Lookup 4 `search` {keywords: paste} → 麻醬麵, 花枝羹, 肉羹, 魷魚羹, 魚冊湯 (5; `more_results` false)
    - Lookup 5 `search` {keywords: paste} → 麻醬麵, 花枝羹, 肉羹, 魷魚羹, 魚冊湯 (5; `more_results` false)
    - Question: "Is the main ingredient made from a grain or starch?"
    - Violations: none.
  - Round 2 (answer; no Challenger call [R12]): "Yes, the main ingredient is a flour milled from a grain."
    - Lookup 1 `search` {cooking_method: Boiled; keywords: bamboo} → 竹筍湯 (1; `more_results` false)
    - Lookup 2 `search` {cooking_method: Boiled; main_ingredients: Wheat} → 紅油抄手, 餛飩湯 (2; `more_results` false)
    - Lookup 3 `search` {keywords: bamboo} → 竹筒飯, 烤茭白筍, 竹筍湯 (3; `more_results` false)
    - Lookup 4 `search` {keywords: paste} → 麻醬麵, 花枝羹, 肉羹, 魷魚羹, 魚冊湯 (5; `more_results` false)
    - Lookup 5 `search` {keywords: bamboo, paste} → 麻醬麵, 花枝羹, 肉羹, 魷魚羹, 魚冊湯, 竹筒飯, 烤茭白筍, 竹筍湯 (8; `more_results` false)
    - Question: "Is the dish served sweet or savory?"
    - Violations: none.
  - Round 3 (answer; no Challenger call [R12]): "It is both—the cake itself is mild and faintly sweet, while the sauce ladled on top is a rich blend of sweet and savory."
    - Lookup 1 `search` {cooking_method: Boiled; flavor: Sweet, Savory; main_ingredients: Wheat; physical_form: Dry} → no entry (`more_results` false)
    - Guess: text `竹筒飯`, confidence 0.1: wrong.
    - Violations: none.
  - Round 4 (description):
    - Description 1, verdict **pass** (ordinal 25): "It is a completely homogeneous, pourable batter made from a fine white flour—there are no whole kernels or individual grains visible anywhere in the finished product. The vendor boils this smooth mixture inside a hollow bamboo stalk until it sets into a firm, seamless block resembling a thick pudding. Served from a street cart, the vendor cuts a wedge from the cylinder and drizzles it with a thick, glossy brown sauce topped with a piece of slow-braised meat. Unlike a dish of cooked kernels, this has the uniform, dense consistency of a custard throughout."
    - Lookup 1 `search` {cooking_method: Boiled; flavor: Sweet, Savory; main_ingredients: Wheat; physical_form: Dry, Sauced} → 紅油抄手 (1; `more_results` false)
    - Lookup 2 `search` {keywords: bamboo} → 竹筒飯, 烤茭白筍, 竹筍湯 (3; `more_results` false)
    - Lookup 3 `search` {cooking_method: Boiled; flavor: Sweet, Savory; main_ingredients: Wheat; physical_form: Sauced} → 紅油抄手 (1; `more_results` false)
    - Lookup 4 `search` {cooking_method: Boiled; flavor: Sweet; main_ingredients: Wheat} → no entry (`more_results` false)
    - Lookup 5 `search` {cooking_method: Boiled; main_ingredients: Wheat} → 紅油抄手, 餛飩湯 (2; `more_results` false)
    - Question: "Is the dish typically eaten as a snack or a meal?"
    - Violations: none.
  - Round 5 (answer; no Challenger call [R12]): "It is most commonly enjoyed as a snack or light meal, grabbed quickly from a street cart rather than served as a full course at a restaurant."
    - Lookup 1 `search` {cooking_method: Boiled; dish_type: Snack, Meal; flavor: Sweet, Savory; main_ingredients: Wheat; physical_form: Dry, Sauced} → 紅油抄手 (1; `more_results` false)
    - Lookup 2 `search` {keywords: bamboo} → 竹筒飯, 烤茭白筍, 竹筍湯 (3; `more_results` false)
    - Lookup 3 `search` {cooking_method: Boiled; keywords: bamboo} → 竹筍湯 (1; `more_results` false)
    - Lookup 4 `search` {cooking_method: Boiled; keywords: bamboo, cake, pudding, paste, cylinder} → 麻醬麵, 甜不辣, 花枝羹, 肉羹, 魷魚羹, 魚冊湯, 竹筍湯 (7; `more_results` false)
    - Lookup 5 `search` {cooking_method: Boiled; keywords: paste} → 麻醬麵, 花枝羹, 肉羹, 魷魚羹, 魚冊湯 (5; `more_results` false)
    - Guess: text `竹筒飯`, confidence 0.1: wrong.
    - Violations: none.
  - Round 6 (description):
    - Description 1, verdict **pass** (ordinal 42): "It is a liquid batter, milled so fine that the original seed is entirely invisible, poured into a hollow bamboo piece and boiled until it solidifies into a seamless pale block with absolutely no particulate or chewable element. The vendor scrapes the smooth cylinder out with a spoon, slices a wedge with a knife, and tops it with a thick oyster-sauce gravy and a small piece of slow-braised meat. It is an extremely cheap grab-and-go treat, costing just a few dollars, especially associated with the streets of southern Taiwan. Where a bamboo-cooked grain dish would give you distinct, chewy kernels in every bite, this is one uniform, dense, slightly sweet paste from edge to edge."
    - Lookup 1 `search` {keywords: bamboo} → 竹筒飯, 烤茭白筍, 竹筍湯 (3; `more_results` false)
    - Lookup 2 `search` {keywords: bamboo, paste} → 麻醬麵, 花枝羹, 肉羹, 魷魚羹, 魚冊湯, 竹筒飯, 烤茭白筍, 竹筍湯 (8; `more_results` false)
    - Lookup 3 `search` {keywords: bamboo, paste} → 麻醬麵, 花枝羹, 肉羹, 魷魚羹, 魚冊湯, 竹筒飯, 烤茭白筍, 竹筍湯 (8; `more_results` false)
    - Lookup 4 `search` {keywords: paste} → 麻醬麵, 花枝羹, 肉羹, 魷魚羹, 魚冊湯 (5; `more_results` false)
    - Lookup 5 `search` {keywords: bamboo} → 竹筒飯, 烤茭白筍, 竹筍湯 (3; `more_results` false)
    - Guess: text `米糕`, confidence 0.8: right (米糕, an alias); the Guesser wins in round 6.
    - Violations: none.
- Memory (node H, the record's `memory`; the files `runs/m6-t6/memory/describer-01.json` and `guesser-01.json` hold the same entry as their last and the same summary):
  - Describer: redos 0, `written` true, `failed` [] (empty), `tokens` 17 (the block read at game start).
    - Entry: "The Guesser twice guessed bamboo tube rice (a dish of whole grains cooked in a bamboo stalk) before finally landing on the correct answer, the smooth batter cake, in round 6. The bamboo-cylinder cooking method was the strongest misdirection; my round-1 rejection confirmed that pairing 'bamboo cylinder' with 'sweet-savory sauce and meat' reads as bamboo rice rather than a uniform custard-like batter. What finally broke through was the repeated emphasis on a completely homogeneous, pourable interior with zero particulate or chewable element, explicitly contrasted against 'a dish of cooked kernels.' Next time I see a bamboo-cooked item, I should lead with the batter or custard texture in the very first sentence, mention the bamboo vessel only secondarily, and front-load the street-cart, few-dollar, grab-and-go context to steer the Guesser away from restaurant-style whole-grain dishes."
    - Summary: null (games 1–5 have none)
  - Guesser: redos 0, `written` true, `failed` [] (empty), `tokens` 18 (the block read at game start).
    - Entry: "Avoid guessing items with visible grains or kernels when the description emphasizes a smooth, liquid, or homogeneous texture. Focus on distinguishing between dishes with distinct textures versus those that are paste-like, as searching for specific physical forms like 'paste' or 'pudding' significantly narrows the results. Use questions to clarify the main ingredient's composition and the flavor profile early on, but wait for specific texture cues before committing to a final guess."
    - Summary: null (games 1–5 have none)
- Per-call table (latency in seconds from the record's `calls`, rounded to the millisecond; input and output from the same; "call" is the tool-loop call index; "load inside" from the server log against the call's generation span start and end):

  | # | node | role | round | kind | call | attempt | latency (s) | input | output | load inside |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | 1 | B | Describer | 1 | text | – | 1 | 164.134 | 791 | 2001 | no |
  | 2 | D | Challenger | 1 | structured | – | 1 | 9.158 | 451 | 62 | yes: 12B started 10:04:44.744 (started in 4.78 s, loaded runners 3) |
  | 3 | B | Describer | 1 | text | – | 1 | 169.526 | 981 | 2039 | no |
  | 4 | D | Challenger | 1 | structured | – | 1 | 5.208 | 455 | 20 | yes: 12B started 10:07:43.459 (started in 2.26 s, loaded runners 3) |
  | 5 | E | Guesser | 1 | tools | 1 | 1 | 1.889 | 2490 | 34 | no |
  | 6 | E | Guesser | 1 | tools | 2 | 1 | 0.720 | 2625 | 18 | no |
  | 7 | E | Guesser | 1 | tools | 3 | 1 | 1.017 | 2899 | 18 | no |
  | 8 | E | Guesser | 1 | tools | 4 | 1 | 0.734 | 3031 | 17 | no |
  | 9 | E | Guesser | 1 | tools | 5 | 1 | 1.328 | 3518 | 17 | no |
  | 10 | E | Guesser | 1 | tools | 6 | 1 | 1.383 | 4005 | 18 | no |
  | 11 | E | Guesser | 1 | structured | – | 1 | 4.654 | 2464 | 38 | no |
  | 12 | B | Describer | 2 | text | – | 1 | 40.578 | 1068 | 382 | no |
  | 13 | E | Guesser | 2 | tools | 1 | 1 | 1.306 | 2520 | 23 | no |
  | 14 | E | Guesser | 2 | tools | 2 | 1 | 0.881 | 2644 | 28 | no |
  | 15 | E | Guesser | 2 | tools | 3 | 1 | 0.905 | 2881 | 18 | no |
  | 16 | E | Guesser | 2 | tools | 4 | 1 | 0.932 | 3155 | 17 | no |
  | 17 | E | Guesser | 2 | tools | 5 | 1 | 1.407 | 3642 | 22 | no |
  | 18 | E | Guesser | 2 | tools | 6 | 1 | 2.081 | 4373 | 36 | no |
  | 19 | E | Guesser | 2 | structured | – | 1 | 5.000 | 2826 | 35 | no |
  | 20 | B | Describer | 3 | text | – | 1 | 34.932 | 1100 | 314 | no |
  | 21 | E | Guesser | 3 | tools | 1 | 1 | 1.758 | 2571 | 43 | no |
  | 22 | E | Guesser | 3 | tools | 2 | 1 | 0.902 | 2631 | 35 | no |
  | 23 | E | Guesser | 3 | structured | – | 1 | 2.352 | 1053 | 31 | no |
  | 24 | B | Describer | 4 | text | – | 1 | 131.737 | 1133 | 1548 | no |
  | 25 | D | Challenger | 4 | structured | – | 1 | 6.625 | 462 | 20 | yes: after an `evicting` line at 10:11:45.559 (predicted 7.1 GiB, system_free 8.2 GiB); 12B started 10:11:45.799 (started in 3.52 s, loaded runners 2) |
  | 26 | E | Guesser | 4 | tools | 1 | 1 | 7.809 | 2705 | 48 | yes: 26B started 10:11:52.210 (started in 2.51 s, loaded runners 2) |
  | 27 | E | Guesser | 4 | tools | 2 | 1 | 0.743 | 2859 | 18 | no |
  | 28 | E | Guesser | 4 | tools | 3 | 1 | 1.523 | 3133 | 48 | no |
  | 29 | E | Guesser | 4 | tools | 4 | 1 | 1.074 | 3287 | 34 | no |
  | 30 | E | Guesser | 4 | tools | 5 | 1 | 0.797 | 3338 | 28 | no |
  | 31 | E | Guesser | 4 | tools | 6 | 1 | 1.208 | 3575 | 33 | no |
  | 32 | E | Guesser | 4 | structured | – | 1 | 4.089 | 2025 | 37 | no |
  | 33 | B | Describer | 5 | text | – | 1 | 40.848 | 1286 | 372 | no |
  | 34 | E | Guesser | 5 | tools | 1 | 1 | 3.079 | 2758 | 61 | no |
  | 35 | E | Guesser | 5 | tools | 2 | 1 | 0.783 | 2925 | 18 | no |
  | 36 | E | Guesser | 5 | tools | 3 | 1 | 1.135 | 3199 | 27 | no |
  | 37 | E | Guesser | 5 | tools | 4 | 1 | 1.209 | 3327 | 45 | no |
  | 38 | E | Guesser | 5 | tools | 5 | 1 | 1.860 | 4041 | 26 | no |
  | 39 | E | Guesser | 5 | tools | 6 | 1 | 1.519 | 4537 | 27 | no |
  | 40 | E | Guesser | 5 | structured | – | 1 | 5.302 | 2981 | 23 | no |
  | 41 | B | Describer | 6 | text | – | 1 | 173.090 | 1319 | 2071 | no |
  | 42 | D | Challenger | 6 | structured | – | 1 | 7.486 | 494 | 20 | yes: after an `evicting` line at 10:15:58.605 (predicted 7.1 GiB, system_free 6.8 GiB); 12B started 10:15:58.809 (started in 4.28 s, loaded runners 2) |
  | 43 | E | Guesser | 6 | tools | 1 | 1 | 7.289 | 2924 | 14 | yes: 26B started 10:16:06.106 (started in 2.26 s, loaded runners 2) |
  | 44 | E | Guesser | 6 | tools | 2 | 1 | 1.048 | 3194 | 22 | no |
  | 45 | E | Guesser | 6 | tools | 3 | 1 | 1.799 | 3925 | 22 | no |
  | 46 | E | Guesser | 6 | tools | 4 | 1 | 1.758 | 4656 | 17 | no |
  | 47 | E | Guesser | 6 | tools | 5 | 1 | 1.401 | 5143 | 18 | no |
  | 48 | E | Guesser | 6 | tools | 6 | 1 | 1.170 | 5417 | 25 | no |
  | 49 | E | Guesser | 6 | structured | – | 1 | 6.852 | 3859 | 22 | no |
  | 50 | H | Describer | 6 | structured | – | 1 | 108.030 | 1205 | 1226 | no |
  | 51 | H | Guesser | 6 | structured | – | 1 | 4.379 | 1574 | 98 | no |

### Game 2 — card-c4431ef9 (湯粄條)

- Card (from `data/cards/cards.json`): official name 湯粄條; aliases 湯板條; English names Hakka Rice Noodle Soup; forbidden words hakka, flat, wide, rice, broth; distractors 米粉湯, 切仔麵, 鼎邊銼, 陽春麵, 魚丸米粉.
- Record `runs/m6-t6/v3-game2.jsonl`: 1 line, `1 line(s) valid`; `variant` V3, `result` right guess, `matched_name` 湯板條, `counters` rounds 1, questions 0, forced passes 1; 11 calls (Challenger 3: 3 D `structured`; Describer 4: 3 B `text`, 1 H `structured`; Guesser 4: 1 E `structured`, 2 E `tools`, 1 H `structured`), attempts {1: 11}; 3 verdicts (fail 3); 2 rejected descriptions; 0 sent-back outputs; 1 lookup (success 1); `memory.game` 2.
- Trace: id `dc46f93854498b1050657ec2978e39d6`, name `card-c4431ef9`, session `m6-t6`, root span 10:18:21.870–10:29:16.953 PST; 36 observations, all session `m6-t6`, levels DEFAULT 36. Node and router spans: B 3, C 3, D 3, E 1, F 1, G 1, H 1, LangGraph 1, route_after_d 3, route_after_e 1, route_c 3, route_f 1, A 1. Tool spans: 1, equal to the record's 1 lookup. Generation spans: 11, equal to the record's `calls` length 11; H generation spans 2 (the record's H calls 2); the multiset of (round, role, attempt, kind) equals the record's (True), with input and output tokens (True); in start-time order each span's (round, role, attempt, kind, tokens, `langgraph_node`) equals the call of the same ordinal (True); span latency within 0.022 s of the record's.
- Loads and evictions (`runs/m5/ollama-server.log`, lines timestamped inside the trace's root span): 4 `starting llama-server` lines: 12B at 10:20:24 (call 2), 12B at 10:22:38 (call 4), 12B at 10:25:26 (call 6), 26B at 10:25:31 (call 7); 1 `evicting` line: 10:20:24.056 (predicted 7.1 GiB, system_free 6.5 GiB), then the 12B load at 10:20:24.323 (call 2) with loaded runners 2, and the next load of another model the 26B at 10:25:31.237 (call 7, loaded runners 2). Every load falls inside one call's generation span (the table's last column); an `evicting` line does not name the model it evicts. No `truncated = 1` line in the whole run window.
- Transcript:
  - Round 1 (description):
    - Description 1, verdict **fail** (ordinal 2), rejected: "Pale, smooth, band-shaped strands of milled grain sit submerged in a light, clear, savory soup. The noodles have a soft, slightly chewy bite and soak up the seasoned liquid around them. A typical bowl is topped with thin slices of braised pork, a scatter of chopped scallions, and a dash of soy sauce. It is the kind of humble, filling meal you grab at a small neighborhood eatery, especially in the mountainous regions of northern Taiwan." Reason: "The description of noodles in a savory soup with braised pork and scallions is too similar to the other listed noodle soups and does not clearly distinguish the specific wide, flat texture of the snack from thin rice noodles or wheat noodles."
    - Description 2, verdict **fail** (ordinal 4), rejected: "The noodle is a smooth, slippery ribbon—broad as a strip of cloth rather than a thin strand—pulled from a starch-based dough and cut into uniform bands. It floats in a light, clear, savory soup that is barely colored, almost translucent. A single piece of braised pork and a sprinkle of chopped scallions rest on top, the only solids besides the noodle itself. You find it at small, no-frills shops in the upland villages of northern Taiwan, where it is the everyday lunch of the local community." Reason: "The description of a broad, starch-based ribbon in a clear soup with braised pork also fits the characteristics of the fish ball rice noodles."
    - Description 3, verdict **fail** (ordinal 6), forced pass [R13]: delivered to the Guesser: "The noodle is a thick, smooth, slightly gelatinous strip—denser and more uniform than a wheat noodle, and far more substantial than a vermicelli thread—formed from a fine, milled grain paste. It sits in a crystal-clear, barely-seasoned liquid with no oil sheen, essentially just flavored water in which the noodle itself is the entire point. The only other elements in the bowl are a thin slice of slow-braised pork and a scatter of scallion rings; there are no balls, no chunks of meat, no leafy greens. It is the everyday lunch of hillside-village families in the Hsinchu and Miaoli counties, sold at tiny, no-frills stalls for a few dollars." Reason: "The description of a clear broth with pork and scallions could also easily describe a simple bowl of rice vermicelli soup."
    - Lookup 1 `search` {keywords: noodle} → 炒米粉, 米粉湯, 炒粄條, 乾粄條, 湯粄條, 炒米苔目, 肉燥乾麵, 陽春麵, 麻醬麵, 榨菜肉絲麵 (10; `more_results` true)
    - Guess: text `湯板條`, confidence 0.8: right (湯板條, an alias); the Guesser wins in round 1.
    - Violations: none.
- Memory (node H, the record's `memory`; the files `runs/m6-t6/memory/describer-02.json` and `guesser-02.json` hold the same entry as their last and the same summary):
  - Describer: redos 0, `written` true, `failed` [] (empty), `tokens` 202 (the block read at game start).
    - Entry: "Game won in round 1 on Hakka Rice Noodle Soup, but two prior descriptions were rejected for being too close to other noodle soups: a generic 'band-shaped strands in savory soup with braised pork' lacked distinguishing texture, and a 'broad starch-based ribbon in clear soup' was explicitly confused with fish ball rice noodles. The winning description succeeded by front-loading the negative exclusions—'no balls, no chunks of meat, no leafy greens'—and by describing the noodle as a 'thick, smooth, slightly gelatinous strip formed from a fine, milled grain paste,' which signals the starch-paste origin without naming the grain. The hyper-minimal soup framing ('essentially just flavored water in which the noodle itself is the entire point') and the geographic anchor of 'hillside-village families in Hsinchu and Miaoli' provided the final disambiguation. Next time I face a noodle soup that shares toppings with a fish-ball or meat-bowl variant, I will lead with what is absent from the bowl before listing what is present, and use 'milled grain paste' or 'starch paste' to characterize the noodle type while steering clear of the grain's name."
    - Summary: null (games 1–5 have none)
  - Guesser: redos 0, `written` true, `failed` [] (empty), `tokens` 107 (the block read at game start).
    - Entry: "When the description emphasizes a very simple, minimalist ingredient list with no oil or extra vegetables, focus on identifying the specific regional origin or the texture of the starch component. Searching for broad categories like noodle types can return too many results, so look for clues regarding the density and smoothness of the grain. If the description provides specific geographic locations like certain northern counties, use that to narrow down the regional specialty immediately."
    - Summary: null (games 1–5 have none)
- Per-call table (latency in seconds from the record's `calls`, rounded to the millisecond; input and output from the same; "call" is the tool-loop call index; "load inside" from the server log against the call's generation span start and end):

  | # | node | role | round | kind | call | attempt | latency (s) | input | output | load inside |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | 1 | B | Describer | 1 | text | – | 1 | 122.093 | 957 | 1434 | no |
  | 2 | D | Challenger | 1 | structured | – | 1 | 8.974 | 454 | 59 | yes: after an `evicting` line at 10:20:24.056 (predicted 7.1 GiB, system_free 6.5 GiB); 12B started 10:20:24.323 (started in 4.53 s, loaded runners 2) |
  | 3 | B | Describer | 1 | text | – | 1 | 125.689 | 1157 | 1456 | no |
  | 4 | D | Challenger | 1 | structured | – | 1 | 5.484 | 470 | 42 | yes: 12B started 10:22:38.799 (started in 1.76 s, loaded runners 2) |
  | 5 | B | Describer | 1 | text | – | 1 | 161.728 | 1284 | 1918 | no |
  | 6 | D | Challenger | 1 | structured | – | 1 | 5.224 | 508 | 43 | yes: 12B started 10:25:26.029 (started in 1.76 s, loaded runners 2) |
  | 7 | E | Guesser | 1 | tools | 1 | 1 | 8.008 | 2622 | 14 | yes: 26B started 10:25:31.237 (started in 3.28 s, loaded runners 2) |
  | 8 | E | Guesser | 1 | tools | 2 | 1 | 2.374 | 3540 | 34 | no |
  | 9 | E | Guesser | 1 | structured | – | 1 | 3.994 | 2002 | 31 | no |
  | 10 | H | Describer | 1 | structured | – | 1 | 205.883 | 1135 | 2476 | no |
  | 11 | H | Guesser | 1 | structured | – | 1 | 2.662 | 602 | 91 | no |

### Game 3 — card-1b8d14cb (滷豆干)

- Card (from `data/cards/cards.json`): official name 滷豆干; aliases 大溪豆干; English names Braised dried tofu; forbidden words tofu, dried, braised, soy, daxi, black; distractors 鐵蛋, 炸豆腐, 滷海帶, 滷蛋, 滷花生.
- Record `runs/m6-t6/v3-game3.jsonl`: 1 line, `1 line(s) valid`; `variant` V3, `result` right guess, `matched_name` 滷豆干, `counters` rounds 1, questions 0, forced passes 0; 9 calls (Challenger 1: 1 D `structured`; Describer 2: 1 B `text`, 1 H `structured`; Guesser 6: 1 E `structured`, 4 E `tools`, 1 H `structured`), attempts {1: 9}; 1 verdicts (pass 1); 0 rejected descriptions; 0 sent-back outputs; 3 lookups (success 3); `memory.game` 3.
- Trace: id `64cf4e498f2d6a696ff88d965eae1131`, name `card-1b8d14cb`, session `m6-t6`, root span 10:29:17.696–10:33:24.048 PST; 26 observations, all session `m6-t6`, levels DEFAULT 26. Node and router spans: B 1, C 1, D 1, E 1, F 1, G 1, H 1, LangGraph 1, route_after_d 1, route_after_e 1, route_c 1, route_f 1, A 1. Tool spans: 3, equal to the record's 3 lookups. Generation spans: 9, equal to the record's `calls` length 9; H generation spans 2 (the record's H calls 2); the multiset of (round, role, attempt, kind) equals the record's (True), with input and output tokens (True); in start-time order each span's (round, role, attempt, kind, tokens, `langgraph_node`) equals the call of the same ordinal (True); span latency within 0.002 s of the record's.
- Loads and evictions (`runs/m5/ollama-server.log`, lines timestamped inside the trace's root span): 3 `starting llama-server` lines: 12B at 10:31:10 (call 2), 26B at 10:31:18 (call 3), 27B at 10:31:33 (call 8); 2 `evicting` lines: 10:31:10.387 (predicted 7.1 GiB, system_free 6.6 GiB), then the 12B load at 10:31:10.558 (call 2) with loaded runners 2, and the next load of another model the 26B at 10:31:18.944 (call 3, loaded runners 1); 10:31:18.650 (predicted 17.4 GiB, system_free 21.7 GiB), then the 26B load at 10:31:18.944 (call 3) with loaded runners 1. Every load falls inside one call's generation span (the table's last column); an `evicting` line does not name the model it evicts. No `truncated = 1` line in the whole run window.
- Transcript:
  - Round 1 (description):
    - Description 1, verdict **pass** (ordinal 2): "It is a small, dense rectangular block of pressed bean curd, firm enough to hold its shape when sliced, with a slightly chewy, springy bite. It is simmered for hours in a dark, spiced liquid loaded with star anise, cinnamon, and a touch of sweetness, which gives its surface a deep, glossy mahogany color. You buy it by the piece from a small counter or night-market stall, often drizzled with the same cooking liquid or a dash of chili oil, and eat it as a quick, savory snack on the go. Unlike soft, silken curd, this one is compact and protein-dense, almost like a savory little brick you can pop into your mouth."
    - Lookup 1 `search` {cooking_method: Braised; flavor: Savory; main_ingredients: Soy; occasion: Night Market; physical_form: Dry} → no entry (`more_results` false)
    - Lookup 2 `search` {cooking_method: Braised; flavor: Savory; main_ingredients: Soy; physical_form: Sauced} → no entry (`more_results` false)
    - Lookup 3 `search` {cooking_method: Braised; main_ingredients: Soy} → 滷豆干 (1; `more_results` false)
    - Guess: text `滷豆干`, confidence 1.0: right (滷豆干, the official name); the Guesser wins in round 1.
    - Violations: none.
- Memory (node H, the record's `memory`; the files `runs/m6-t6/memory/describer-03.json` and `guesser-03.json` hold the same entry as their last and the same summary):
  - Describer: redos 0, `written` true, `failed` [] (empty), `tokens` 461 (the block read at game start).
    - Entry: "Game won instantly in round 1 on braised dried tofu. The description succeeded by layering texture (dense, chewy, springy brick), cooking method (simmered in a spiced liquid with star anise and cinnamon), visual (glossy mahogany), and purchase context (night-market stall, sold by the piece) into a single paragraph, with 'bean curd' cleanly substituting for the forbidden word 'tofu' and 'simmered' standing in for 'braised.' No misdirection occurred and no description was rejected, so the Guesser had no competing candidates to confuse it with. Next time I describe a protein-block snack, I will front-load the shape-and-density descriptor ('compact rectangular block') before the cooking method, since that combination immediately narrows the field away from silken or soft variants, and I will keep the street-stall, grab-and-go context as a secondary anchor rather than the lead."
    - Summary: null (games 1–5 have none)
  - Guesser: redos 0, `written` true, `failed` [] (empty), `tokens` 193 (the block read at game start).
    - Entry: "When the description highlights a specific cooking liquid and a deep, glossy color, use the protein source and cooking method as the primary search filters. I found that searching for a combination of the main ingredient and the braising technique is more effective than adding secondary attributes like physical form or flavor, which may return zero results. If the texture is described as dense and firm, I can confidently guess once the cooking method and ingredient are identified."
    - Summary: null (games 1–5 have none)
- Per-call table (latency in seconds from the record's `calls`, rounded to the millisecond; input and output from the same; "call" is the tool-loop call index; "load inside" from the server log against the call's generation span start and end):

  | # | node | role | round | kind | call | attempt | latency (s) | input | output | load inside |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | 1 | B | Describer | 1 | text | – | 1 | 112.608 | 1218 | 1280 | no |
  | 2 | D | Challenger | 1 | structured | – | 1 | 8.240 | 494 | 20 | yes: after an `evicting` line at 10:31:10.387 (predicted 7.1 GiB, system_free 6.6 GiB); 12B started 10:31:10.558 (started in 5.05 s, loaded runners 2) |
  | 3 | E | Guesser | 1 | tools | 1 | 1 | 9.087 | 2701 | 46 | yes: after an `evicting` line at 10:31:18.650 (predicted 17.4 GiB, system_free 21.7 GiB); 26B started 10:31:18.944 (started in 3.53 s, loaded runners 1) |
  | 4 | E | Guesser | 1 | tools | 2 | 1 | 1.072 | 2764 | 44 | no |
  | 5 | E | Guesser | 1 | tools | 3 | 1 | 0.802 | 2825 | 28 | no |
  | 6 | E | Guesser | 1 | tools | 4 | 1 | 0.939 | 2952 | 30 | no |
  | 7 | E | Guesser | 1 | structured | – | 1 | 2.888 | 1399 | 29 | no |
  | 8 | H | Describer | 1 | structured | – | 1 | 102.229 | 1092 | 1134 | yes: 27B started 10:31:33.525 (started in 2.52 s, loaded runners 2) |
  | 9 | H | Guesser | 1 | structured | – | 1 | 2.965 | 778 | 96 | no |

### Game 4 — card-47d7897f (薑絲大腸)

- Card (from `data/cards/cards.json`): official name 薑絲大腸; aliases 薑絲炒大腸, 客家薑絲大腸; English names Stir-Fried Pork Intestines with Ginger; forbidden words ginger, intestine, vinegar, hakka, shredded; distractors 滷大腸, 燙粉腸, 客家小炒, 麻油腰子, 大腸麵線.
- Record `runs/m6-t6/v3-game4.jsonl`: 1 line, `1 line(s) valid`; `variant` V3, `result` right guess, `matched_name` 薑絲大腸, `counters` rounds 1, questions 0, forced passes 0; 7 calls (Challenger 1: 1 D `structured`; Describer 2: 1 B `text`, 1 H `structured`; Guesser 4: 1 E `structured`, 2 E `tools`, 1 H `structured`), attempts {1: 7}; 1 verdicts (pass 1); 0 rejected descriptions; 0 sent-back outputs; 1 lookup (success 1); `memory.game` 4.
- Trace: id `4f7c914f0e3cfaac3f79564db1e3b5c6`, name `card-47d7897f`, session `m6-t6`, root span 10:33:24.762–10:36:51.899 PST; 22 observations, all session `m6-t6`, levels DEFAULT 22. Node and router spans: B 1, C 1, D 1, E 1, F 1, G 1, H 1, LangGraph 1, route_after_d 1, route_after_e 1, route_c 1, route_f 1, A 1. Tool spans: 1, equal to the record's 1 lookup. Generation spans: 7, equal to the record's `calls` length 7; H generation spans 2 (the record's H calls 2); the multiset of (round, role, attempt, kind) equals the record's (True), with input and output tokens (True); in start-time order each span's (round, role, attempt, kind, tokens, `langgraph_node`) equals the call of the same ordinal (True); span latency within 0.001 s of the record's.
- Loads and evictions (`runs/m5/ollama-server.log`, lines timestamped inside the trace's root span): 1 `starting llama-server` line: 12B at 10:35:20 (call 2); no `evicting` line. Every load falls inside one call's generation span (the table's last column); an `evicting` line does not name the model it evicts. No `truncated = 1` line in the whole run window.
- Transcript:
  - Round 1 (description):
    - Description 1, verdict **pass** (ordinal 2): "A pork offal dish in which the large, tubular gut of the pig is pre-boiled, sliced into small coin-shaped rounds, then flash-cooked in a screaming-hot wok. The plate is loaded with dozens of very fine, pale-yellow matchsticks of an aromatic knobby root, delivering a sharp, warming heat that cuts through the rich, chewy, slightly springy meat. The finished dish is a glistening tangle of browned rings and pale strips, served piping hot at street stalls and small neighborhood eateries, typically paired with a bowl of plain steamed rice. The texture is distinctly bouncy and firm, with a deep savory umami that sets it far apart from any ordinary pork stir-fry."
    - Lookup 1 `search` {cooking_method: Stir-Fried; flavor: Spicy, Savory; main_ingredients: Pork, Root Vegetables} → 客家小炒, 薑絲大腸 (2; `more_results` false)
    - Guess: text `薑絲大腸`, confidence 1.0: right (薑絲大腸, the official name); the Guesser wins in round 1.
    - Violations: none.
- Memory (node H, the record's `memory`; the files `runs/m6-t6/memory/describer-04.json` and `guesser-04.json` hold the same entry as their last and the same summary):
  - Describer: redos 0, `written` true, `failed` [] (empty), `tokens` 659 (the block read at game start).
    - Entry: "Game won instantly in round 1 on Stir-Fried Pork Intestines with Ginger. The winning description layered a clear protein identifier ('pork offal…large, tubular gut of the pig…coin-shaped rounds') with a sensory stand-in for the forbidden spice ('pale-yellow matchsticks of an aromatic knobby root, delivering a sharp, warming heat'), and the Guesser had no competing candidate to consider. No description was rejected and no misdirection occurred, so the key lesson is structural: when a dish is defined by a specific offal cut plus a single dominant aromatic, naming the organ generically ('tubular gut') and pairing the spice with its tactile-thermal signature ('knobby root…warming, sharp heat') is sufficient to bypass the forbidden words without ambiguity. Next time I face an offal-plus-spice card, I will front-load the animal-part shape and cut (rings, strips, coils) before the cooking method, and I will describe any forbidden spice by its physical form plus its mouth-feel rather than by flavor adjectives alone, since 'warming heat' is more diagnostic than 'spicy' for distinguishing ginger from chili or pepper."
    - Summary: null (games 1–5 have none)
  - Guesser: redos 0, `written` true, `failed` [] (empty), `tokens` 284 (the block read at game start).
    - Entry: "When a description features a combination of a specific protein and a distinct, aromatic vegetable garnish, prioritize searching for the interplay between the main ingredient and the secondary root or herb. Using a multi-attribute search including cooking method, flavor, and main ingredients is highly effective for narrowing down stir-fried dishes with contrasting textures. Since I achieved a high-confidence win without asking questions, I can rely on identifying the specific textural contrast between chewy meat and fine, sharp vegetable strips to make a direct guess."
    - Summary: null (games 1–5 have none)
- Per-call table (latency in seconds from the record's `calls`, rounded to the millisecond; input and output from the same; "call" is the tool-loop call index; "load inside" from the server log against the call's generation span start and end):

  | # | node | role | round | kind | call | attempt | latency (s) | input | output | load inside |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | 1 | B | Describer | 1 | text | – | 1 | 115.579 | 1426 | 1293 | no |
  | 2 | D | Challenger | 1 | structured | – | 1 | 6.088 | 510 | 20 | yes: 12B started 10:35:20.470 (started in 3.02 s, loaded runners 3) |
  | 3 | E | Guesser | 1 | tools | 1 | 1 | 2.898 | 2794 | 44 | no |
  | 4 | E | Guesser | 1 | tools | 2 | 1 | 1.147 | 3043 | 31 | no |
  | 5 | E | Guesser | 1 | structured | – | 1 | 2.605 | 1491 | 30 | no |
  | 6 | H | Describer | 1 | structured | – | 1 | 68.112 | 1301 | 705 | no |
  | 7 | H | Guesser | 1 | structured | – | 1 | 3.205 | 798 | 109 | no |

### Game 5 — card-b223994f (肉羹)

- Card (from `data/cards/cards.json`): official name 肉羹; aliases 肉羹湯, 香菇肉羹; English names Pork Thick Soup, Meat paste soup, bah-kenn, Rou Geng; forbidden words pork, fish, paste, thick, starch, bamboo; distractors 魷魚羹, 花枝羹, 土魠魚羹, 米粉羹, 生炒鴨肉羹.
- Record `runs/m6-t6/v3-game5.jsonl`: 1 line, `1 line(s) valid`; `variant` V3, `result` right guess, `matched_name` 肉羹, `counters` rounds 1, questions 0, forced passes 1; 12 calls (Challenger 3: 3 D `structured`; Describer 4: 3 B `text`, 1 H `structured`; Guesser 5: 1 E `structured`, 3 E `tools`, 1 H `structured`), attempts {1: 12}; 3 verdicts (fail 3); 2 rejected descriptions; 0 sent-back outputs; 2 lookups (success 2); `memory.game` 5.
- Trace: id `76e3d20a19b2564bb7a4f02952a35f64`, name `card-b223994f`, session `m6-t6`, root span 10:36:52.620–10:47:44.103 PST; 38 observations, all session `m6-t6`, levels DEFAULT 38. Node and router spans: B 3, C 3, D 3, E 1, F 1, G 1, H 1, LangGraph 1, route_after_d 3, route_after_e 1, route_c 3, route_f 1, A 1. Tool spans: 2, equal to the record's 2 lookups. Generation spans: 12, equal to the record's `calls` length 12; H generation spans 2 (the record's H calls 2); the multiset of (round, role, attempt, kind) equals the record's (True), with input and output tokens (True); in start-time order each span's (round, role, attempt, kind, tokens, `langgraph_node`) equals the call of the same ordinal (True); span latency within 0.001 s of the record's.
- Loads and evictions (`runs/m5/ollama-server.log`, lines timestamped inside the trace's root span): 3 `starting llama-server` lines: 12B at 10:40:01 (call 2), 12B at 10:42:15 (call 4), 12B at 10:44:41 (call 6); no `evicting` line. Every load falls inside one call's generation span (the table's last column); an `evicting` line does not name the model it evicts. No `truncated = 1` line in the whole run window.
- Transcript:
  - Round 1 (description):
    - Description 1, verdict **fail** (ordinal 2), rejected: "A smooth, glossy soup in which small, round, gelatinous nuggets of finely ground meat float in a pale, clear broth, each piece so uniform and tender it nearly dissolves on the tongue. Tiny, dark, crinkly shards of wood-ear fungus are scattered throughout, giving an occasional slight snap against the otherwise silky mouthfeel. The meat is ground to a fine consistency, bound with tapioca flour, and spooned into simmering water so each drop sets into a seamless, wrapper-free morsel. It is a staple of Taiwanese noodle shops, typically ladled over rice noodles and served by the bowl at a street-side counter for a few dollars." Reason: "The description of a smooth, gelatinous meat nugget in a clear broth also perfectly fits the snack made with shredded squid or cuttlefish."
    - Description 2, verdict **fail** (ordinal 4), rejected: "The protein here is ground pig meat, not a sea creature, so each small, glossy morsel carries a deep, savory umami rather than any briny or rubbery quality. Each drop is bound with a little tapioca flour and spooned into gently simmering, pale broth, where it sets into a seamless, wrapper-free nugget that melts under the tongue. A scattering of crinkly wood-ear fungus shards provides the only textural contrast in an otherwise entirely silky bowl. It is the default topping ladled over rice noodles at a street-side counter, served by the bowl for a few dollars." Reason: "The description of the savory, silky protein in a pale broth with wood-ear fungus also applies to the version made with duck."
    - Description 3, verdict **fail** (ordinal 6), forced pass [R13]: delivered to the Guesser: "The protein is ground pig shoulder, milled to a whisper-smooth consistency and bound with a little tapioca so each spoonful sets into a seamless, custard-like morsel that dissolves under the tongue. The cooked nuggets are a pale, rosy-gray, distinctly lighter and finer than the darker, coarser texture of any bird-meat variant. Crinkly wood-ear mushroom shards provide the sole textural contrast in an otherwise entirely silky, pale broth. It is the default, most-ordered topping ladled over rice noodles at a street-side noodle counter, sold by the bowl for a few dollars." Reason: "The description of a pale, silky, custard-like texture in a broth could easily be confused with the fish-based variants rather than specifically the pork version."
    - Lookup 1 `search` {keywords: pork} → 滷肉飯, 焢肉飯, 腿庫飯, 肉粽, 香菇肉粥, 肉燥乾麵, 榨菜肉絲麵, 大腸麵線, 肉粿, 刈包 (10; `more_results` true)
    - Lookup 2 `search` {cooking_method: Boiled; main_ingredients: Pork; physical_form: Thick Soup} → 米粉羹, 大腸麵線, 西魯肉, 肉羹 (4; `more_results` false)
    - Guess: text `肉羹`, confidence 0.9: right (肉羹, the official name); the Guesser wins in round 1.
    - Violations: none.
- Memory (node H, the record's `memory`; the files `runs/m6-t6/memory/describer-05.json` and `guesser-05.json` hold the same entry as their last and the same summary):
  - Describer: redos 0, `written` true, `failed` [] (empty), `tokens` 906 (the block read at game start).
    - Entry: "Game won in round 1 on Pork Thick Soup (rou geng / bah-kenn), but two prior descriptions were rejected: the first was too generic ('smooth gelatinous meat nugget in clear broth') and fit a squid or cuttlefish version, and the second still applied to a duck variant. The winning description succeeded by explicitly naming the animal source as 'pig shoulder' (bypassing the forbidden word 'pork'), using 'tapioca' in place of 'starch,' and adding a direct negative contrast—'distinctly lighter and finer than the darker, coarser texture of any bird-meat variant'—to rule out duck. The key lesson: when a dish's defining feature is a smooth, bound protein in broth, generic texture language is insufficient because the same mouthfeel describes squid, cuttlefish, duck, and pork versions alike, so I must front-load the specific animal body part and explicitly exclude the closest alternatives (seafood, poultry) before describing texture. Next time I face a bound-protein soup that shares its silky profile with multiple meats, I will lead with the animal's cut (shoulder, loin) and immediately add a one-clause exclusion of the nearest competing protein so the Guesser cannot anchor on a seafood or poultry variant."
    - Summary: null (games 1–5 have none)
  - Guesser: redos 0, `written` true, `failed` [] (empty), `tokens` 388 (the block read at game start).
    - Entry: "When the description emphasizes a fine, smooth, and almost liquid texture, focus on identifying the specific type of ground protein and the presence of any minimal textural contrasts like mushrooms. Searching for a combination of the main ingredient, the cooking method, and the physical consistency of the broth is highly effective for narrowing down thick-soup dishes. Since a high-confidence win was achieved without questions, rely on the distinction between different meat textures and the presence of starch-based thickening to make a direct guess."
    - Summary: null (games 1–5 have none)
- Per-call table (latency in seconds from the record's `calls`, rounded to the millisecond; input and output from the same; "call" is the tool-loop call index; "load inside" from the server log against the call's generation span start and end):

  | # | node | role | round | kind | call | attempt | latency (s) | input | output | load inside |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | 1 | B | Describer | 1 | text | – | 1 | 188.793 | 1674 | 2191 | no |
  | 2 | D | Challenger | 1 | structured | – | 1 | 7.274 | 495 | 47 | yes: 12B started 10:40:01.545 (started in 3.27 s, loaded runners 3) |
  | 3 | B | Describer | 1 | text | – | 1 | 126.389 | 1876 | 1454 | no |
  | 4 | D | Challenger | 1 | structured | – | 1 | 5.809 | 484 | 45 | yes: 12B started 10:42:15.231 (started in 2.01 s, loaded runners 3) |
  | 5 | B | Describer | 1 | text | – | 1 | 140.396 | 2030 | 1637 | no |
  | 6 | D | Challenger | 1 | structured | – | 1 | 6.158 | 482 | 51 | yes: 12B started 10:44:41.477 (started in 2.27 s, loaded runners 3) |
  | 7 | E | Guesser | 1 | tools | 1 | 1 | 2.768 | 2877 | 14 | no |
  | 8 | E | Guesser | 1 | tools | 2 | 1 | 2.506 | 3864 | 39 | no |
  | 9 | E | Guesser | 1 | tools | 3 | 1 | 1.433 | 4281 | 25 | no |
  | 10 | E | Guesser | 1 | structured | – | 1 | 4.363 | 2723 | 22 | no |
  | 11 | H | Describer | 1 | structured | – | 1 | 152.007 | 1856 | 1704 | no |
  | 12 | H | Guesser | 1 | structured | – | 1 | 3.358 | 893 | 108 | no |

### Game 6 — card-370cd9f4 (年糕)

- Card (from `data/cards/cards.json`): official name 年糕; aliases 甜年糕; English names Sweet Sticky Rice Cake, Nian Gao; forbidden words new, year, glutinous, brown, sugar, sticky; distractors 炸年糕, 發粿, 黑糖糕, 紅龜粿, 九層粿.
- Record `runs/m6-t6/v3-game6.jsonl`: 1 line, `1 line(s) valid`; `variant` V3, `result` right guess, `matched_name` 年糕, `counters` rounds 4, questions 2, forced passes 0; 36 calls (Challenger 6: 6 D `structured`; Describer 9: 8 B `text`, 1 H `structured`; Guesser 21: 4 E `structured`, 16 E `tools`, 1 H `structured`), attempts {1: 36}; 6 verdicts (fail 4, pass 2); 4 rejected descriptions; 0 sent-back outputs; 12 lookups (success 12); `memory.game` 6.
- Trace: id `b81c35ae05aa50b68adf144619c7c076`, name `card-370cd9f4`, session `m6-t6`, root span 10:47:44.840–11:13:09.583 PST; 104 observations, all session `m6-t6`, levels DEFAULT 104. Node and router spans: B 8, C 8, D 6, E 4, F 2, G 4, H 1, LangGraph 1, route_after_d 6, route_after_e 4, route_c 8, route_f 2, A 1. Tool spans: 12, equal to the record's 12 lookups. Generation spans: 36, equal to the record's `calls` length 36; H generation spans 2 (the record's H calls 2); the multiset of (round, role, attempt, kind) equals the record's (True), with input and output tokens (True); in start-time order each span's (round, role, attempt, kind, tokens, `langgraph_node`) equals the call of the same ordinal (True); span latency within 0.023 s of the record's.
- Loads and evictions (`runs/m5/ollama-server.log`, lines timestamped inside the trace's root span): 7 `starting llama-server` lines: 12B at 10:50:09 (call 2), 12B at 10:52:19 (call 4), 12B at 10:55:22 (call 6), 12B at 11:00:19 (call 27), 12B at 11:04:52 (call 29), 12B at 11:09:13 (call 31), 26B at 11:09:18 (call 32); 1 `evicting` line: 11:00:19.234 (predicted 7.1 GiB, system_free 6.2 GiB), then the 12B load at 11:00:19.520 (call 27) with loaded runners 2, and the next load of another model the 26B at 11:09:18.362 (call 32, loaded runners 2). Every load falls inside one call's generation span (the table's last column); an `evicting` line does not name the model it evicts. No `truncated = 1` line in the whole run window.
- Transcript:
  - Round 1 (description):
    - Description 1, verdict **fail** (ordinal 2), rejected: "It is a small, round or bar-shaped treat made entirely from milled rice flour, with a dense, pillowy, chewy interior that yields easily to the teeth. The sweet variety is pale white, sold in neat little stacks at night-market carts for a few dollars, and can be eaten soft and warm straight from the steamer. Alternatively, it is pan-fried until the exterior turns golden and crisp while the core stays tender. It is a quintessential grab-and-go snack, often paired with a drizzle of dark syrup or a scattering of toasted black sesame." Reason: "The description of the pan-fried version with a golden exterior and tender core also fits the fried rice cake variant."
    - Description 2, verdict **fail** (ordinal 4), rejected: "It is a small, dense cylinder or short bar made from a smooth, uniform paste of milled rice flour, with no visible grains—just a pillowy, yielding chew throughout the entire piece. The sweet version is pale white, sold in neat little stacks at night-market carts for a few dollars, and can be eaten soft and warm straight from the steamer. It is often dusted with toasted black sesame or given a thin drizzle of dark syrup as a simple finishing touch. You grab a piece from the cart and eat it on the spot, with no plate, no broth, no other components." Reason: "The description of a dense, pillowy rice flour paste served warm and plain could easily be confused with the brown sugar rice cake."
    - Description 3, verdict **pass** (ordinal 6): "It is a short, white cylinder of milled rice flour, completely uniform in color with no mottling or dark streaks, setting it apart from any caramelized or molasses-laden variant. The interior is dense and yielding, with a smooth, pillowy chew that resists tearing rather than crumbling. At a night-market cart, a vendor slices a piece from a large steamed block and hands it over still warm, sometimes dusted with toasted black sesame or drizzled with a thin, pale syrup. You eat it standing up, in one or two bites, with no plate, no broth, no other components."
    - Lookup 1 `search` {cooking_method: Steamed; dish_type: Snack; flavor: Sweet; main_ingredients: Rice; occasion: Night Market; physical_form: Dry} → 豬血糕 (1; `more_results` false)
    - Lookup 2 `search` {cooking_method: Steamed; dish_type: Snack; main_ingredients: Rice; physical_form: Dry} → 豬血糕, 鹹粿, 芋粿巧, 客家菜包, 草仔粿, 蘿蔔糕, 糯米腸 (7; `more_results` false)
    - Lookup 3 `search` {cooking_method: Steamed; dish_type: Snack; flavor: Sweet; main_ingredients: Rice} → 豬血糕 (1; `more_results` false)
    - Lookup 4 `search` {cooking_method: Steamed; dish_type: Snack; main_ingredients: Rice; physical_form: Dry} → 豬血糕, 鹹粿, 芋粿巧, 客家菜包, 草仔粿, 蘿蔔糕, 糯米腸 (7; `more_results` false)
    - Lookup 5 `search` {cooking_method: Steamed; dish_type: Snack; flavor: Savory; main_ingredients: Rice} → 豬血糕, 碗粿, 鹹粿, 肉粿, 芋粿巧, 客家菜包, 草仔粿, 蘿蔔糕, 糯米腸 (9; `more_results` false)
    - Question: "Does the snack contain any meat or animal blood?"
    - Violations: none.
  - Round 2 (answer; no Challenger call [R12]): "No, it contains no meat or animal blood—it is made entirely from milled rice flour and water."
    - Lookup 1 `search` {cooking_method: Steamed; dish_type: Snack; flavor: Sweet; main_ingredients: Rice; physical_form: Dry} → 豬血糕 (1; `more_results` false)
    - Lookup 2 `search` {cooking_method: Steamed; dish_type: Snack; main_ingredients: Rice; physical_form: Dry} → 豬血糕, 鹹粿, 芋粿巧, 客家菜包, 草仔粿, 蘿蔔糕, 糯米腸 (7; `more_results` false)
    - Lookup 3 `search` {cooking_method: Steamed; dish_type: Snack; flavor: Sweet; main_ingredients: Rice; physical_form: Dry} → 豬血糕 (1; `more_results` false)
    - Lookup 4 `search` {cooking_method: Steamed; dish_type: Snack; main_ingredients: Rice; physical_form: Dry} → 豬血糕, 鹹粿, 芋粿巧, 客家菜包, 草仔粿, 蘿蔔糕, 糯米腸 (7; `more_results` false)
    - Lookup 5 `search` {cooking_method: Steamed; dish_type: Snack; flavor: Sweet; main_ingredients: Rice} → 豬血糕 (1; `more_results` false)
    - Question: "Is the flavor profile primarily sweet?"
    - Violations: none.
  - Round 3 (answer; no Challenger call [R12]): "Yes, the flavor is primarily sweet, with a gentle, clean sweetness rather than a deep caramel or molasses richness."
    - Lookup 1 `search` {cooking_method: Steamed; dish_type: Dessert; flavor: Sweet; main_ingredients: Rice} → 麻糬, 狀元糕, 年糕, 紅龜粿, 發粿, 九層粿, 涼糕, 茯苓糕, 桂圓米糕 (9; `more_results` false)
    - Guess: text `麻糬`, confidence 0.7: wrong.
    - Violations: none.
  - Round 4 (description):
    - Description 1, verdict **fail** (ordinal 27), rejected: "It is formed as a short, firm cylinder rather than a small round ball, and its texture is dense and cake-like rather than elastic or bouncy when pressed between the fingers. The dough is prepared by mixing milled rice flour into a smooth paste and steaming it into one large block, from which individual pieces are cut—unlike a treat that is hand-shaped into separate spheres and often stuffed with a filling. The surface is matte and pale, with a clean, mild sweetness that reads more like a simple steamed cake than a rich, filling-laden confection. At a cart, you buy a single slice still warm, and it keeps its shape in your hand without stretching or drooping." Reason: "The description of a dense, steamed rice flour cake with a mild sweetness could also easily describe the brown sugar cake."
    - Description 2, verdict **fail** (ordinal 29), rejected: "It is made from milled rice flour and water with only a whisper of added sweetness—far less than a dessert confection—giving it a clean, almost bread-like flavor where the grain itself is the star. The piece is a neat, flat slice, roughly the size of a matchbook, cut with a wire from a large, uniformly pale steamed block, and it holds a dense, firm structure that separates cleanly under the teeth without any stretch or elastic pull. It is a solid, single-substance piece with no interior filling or layered pocket, unlike a small hand-rolled ball wrapped around a center. You buy it warm from a cart and eat it plain, and it reads more like a dense, mild steamed bread than a rich, sweet treat." Reason: "The description of a dense, firm, plain steamed rice cake without filling or stretch could also apply to a simple brown sugar rice cake if the sweetness is kept minimal."
    - Description 3, verdict **pass** (ordinal 31): "It is a flat, disc-shaped piece with a uniformly pale, cream-white surface—no dark flecks, no mottling, no caramel-toned streaks running through the interior. The sweetness is light and clean, closer to a simple steamed cake with a hint of sweetener than to a deep, molasses-rich confection. The texture is firm and dense, breaking cleanly under the teeth like a thick rice-flour cake rather than springing back or stretching between the fingers. At the cart, a vendor uses a wire to slice one piece from a large rectangular steamed block, and you receive it warm, plain, with nothing added."
    - Lookup 1 `search` {cooking_method: Steamed; flavor: Sweet; main_ingredients: Rice} → 豬血糕, 麻糬, 狀元糕, 年糕, 紅龜粿, 發粿, 九層粿, 涼糕, 茯苓糕, 桂圓米糕 (10; `more_results` false)
    - Guess: text `年糕`, confidence 0.8: right (年糕, the official name); the Guesser wins in round 4.
    - Violations: none.
- Memory (node H, the record's `memory`; the files `runs/m6-t6/memory/describer-06.json` and `guesser-06.json` hold the same entry as their last and the same summary):
  - Describer: redos 0, `written` true, `failed` [] (empty), `tokens` 1172 (the block read at game start).
    - Entry: "Game 6 won in round 4 on Nian Gao (Sweet Sticky Rice Cake), but the Guesser first guessed mochi in round 3, drawn by the 'pillowy chew' and 'dense, yielding' language that overlaps with an elastic rice ball. Three descriptions were rejected for reading as the brown-sugar rice cake variant, confirming that 'warm, plain, dense rice-flour paste' is too generic to separate the pale sweet version from the caramelized one. What finally worked was the explicit texture contrast—'breaks cleanly under the teeth rather than springing back or stretching between the fingers'—plus the shape cue 'flat, disc-shaped slice cut with a wire from a large block,' which together rule out both mochi (round, elastic) and the brown-sugar cake (darker, mottled). Next time I face a rice-flour cake, I will lead with the cut shape (flat slice vs. ball) and the clean-break-versus-stretch contrast in the first sentence, then immediately state 'uniformly pale, no dark streaks' to kill the brown-sugar alternative before the Guesser can anchor on it."
    - Summary: "Game 1 (smooth batter cake): The Guesser confused it with bamboo tube rice twice because the bamboo-cooking method was the strongest visual cue; the fix was to lead with the homogeneous, pourable batter texture, demote the bamboo vessel to a secondary detail, and front-load the street-cart, few-dollar context. Recurring principle across early games: when a cooking vessel, method, or generic texture is shared with a different dish, describe the interior character first and the shared feature second, and add an explicit negative exclusion (no whole grains, no chewable kernels) in the same sentence to block the competing candidate. Front-loading the most diagnostic shape-or-texture cue before any context or vessel detail is the single most reliable disambiguation strategy."
  - Guesser: redos 0, `written` true, `failed` [] (empty), `tokens` 491 (the block read at game start).
    - Entry: "When the description emphasizes a uniform, pale, and minimalist appearance, use questions to rule out savory or meat-based components and confirm a sweet flavor profile early. Searching for a combination of cooking method, flavor, and main ingredient is highly effective for narrowing down broad results to a single item. If the texture is described as dense and firm rather than stretchy or soft, use that distinction to differentiate between similar starch-based snacks."
    - Summary: "Avoid guessing items with visible grains or kernels when the description emphasizes a smooth, liquid, or homogeneous texture. Focus on distinguishing between dishes with distinct textures versus those that are paste-like, as searching for specific physical forms like 'paste' or 'pudding' significantly narrows the results. Use questions to clarify the main ingredient's composition and the flavor profile early on, but wait for specific texture cues before committing to a final guess. When the description emphasizes a very simple, minimalist ingredient list with no oil or extra vegetables, focus on identifying the specific regional origin or the texture of the starch component. Searching for broad categories like noodle types can return too many results, so look for clues regarding the density and smoothness of the grain. If the description provides specific geographic locations like certain northern counties, use that to narrow down the regional specialty immediately. When the description highlights a specific cooking liquid and a deep, glossy color, use the protein source and the cooking method as the primary search filters. If the texture is described as dense and firm, I can confidently guess once the cooking method and ingredient are identified."
  - The Guesser's summary repeats entries (by script): it is the game-1 entry and the game-2 entry verbatim, in full, followed by the game-3 entry's first and last sentences with one word added ("the cooking method"); games 2 and 3 are still among `guesser-06.json`'s five entries. The Describer's summary shares no more than 10 characters with any Describer entry.
- Per-call table (latency in seconds from the record's `calls`, rounded to the millisecond; input and output from the same; "call" is the tool-loop call index; "load inside" from the server log against the call's generation span start and end):

  | # | node | role | round | kind | call | attempt | latency (s) | input | output | load inside |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | 1 | B | Describer | 1 | text | – | 1 | 144.484 | 1928 | 1596 | no |
  | 2 | D | Challenger | 1 | structured | – | 1 | 8.073 | 466 | 36 | yes: 12B started 10:50:09.457 (started in 4.54 s, loaded runners 3) |
  | 3 | B | Describer | 1 | text | – | 1 | 122.411 | 2095 | 1403 | no |
  | 4 | D | Challenger | 1 | structured | – | 1 | 5.807 | 471 | 45 | yes: 12B started 10:52:19.977 (started in 2.02 s, loaded runners 3) |
  | 5 | B | Describer | 1 | text | – | 1 | 176.425 | 2255 | 2089 | no |
  | 6 | D | Challenger | 1 | structured | – | 1 | 4.990 | 471 | 20 | yes: 12B started 10:55:22.237 (started in 2.02 s, loaded runners 3) |
  | 7 | E | Guesser | 1 | tools | 1 | 1 | 3.506 | 2979 | 54 | no |
  | 8 | E | Guesser | 1 | tools | 2 | 1 | 1.357 | 3191 | 45 | no |
  | 9 | E | Guesser | 1 | tools | 3 | 1 | 2.386 | 4011 | 43 | no |
  | 10 | E | Guesser | 1 | tools | 4 | 1 | 1.382 | 4212 | 45 | no |
  | 11 | E | Guesser | 1 | tools | 5 | 1 | 2.412 | 5032 | 44 | no |
  | 12 | E | Guesser | 1 | tools | 6 | 1 | 2.836 | 6041 | 45 | no |
  | 13 | E | Guesser | 1 | structured | – | 1 | 7.839 | 4527 | 38 | no |
  | 14 | B | Describer | 2 | text | – | 1 | 35.139 | 2382 | 299 | no |
  | 15 | E | Guesser | 2 | tools | 1 | 1 | 2.884 | 3016 | 47 | no |
  | 16 | E | Guesser | 2 | tools | 2 | 1 | 1.342 | 3221 | 45 | no |
  | 17 | E | Guesser | 2 | tools | 3 | 1 | 2.458 | 4041 | 51 | no |
  | 18 | E | Guesser | 2 | tools | 4 | 1 | 1.386 | 4250 | 45 | no |
  | 19 | E | Guesser | 2 | tools | 5 | 1 | 2.391 | 5070 | 43 | no |
  | 20 | E | Guesser | 2 | tools | 6 | 1 | 1.519 | 5271 | 51 | no |
  | 21 | E | Guesser | 2 | structured | – | 1 | 6.417 | 3763 | 34 | no |
  | 22 | B | Describer | 3 | text | – | 1 | 40.570 | 2420 | 378 | no |
  | 23 | E | Guesser | 3 | tools | 1 | 1 | 2.695 | 3060 | 39 | no |
  | 24 | E | Guesser | 3 | tools | 2 | 1 | 2.011 | 3867 | 26 | no |
  | 25 | E | Guesser | 3 | structured | – | 1 | 3.622 | 2310 | 30 | no |
  | 26 | B | Describer | 4 | text | – | 1 | 167.444 | 2448 | 1991 | no |
  | 27 | D | Challenger | 4 | structured | – | 1 | 7.865 | 488 | 37 | yes: after an `evicting` line at 11:00:19.234 (predicted 7.1 GiB, system_free 6.2 GiB); 12B started 11:00:19.520 (started in 3.79 s, loaded runners 2) |
  | 28 | B | Describer | 4 | text | – | 1 | 265.314 | 2647 | 3185 | no |
  | 29 | D | Challenger | 4 | structured | – | 1 | 5.879 | 504 | 52 | yes: 12B started 11:04:52.494 (started in 1.77 s, loaded runners 2) |
  | 30 | B | Describer | 4 | text | – | 1 | 255.319 | 2855 | 3048 | no |
  | 31 | D | Challenger | 4 | structured | – | 1 | 4.642 | 479 | 20 | yes: 12B started 11:09:13.738 (started in 1.76 s, loaded runners 2) |
  | 32 | E | Guesser | 4 | tools | 1 | 1 | 8.881 | 3210 | 30 | yes: 26B started 11:09:18.362 (started in 2.76 s, loaded runners 2) |
  | 33 | E | Guesser | 4 | tools | 2 | 1 | 2.380 | 4149 | 31 | no |
  | 34 | E | Guesser | 4 | structured | – | 1 | 5.062 | 2597 | 30 | no |
  | 35 | H | Describer | 4 | structured | – | 1 | 193.188 | 2804 | 2092 | no |
  | 36 | H | Guesser | 4 | structured | – | 1 | 8.843 | 1813 | 322 | no |

### Game 7 — card-aae840e9 (杏仁豆腐)

- Card (from `data/cards/cards.json`): official name 杏仁豆腐; aliases 杏仁凍; English names Almond Jelly, Xing Ren Dou Fu; forbidden words almond, jelly, cubes, syrup, white; distractors 仙草凍, 愛玉冰, 豆花, 菜燕, 杏仁茶.
- Record `runs/m6-t6/v3-game7.jsonl`: 1 line, `1 line(s) valid`; `variant` V3, `result` right guess, `matched_name` 杏仁豆腐, `counters` rounds 2, questions 1, forced passes 0; 13 calls (Challenger 1: 1 D `structured`; Describer 3: 2 B `text`, 1 H `structured`; Guesser 9: 2 E `structured`, 6 E `tools`, 1 H `structured`), attempts {1: 13}; 1 verdicts (pass 1); 0 rejected descriptions; 0 sent-back outputs; 4 lookups (error 1, success 3); `memory.game` 7.
- Trace: id `99b37d625973da17c1b2db7687e627ca`, name `card-aae840e9`, session `m6-t6`, root span 11:13:10.305–11:20:18.373 PST; 37 observations, all session `m6-t6`, levels DEFAULT 36, ERROR 1. Node and router spans: B 2, C 2, D 1, E 2, F 1, G 2, H 1, LangGraph 1, route_after_d 1, route_after_e 2, route_c 2, route_f 1, A 1. Tool spans: 4, equal to the record's 4 lookups. Generation spans: 13, equal to the record's `calls` length 13; H generation spans 2 (the record's H calls 2); the multiset of (round, role, attempt, kind) equals the record's (True), with input and output tokens (True); in start-time order each span's (round, role, attempt, kind, tokens, `langgraph_node`) equals the call of the same ordinal (True); span latency within 0.001 s of the record's.
  - The ERROR observation: TOOL `search`, the lookup the tool's schema rejected (its status message is the record's lookup result).
- Loads and evictions (`runs/m5/ollama-server.log`, lines timestamped inside the trace's root span): 2 `starting llama-server` lines: 12B at 11:15:20 (call 2), 26B at 11:15:27 (call 3); 1 `evicting` line: 11:15:20.753 (predicted 7.1 GiB, system_free 7.0 GiB), then the 12B load at 11:15:20.934 (call 2) with loaded runners 2, and the next load of another model the 26B at 11:15:27.506 (call 3, loaded runners 2). Every load falls inside one call's generation span (the table's last column); an `evicting` line does not name the model it evicts. No `truncated = 1` line in the whole run window.
- Transcript:
  - Round 1 (description):
    - Description 1, verdict **pass** (ordinal 2): "A delicate, silken set dessert made from the milk of a flat, teardrop-shaped nut, chilled until it holds a smooth, custard-like form in a small round bowl. It has no graininess, no egg, no starch lump—just a pure, creamy melt that dissolves on the tongue. Served ice-cold, it is crowned with a pourable sweet sauce and a scatter of fresh fruit. You will find it at Chinese teahouses and dessert stalls, presented as a light, elegant finish to a meal."
    - Lookup 1 `search` {flavor: Sweet; main_ingredients: Milk; physical_form: Set} → status `error`, not searched (the message's one line break shown as " / "): "The search was not run; the tool's schema rejects these arguments: / physical_form[0]: Input should be 'Dry', 'Sauced', 'Soup', 'Thick Soup', 'Shaved Ice', 'Ice Pop', 'Smooth Drink', 'Drink with Add-ins' or 'Slush' (got 'Set')"
    - Lookup 2 `search` {flavor: Sweet; main_ingredients: Milk} → 花生捲冰淇淋, 紅豆煉乳冰, 芒果冰, 牛奶雪花冰, 月見冰, 木瓜牛奶, 奶茶, 珍珠奶茶, 黑糖珍珠鮮奶, 仙草凍奶茶 (10; `more_results` true)
    - Lookup 3 `search` {main_ingredients: Milk; physical_form: Shaved Ice} → 紅豆煉乳冰, 芒果冰, 牛奶雪花冰, 月見冰 (4; `more_results` false)
    - Question: "Is the main ingredient derived from a nut or a seed?"
    - Violations: none.
  - Round 2 (answer; no Challenger call [R12]): "It is derived from a nut—the flat, teardrop-shaped kernel of a small tree, commonly grouped with walnuts and pecans in the pantry."
    - Lookup 1 `search` {keywords: almond} → 杏仁豆腐, 杏仁茶 (2; `more_results` false)
    - Guess: text `杏仁豆腐`, confidence 1.0: right (杏仁豆腐, the official name); the Guesser wins in round 2.
    - Violations: none.
- Memory (node H, the record's `memory`; the files `runs/m6-t6/memory/describer-07.json` and `guesser-07.json` hold the same entry as their last and the same summary):
  - Describer: redos 0, `written` true, `failed` [] (empty), `tokens` 1376 (the block read at game start).
    - Entry: "Game won in round 2 on Almond Jelly (Xing Ren Dou Fu). The decisive cue was describing the base as 'the milk of a flat, teardrop-shaped nut'—a physical-form stand-in for the forbidden word that immediately narrows the field to a single ingredient—combined with stacked negative exclusions (no egg, no starch lump, no graininess) that killed panna cotta, egg custard, and starch-pudding alternatives in one stroke. The round-2 confirmation that the nut is 'commonly grouped with walnuts and pecans in the pantry' gave the Guesser the final species-level identification it needed to lock the name. No rejections or misdirection occurred, so the lesson is additive: for any set dessert whose identity hinges on a single nut or seed, lead with the kernel's shape and the word 'milk' as the derivation, then immediately stack two or three 'no X' exclusions to eliminate the nearest dairy- or starch-based look-alikes before mentioning serving context."
    - Summary: "Across the earliest games, the recurring principle is to front-load the single most diagnostic cue—shape, texture, or ingredient origin—before any cooking vessel, context, or shared method, because those shared features are what draw the Guesser toward a competing dish. Negative exclusions ('no eggs, no starch lump, no whole grains') placed in the same sentence as the positive description reliably block the nearest alternatives. When a forbidden ingredient must be referenced, a physical-form stand-in ('flat, teardrop-shaped kernel,' 'milled grain paste,' 'bean curd') communicates the identity without the banned word. Geographic or cultural context (hillside villages, night-market stalls, teahouses) works best as a secondary anchor, not the lead. The Guesser's confusion pattern is consistent: it anchors on the most visually or texturally salient feature first, so if that feature is shared with another snack, the description must preemptively exclude the look-alike before the Guesser can lock on."
  - Guesser: redos 0, `written` true, `failed` [] (empty), `tokens` 706 (the block read at game start).
    - Entry: "When the description highlights a smooth, custard-like texture and a lack of grains or starch, use questions to confirm if the primary ingredient is a nut or a seed. Avoid using specific physical forms like 'set' in searches, as the tool may reject non-standard terms; instead, focus on searching for the main ingredient and flavor profile. If the description mentions a specific nut type, a targeted keyword search can lead to a high-confidence win."
    - Summary: "Avoid guessing items with visible grains or kernels when the description emphasizes a smooth, liquid, or homogeneous texture. Focus on distinguishing between dishes with distinct textures versus those that are paste-like, as searching for specific physical forms can significantly narrow the results. When the description emphasizes a very simple, minimalist ingredient list, focus on identifying the specific regional origin or the texture of the starch component. Use questions to rule out savory or meat-based components and confirm a sweet flavor profile early. When a description highlights a specific cooking liquid and a deep, glossy color, use the protein source and the cooking method as the primary search filters. If the texture is described as dense and firm, identify the ingredient and cooking method to make a confident guess. When descriptions feature a specific protein and an aromatic vegetable garnish, prioritize searching for the interplay between the main ingredient and the secondary herb. When the description emphasizes a fine, smooth, and almost liquid texture, focus on identifying the specific type of ground protein and the presence of any minimal textural contrasts."
- Per-call table (latency in seconds from the record's `calls`, rounded to the millisecond; input and output from the same; "call" is the tool-loop call index; "load inside" from the server log against the call's generation span start and end):

  | # | node | role | round | kind | call | attempt | latency (s) | input | output | load inside |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | 1 | B | Describer | 1 | text | – | 1 | 130.362 | 2130 | 1388 | no |
  | 2 | D | Challenger | 1 | structured | – | 1 | 6.734 | 463 | 15 | yes: after an `evicting` line at 11:15:20.753 (predicted 7.1 GiB, system_free 7.0 GiB); 12B started 11:15:20.934 (started in 3.77 s, loaded runners 2) |
  | 3 | E | Guesser | 1 | tools | 1 | 1 | 8.810 | 3182 | 29 | yes: 26B started 11:15:27.506 (started in 2.77 s, loaded runners 2) |
  | 4 | E | Guesser | 1 | tools | 2 | 1 | 0.825 | 3287 | 25 | no |
  | 5 | E | Guesser | 1 | tools | 3 | 1 | 2.431 | 4273 | 29 | no |
  | 6 | E | Guesser | 1 | tools | 4 | 1 | 1.753 | 4669 | 47 | no |
  | 7 | E | Guesser | 1 | structured | – | 1 | 6.054 | 3133 | 31 | no |
  | 8 | B | Describer | 2 | text | – | 1 | 62.259 | 2268 | 643 | no |
  | 9 | E | Guesser | 2 | tools | 1 | 1 | 1.502 | 3230 | 14 | no |
  | 10 | E | Guesser | 2 | tools | 2 | 1 | 1.071 | 3427 | 30 | no |
  | 11 | E | Guesser | 2 | structured | – | 1 | 3.720 | 1874 | 29 | no |
  | 12 | H | Describer | 2 | structured | – | 1 | 179.140 | 2134 | 2007 | no |
  | 13 | H | Guesser | 2 | structured | – | 1 | 8.098 | 1475 | 311 | no |
