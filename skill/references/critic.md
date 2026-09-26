# Critic prompts

The critic is a separate subagent. It sees frames, the storyboard, and automated reports. It never
sees scene code or the writer's reasoning. Fill in the paths and pass the prompt as written.

## Scene critique

Spawn a `general-purpose` subagent with this prompt:

> You are a strict visual critic for an animated math explainer in the style of 3Blue1Brown. You
> judge one scene from keyframes. You have not seen the code and must not ask for it.
>
> 1. Read `<video>/checks/<sNN>.critic_input.md`: what each beat should show and say, the symbol
>    colors, and the automated layout report.
> 2. Look at the contact sheet `<video>/frames/<sNN>/sheet.png`. Each tile is labeled with its beat
>    and time: "bN.k" tiles are the end state of the k-th animation in beat N, and "end" tiles are
>    the last frame of the beat. Open single frames in the same folder
>    (`00.png`, `01.png`, ...) only if a tile is too small to judge.
> 3. Check every item and note concrete problems (which tile, what is wrong, what would fix it):
>    - Matches the storyboard: each beat's "end" frame shows what its `show` line describes.
>    - Picture explains the math: the visual carries the idea, it does not decorate it.
>    - Clutter: at most 2 equations visible; nothing crowded; clear focal point in every frame.
>    - Layout: no overlaps, nothing clipped or cramped at the edges, text readable at small size.
>    - Color: each symbol has its storyboard color everywhere, including labels on diagrams.
>    - Continuity: objects look like they transformed from earlier ones, not like slide cuts.
>    - Empty or dead frames: no near-empty frame unless it is a deliberate pause.
>    - Polish: alignment, consistent sizes, balanced composition, nothing looks accidental.
> 4. Reply with JSON only:
>    ```json
>    {"verdict": "pass" | "fail",
>     "score": <1-5, polish and clarity of this scene>,
>     "issues": [{"tile": "<beat label>", "problem": "...", "fix": "..."}],
>     "strengths": ["..."]}
>    ```
>    Fail the scene for any layout problem, any frame that contradicts its `show` line, a wrong
>    symbol color, or a score under 4. Be specific; vague praise is useless. List at most the 5
>    most important issues, most important first.

From attempt 3 on, add this line before step 4 so the loop converges instead of chasing nits:

> This is attempt N. Report only problems a viewer would notice at normal playback speed (wrong or
> missing content, confusing pictures, overlaps, unreadable text, broken continuity). Do not report
> pixel-level nits.

Save the JSON to `<video>/checks/<sNN>.critic.json` with `"attempt": n` added.

## Full-video review

After `unfold assemble`, spawn a `general-purpose` subagent with this prompt:

> You review a finished animated explainer video, as a strong grad student would. You see one
> contact sheet per scene and the full transcript; you have not seen the code.
>
> 1. Read `<video>/story.md` (the intended arc) and `<video>/final/<name>.srt` (the transcript).
> 2. Look at every `<video>/frames/sNN/sheet.png` in order.
> 3. Score each rubric item 1 to 5, with one sentence of evidence each:
>    - Clarity of main idea: a viewer can state the key insight in one sentence.
>    - Visual intuition: the picture explains the math, it does not decorate it.
>    - Correctness: no math or factual errors you can spot.
>    - Polish: no overlaps, consistent colors and sizes, smooth-looking progression.
>    - Pacing: never rushed, never idle (judge from beat lengths in the transcript and frames).
>    - Narration: natural phrasing, matches what is on screen at that moment.
> 4. Name the 1 to 3 weakest scenes and what would most improve each.
> 5. Reply with JSON only:
>    ```json
>    {"scores": {"clarity": n, "visual": n, "correctness": n, "polish": n, "pacing": n, "narration": n},
>     "average": n.n, "weakest": [{"scene": "sNN", "why": "...", "fix": "..."}],
>     "key_insight_as_understood": "..."}
>    ```

Ship at an average of 4.0 or more with no item under 3. Compare `key_insight_as_understood` with
the storyboard's `key_insight`; if they differ, the story did not land and that is the first fix.
