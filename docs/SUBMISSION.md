# Submission checklist — Flip the Switch

**Deadline: 2026-11-08 03:29 JST** (2026-11-07 23:59 IST). Internal target: evening of
Nov 7 JST. Team: solo (Xinang Li). Track: **2 — Best Personal or Creative Workflow**.

## The three deliverables

- [ ] **GitHub repository** — `charlot3/switch-world`, public (or shared with the judges).
- [ ] **Demo video** — 3–5 minutes, follows [`DEMO.md`](DEMO.md).
- [ ] **README** — says what the project does and **how Switch is used**; the
      [`../README.md`](../README.md) "Why Switch is core" and "Quickstart" sections are the
      required parts.

## Requirements and judging criteria → evidence

The official brief has one hard task requirement and four judging criteria. The task row is
not a fifth criterion.

| Requirement / criterion | Where the evidence lives |
| --- | --- |
| **Hard requirement:** one human + at least one AI agent + a real task, in team chat, connected through Switch | README "The task the human and agents get done together"; the demo's scene and the exported scene card |
| Use of Switch | README "Why Switch is core"; `docs/SWITCH.md`; `docker compose down` in the demo |
| Technical execution | one Compose stack, one world-engine command, four character registrations plus the director; a fresh clone reproduces the demo |
| Creativity and impact | the secret ledger and the who-knows-what dashboard; the authored canon/worldline guardrail (`docs/CANON.md`); the cast cards and 立绘 (`docs/CAST.md`); `docs/ARCHITECTURE.md` |
| Presentation | the 5-minute shot list; README quickstart; no missing steps |

## Before recording

- [ ] Switch + Mattermost healthy; the five agents registered; `#world` and four DMs exist.
- [ ] Switch Console connected; **Claude Code Signed in** (the live fallback), with the
      OpenCode configs present as the preferred path; the README explains the Console
      0.40.1 check.
- [ ] World engine up; dashboard renders the seed state; the Story arc strip, a Profile
      sheet, and Settings → Canon & worldline are rehearsed.
- [ ] The four busts and full-body 立绘 are in `web/assets/portraits/`; Mattermost bot
      avatars match the same set.
- [ ] Rehearsed the full demo twice; saved a fallback recording.
- [ ] `.env`, `.switch/`, `opencode.json`, API keys, and Mattermost admin pages are not
      visible.
- [ ] The demo transcript is committed as `docs/demo-transcript.md`.

## Before submitting

- [ ] `git status` clean in the submodule; the parent hub pointer committed.
- [ ] `README.md` has no "planned" claims left for the parts the demo uses.
- [ ] `docker compose --env-file .env -f deploy/switch/<tag>/docker-compose.yml
      --profile collab --profile gateway down` followed by the same command with `up -d`
      works from a clean state.
- [ ] The repo is public, or the submission form has the access it needs.
- [ ] The demo video is uploaded (YouTube/unlisted or the platform's uploader) and the link
      works in a private window.
- [ ] Submit on the WeMakeDevs page before the deadline; keep the confirmation.
- [ ] Optional side tracks: best blog post; `#HowISwitch` social post; Wispr scorecard if
      used.

## Deadline math

| Zone | Deadline |
| --- | --- |
| IST | 2026-11-07 23:59 |
| JST | **2026-11-08 03:29** |
| UTC | 2026-11-07 18:29 |

Leave at least 6 hours of buffer. A late submission is a zero regardless of quality.
