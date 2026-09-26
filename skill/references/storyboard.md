# storyboard.yaml

The storyboard is the contract between the story and the code. The lint (`unfold lint`) enforces
the rules below; the math check (`unfold mathcheck`) verifies every `math` item. A complete worked
example is `<repo>/examples/reference/storyboard.yaml`.

## Schema

```yaml
title: <video title, used for the file name and metadata>
guiding_question: <from story.md>
key_insight: <from story.md>

# Each symbol gets one of five semantic colors and keeps it for the whole video.
# Keys are the exact TeX used in equations. Use the full token: "m_t", "\hat{m}_t", "\beta_1".
symbols:
  "x": sky
  "\theta": amber
# roles: sky, amber, mint, rose, violet (roughly: main variable, parameter, result, error/cost, other)

# Optional: words the voice mispronounces -> how to spell them for speech.
pronounce:
  Adam: Adam
  arXiv: archive

# Optional: \newcommand lines copied from paper.json "macros", if on-screen math needs them.
tex_preamble: []

scenes:
  - id: s01                 # s01, s02, ... in order
    title: <chapter title>
    new_ideas: [<the one new idea>]     # at most one
    beats:
      - id: b1
        say: <narration, 1 to 3 sentences, written exactly as it should be spoken>
        show: <what is on screen and what moves, in plain words>
        text: [<on-screen words>]        # optional; 12 words max per beat
        introduces: ["x"]                # symbols drawn/named in this beat
        math:                            # at most 2 equations on screen
          - tex: 'x^2 + y^2 = 1'
            source: eq3                  # copied from the paper: must match eqN
          - tex: 'y = \sqrt{1 - x^2}'
            derived: true                # a step the video adds
            check: identity              # or {equals: '<tex>'} or {at: {x: 0.6}, value: 0.8}
          - tex: 'r = 1'
            illustration: true           # numbers or labels, not a claim
        transform: true                  # this beat has a continuous transform
        hard: true                       # a hard step: at least 1.5 s pause after the reveal
        pause: 0.5                       # optional pause after the narration (default 0.35 s)
        cite: p4                         # optional page for claims in the narration
```

## Rules (lint errors unless marked)

- `title`, `guiding_question`, `key_insight` are required; every scene has a `title`.
- Every scene has at least one beat with `transform: true` (no pure slide cuts).
- At most one entry in `new_ideas` per scene.
- Narration is speakable: no `\ $ ^ _ { }`. Write "x squared", "beta one", "m hat t".
- A symbol in `symbols` may only appear in an equation after a beat `introduces` it.
- At most 2 `math` items per beat, and plan the scene so no more than 2 equations are on screen.
- At most 12 words of `text` per beat.
- `hard: true` beats get at least 1.5 s of pause (the library enforces it).
- Each math item has exactly one of `source`, `derived`, `illustration`.
- Warnings: beats over 60 words; beats without `show`; total length more than 30% off target.

## Writing good beats

- YAML: a plain value cannot contain ": " (colon then space). Use a period instead, or quote the
  value. Put TeX in single quotes: `tex: '\frac{1}{2}'`.
- Digit groups in math: `12{,}288` (the math check reads it as 12288; `\,` also works).

- One beat = one visual change the narration talks about. If the picture changes twice, split it.
- The `show` line is what the critic compares frames against, so make it concrete: objects,
  positions, colors, what moves.
- Narration names what the viewer sees at that moment ("this blue curve"), not what is coming.
- Budget about 155 spoken words per minute, plus pauses.
- Prefer a concrete number example on screen before the symbolic version.
