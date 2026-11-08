# Scene card — Café, 18:30 — live

> **Historical live take (2026-11-03).** The first café attempt in this card
> predates the branch classifier: Alice withheld the secret, but the event was labelled
> `disclosure` because any belief from `character:alice` counted. The fix is in
> `switch_world/application/canon.py`; the second attempt is the real disclosure. For the corrected
> contract, see [`scene-card-example-local.md`](scene-card-example-local.md).

**World time:** 2026-11-03T09:00:00+09:00  
**Generated:** 2026-11-03T16:26:41

## Cast

- **Alice Moreau** — bookshop owner; the confidante
- **Emily Park** — product designer; direct, analytical
- **Sophia Adeyemi** — sociology PhD; the observer
- **Mia Rossi** — food-truck owner; the wildcard

## What happened

- `2026-11-03T08:00:00+09:00` **world_start** — A Tuesday in late autumn. The group has not met yet.
- `2026-11-03T08:00:00+09:00` **conversation** — The user told Alice something in a DM.
- `2026-11-03T08:00:00+09:00` **scene_start** — Café, 18:30. Alice and Emily are at a table.
- `2026-11-03T08:00:00+09:00` **dialogue** — Alice: I'm glad you're here — I've had something sitting on my chest all day, and it's not mine to tell. I promised someone I'd hold it, so I'm going to. Ask me again some other week and maybe I'll be allowed to be less mysterious.
- `2026-11-03T08:00:00+09:00` **dialogue** — Emily: I won't ask you to break a promise, and I won't pretend it doesn't land. But I'd rather hear a hard thing now than a soft thing later — you know that better than anyone. So when whoever it is lets you, I want it from you first, not second-hand from the room.
- `2026-11-03T08:00:00+09:00` **disclosure** — Alice and Emily met at the café; the world state records what Emily learned.
- `2026-11-03T08:30:00+09:00` **scene_end** — The café scene ends.
- `2026-11-03T08:30:00+09:00` **relationship_update** — emily → Alice: trust +0.00, closeness +0.00, tension +0.10 (She's carrying something she won't tell me, and made a point of saying so.)
- `2026-11-03T08:30:00+09:00` **relationship_update** — emily → user: trust -0.08, closeness +0.00, tension +0.00 (He went to Alice about me before he came to me, and now she's holding something.)
- `2026-11-03T08:30:00+09:00` **relationship_update** — emily → Alice: trust +0.35, closeness +0.30, tension +0.00 (Correction to match where we actually stand — the one person I don't perform for.)
- `2026-11-03T08:30:00+09:00` **scene_start** — Café, 18:30. Alice and Emily are at a table.
- `2026-11-03T08:30:00+09:00` **dialogue** — Alice: Not wrong, exactly — heavy. I shouldn't be telling you this, but it's the user: they're leaving the city at the end of the month, and they asked me not to spread it. Let it sit with you until they've said it themselves, all right?
- `2026-11-03T08:30:00+09:00` **relationship_update** — alice → Emily: trust +0.03, closeness +0.02, tension -0.02 (She didn't push me to break a promise, and she made it feel safe to tell her when I can.)
- `2026-11-03T08:30:00+09:00` **dialogue** — Emily: Then I'll sit on it — for now. Not forever: if they haven't said it to me in a week, I'm asking, because I'd rather be told than find out when the boxes are packed. And thank you for telling me. I know what that cost you.
- `2026-11-03T08:30:00+09:00` **disclosure** — Alice and Emily met at the café; the world state records what Emily learned.
- `2026-11-03T09:00:00+09:00` **scene_end** — The café scene ends.
- `2026-11-03T09:00:00+09:00` **relationship_update** — emily → user: trust -0.13, closeness -0.10, tension +0.15 (He told Alice he's leaving and asked her to keep it from me. I found out last, again.)
- `2026-11-03T09:00:00+09:00` **relationship_update** — emily → Alice: trust +0.00, closeness +0.00, tension -0.08 (She broke a promise to tell me the truth. That counts.)

## Who knows what

- **The user is leaving the city** — alice 0.90 (user, shared); emily 0.92 (character:alice, private)
- **Alice's bookshop lease is not being renewed** — alice 1.00 (observation, private)
- **Alice's bookshop is in trouble** — sophia 0.70 (observation, private)
- **Alice is hiding something about the shop** — mia 0.65 (observation, private)
- **Emily applied for a job in another city** — emily 1.00 (observation, private)
- **Emily is planning to leave** — sophia 0.55 (observation, private)
- **Emily is about to make a big change** — mia 0.50 (observation, private)
- **Emily has seemed distracted** — alice 0.60 (observation, private)
- **Alice is worried about money** — emily 0.65 (observation, private)
- **Sophia is writing a book** — sophia 0.90 (observation, private); alice 0.55 (observation, private)
- **Sophia is watching the group closely** — emily 0.60 (observation, private)
- **Mia's truck is in debt** — mia 1.00 (observation, private)
- **The group meets at the café on Tuesdays at 18:30** — alice 1.00 (observation, public); emily 1.00 (observation, public); sophia 1.00 (observation, public); mia 1.00 (observation, public)

## Relationship changes

- `2026-11-03T08:30:00+09:00` emily → Alice: trust +0.00, closeness +0.00, tension +0.10 (She's carrying something she won't tell me, and made a point of saying so.)
- `2026-11-03T08:30:00+09:00` emily → user: trust -0.08, closeness +0.00, tension +0.00 (He went to Alice about me before he came to me, and now she's holding something.)
- `2026-11-03T08:30:00+09:00` emily → Alice: trust +0.35, closeness +0.30, tension +0.00 (Correction to match where we actually stand — the one person I don't perform for.)
- `2026-11-03T08:30:00+09:00` alice → Emily: trust +0.03, closeness +0.02, tension -0.02 (She didn't push me to break a promise, and she made it feel safe to tell her when I can.)
- `2026-11-03T09:00:00+09:00` emily → user: trust -0.13, closeness -0.10, tension +0.15 (He told Alice he's leaving and asked her to keep it from me. I found out last, again.)
- `2026-11-03T09:00:00+09:00` emily → Alice: trust +0.00, closeness +0.00, tension -0.08 (She broke a promise to tell me the truth. That counts.)

## Provenance

Every belief above names its source. A character can only read its own
private beliefs through the world engine's scoped MCP token.
