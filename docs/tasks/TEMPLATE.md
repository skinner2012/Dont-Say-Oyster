# Ticket file template

One file per milestone, `docs/tasks/M<n>-<short-name>.md`, written when the previous milestone is done. Tickets are cut from the milestone's block in `docs/tasks/BACKLOG.md` and from the milestone's bullets in `SPEC.md`. `SPEC.md` wins where they disagree.

## File layout

```markdown
# M<n> — <milestone title as in SPEC.md>

## Goal & exit criterion

See `SPEC.md`, Milestones, M<n>. Do not copy the bullets here; they go stale.

**Exit criterion:** <the milestone's "Done when" line from SPEC.md, verbatim; the one line that is copied.>

- **Real:** <what this milestone actually delivers, one line.>
- **Absent:** <what it deliberately does not touch, one line; name the milestone that does.>

## How to use these tickets

<One paragraph: the dependency order (which tickets are parallel, which are sequential), and "one ticket, one commit".>

## Tickets

### T1 — <title>
- **Status:** todo | done <hash> | blocked
- **Produces:** <the artifact: files, modules, data, a decision written down>
- **Consumes:** <inputs from earlier tickets or milestones; omit if none>
- **Detail:**
  - <only what SPEC.md does not say: module boundary, file names, how to test>
  - <cite rules as [R17]; never restate them>
- **Acceptance:** <an observable check: a command, a test, a file that exists with a stated property>
- **Out of scope:** <what this ticket must not touch, even though it is nearby>
- **Depends on:** <T-ids in this file, or M<n> for a finished milestone; "—" if none>

## Open questions for the author

<Filled by the ticket writer or an implementer when SPEC.md is ambiguous or wrong; empty otherwise.>

## Audit findings

<One line per finding: ticket, finding, fixed <hash> | deferred by author <date>.>
```

## Field rules

- **Produces** names the artifact, not the activity. "Corpus loader in `corpus/load.py` that returns typed entries", not "work on the loader".
- **Detail** adds only what `SPEC.md` leaves open. If a bullet could be replaced by a rule id, replace it.
- **Acceptance** is something a second agent can run or look at and get yes or no. Program logic is checked with scripted model outputs (a fixed fake response fed into the node). A ticket whose job is a live run (a smoke test, a batch, a hand review) is accepted by the record it leaves behind, not by the result's quality.
- **Out of scope** is mandatory. It is the line that keeps one ticket at one commit. Write what a diligent implementer would be tempted to do next and say no.
- **Status** is updated by whoever changes it, in its own small docs commit: the implementer writes `done <hash>` after the implementation commit; `blocked` names the open question.
- **Depends on** must resolve: every T-id exists in this file or names a finished milestone (`M1`), and the graph has no cycle. Tickets of earlier milestones are not cited; their artifacts are named in Consumes.

## Cutting tickets from the backlog

- One ticket does one thing. If a backlog item does two things (build X and check Y), split it.
- If two backlog items cannot land as separate commits (one is useless without the other, or they touch the same function), merge them into one ticket and say so in Detail.
- Keep the backlog ids in Detail (`from BACKLOG M2.12, M2.14`) so coverage can be checked.
- Decisions the author must make (a criterion, a prompt, a schema field list) are their own tickets with Produces = "the decision, written down in <file>". They are usually the first tickets in the file.
- A ticket that only runs something and reads the result (a live game, a batch) has Acceptance = the record it leaves behind, not the result's quality.

## Example

```markdown
### T3 — Corpus entry schema and loader
- **Status:** todo
- **Produces:** `corpus/schema.py` (one entry: Chinese official name, accepted aliases, English names, forbidden words, attributes) and `corpus/load.py` that reads the corpus JSON into typed entries.
- **Consumes:** the attribute field list from T2.
- **Detail:**
  - Fields and languages as in `SPEC.md`, Corpus and Cards; attribute fields are the search tool's filter fields [R44].
  - Unknown fields are an error, not a warning.
  - Test fixture: a hand-written three-entry corpus under `tests/fixtures/`.
  - From BACKLOG M1.3. Paths in this example are illustrative; the real layout is decided in M1.1.
- **Acceptance:** `uv run pytest tests/test_corpus_load.py` passes: the three-entry fixture loads into three typed entries; a fixture with a misspelled field fails to load.
- **Out of scope:** building the real corpus (T4), distractors (T7–T8), cards (T10).
- **Depends on:** T1, T2.
```

## Procedure for the agent that writes a ticket file

Read `CLAUDE.md`, then `SPEC.md` in full, then this file, then the milestone's block in `docs/tasks/BACKLOG.md` (that block only). Then:

- Cut the tickets from the backlog block by the rules above. The dispatch prompt gives a target count; merge and split as the rules say, and keep the backlog ids in Detail.
- `SPEC.md` wins over `BACKLOG.md` wherever they differ. The dispatch prompt lists the known differences; look for others.
- Every ticket has every field. Out of scope is never empty; Depends on is "—" only when nothing comes before it.
- Acceptance is observable; model behaviour is verified with scripted outputs.
- Do not change `SPEC.md` or `BACKLOG.md`. If the spec is ambiguous or wrong, list it under `## Open questions for the author` at the end of the ticket file instead of deciding it yourself.
- Report back: the ticket count, the dependency order in one line, and the open questions.

The dispatch prompt from the author is one line plus four variables: the milestone, the target ticket count, the known `SPEC.md`/`BACKLOG.md` differences, and the files earlier milestones already produced. Example: "Write the tickets for M1 following docs/tasks/TEMPLATE.md. Aim for about 7 tickets. Known differences: none. Files from earlier milestones: none."

## Verification before the author reviews

A different session or subagent (Sonnet is enough) reads the ticket file, this file, the milestone's `BACKLOG.md` block, and the `SPEC.md` sections the tickets cite, then reports pass or fail per item:

- Every Depends on resolves to a ticket in the file or a finished milestone, and the graph has no cycle.
- Every Acceptance is observable: a command, a test, or a file property, not a judgement.
- Every backlog id in the milestone's block appears in at least one ticket's Detail; an id in two tickets is a split, and both tickets say so.
- The milestone's exit criterion is covered by the union of the Acceptances.
- Every cited rule id and section name exists in `SPEC.md`.
- No ticket does two things; every ticket has every field, Status set to todo; no Out of scope is empty.
- Detail does not restate `SPEC.md`; rules appear as ids.
