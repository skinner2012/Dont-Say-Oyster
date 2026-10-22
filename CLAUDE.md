# Don't Say Oyster — CLAUDE.md

Behavioural contract for Claude Code on this repo. Every line here should change how the agent acts; it is not documentation.

## What this project is

A Taboo-like guessing game about Taiwanese snacks, played by three local LLM agents (Describer, Guesser, Challenger) on Ollama with LangChain/LangGraph and Phoenix tracing. It is built as four ablation variants V0–V3 and run on a Mac mini M4 Pro (64 GB). The output is material for a Substack post, not a product.

## Source of truth

- `SPEC.md` is the only authority on what the system does. Rules are numbered **R1–R50**; cite them as `[R17]` instead of restating them.
- If code and `SPEC.md` disagree, `SPEC.md` wins until the author changes it.
- `docs/DECISIONS.md` records why `SPEC.md` says what it says. Every change to `SPEC.md` gets a new entry there: date, the commit hash of the change, what was added, changed, or removed, and why. Read only the sections for the area in question, and only before proposing or reviewing a `SPEC.md` change, or when a design choice blocks a ticket; not for routine ticket work.
- Non-goals in `SPEC.md` are binding. Do not propose features, "more complete" designs, or extra safeguards unless asked. Audit findings are not proposals; report them.

## Progress

Progress lives in the repo: each ticket carries a `Status` line (`todo`, `done <hash>`, `blocked`), and each ticket file ends with `## Audit findings` (finding, fixed or deferred, who decided). To see where the project is: `git log` on the milestone branch plus the current ticket file. Auto-memory (`MEMORY.md`) is for session notes only (what was tried, what is next); read it at session start, write it at session end, and never treat it as the only record.

## How to work with the author

- The author edits `SPEC.md` personally; agents write tickets, `docs/DECISIONS.md` entries, and `docs/tasks/BACKLOG.md` patches. On `SPEC.md`, Claude points to exact lines, explains the problem, gives wording only when asked, and judges the result as pass or fail.
- Line numbers shift constantly. Always re-read the file from disk before citing a line; never cite from memory. Check that the author's edit is saved before judging it.
- Give an honest opinion when asked, including disagreement. Do not agree to be agreeable.

## Delegation

- Fable at high effort: deep design reviews, fresh-eyes audits, and the cases named below.
- Opus: translation, restructuring, generating tickets and other long-form drafts.
- Sonnet: mechanical extraction and verification (rule inventories, diff checks, dependency checks).
- Implementing a ticket: Opus by default; Fable at high effort for the hard ones (LangGraph wiring, the tool loop, the memory check rule).
- Problems during implementation or testing: the implementing session debugs first and finds the root cause before changing anything. Escalate to Fable at high effort when the root cause is unclear after one honest attempt, or when the problem looks like a `SPEC.md` gap rather than a code bug. A ticket blocked on a `SPEC.md` gap stops; record the question in the ticket file under `## Open questions for the author` and move to a ticket that does not depend on it.
- Changing `SPEC.md`: the author edits; Fable at high effort reviews the change for consistency with the rest of the spec and judges pass or fail; Sonnet re-checks cross-references (rule numbers, milestones, State table) and the affected `docs/tasks/BACKLOG.md` items and any open ticket file. Rule ids are append-only (`R51`, …); never renumber. The reviewing session then adds the `docs/DECISIONS.md` entry in the next commit, citing the `SPEC.md` commit's hash.
- Every generated artifact gets an independent verification pass by a different session or subagent before the author reviews it.

### Dispatching an agent

- Tell a subagent which files to read: `CLAUDE.md`, its ticket, and the `SPEC.md` sections and rules the ticket cites. Paste in anything it needs from `MEMORY.md`; do not assume it can see it.
- Every implementation dispatch names the tickets, a time budget, and says: commit each ticket when its Acceptance passes, never hold more than one finished ticket uncommitted; report one line after each ticket; stop and report when the budget is exceeded; do no unrequested work.

### Auditing a ticket

- The auditor is never the session that wrote the code. It reviews the diff against the ticket's Acceptance and the cited rules.
- Beyond checking that each claim is true, run three passes: is one counted thing one real thing (a retried model call is one call in the log but two in latency); who divides this number downstream and by what (hit rate is over forty cards, not over games that reached a guess); which statements in `SPEC.md`, the ticket file, or other code does this change make false.
- Re-derive numbers independently, do not let the implementer's report bound the audit, and finish by stating what was not checked.
- A finding is closed by a fix or by the author's explicit deferral, never by the agent that reported it.

## Rules of engagement

- Dependencies named in `SPEC.md` (LangChain, LangGraph, Phoenix) and the dev toolchain chosen in M1 (test runner, linter, type checker, Chinese script converter) are pre-approved. Ask before adding any other.
- Never commit secrets. Endpoints and keys come from `.env`.
- Pin everything that affects reproducibility: model tags and quantization, `num_ctx`, temperature, library versions. The ablation comparison depends on it.
- Prefer surgical edits over rewrites. Write a test for each new behaviour.
- Each ticket is self-contained: it can be completed from the ticket, the `SPEC.md` sections it cites, and the artifacts its Consumes line names.

## Commit workflow

- Before every commit: lint, type check, and the affected tests pass (commands in `## Commands`, filled by M1.1). A commit touching only Markdown needs no code gate; say so instead of running one.
- Before handing a ticket back as complete: run the full test suite once at the end, green. Not after every commit.
- Commit only currently staged files. One commit is one of: a ticket's implementation; an audit fix for one finding; a ticket's `Status` or `Audit findings` update; one `SPEC.md` change with its `BACKLOG.md` patch; one doc fix. If staged files span two of these, stop and report.
- In the session talking to the author: propose the commit message and wait for explicit approval before committing, even in auto mode. A dispatched implementer commits its ticket without asking once the ticket's Acceptance passes, with the message format below. Format: Conventional Commits, title only, `type(scope): concise description`, no body except the `Co-Authored-By` trailer. Scope is the module or doc touched (`corpus`, `oracle`, `spec`, `tasks`, `docs`).

- Branches: one branch per milestone (`m1-corpus`, `m2-one-game`, …). Every commit during a milestone, including `SPEC.md`, `BACKLOG.md`, and `DECISIONS.md` changes, lands on that branch. When the milestone's `Done when` holds, rebase onto `main` and fast-forward `main` to the branch; never create a merge commit (the author's preference, 2026-10-16). `main` moves only at the end of a milestone.

## Start here (first session in this repo)

1. The initial import commit on `main` holds the five files plus the first `docs/DECISIONS.md` Process entry: "SPEC v1 imported" with that commit's hash added in the next commit on the milestone branch.
2. Create branch `m1-corpus`. Write `docs/tasks/M1-corpus.md` by the procedure in `docs/tasks/TEMPLATE.md`; the author reviews it.
3. Backlog item M1.1 sets up the repo and the dev toolchain, and appends a `## Commands` section to this file with the lint, type-check, and test commands.
4. Record the date of the first code commit in `docs/DECISIONS.md`.

## Milestones and tickets

- `SPEC.md` lists the milestones in order (M1, M2, …); each is a bullet list ending in a `Done when` line. A milestone is done when that line is true; the author declares it in a one-line `docs/DECISIONS.md` Process entry, the last commit on the branch before `main` is fast-forwarded.
- Tickets live in `docs/tasks/M<n>-<short-name>.md` (short name: two or three lowercase words from the milestone title, hyphenated, e.g. `M1-corpus.md`, `M2-one-game.md`), one file per milestone, written **only when the previous milestone is done**. The format is in `docs/tasks/TEMPLATE.md`.
- One ticket = one implementation commit (audit fixes and Status updates are separate small commits), so a ticket does one thing; its scope boundary (what it does and does not touch) is part of the ticket. A ticket's Acceptance must be observable; program logic is verified with scripted model outputs, and a ticket whose job is a live run is accepted by the record it leaves, not by the result's quality.
- A ticket's Detail says only what `SPEC.md` does not: module boundaries, file names, how to test. Rules are cited by `[R#]`, never paraphrased.
- A ticket is done when its code and tests pass, its Acceptance holds, every audit finding is fixed or explicitly deferred by the author, and its `Status` line says `done <hash>`. Code merely written is not done.
- `docs/tasks/BACKLOG.md` holds the draft work items that each milestone's tickets are cut from. It is raw material, not a plan; `SPEC.md` wins where they disagree. Read it only when cutting or verifying a milestone's tickets, or patching it after a `SPEC.md` change, and only that milestone's block.

## Commands

Run from the repo root; each must exit 0.

- Lint: `uv run ruff check .`
- Type check: `uv run mypy`
- Test: `uv run pytest`
