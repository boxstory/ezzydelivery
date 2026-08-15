---
name: llm-council
description: Convene a council of independent adversarial reviewers to validate claims, audit a module, or stress-test a plan before acting on it. Each member gets one lens and is told to REFUTE by default; a synthesis pass dedupes and ranks. Use when a set of findings/claims needs verification (especially your own — self-review is biased), when a module needs a broad multi-angle audit, or when the user asks for a "council", "panel", "second opinion", "validate these", "stress-test this", or a multi-agent review. Runs via the Workflow tool, so it needs the user to have asked for it.
user-invocable: true
argument-hint: "[claims to validate | module to audit | plan to stress-test]"
---

# LLM Council

A council is **N independent reviewers, one lens each, defaulting to REFUTED**, followed by a
synthesis pass that dedupes and ranks. It exists because a single reviewer — especially the author —
confirms their own findings. The adversarial default is the whole point: a claim that survives three
agents trying to kill it is worth acting on; one that nobody challenged is not.

Implement it with the **Workflow** tool. Workflow requires explicit user opt-in; invoking this skill
counts as that opt-in.

## When to convene one

| Situation | Council shape |
|---|---|
| Validate a list of claims/findings | One refuter per claim + 2-3 sweeps for what was missed |
| Audit a module | 5 lenses (correctness, security, data integrity, ops/UX, performance) + verify pass |
| Stress-test a plan before building | 3-4 approaches generated independently, judged, best synthesised |
| Verify one high-stakes claim | 3 refuters on the same claim, majority rules |

Don't convene one for a question a single grep answers.

## Ground rules block — always include this

Every member gets the same preamble. On this box the read-only rules are not optional:

```
## HARD RULES — violating these breaks the user's production system
- READ-ONLY. Do NOT edit, create or delete any file. Do NOT reload gunicorn. Do NOT run collectstatic.
- **Never run `manage.py test`.** All sessions share ONE test database; a concurrent run deadlocks
  unrelated test classes and corrupts --keepdb. Other agents run alongside you right now.
- Do NOT run `manage.py migrate` or `makemigrations`. The default DB is PRODUCTION.
- Read-only introspection is encouraged: `source /home/ezzyadmin/ezdlproject/venvezzy/bin/activate`
  then `python -c "..."` with django.setup(), or `manage.py shell -c`. SELECTs only.
```

Then add an **architecture facts** section so members don't waste turns rediscovering things
(tenant model, gating middleware, which fields are money, what runs on cron vs Celery). Pull these
from `CLAUDE.md` and the memory directory. A council that spends its budget relearning the codebase
returns shallow findings.

## The refutation instruction

This is the load-bearing sentence. Use it verbatim:

> Your default answer is REFUTED. Only mark a claim CONFIRMED if you personally read the code (or ran
> read-only introspection) and the failure scenario genuinely holds. Cite exact file:line and the
> output you actually read. Do not speculate.

Then enumerate the specific ways *this kind* of claim is usually wrong — it gives the refuter
somewhere to dig:

- the endpoint isn't actually reachable or writable
- a permission class / `perform_create` override already neutralises it
- the field is read-only, `auto_now`, or overwritten by a signal immediately after
- the "vulnerable" path is dead code
- the pattern only appears in static markup with no attacker-controlled data
- a raw count was quoted where only a handful of instances carry untrusted data

## Structured verdicts

Force a schema so the synthesis step gets data, not prose. Minimum fields:

```js
{ claim_id, verdict: 'CONFIRMED'|'PARTLY_CONFIRMED'|'REFUTED',
  severity: 'critical'|'high'|'medium'|'low'|'none',
  reasoning, evidence /* file:line + what was actually read */,
  failure_scenario /* concrete inputs -> wrong outcome, or why none exists */,
  corrections /* where the claim was overstated */, recommended_fix }
```

`corrections` matters as much as `verdict` — most claims are directionally right but wrong about
scope or severity, and that nuance is what the user needs.

## Shape

`parallel()` for the members (they're independent), a barrier before synthesis (the chair genuinely
needs every verdict at once to dedupe), then one chair agent. Keep it under ~15 agents unless the
user asks for more.

```js
phase('Adjudicate')
const verdicts = await parallel(CLAIMS.map(c => () =>
  agent(`${GROUND_RULES}\n\n${c.claim}`, { label: `refute:${c.label}`, schema: VERDICT_SCHEMA })))

phase('Sweep')   // what did the original pass miss entirely?
const sweeps = await parallel(LENSES.map(l => () =>
  agent(`${GROUND_RULES}\n\n${l.prompt}`, { label: l.label, schema: FINDINGS_SCHEMA })))

phase('Synthesise')
const report = await agent(`You are the council chair...\n${JSON.stringify(verdicts)}`)
```

Always pair the refuters with **sweep lenses**, or the council only ever grades the homework it was
handed. The three that consistently earn their keep:

1. **missed-surfaces** — what input/output paths did the original scope exclude? (admin, management
   commands, cron kwargs, webhooks, AI-agent tool args, template tags, open redirects)
2. **fix-quality** — assume the fixes are subtly wrong and prove it. **Regressions outrank
   theoretical weaknesses**; a validator that rejects existing valid data is worse than the hole it
   closed.
3. **adjacent-class** — the thing the audit may have given false confidence about (authz and tenant
   isolation, when the audit was about injection).

## Chair instructions

Tell the chair to be blunt: which claims did not survive, corrected severities, dedupe across sweeps,
drop anything the evidence doesn't support, and surface regressions above everything. Ask for prose —
the chair's job is judgement, and a schema flattens it.

## Reporting back

Lead with what was **refuted or downgraded**, not what was confirmed — that's the information the
user doesn't already have. Give the corrected severity table, then the prioritised fix list including
an explicit "don't bother with" line. Never present a council verdict as more certain than its
evidence: if a member marked something PARTLY_CONFIRMED, say so.
