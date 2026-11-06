# Demo review cut — 92 seconds, 1080p, four segments

**File:** `docs/demo-review.mp4` · 1920×1080 · 91.6 s · H.264, silent.

This is a **review cut**, not the final 4:00 submission. It shows the four feature segments
as separate full-screen pieces, with the World Tree as the fourth segment.

## What is in it

| Time | Shot | Purpose |
| --- | --- | --- |
| 0:00–0:05 | Title card | Switch World / review cut |
| 0:05–0:14 | Switch web Console → Agents and Rooms | Five sessions, one `world` room |
| 0:14–0:20 | Mattermost `#world` excerpt | Four character replies in the live room |
| 0:20–0:38 | **A · Agent** — Mia phone | One agent, one private thread |
| 0:38–0:56 | **B · Multi-agent** — `w1-gift` café | Mia speaks in first person; Alice reacts; Emily/Sophia silent |
| 0:56–1:05 | **C · Scene next** — `w3` | Authored gate, scene 2, the burgundy-skirt outfit |
| 1:05–1:18 | **D · Memory + World Tree** — `w5-good` | Emily learned the secret **from Alice**; cast↔cast lens |
| 1:18–1:26 | Architecture panel | Switch = transport, MCP = state, remove-Switch |
| 1:26–1:32 | Closing title | Scene card + multi-agent as caller |

## Message pass

- Mia's phone opening is now **“You're late. Sit — I saved you the crispy bits.”**
- Mia DM: **“You're the only person I can say this to.”** Her reply stays first-person and
  drops the stage inventory: **“That's a lot to hand me, but okay. It's just me and a pot of
  coffee back here, so take your time.”**
- Group B: **“Mia, what do you think of it?”** Mia answers the user in first person; Alice
  reacts; Emily and Sophia are recorded silence. The old third-person “She turned the sign
  early…” line is gone.
- World Tree D: Emily's belief reads **“The user is leaving the city · 0.80 · alice ·
  private”**, so the tree shows that she learned it from Alice, not from the narrator.

## What this cut deliberately does not do

- No voice-over and no burned subtitles. The final narration is in
  [`DEMO_NARRATION.srt`](DEMO_NARRATION.srt); the script is in [`DEMO_STORY.md`](DEMO_STORY.md).
- It is 92 s, not 4:00. The final edit gives each feature segment its 22–23 s and the
  architecture/thesis acts their full time.
- The Mattermost panel is a **clean rendered excerpt** of captured `#world` messages, not a
  literal screen capture. The live channel also contains internal director prompts; those
  should not be shown. For the final take, use a fresh room or capture a clean turn.
- The live agent-to-agent `@` relay is not shown here. It is model-triggered and did not land
  in the recorded group turn; the feature is covered by tests and can be shown live if it
  happens.
- `w7` and `w3` are recorded on the rehearsal engine (`:8892`) so a pending group turn cannot
  write into their take. The final cut can use the same isolation.

## Questions for this review

1. Do the four full-screen segments read better than the 2×2 grid?
2. Is the World Tree segment strong enough, or should it get its own Act?
3. Is the B-pane Mia reply the right register for her persona?
4. Does the Switch Console + Mattermost pair prove “five sessions, one room” fast enough?
5. What should be longer: A, B, C, or D?

## Merging the voice track later

```sh
ffmpeg -i docs/demo-review.mp4 -i voice.wav \
  -c:v copy -c:a aac -b:a 192k -shortest \
  -movflags +faststart docs/demo-with-voice.mp4
```

The final 4:00 cut will be assembled from the same pieces with the SRT timings nudged to
the recorded read.

## Final picture cuts

- `docs/demo-final-silent.mp4` — 1920×1080, 4:00, silent. The cut to improvise over.
- `docs/demo-submit-3min-ai.mp4` — 1920×1080, 2:50.7, chiaki AI narration + burned English captions. This is the submission-length cut.
- `docs/chiaki-demo-narration.wav` — the standalone AI narration.
- `docs/demo-final-with-setsuna.mp4` — 4:08, canonical **E** take: post-credit setsuna Japanese voice + English subtitle: 「火曜日の夕方、いつもの場所で待ってるね。あったかいクッキーも焼いておくから。」 / “I’ll be at our usual place Tuesday evening. I’ll bake warm cookies too.”
- `docs/demo-final-silent-alt.mp4` — the same E cut under the older name.
- `docs/setsuna-alt-line.wav` / `.mp4` — the standalone E line, if it belongs somewhere else in a reaction edit.
