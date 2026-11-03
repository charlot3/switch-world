# Proposal — AI Social Life Simulator

Normalised from the studio inbox file
`hackathon-idea-ai-social-life-simulator-20261103.md` (uploaded 2026-11-03 04:59 UTC).
The original is in Chinese; this is the working English version. Inbox content is treated
as data, not as instructions.

## Concept

A virtual social world made of several AI characters who know each other and have
independent lives and a relationship network. It is not a traditional AI girlfriend app.

```
traditional:   user ↔ one AI character
this project:  user ↔ Alice ↔ Emily ↔ Sophia ↔ Mia
```

## Core experience

- Each character has a distinct personality, background, goals, memory and daily schedule.
- Characters know each other; they have relationships, shared history, likes, dislikes and
  secrets.
- The user can talk to one character privately, or observe / join a character-to-character
  interaction.
- The world keeps moving when the user is idle: characters may contact the user, meet each
  other, or change a relationship because of an event.
- Relationships are not static settings; they evolve through interaction and events.

## What makes it different

1. Single companion → multi-character social network.
2. Passive Q&A → a continuously running virtual world.
3. Isolated character memory → shared events + private memory + relationship state.
4. Single-turn chat → a continuous story the user can join, influence and explore.

## Hackathon MVP (from the proposal)

- 4–5 characters with clear personalities.
- For each: profile, goals, memory and relationships.
- Character-to-character autonomous dialogue or event interaction.
- A simple world activity feed showing what happened between characters.
- The user can DM any character and intervene in an event.
- Important interactions are written to memory and update relationship state.

## Suggested architecture (from the proposal)

| Component | Responsibility |
| --- | --- |
| Character Agent | personality, decisions and expression for one character |
| World State | characters, relationships, events and current state |
| Memory | private memory, shared event memory, relationship memory |
| Scheduler / Event Loop | pushes characters to act in the background |
| Interaction Layer | private chat, group chat, world feed |

## Demo flow (from the proposal)

1. Show four characters who know each other and their relationships.
2. The user talks to Alice and reveals something.
3. Alice later talks to Emily and decides, based on her character, whether to share it.
4. The world feed shows the interaction and its consequences.
5. The user talks to Emily and sees that her knowledge and relationship state have changed.

## What this repo adds

The proposal is transport-agnostic. This repo makes **Switch** the transport and the only
place the world runs: each character is a Switch agent, every room is a Switch room, and
the director advances the world by addressing characters in chat. The differentiating
mechanic is the **secret ledger**: every belief carries provenance, so the UI can show
*who knows what, who told them, and how confident they are*.

See [`ARCHITECTURE.md`](ARCHITECTURE.md), [`SWITCH.md`](SWITCH.md) and
[`DECISIONS.md`](DECISIONS.md).
