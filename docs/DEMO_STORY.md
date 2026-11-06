# Demo story — switch-world

**Thesis:** Four characters, one room, one human showrunner, and a world that records who believes what — a four-minute proof that the missing layer in AI characters is not another voice, but a small persistent cast that can address each other inside authored canon.

Target runtime: **4:00, hard stop.** The official page does not state a hard maximum; 4:00 is our safety cut. Everything below is written to be spoken, not read.

---

## At a glance

| Act | Time | Purpose |
| --- | --- | --- |
| **I — What we built** | 0:00–0:30 | Show the product in one breath: four characters, one room, a human showrunner, a world that records beliefs. |
| **II — Four features, one frame** | 0:30–2:00 | A 2×2 composite: Agent / Multi-agent / Scene next / Memory system. Each pane proves one mechanism in ~22 seconds. |
| **III — Architecture and Switch** | 2:00–3:00 | Switch vs MCP vs director vs model; the graph; the remove-Switch proof. |
| **IV — Why a game, not a business case** | 3:00–3:50 | The market gap, stated carefully: multi-agent as caller in a playable world. |
| **Close** | 3:50–4:00 | The scene card, the repo, the README, the paper/story ambition. |

---

## Act I — What we built (0:00–0:30)

**Screen.** `:8890` → **Story**, `w1-gift` loaded. The café/bookshop stage is up, the four cast cards sit below, the arc strip and the phone are visible but not touched.

**Shots.**

| Time | Shot |
| --- | --- |
| 0:00–0:08 | Hold the Story stage: four portraits, the current beat, the turn log. |
| 0:08–0:16 | Slow push across the four cast cards; hover the heart meters, do not click. |
| 0:16–0:24 | Cut to **Secret Ledger**: the belief matrix, one row expanded with source and confidence. |
| 0:24–0:30 | Title card: **switch-world**. |

**Narration.**

> Four characters — Alice, Emily, Sophia, Mia. One room. You are the showrunner, not a menu. And underneath the scene, a world that records what each of them believes: who told them, when, and how sure they are. They can talk to you, to the room, in a whisper only one of them hears, and — one hop — to each other.

**What the audience should feel.** This is not a chatbot with a skin. The interesting object is the ledger behind the scene.

---

## Act II — Four features, one frame (0:30–2:00)

**Production truth:** Act II is **four separate full-screen segments**, not a 2x2 composite. Each segment gets its own 22–23 seconds and its own UI surface. This is easier to read on video than four panes competing for attention, and it gives the World Tree room to breathe.

| Pane | Time | Exact action | Caption (≤10 words) | What it proves | Fallback |
| --- | --- | --- | --- | --- | --- |
| **A · AGENT** | 0:30–0:52 | `:8890` → **Story**; load `w7-last-call`, scene 1 `truck-dusk` (Mia only). Hold her CG and nameplate. Open the phone (Mia is already a friend in `w7`), type **“You're the only person I can say this to.”**, let the reply land. Close the phone; click Mia's cast card → **Profile**; hold the full-body portrait, quote, relationship bars, and the **4/5 hearts** meter. | “One agent, one voice, one private thread.” | Each character is a separately modeled agent with a persistent private voice and a portrait identity, not a mask on one shared prompt. At four hearts the contact contract is `limited`, not refused. | Pre-warm the DM. If the model misses, hold the profile sheet and a still of the reply. The phone keeps the user line visible while the reply is slow. Never wait more than 5 seconds. |
| **B · MULTI-AGENT** | 0:52–1:15 | `:8890` → **Story**; load `w1-gift` so all four are present. Type **“Mia, what do you think of it?”** Hold the turn log: the direction line reads **“Mia takes the lead · Alice reacts · Emily, Sophia stay quiet.”** Hold the dimmed silence rows. If a reply contains `@name`, hold the **“↳ reply to <name>”** note and the relayed reply. | “One room, not four chatbots: lead, reactor, silence.” | The director plans the room before any model call — one primary, one reactor, recorded silence — so it is a room, not four parallel chatbot replies. A mention, when it occurs, relays exactly one hop in public. | The plan and the silence rows are deterministic; hold there. For the relay, use a 6-second pre-recorded clip or a still of “↳ reply to”; if it is absent, drop the relay and say “one hop” over the plan. Do not retry live. |
| **C · SCENE NEXT** | 1:15–1:37 | `:8890` → **Worlds**; `w3-quiet-route` take pre-loaded, current take **“The Quiet Route”**, scene 1 of 2. Show the gate note **“Say a line or let a cue change the scene before advancing.”** → **Story**; click the choice **“That skirt in the window — the short one. It's you.”** (the cue matches `skirt\|friday\|wear\|dress`). → **Worlds**; click **Next scene** → **“Scene 2 of 2 loaded.”** Optional 2-second cut to Settings → **Canon & worldline**. | “Authored take, scene gate: only change moves the story.” | The story advances through an authored, linear take and a state-change gate, so canon cannot be skipped by prose. | No model dependency. If locked, click a cue-matching choice (`skirt` / `friday` / `wear`) then **Next scene**; if the API returns 409 `NOTHING_CHANGED`, Refresh in Worlds. Static: the take JSON plus the gate note. |
| **D · MEMORY + WORLD TREE** | 1:37–2:00 | `:8890` → **Worlds**; load `w5-good`. → **World Tree**; hold the `user` root, the four branches and the **1 / 4 know** secret plate. Click **Emily**; hold her belief **“The user is leaving the city” · 0.80 · alice · private** and her relationship bars. Click **Cast ↔ cast**; hold the character↔character graph (Alice–Emily strained, Emily–Sophia distant, Emily–Mia steady). Optional cut to **Secret Ledger** for the full matrix. | “Belief, source, relationship: the tree remembers.” | The World Tree is the readable social state: who is connected to whom, who holds the secret, and that Emily learned it **from Alice**, not from the narrator. It is provenance made spatial. | No model dependency. If the tree is slow, hold the same screen; `w5-good` seeds the Alice→Emily belief. Fallback: the Ledger matrix and Emily's belief row. |

### The agent-to-agent relay (confirmed in code)

The relay exists in `director/group.py`: the first planned speaker who names another **present** character with `@name` triggers **one** follow-up prompt to that character. The relayed reply is recorded as a normal beat with `↳ reply to <name>` in the turn log, and an `@` inside that reply is **not** relayed again. It is public scene delivery, not a private room or a whisper.

On camera it is model-triggered, not scripted. Say it only if it lands:

> “When a speaker names another, the room relays exactly one hop — public, never a chain.”

If no `@name` appears, do **not** wait or retry. Hold the deterministic plan and say the same line over it, then move on.

### Four full-screen segment spec

- **Master 3840×2160** (or 1920×1080 for review), 30 fps. One UI surface per segment; no split screen.
- **A · Agent:** the phone fills the right third; keep the scene stage visible on the left so the private thread is clearly *inside* the world.
- **B · Multi-agent:** the turn log is the hero; crop to the log column and keep the direction line, the silent portraits and the Mia/Alice exchange readable.
- **C · Scene next:** Worlds take card + gate note, then the scene that follows. Let the `Scene 2 of 2 is ready` state breathe for a beat.
- **D · Memory + World Tree:** the tree is the hero; the right panel carries Emily's belief source and the cast↔cast lens. No cursor wandering.
- **Labels:** each segment opens with a small `A · AGENT` / `B · MULTI-AGENT` / `C · SCENE NEXT` / `D · MEMORY + WORLD TREE` plate. The caption changes once per segment, not per line.
- **Audio:** one voice-over, no per-segment audio. 200ms caption fades.
- The four read in order as one system: **one voice → the room → the authored gate → the state that survives the scene.**

---

## Act III — Architecture and Switch (2:00–3:00)

**Screen.** `docs/architecture.png` full-bleed, then the Switch Console, the live `#world` room, and a terminal. Keep the graph on screen as the spine and cut away only to the evidence.

| Time | Shot | On-screen text |
| --- | --- | --- |
| 2:00–2:06 | `docs/architecture.png` full-bleed; all six bands visible | **One world. Six layers.** |
| 2:06–2:18 | Highlight band **3 · SWITCH** in `docs/architecture.mmd` / `architecture.png`; cut to **Switch Console → Sessions**, showing `alice`, `emily`, `sophia`, `mia`, `director` with **Show activity** open on one session | **Switch = rooms · agent identities · delivery · sessions · Console.** **It is not the world state.** |
| 2:18–2:30 | Highlight band **4 · WORLD ENGINE**; cut to Mattermost **`#world`** showing the director's addressed beat (`@alice It is 18:30 at the café…`) and Alice's reply | **MCP engine = scoped tokens · beliefs · provenance · relationships · scene card.** **Token → character; Alice cannot read Emily's private beliefs.** |
| 2:30–2:38 | Highlight **Director / DIR** in band 2; stay in `#world` on the chained turn (`@emily Alice says: “…”`) | **Director = plan · gate · ending · one-hop relay.** **Deterministic Python, no model session.** |
| 2:38–2:44 | Highlight band **5 · MODELS**: Bifrost → OpenCode shim → DeepSeek v4.1 Flash | **Bifrost routes. OpenCode is preferred; Claude Code is the live fallback.** **Low reasoning by default; high only for body/contact.** |
| 2:44–2:52 | Terminal: `docker compose down`; cut to a frozen `#world` where the director's next post fails; then the dashboard still rendering the last state | **Remove Switch: rooms, sessions, delivery, live beats stop.** **Remain: world DB, dashboard projection, phone DM, local beat runner, scene card.** |
| 2:52–3:00 | Open `docs/scene-card-example.md` (or the dashboard download) and scroll the provenance rows | **Scene card = summary · who knew what · from whom · confidence · relationship deltas.** |

**Voice-over (read across 2:00–2:52).**

> Six layers, one world. Switch is the transport: rooms, one identity per character, delivery, and a Console session you can inspect. It does not hold the world state. The MCP world engine holds the facts: beliefs, provenance, relationships, the scene card. Each character carries a scoped token, so Alice cannot read Emily's private beliefs — that is enforced at the API, not in the prompt. The director is deterministic Python: it plans the turn, gates the ending, relays one hop. It is not an LLM scheduler. The model only writes the sentence. Bifrost routes; OpenCode is the preferred connector, with Claude Code as the live fallback here. Now remove Switch. Rooms, sessions, delivery, live beats — gone. What remains: the world database, the dashboard projection, the phone DM, the local beat runner, and the scene card.

### Accuracy guards for this act

- Do **not** say Switch stores beliefs or relationships. It stores rooms, identities, sessions and delivery.
- Do **not** say OpenCode is the live connector without naming the Claude Code fallback. The configs are generated for OpenCode; the live cast runs on Claude Code while Console's OpenCode check is blocked.
- Do **not** call the director an LLM scheduler. It is a script that posts addressed turns; the model writes dialogue.
- The remove-Switch proof is honest: the dashboard still renders the **last recorded state**, because it is a projection. It does not keep acting.

---

## Act IV — Why a game, not a real business case (3:00–3:50)

**Screen.** A simple three-lane market-gap diagram, built once and held:

| Lane | What is crowded | Examples |
| --- | --- | --- |
| **1 · Character intelligence** | A character answers a player | [NVIDIA ACE](https://developer.nvidia.com/ace), [Convai](https://convai.com/), [Inworld](https://inworld.ai/) |
| **2 · Task automation** | Agents coordinate inside a workflow | [AutoGen](https://arxiv.org/abs/2308.08155), [CrewAI](https://www.crewai.com/), [LangGraph](https://www.langchain.com/langgraph) |
| **3 · Research simulation** | Societies of agents in a sandbox | [Generative Agents](https://arxiv.org/abs/2304.03442), [Project Sid](https://arxiv.org/abs/2411.00114) |
| **The open lane** | A small persistent cast that can **address each other** inside a playable world, with scoped identity, private memory and auditable provenance | no public product surface we checked documents the full combination |

**Hold the caveat on screen for the first two seconds:** *product-surface inference, not a measured market study.* [Hidden Door](https://hiddendoor.co/) is the closest commercial counterexample — persistent worlds, ensemble casts, relationships and canon — but its public page does not document agent-to-agent address or per-character private-state provenance.

**Three evidence bullets (show one at a time, 5 seconds each).**

- **They answer you.** ACE, Convai and Inworld ship character intelligence and voice for player-facing conversation. ACE also lists teams and populations, but as ambient behavior, not an auditable social-state contract.
- **They finish tasks.** AutoGen, CrewAI and LangGraph coordinate agents inside a workflow. The unit is a task; there is no world, no persistent identity and no social memory.
- **They simulate society, not ship a room.** Generative Agents (25 agents), Project Sid (10–1000+) and Hidden Door (ensemble worlds) prove the pieces. None documents scoped identity plus private memory plus agent-to-agent address plus provenance as one playable loop.

### 45-second closing narration

> Most AI NPC demos end the same way: one character, one player, one conversation. NVIDIA ACE, Convai and Inworld build characters answering a player. AutoGen, CrewAI and LangGraph automate tasks, not lives. The closest counterexamples are prototypes or story engines: Stanford's twenty-five generative agents, Altera's Minecraft society of up to a thousand agents, Hidden Door's ensemble worlds. We did not find one that documents the combination: a small cast that can address each other, hold private memories, and respect boundaries with provenance. That is the gap. We built it as a game because a game is the cheapest testbed — stakes, a room, a witness. A business case would turn the cast into a workflow; a game keeps the stakes and gives the research a story people can feel.

*123 words, about 164 wpm if read in 45 seconds; the SRT allocates this block 55 seconds, closer to 134 wpm. This is a tightened cut of the market brief; the claims are unchanged.*

### What we say — and what we do not

| Do not say | Say instead |
| --- | --- |
| “No one has built multi-agent AI NPCs.” | “We did not find this combination in the public product surfaces we checked.” |
| “The market is empty / a $X billion opportunity.” | “The category is thin.” The gap is a product-surface inference, not a forecast. No market-size statistic is used. |
| “ACE, Convai and Inworld are single-character only.” | “Their product surface is player-facing conversation; multi-character behavior is ambient or interrogative, not an auditable agent-to-agent social contract.” |
| “Our agents freely call each other.” | “Agents can address each other, one hop, through the director, in the public room.” |
| “First persistent memory / first provenance.” | “The combination: scoped identity, private beliefs, agent-to-agent address and provenance, applied to a playable social loop.” |
| “Hidden Door has no multi-agent state.” | “Hidden Door documents ensemble casts, relationships, rules and canon. We differentiate on agent-to-agent calls, per-character scoped identity and provenance.” |
| “This is peer-reviewed novelty.” | “A design probe and research vehicle.” SOTOPIA and Generative Agents already evaluate social agents. |
| “A real business case does not exist.” | “Business multi-agent automation is a real market. A business case would collapse the social cast into a workflow — that is the point, not that no one sells agents.” |

---

## Close (3:50–4:00)

**Screen.** The exported scene card (summary, who-knew-what, provenance, relationship deltas) next to the repo and the README's **MCP model** section. Hold the repo URL: <https://github.com/charlot3/switch-world>.

**Narration.**

> The artifact is a scene card: who knew what, from whom, with what confidence. Reproducible, MCP-first. The repo and README are the methods section — and the paper starts here.

**Ambition, stated carefully.** This is a research vehicle: a design probe for multi-agent social play, with an auditable artifact a paper can cite and a story an audience can feel. Do not claim peer-reviewed novelty until a literature review is done.

---

## Review cut

A silent 92-second, 1080p four-segment review cut lives at [`demo-review.mp4`](demo-review.mp4); its scope and review questions are in [`DEMO_REVIEW.md`](DEMO_REVIEW.md). It is a layout check, not the final 4:00 edit.

## Production notes

### What to show

- The dashboard at `:8890` only, at 110% zoom, 1440p or higher.
- Switch Console sessions, the bridged `#world` room, and one live agent reply.
- The architecture graph (`docs/architecture.png`) and, if time allows, the mermaid source.
- The scene card export and the README MCP section.
- The shelf fact in one line if you need it: **eight loadable worlds/takes**, including `w7-last-call`.
- Deterministic surfaces whenever a model is slow: the turn plan, the silence rows, the profile sheet, the gate note, the memory chain, the ledger.

### What not to show

- `.env`, API keys, `.switch/`, generated `opencode.json` / `.mcp.json`, admin pages, or the Mattermost System Console.
- The `:8892` rehearsal tab.
- Debug consoles, stack traces, or a model timeout. Cut to the authored fallback and keep going.
- Any claim that Switch holds beliefs, that the director is an LLM, or that the live model is OpenCode without the fallback caveat.

### Fallbacks, in priority order

1. **Pre-record the four-up.** Composite four 22–23-second clips; do not attempt four live panes on one engine.
2. **Pre-warm one DM and one group turn** so the first live call is not the first call.
3. **Hold deterministic evidence** if a model misses: turn plan, silence rows, profile sheet, gate note, memory chain, ledger.
4. **Keep a full rehearsal recording on disk** and cut to it for any beat that fails twice.
5. **If Switch is down before recording,** record the dashboard-only path and state the remove-Switch result as the honest consequence, not as a live failure.

### Voice-over recording notes

- One narrator, one bed. Record at a measured **150–165 wpm**; the closing can push to ~165.
- Leave 0.3 seconds of air before and after each act; the picture cuts carry the transitions.
- Pronounce the cast as **Alice, Emily, Sophia, Mia**; say “Switch” as the product, not “the switch.”
- Do not say “first,” “only,” “nobody,” or a market size. Those are the claims the market brief explicitly rules out.
- Record the narration against the final picture, not the script, so the SRT timings can be nudged to the actual read.
- No per-pane audio in the four-up; the composite carries one voice.

### SRT-ready narration block

Timestamps are approximate and should be nudged to the recorded read. One line per cue.
The same cues are saved as [`docs/DEMO_NARRATION.srt`](DEMO_NARRATION.srt).

```srt
1
00:00:00,000 --> 00:00:06,000
Four characters: Alice, Emily, Sophia, Mia.

2
00:00:06,000 --> 00:00:12,000
One room.

3
00:00:12,000 --> 00:00:19,000
You are the showrunner, not a menu.

4
00:00:19,000 --> 00:00:30,000
Underneath, a world records what each believes — who told them, when, how sure — and they can talk to you, to the room, in a whisper, one hop to each other.

5
00:00:30,000 --> 00:00:35,000
One agent: Mia.

6
00:00:35,000 --> 00:00:41,000
Her own session, her own voice, her own memory, her own portrait.

7
00:00:41,000 --> 00:00:46,000
A private thread the room never sees.

8
00:00:46,000 --> 00:00:52,000
Four of five hearts — and at that tier, contact is limited, not refused.

9
00:00:52,000 --> 00:00:56,000
One room, not four chatbots.

10
00:00:56,000 --> 00:01:04,000
Before any model call, the director plans: one lead, one reactor, the rest silent.

11
00:01:04,000 --> 00:01:12,000
A mention relays exactly one hop — in public, never a chain.

12
00:01:15,000 --> 00:01:21,000
The story is authored: two scenes, one gate.

13
00:01:21,000 --> 00:01:27,000
It opens only when a line or a cue changes the state.

14
00:01:27,000 --> 00:01:32,000
Prose cannot skip the canon.

15
00:01:37,000 --> 00:01:42,000
And the world tree remembers.

16
00:01:42,000 --> 00:01:48,000
Emily learned the secret from Alice: source alice, confidence 0.80.

17
00:01:48,000 --> 00:01:53,000
Not from the narrator — from a character who chose to tell her.

18
00:01:53,000 --> 00:02:00,000
Who is connected to whom, and who is holding the secret.

19
00:02:00,000 --> 00:02:06,000
One world, six layers.

20
00:02:06,000 --> 00:02:12,000
Switch is the transport: rooms, identities, delivery, sessions.

21
00:02:12,000 --> 00:02:18,000
It is not the world state.

22
00:02:18,000 --> 00:02:26,000
The MCP engine holds beliefs, provenance, relationships, the scene card.

23
00:02:26,000 --> 00:02:32,000
Each token maps to one character; Alice cannot read Emily's private beliefs.

24
00:02:32,000 --> 00:02:38,000
The director is deterministic Python: plan, gate, ending, one-hop relay.

25
00:02:38,000 --> 00:02:42,000
It is not an LLM scheduler.

26
00:02:42,000 --> 00:02:46,000
The model only writes the sentence.

27
00:02:46,000 --> 00:02:50,000
Bifrost routes; OpenCode is preferred, Claude Code is the live fallback.

28
00:02:50,000 --> 00:02:54,000
Remove Switch: rooms, sessions, delivery, live beats — gone.

29
00:02:54,000 --> 00:03:00,000
Remain: the world database, the projection, the phone, the scene card.

30
00:03:00,000 --> 00:03:04,000
Most AI NPC demos end the same way:

31
00:03:04,000 --> 00:03:08,000
one character, one player, one conversation.

32
00:03:08,000 --> 00:03:13,000
NVIDIA ACE, Convai and Inworld build characters answering a player.

33
00:03:13,000 --> 00:03:17,000
AutoGen, CrewAI and LangGraph automate tasks, not lives.

34
00:03:17,000 --> 00:03:22,000
The closest counterexamples are prototypes or story engines:

35
00:03:22,000 --> 00:03:26,000
Stanford's twenty-five generative agents,

36
00:03:26,000 --> 00:03:31,000
Altera's Minecraft society of up to a thousand agents,

37
00:03:31,000 --> 00:03:34,000
Hidden Door's ensemble worlds.

38
00:03:34,000 --> 00:03:38,000
We did not find one that documents the combination:

39
00:03:38,000 --> 00:03:42,000
a small cast that can address each other,

40
00:03:42,000 --> 00:03:45,000
hold private memories, respect boundaries — with provenance.

41
00:03:45,000 --> 00:03:47,000
That is the gap.

42
00:03:47,000 --> 00:03:50,000
We built it as a game: stakes, a room, a witness.

43
00:03:50,000 --> 00:03:55,000
A business case becomes a workflow; a game keeps the story people can feel.

44
00:03:55,000 --> 00:04:00,000
The scene card is the artifact — and the paper starts here.
```

*Cue 42–44 are intentionally tight; if the read runs long, extend into the 3:50–4:00 close, which carries only the scene-card and repo shot.*

---

## Sources

All sources below support the summaries in Act IV. Access dates are 2026-11-06 unless the source is a dated paper.

1. **NVIDIA ACE — official developer page.** <https://developer.nvidia.com/ace>. Character intelligence, speech and animation building blocks for in-game characters; lists teams and populations, but describes character intelligence rather than a persistent inter-agent social ledger.
2. **Convai — official site.** <https://convai.com/>. Conversational 3D AI characters; the documented loop is a character conversing with a user.
3. **Inworld — official site.** <https://inworld.ai/>. Realtime speech and hosted LLM inference for companions and agents; one conversational session, not a multi-character world model.
4. **Hidden Door — official site.** <https://hiddendoor.co/>. Persistent AI narrative worlds with a canon-tracking narrative world model, ensemble casts, relationships and rules. Closest commercial counterexample; the public page does not document agent-to-agent address or per-character private-state provenance.
5. **Generative Agents — Park et al., arXiv:2304.03442.** <https://arxiv.org/abs/2304.03442> (2023-04-07; rev. 2023-08-06). 25 LLM agents with memory, reflection, planning and emergent agent-to-agent social behavior; a research prototype.
6. **Project Sid — Altera, arXiv:2411.00114.** <https://arxiv.org/abs/2411.00114> (2024-10-31). 10–1000+ agents in Minecraft with emergent roles, shared rules and cultural transmission; a research simulation.
7. **AutoGen — Microsoft, arXiv:2308.08155.** <https://arxiv.org/abs/2308.08155> (2023-08-16; rev. 2023-10-03). A multi-agent conversation framework for task completion; the unit of work is a task, not a persistent social world.
8. **CrewAI — official site.** <https://www.crewai.com/>. Enterprise agent build and runtime for business processes; multi-agent automation, not social simulation.

**Also checked:** [LangGraph](https://www.langchain.com/langgraph) (stateful multi-agent orchestration for task automation); [SOTOPIA](https://arxiv.org/abs/2310.11667) (2023-10-18; research benchmark for multi-agent social interaction); [Whispers from the Star](https://store.steampowered.com/app/3730100) (released 2025-08-14; one stranded astronaut in real-time AI conversation); [Suck Up!](https://store.steampowered.com/app/2726370) (released 2025-10-01; player-facing deception with “real AI characters”); [Dead Meat](https://store.steampowered.com/app/2628740) (2026; interrogate an AI suspect cast); [AI People](https://www.goodai.com/ai-people/) (AI-native life sim; public page documents NPC planning, not multi-agent provenance); Ubisoft NEO NPCs / Teammates (2024 GDC prototype; 2025 follow-up described as an R&D experiment).

**Confidence.** Verified: the cited pages and papers support the summaries above. Inference: the combination is rare in the public product surfaces we checked; absence from those surfaces is not proof of absence. No market-size statistic is used.

---

## Repo grounding

Read-only reference for this script:

- `README.md`
- `docs/DEMO_TODAY.md`
- `docs/DEMO.md`
- `docs/ARCHITECTURE.md`
- `docs/SCENE_PROTOCOL.md`
- `docs/WORLDS.md`
- `world/takes/w3-quiet-route.json`
- `world/takes/w7-last-call.json`
- `world/scenarios/w1-gift.json`
- `director/group.py`
- `docs/architecture.mmd`
