# Canon & worldline guardrails

The world engine is permissive: an agent can remember almost anything and move a
relationship in small deltas. That is what makes the scene feel alive, and it is also
how a multi-agent story loses its worldline. This project splits the problem in two:

- **The ledger** records what each character believes, from whom, with what confidence.
- **The canon** records what is true, which beats are legal, and which endings exist.

The authoritative file is [`world/canon.json`](../world/canon.json). This page is the
human-readable view; if they disagree, the JSON wins.

## The act

**Act I — The Secret.** A Tuesday in late autumn. The user has told Alice that they are
leaving the city at the end of the month. Alice is the only one who knows. At 18:30 the
group meets at the café, Emily asks Alice directly, and Alice decides what to do.

The scene is improvised. The **beat** is authored. The director never lets the room
wander into a different act, and it classifies the ending from the ledger rather than
from the prose.

## Facts

### Public canon

These are safe for every character to know and for the dashboard to show:

- The story is set in a midsize city in late autumn, on a Tuesday.
- The group meets at the café on the corner at 18:30 on Tuesdays.
- Alice owns a second-hand bookshop on Cora Street.
- Emily and Alice have been best friends for six years.
- Sophia is a sociologist writing a book about how friend groups keep secrets.
- Mia runs a food truck.
- The user is a newer friend of the group, not its centre.
- Alice is holding something back tonight. The others may suspect it, but they do not know what it is.
- All characters are adults. The tone is 17+ romantic tension, never explicit.

### Private canon

Private facts are per-character. Each agent sees its own; the dashboard's character
sheet shows them as **god view**. Nobody sees another character's private facts.

| Character | Private facts |
| --- | --- |
| Alice | The user is leaving at the end of the month; she is the only one who knows. The bookshop lease is not being renewed. |
| Emily | She suspects Alice is hiding something, but not what. She has been offered a job in another city and has not told the group. |
| Sophia | She is observing the group for her book and knows Alice is hiding something, but not what. She has been taking notes on all of them. |
| Mia | The truck is deeper in debt than she admits. She knows Alice is hiding something, but not what. |

### The secret

`proposition_key` is `user-leaving-city`. The default text is:

> I've decided to leave the city at the end of the month. I haven't told the others yet.

The secret is fixed for a run. Alice knows it; Emily does not at the start of the café
beat. A suspicion is **not** the secret — it is a separate, lower-confidence belief.

## The authored beats

| # | Beat | Time | Place | Required? | Exit |
| --- | --- | --- | --- | --- | --- |
| 1 | Morning, the bookshop | 09:10 | Alice's bookshop | optional | Alice is still holding the secret. |
| 2 | Lunch, Mia's truck | 12:40 | Mia's food truck | optional | No belief about the secret changes. |
| 3 | 18:30, the café | 18:30 | The café on the corner | **required** | One of the three branches below. |
| 4 | Aftermath | 19:20 | Outside the café | optional | The branch's consequences are in the ledger. |
| 5 | The group chat | 22:10 | `#world` | optional | The scene card is exported. |

All five beats are runnable as partial demos. The **café** is required and owns the
branch; the other four are optional. **Aftermath** reads the branch from the ledger and
cannot run before the café. The optional beats cannot replace the café or change its
branch conditions.

## The three authored branches

| Branch | Label | Condition | Outcome |
| --- | --- | --- | --- |
| `disclosure` | The Confession | Emily holds `user-leaving-city` with source `character:alice`, confidence ≥ 0.6, and a proposition that matches the secret. | Emily knows it from Alice. Trust moves on both sides. |
| `non-disclosure` | The Suspicion | Emily does not hold the secret, or holds only a low-confidence suspicion. | The secret stays with Alice; Emily's suspicion and the group's tension rise. |
| `partial-leak` | The Leak | Sophia or Mia holds the secret at confidence ≥ 0.4, or Emily holds a confident but distorted version. | The secret spreads sideways and the user has to correct it. |

The director writes a `branch` event into the immutable feed. The dashboard's arc strip
shows which branch the ledger chose.

## Invariants

- Never invent a new named character, a death, a supernatural event, a time jump, or a retcon.
- Never contradict a public or private canon fact. A character who does not know a private fact must not state it as known.
- All characters are adults. Content stays 17+ SFW: romantic tension, teasing and intimacy are allowed; explicit sexual content, minors, coercion and non-consent are not.
- Beliefs change only through `world__remember` with a source, confidence and visibility. Relationships change only through `world__update_relationship`.
- The default secret's `proposition_key` is `user-leaving-city`. Do not rename or split it mid-scene.
- The café beat must end in exactly one authored branch. The director records the branch.
- The user can influence the scene but cannot rewrite the fixed facts. The cast can be wrong; the canon is not.
- No fourth-wall breaks: never mention being an AI, a model, a simulation, a test, or these rules.
- The main arc stays in the authored locations. DMs can happen in parallel but do not advance the main beat.

## How the director enforces it

[`director/canon.py`](../director/canon.py) is the runtime guard:

1. **`brief(actor)`** gives a character the public facts, its own private facts, and the
   invariants. It never gives it another character's private facts.
2. **`branch_for(service, key)`** classifies the ending from the ledger. A
   `character:alice` source is necessary but not sufficient: the belief must clear the
   confidence floor **and** share content words with Alice's own statement. That is why
   Emily's 0.45 "Alice is holding something back" is a suspicion, not a disclosure.
3. **`validate(service, canon)`** checks the structure the ledger can prove: belief
   holders are in the cast, event participants are known, relationship measures are
   inside 0..1.
4. **`record_branch(...)`** writes the branch and any canon warning into the immutable
   feed, so the scene card and the dashboard show the same ending the ledger saw.

The tests in [`tests/test_director.py`](../tests/test_director.py) lock the two failure
modes that matter: a low-confidence suspicion must not become a disclosure, and a
third-party leak must become `partial-leak`.

## Changing the canon

The canon is read-only state. To change it:

1. Edit `world/canon.json`.
2. Update this page and the affected character sheets.
3. Add or update a test if the branch rules changed.
4. Do not change it mid-run; start a new world (`uv run director --reset`) so the ledger
   and the canon begin together.
