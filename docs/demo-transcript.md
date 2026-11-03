# Demo transcript

**Status:** not recorded yet. Fill this in during the Day 3 rehearsal, then commit it. The
demo video should match this transcript; if a live model call fails on camera, cut to the
recorded rehearsal for that beat.

## Format

```
# Rehearsal — <date/time JST>
# Model/provider: OpenCode · <model>
# World engine: <commit>

## 0:00 Switch Console
- server: <status>
- agents: alice (OpenCode), emily (OpenCode), sophia (OpenCode), mia (OpenCode), director
- rooms: #world, DM-alice, DM-emily, DM-sophia, DM-mia

## 0:30 DM Alice
user: I've decided to leave the city at the end of the month. I haven't told the others yet.
alice: <reply>
world: belief user-leaving-city · holder alice · source user · confidence 1.00 · private

## 1:30 #world café beat
director: @alice It is 18:30 at the café. Emily is here. You have something on your mind.
alice: <reply>
director: @emily Alice says: "<alice's line>" — how do you respond?
emily: <reply>
world: belief user-leaving-city · holder emily · source character:alice · confidence 0.80 · shared
world: relationship emily→alice trust -0.10 · reason "heard second-hand"
world: relationship emily→user trust -0.05 · reason "told Alice first"
world: event disclosure · participants alice, emily · public

## 3:00 Dashboard
- matrix: alice 1.00 (user), emily 0.80 (alice), sophia —, mia —
- provenance: user → alice (18:32) → emily (18:36)
- edges: emily→alice 0.75, emily→user 0.40

## 3:30 DM Emily
user: Hey, are you around?
emily: <reply referencing the belief and the changed view>

## 4:00 Scene card
- data/exports/scene-card-<date>.md
- summary, beliefs, provenance, deltas, transcript links

## 4:30 Remove Switch
- docker compose down
- director post fails; no session starts; dashboard still renders
- docker compose --profile collab --profile gateway up -d
- refresh dashboard: belief and deltas persist

## Notes
- beats that failed:
- prompts that needed a retry:
- what to cut if time is short:
```
