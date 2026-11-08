# UI spec — one world, two modes

This is the layout contract for the dashboard. It exists because the shell used to switch
at four different viewport widths (`1180`, `980`, `900`, `860`), so a 1000px laptop paid
198px for the rail and 330px for the phone before measuring the stage. The stage collapsed
to ~394px, the scene art to ~200px, and at 500px an embedded / desktop-site view could show
the rail with the main pane clipped off-screen.

## Shell modes

`shellMode()` in `web/js/main.js` sets `html[data-shell]` from
`min(innerWidth, visualViewport.width)`. This is deliberately **not** a media query: an
iframe or a WebView can report a 980px layout viewport while the visible pane is 500px.

| Mode | Width | Rail | Stage | Phone |
| --- | --- | --- | --- | --- |
| `wide` | >= 1360 | labelled column | flexible | sticky column |
| `compact` | 761–1359 | icon rail | full width | closed fixed drawer |
| `phone` | <= 760 | horizontal icon rail | full width | full-screen drawer |

The phone is closed by default in the drawer modes; "Open the phone" in the scene, or the
cast card's Chat button, opens it. The close button (and Escape) returns to the stage.

## Story

- The stage owns the viewport on phone: the scene CG is a 220–320px banner, not a
  68vh poster. The line, choices, composer and Next follow immediately.
- On compact widths the scene keeps two columns when the stage is wide enough; the phone
  no longer steals the column.
- The phone remains a phone-shaped column only at `wide`; below that it is an overlay.
- The scene CG is layered as a blurred cover backdrop plus a contained foreground, so
  the full figure and face stay in frame.

## Deferred

The full Play/Studio information-architecture split (a separate operator surface for
health, agents, rooms and logs) is specified but not shipped for the Flip deadline. The
existing Settings remains the operator drawer; the Story no longer carries the debug
"Copy live-beat command" control.
