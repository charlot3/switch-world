# The cast: design notes and the art pipeline

The cast is not a list of four prompts. Each character is a **visual hook**, an
**archetype with a contradiction**, and a **private stake** that can survive a scene
without the user. That is what makes a galgame cast feel like people rather than
options.

## What makes these four read as a set

### 1. One silhouette each

At card size, the player should recognise the character before reading the name:

| Character | Silhouette hook | Palette | Read at a glance |
| --- | --- | --- | --- |
| Alice Moreau | loose chestnut bun, round gold glasses, soft cream cardigan | rose / cream / burgundy | warm, bookish, a little tired |
| Emily Park | sharp black bob with blunt bangs, structured charcoal blazer, scar through one eyebrow | lavender / ink / white | precise, guarded, expensive taste |
| Sophia Adeyemi | dark curls in a low bun, thin gold glasses, black turtleneck, long charcoal coat | gold / black / warm brown | still, observational, older than the room |
| Mia Rossi | auburn high ponytail, freckles, mustard sweater under a white apron | orange / mustard / cream | loud, tactile, already in motion |

The four hair shapes (bun / bob / low bun / ponytail), the four outfit silhouettes
(soft cardigan / sharp blazer / long coat / apron), and the four colour families do
most of the work. A player can tell them apart in a 220px card.

### 2. Archetype plus contradiction

A galgame character becomes interesting when the archetype has a crack in it:

| Archetype | The crack | Why the player comes back |
| --- | --- | --- |
| **The Confidante** | She keeps everyone's secrets but cannot ask for help with her own. | You want to be the one person she tells. |
| **The Straight Shooter** | She demands honesty but is hiding her own news. | You want to see what happens when her rule applies to her. |
| **The Observer** | She studies the group for a book, which makes her the least neutral person in it. | You want to know what she wrote about you. |
| **The Wildcard** | She makes the joke first because she is afraid of being left behind. | You want to be the person who stays. |

The stakes are non-romantic as well as romantic: a lease, a job offer, a book, a debt.
The romance is the weather, not the only plot.

### 3. 17+ tension without explicit content

Everyone is an adult, fully clothed, and drawn with a clear, modest silhouette. The
tension comes from eye contact, a beat held too long, a sentence that stops early, and
the gap between what a character says and what the ledger records. The dashboard's
**private · god view** panel shows that gap; the characters never do.

### 4. A card is a character sheet, not a thumbnail

Each card carries:

- the **bust** (the 立绘 crop used in the story and on the card);
- a one-line **tagline** and a two-line **introduction**;
- three **traits** and an **affinity** meter (derived from the user↔character edge);
- **Story** and **Profile** actions.

The **Profile** sheet adds:

- the **full-body 立绘**;
- age, height, birthday and a specialty;
- likes and dislikes;
- the private canon line, labelled **god view**;
- a sample quote;
- the character's outgoing **trust / closeness / tension** bars, including the user;
- a DM link.

That is enough to make a card feel like a route preview without turning the whole
dashboard into a dating-sim stat screen. The README and the scene card keep the
non-romantic, provenance-first framing.

## The image pipeline

`scripts/generate-cast-art.py` is the single flow. It talks to the local rin-studio
API (proxy-studio / ComfyUI) and writes into `web/assets/portraits/`.

### One scaffold, two shot types

Every prompt shares:

```
visual novel character key visual, character sheet, solo, [shot],
centered composition, eye level, looking at viewer, [head placement],
same camera distance, same head size, soft warm late-afternoon key light,
muted plum and gold palette, soft cel shading, clean lineart, detailed eyes,
[character block], [background] softly blurred bokeh,
no text, no watermark, adult woman, fully clothed, modest clothing, tasteful
```

- **Bust** (`--kind bust`): `waist-up portrait`, `portrait` 832×1216, seed **424242**
  for every character. This is the card and story art.
- **Full body** (`--kind full`): `full body, standing, front view, head to toe, entire
  figure including shoes, small figure centered with space above the head and below the
  feet`, `tall` 768×1344, seed **515151** for every character. This is the 立绘 in the
  profile sheet. The first pass cropped Alice's feet, so the scaffold now asks for the
  whole figure and space at both edges. The model still varies the figure scale by a few
  percent; the profile sheet applies a small per-character display scale (1.0–1.08) so the
  four 立绘 read at the same size next to the same text block.

The seed holds the camera, crop and light constant. The character block changes hair,
face, outfit and background hint; that is where the individuality comes from. The
avatar is a 640×640 crop of the bust at `(96, 88)`, scaled to 512×512;
`scripts/update-mattermost-avatars.sh` pushes the four crops to the bot accounts.

### Reproducing or changing the set

```sh
# four busts + avatars
python3 scripts/generate-cast-art.py --kind bust --force

# four full-body 立绘
python3 scripts/generate-cast-art.py --kind full --force

# both, one character
python3 scripts/generate-cast-art.py --only mia --kind both --force
```

The script writes `web/assets/portraits/PROMPTS.md` with the exact prompt, size, seed
and filename for every image, and a horizontal `contact-bust.png` / `contact-full.png`
so the set can be judged side by side.

### Why the old set looked "nice but not aligned"

The first pass generated each character independently. Alice was a three-quarter shot
with a book, Emily and Sophia were waist-up, Mia was chest-up, and the light ranged from
cool office daylight to purple dusk. Each image was good; the **set** was not a set.

The fix is not a better model. It is a shared scaffold, a fixed seed per shot type, and
a named background treatment. The character block is the only variable.

## Character sheets

The in-world sheets with goals, fears, priors, seed beliefs and disclosure policies are
in [`world/characters/`](../world/characters/). The canon that those sheets must not
contradict is in [`docs/CANON.md`](CANON.md) and [`world/canon.json`](../world/canon.json).
