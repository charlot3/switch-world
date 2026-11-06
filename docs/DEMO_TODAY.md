# Today's recording plan — Flip the Switch

Open [`demo-links.html`](../demo-links.html) in Chrome first: it has every URL below, a
4:00 take timer, the pre-flight checklist and the architecture plate. The four-act narrative
and the voice-over cues are in [`DEMO_STORY.md`](DEMO_STORY.md) and
[`DEMO_NARRATION.srt`](DEMO_NARRATION.srt).

Goal: one **4:00** submission video that proves Switch is the world, the group is not four
chatbots, the 4-heart contract belongs to the most enthusiastic character, and the artifact
persists.

Record the Flip cut first. The Geek Room Bifrost/Tavily cut is a separate, shorter video;
do not mix it into this one.

## URLs

| What | URL |
| --- | --- |
| Final dashboard / world engine | <http://127.0.0.1:8890> |
| Rehearsal dashboard (separate DB) | <http://127.0.0.1:8892> |
| Switch Console | the Electron app |
| `#world` | <http://127.0.0.1:8065/switch/channels/world> |
| Architecture graph | Studio → Architecture, or `docs/architecture.png` |

Use **8890** for the final take. Use **8892** only for rehearsal. Both can reach the same
Switch `#world`, so do not send from both at the same time.

## Pre-flight (5 minutes before recording)

- [ ] `8890` answers: `curl -s http://127.0.0.1:8890/api/state`.
- [ ] Switch API `:8000`, gateway `:3000`, Mattermost `:8065` are healthy.
- [ ] Switch Console shows five sessions: `alice`, `emily`, `sophia`, `mia`, `director`.
- [ ] `#world` has the user and the four character agents; the director is a member.
- [ ] Bifrost `:8080` and the OpenCode adapter `:8090` answer (`/health`).
- [ ] One warm-up line in `#world` has produced an agent reply in the last few minutes.
- [ ] Screen recording is 1440p+, notifications off, browser zoom 110%.
- [ ] Fallback: the best previous rehearsal clip is on disk.

## Test pass — do this before recording

1. **Worlds shelf**: load `w1-gift`, `w7-last-call`, `w5-good`, `w5-bad` once each. All must
   show a scene card and art, with no 500.
2. **Live Switch reply**: on `w1-gift`, send “I brought you something.” Alice must answer
   through the live room, not the authored fallback.
3. **Group staging**: advance `w1-gift` to the café and ask “Mia, what do you think of it?”
   The feed should show a primary, a reactor and at least one silence beat.
4. **Whisper**: tick the whisper box, target Alice, send a private line. Only Alice answers;
   one or two observers react publicly without repeating the words.
5. **4-heart showcase**: load `w7-last-call`; the heart meter must show **4/5**. Send
   “I want to hug you right here.” The verdict must be `limited` (warm, not a refusal).
6. **Endings**: load `w5-good`, choose “I'm staying.”, advance; the good ending card appears.
   Load `w5-bad`, choose the Emily line, advance; the bad ending card appears with evidence.
7. **Artifact**: Settings → Scene card → **Load**, then **Download .md**.
8. **Reset**: load `w1-gift` again and confirm the world is clean before the real take.

## The 4:00 cut

| Time | Where | Action | What must be visible |
| --- | --- | --- | --- |
| 0:00–0:20 | Switch Console | Show the five sessions and `#world`; cut to a live agent line. | Four character agents + director are separate sessions in one room. |
| 0:20–1:10 | `w1-gift` | “I brought you something.” → advance to the café → “Mia, what do you think of it?” | The gift becomes a belief; Alice is primary, Emily reacts, Mia is a recorded silence; open the belief/provenance panel. |
| 1:10–1:35 | `w1-gift` café | Whisper to Alice: “I've decided to leave the city. Don't tell the others yet.” | Only Alice hears it; Emily/Sophia react to the fact that something happened, not the words. |
| 1:35–2:35 | `w7-last-call` | 4/5 hearts. “Save me the crispy bits.” → “I want to hug you right here.” → advance → “I like this version of you.” | Mia is openly eager, then quiet and honest; the contact verdict is `limited`, not refused. |
| 2:35–3:15 | `w5-good` → `w5-bad` | Choose the stay line, advance for the good card; reload, choose the Emily line, advance for the bad card. | Same setup, opposite ending; the evidence list and belief matrix explain why. |
| 3:15–3:35 | Settings | Scene card → Load → Download; show the provenance chain. | The human+agent task produced an artifact, not just a chat log. |
| 3:35–3:50 | Studio / README | Show the architecture graph: dashboard → Switch → agents → MCP → SQLite, with Bifrost/Tavily on the side. | Switch is the transport; the MCP world engine is the only write path. |
| 3:50–4:00 | Repo / README | Close on the public repo and the MCP model section. | The reviewer can reproduce it. |

## Voice-over spine

- “These are four separate Switch agents and a director in one live room. The dashboard is
  a projection; Switch is the world.”
- “The gift is not a prompt detail. It is a belief, written through a scoped MCP token, and
  the room answers as a room: one primary, one reactor, one silence.”
- “A whisper reaches one person. The room sees the pause, not the words.”
- *(Optional, only if it happens on camera)* “Characters can @ each other too; the director
  relays one reply, then stops — a single hop, still in the public room.”
- “At four hearts the contract changes: contact is not refused, but she still sets the
  limit. Mia is the most openly enthusiastic of the four, so her four-heart route is eager
  first and honest second.”
- “The model writes the sentence. The ledger chooses the ending.”
- “Remove Switch and there is no transport, no rooms and no sessions; the dashboard still
  shows the last state.”

## Do not show

- `.env`, API keys, `.switch/`, generated `opencode.json` / `.mcp.json`, or admin pages.
- The 8892 rehearsal tab.
- Debug consoles, stack traces, or a model timeout. Cut to the authored fallback and keep
  going.

## After recording

- [ ] Watch the clip once at 1× for audio and cursor mistakes.
- [ ] Confirm no secrets or private windows are visible.
- [ ] Save the clip and the scene-card `.md` next to it.
- [ ] Reset `8890` to `w1-gift` for the next rehearsal.
