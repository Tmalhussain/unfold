# Understanding and story

## Story principles (stage 3)

1. Open with a question the viewer wants answered, not with the paper's title.
2. Show one specific worked example before any general statement.
3. Introduce at most one new idea per scene.
4. Geometry and pictures first, algebra second.
5. Make the viewer predict, then reveal.
6. Cut anything that does not serve the main result; point to the paper for the rest.
7. Every symbol is earned on screen (drawn, named, colored) before it appears in an equation.

Audience level sets what counts as a prerequisite:
- highschool: algebra and functions; explain every piece of notation.
- undergrad: calculus, linear algebra, basic probability.
- grad: field background; skip textbook material, keep the paper's own ideas slow.
- expert: move fast through setup; spend the time on what is new.

## `concepts.md` template

```markdown
# Concepts: <paper title>

## Main result
<one or two sentences, plain words, with the page it is stated on>

## Key insight
<the one sentence a viewer should be able to repeat after watching>

## Definitions (in dependency order)
- <term>: <plain definition>; symbol `<tex>`; first used p. N
- ...

## How the result follows
1. <step, citing eqN / page>
2. ...

## Prerequisites for <level>
- <what the viewer must already know>; <what the video must teach on the way>

## What to leave out
- <sections, lemmas, experiments that do not serve the main result>
```

## `story.md` template

```markdown
# Story: <working title>

Guiding question: <a question a curious viewer wants answered>
Key insight: <from concepts.md>
Target: <level>, <minutes> min

## Arc
1. Hook: <the question, posed with a concrete picture>
2. Concrete example: <specific numbers or a specific shape; what the viewer sees>
3. Build-up: <the pieces, one idea per scene, in order>
4. Aha: <the moment the key insight lands; what moves on screen>
5. Generalization: <from the example to the paper's general statement>
6. Payoff: <answer the guiding question; one line on what the paper does next>

## Visual metaphors
- <idea> -> <picture or motion that carries it>

## Principle check
| Principle | Score 1-5 | Why |
| --- | --- | --- |
| Question first | | |
| Example before general | | |
| One idea per scene | | |
| Pictures before algebra | | |
| Predict, then reveal | | |
| Cut what does not serve | | |
| Symbols earned | | |
```

Rework any principle scored under 4 before writing the storyboard.
