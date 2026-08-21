---
name: ge-write-issue
description: "Use when AUTHORING a GitHub issue, comment, or report that a human will read — especially a non-technical stakeholder, a client, or someone outside the repo. Covers what goes in an issue versus a comment, how to layer detail so the reader can stop early, how to ask a question that actually gets answered, and how to assign it so someone is on the hook. Triggers on: 'open an issue for', 'post this to the issue', 'ask the client', 'report this back', 'write it up as an issue', 'file a question', 'let them know', or any request to communicate findings outward through GitHub. This is about WRITING issues; ge-analyze and ge-context are about WORKING ON issues that already exist."
---

# ge-write-issue: authoring issues people actually read

An issue you write for a stakeholder is not a note to yourself. It competes with their inbox,
and it is usually read on a phone, once, quickly. The reader decides in about two sentences
whether to keep going. Everything here follows from that.

The companion rule set for *where* things go — issues vs. comments vs. decision records —
is `misc/docs/github-surfaces-allocation-report.md`. This skill is about the writing.

## The shape

**Front-load the ask. Layer everything else.** The body has four zones, in this order:

1. **The ask, in one bold sentence**, phrased as the question or the action — not the topic.
2. **What to do about it**, in two or three lines. Options, if there are options. Say which one
   you prefer and why, in a clause, not a paragraph. People answer a recommendation faster than
   they answer a menu.
3. **`Blocks:`** — what stops until they reply. This is the line that turns a curiosity into an
   obligation. If nothing is blocked, say so plainly; a reader who discovers later that nothing
   was blocked stops trusting the line.
4. **Collapsed detail** — everything else, in `<details>` blocks.

A reader who stops after zone 1 must still know what is being asked. A reader who stops after
zone 3 must be able to act.

## Layer with `<details>`, not with comments

```markdown
<details>
<summary>Why we're asking</summary>

The reasoning, the history, the thing they told us that we're building on.
</details>

<details>
<summary>What we measured</summary>

The numbers, the field names, the code. Name the snapshot or the version for every figure.
</details>
```

**Why `<details>` and not detail-in-comments-linked-by-permalink:**

- **The body is what gets retrieved.** A semantic search, an agent reading the issue, and the
  GitHub list view all surface the *body*. Detail parked in comments is one click further away
  from every future reader, including your own next session.
- **One notification, not five.** Each comment pings every subscriber. A stakeholder who gets
  five notifications for one question learns to mute the repo.
- **No bookkeeping.** The comments-plus-permalinks pattern needs the body edited after each
  comment to carry the links, and the links break nothing but rot quietly when a comment is
  edited or deleted.
- **It degrades gracefully.** Email clients ignore the toggle and render `<details>` expanded,
  which is exactly the fallback you want: worst case, they see everything in order.

Give each `<summary>` a name that says what is inside, so the reader can choose. `Why we're
asking`, `What we measured`, `The technical bit`, `If you want to trim the list`. Never
`More info` or `Details` — an unlabelled fold is a fold nobody opens.

**Comments keep one job: new evidence after the fact.** Narrowing a question, reporting what
you found, recording their answer. When a comment settles something, edit the settled version
back into the body — the body is the artifact, the thread is the history.

## Asking a question that gets answered

- **One question per issue.** A batched issue gets one answer and stalls on the rest. This is
  the single most common failure and it is not recoverable after the fact — you cannot split a
  half-answered issue without losing the thread.
- **Title it as the question**, not the subject area. `Q7 — What does Status actually govern?`
  beats `Status field`. Titles are read in a list, out of context.
- **Assign it to the person who can answer.** Assignment is the only mechanism that both
  notifies a named person and leaves a queryable record that they owe a reply. Labels notify
  nobody.
- **`@mention` them in the body too** if they are not a frequent GitHub user. Assignment is
  quiet.
- **Read the assignee back.** A successful API call is not proof the assignment took.
- **Say what it costs to guess wrong.** Not "we'd like to know" — "if we guess wrong here, the
  number we publish is measuring your software rather than your data."
- **Offer a cheap answer.** "A rough answer is fine — *X is meaningless, the rest are real*
  would be enough to work from." Lowering the bar to reply is worth more than any amount of
  additional justification.
- **Create the real dependency edge**, not just the `Blocks:` prose. Prose is not queryable.

  ```bash
  qid=$(gh api repos/OWNER/REPO/issues/<question> --jq .id)
  gh api -X POST repos/OWNER/REPO/issues/<blocked>/dependencies/blocked_by -F issue_id=$qid
  ```

## Tone for someone outside the team

- **Informal, concrete, no hedging.** "Either one unblocks us" beats "it would be beneficial if
  one of these could potentially be actioned."
- **Credit them when you are building on something they told you.** It shows the last answer
  was used, which is most of why anyone answers the next one.
- **Never make them feel tested.** Do not pre-fill an answer for them to confirm — a
  pre-filled cell gets confirmed by silence and comes back carrying their name on a judgement
  you made.
- **Never paste a wall of field names in the open body.** Fold it, and say how many there are.
- **Quote your own past mistake when it explains the ask.** "You corrected us on exactly this
  in August" earns more trust than any assurance about rigour.

## Before posting

- Every figure names its snapshot, version, or date. A number without one is not checkable.
- No absolute local paths, hostnames, machine names, tokens, or personal email addresses.
  Issues outlive the context that made them safe.
- Read it as the recipient: stop after two sentences and ask whether you would know what to do.
- If it is going to a client, **show it to the user before posting** unless they have said
  otherwise for this batch.

## Reporting findings back (not a question)

Same shape, minus the assignment. Lead with the conclusion, fold the evidence, and say what
changed as a result. A report that does not say what it changes is a status update, and status
updates are what people stop reading first.
