# Flip the Switch — requirements

Normalised from the studio inbox file
`flip-the-switch-requirements-20261103.md` (uploaded 2026-11-03 05:06 UTC), which was
compiled from <https://www.wemakedevs.org/hackathons/switch>. Check the official page
again before submitting; this is a working summary, not the source of truth.

## One-line task

Connect an AI agent you already use (Claude Code, Codex, Cursor, OpenCode, Antigravity,
etc.) to team chat (Slack, Microsoft Teams, Discord, Telegram, Mattermost) through the
open-source tool **Switch**, so the agent works with humans as a teammate on real tasks.

## Hard requirements

- **Switch must be core.** Removing Switch must stop the project. The README must explain
  how Switch is used.
- **Three deliverables:** a GitHub repository, a demo video, and a README.
- **Build window:** 2026-11-04 00:01 IST → 2026-11-07 23:59 IST
  (**2026-11-04 03:31 JST → 2026-11-08 03:29 JST**).
  **Submission deadline: 2026-11-08 03:29 JST.** Internal target: the evening of Nov 7.
- Existing agents, libraries and templates may be used, but the Switch integration and the
  workflow itself must be built during the event.
- AI coding tools are allowed; the submitter must understand and be able to explain the
  work.
- Eligibility: global, free, solo or teams of up to 4. **This entry is solo (Xinang Li).**

## Environment and tools

- **Switch Console** desktop app (macOS stable; Windows/Linux early access).
- **Docker** self-hosting of Switch on this machine, free.
- The agent side needs a subscription or API key; Claude Code, Codex and OpenCode work
  out of the box. Custom agents can use the agent protocol (LangChain, Google ADK, OpenAI).
- No company Slack workspace needed: self-hosted Switch ships **Mattermost** for building
  and recording the demo. Slack/Teams/Discord/Telegram can also be connected.
- Resources: the official quickstart (~10 minutes to get an agent replying in a channel),
  <https://docs.switchagents.ai>, the Switch GitHub repo, and the WeMakeDevs Discord.

## Tracks and prizes ($10,000 pool)

| Track | Prize | What it rewards |
| --- | --- | --- |
| 1 — Best Business Workflow | $2,000 | the most practical human + agent workflow that gets work done |
| 2 — Best Personal or Creative Workflow | $2,000 | Switch + agent on everyday tasks, personal projects or creative ideas |
| 3 — Best Core Contribution | $100 × 20 | PRs to the Switch open-source core; only hackathon-labelled issues, apply and be assigned first; max 5 open PRs; open by 2026-11-07 23:59 IST; low-quality PRs excluded |
| Side — Code with Wispr | $500 | best project built with Wispr Flow voice coding; include the Wispr scorecard |
| Side — Best Blog | AirPods 5 | best write-up of the build; stacks with any track |
| #HowISwitch | keyboard × 5 | social posts with the tag |
| Swag / certificates | — | random draw / every submission |

## Judging criteria (official four)

1. **Use of Switch** — is Switch core? Does the project stop without it?
2. **Technical execution** — does it run? Can someone clone the repo and reproduce it?
3. **Creativity and impact** — is the idea new? Does it solve a real problem?
4. **Presentation** — do the demo video and README explain how Switch is used?

Process: WeMakeDevs screens all submissions, then a shortlist is judged by Switch, DevTools
Academy and WeMakeDevs.

## This entry

- **Topic:** AI Social Life Simulator → reframed as a Switch-native social world.
- **Track:** 2 — Best Personal or Creative Workflow.
- **Base connector:** OpenCode for character sessions (better roleplay fit); Claude Code is
  the fallback.
- **The task:** a collaborative scene with a deliverable. The user gives Alice a secret; the
  four agents carry it through a day of encounters and produce a changed belief and
  relationship state. The director exports a **scene card** (summary, who knew what,
  provenance, relationship deltas, transcript links) — that is the real artifact the human
  and the agents made together.
- **Why it fits:** the product *is* a group chat; Switch is the rooms, the agents and the
  delivery, not an add-on.
- **Build rhythm:** Nov 3 (owner-authorized prototype) — world engine, dashboard, local café
  beat; Nov 4 — Switch + Mattermost + OpenCode + first agent + director ownership spike;
  Nov 5 — four characters + world engine integration; Nov 6 — director beats + dashboard +
  scene card + demo; Nov 7 — record, README, submit.

Source for the official rules: <https://www.wemakedevs.org/hackathons/switch>.
