# Reference notes — dsh-adult-tension

We reviewed `daha1216/dsh-adult-tension` for **interaction and runtime engineering**, not
content. That project is an adult-only text runtime; this project remains SFW 17+, adults,
and fully clothed. No explicit content, world files or prose were copied.

## What we adopted

- **Generation vs. state split**: the model writes prose; code owns the clock, facts,
  relationships, promises, scene order and ending evidence. Our take/scenario layer already
  follows this; the take protocol makes it explicit.
- **Idempotency and revision**: a write carries `request_id`; a retry returns the original
  response; `expected_revision` prevents double advances. We add this to group turns and
  take/scene advance.
- **Bounded context**: projections cap the prompt (the reference uses 20 KB). We add one
  projection with a ~12 KB cap, trimming old DMs/scene lines before memory.
- **NPC goals and limits**: NPCs have goals, fears and boundaries, and respond on a
  spectrum (refuse, negotiate, limited, surface, sincere) rather than unconditional
  compliance. We add the spectrum as a `response` field while keeping the topic gate.
- **Attempt vs. result**: actions on an NPC are attempts; player-owned speech/body/items
  are results. This prevents "I kiss her" from being treated as a success.
- **Each scene advances something**: a continue/next step must change at least one fact or
  event, or it is refused. We implement this as the take `must_change` invariant.
- **Off-screen time**: fast-forward can mature a promise or move an absent character
  without a model call. We add a single deterministic `offscreen` event on clock advance.
- **Safety is engine-enforced**: a pause/boundary is a runtime flag, not a prompt request.
  We add a paused state that refuses new scene/DM writes with a neutral message.
- **Content validation**: a schema/validator gate before a world is playable. We add
  `scripts/validate-takes.py`.
- **Status HUD**: time, location and turn number are visible at a glance.

## What we did not adopt

- Adult content, explicit scene contracts, age/safety rules for explicit intimacy, or any
  world/NPC prose from the repository.
- The full six-layer runtime, CLI envelope, OS-specific data directories, multi-session
  saves/import/export, and the 211-world content pipeline. Those are larger than the Flip
  demo and would delay the video.
- The reference's explicit intimacy machinery is out of scope; our boundary work is
  refusal/consequence only.

## Why it matters for the demo

The take layer gives the video a deterministic score; the model still improvises each
line. Idempotency/revision and fallback lines make recording reliable. The response
spectrum and attempt/result split make the social behaviour believable. The validation
and status HUD make the system legible to a judge.
