# contentmaxxer

`contentmaxxer` is a source-grounded, Manim-first production CLI for technical reels and carousels. It caches every URL or local note inside the job, turns evidence into typed claims, requires factual scenes and slides to cite those claims, and runs hard QA gates before declaring an artifact complete.

Educational reels use narration-led timing, four-word kinetic captions, hand-drawn multi-sketch explanations, actual rendered-frame contact sheets, and encoded-audio checks for loudness, peak, dead air, alignment, and A/V drift. See the [educational reel playbook](docs/EDUCATIONAL_REELS.md), [open-source voice notes](docs/OPEN_SOURCE_TTS.md), and [director prompt](prompts/educational-reel-system.md).

Carousels use an engagement-first editorial system: three scored angles, at least 12 hooks, a cover-to-payoff swipe narrative, original full-bleed art, three rendered cover tests, and hard gates for hook brevity, one idea per slide, visual variety, and save/share/comment payoff. See the [carousel engagement playbook](docs/CAROUSEL_ENGAGEMENT_PLAYBOOK.md) and [agent system prompt](prompts/carousel-system.md).

Manim is the polished director. `--renderer auto` prefers it and clearly records a `raster_fallback` when Manim is unavailable. The fallback is useful for smoke tests; it is never mislabeled as polished Manim output. The manual `render` command remains available for bespoke scenes. Remotion is intentionally not part of this runtime.

The existing `hand_drawn` animation remains the default. Four opt-in visual experiments use one persistent argument map instead of rapid card changes:

- `whiteboard`: imperfect marker strokes on ruled paper
- `warm_papyrus`: warm ink, gears, and inventor-folio mechanics
- `future_minimal`: sparse neon frontier-signal diagrams
- `director_cut`: cinematic split-letter editorial collage

Select one with `--animation-style whiteboard` (or another style above).

Each experimental style receives a source-derived visual story from the compiled plan: a short core concept plus grounded beat roles and labels. Dominant mechanism primitives currently route orbital motion, gradient descent, self-attention, and Bayesian updating into evolving explanatory diagrams, so the same underlying idea remains visible while each beat adds the next causal step. The open-weights debate profile uses the same semantic-continuity system for an argumentative source map: shared benefits, irreversibility, attacker-versus-defender risk, and policy responses remain addressable objects instead of being replaced by generic cards. Previously unseen ordered mechanisms now route to a persistent process journey. The compiler derives reusable operations such as lookup, dispatch, route, transform, verify, resolve, and store from the cited stage. A faint full-route sketch establishes the whole mechanism; one carrier follows curved ink between alternating landmarks, and completed stages remain visible around the canvas instead of accumulating in a vertical flowchart. Sparse path transits retrace the exact active curve during long narration spans without replacing the aligned semantic-word reactions. The classifier requires distinctive attention evidence instead of treating generic words such as `key`, `value`, or `context` as proof of a Transformer lesson. Bayesian multiplication and normalization fire on their matching narration cues instead of jumping ahead at the beginning of a beat. Between structural changes, narration terms animate only the named semantic object—such as gravity, velocity, loss, query, weights, or the fair coin—while captions retain their fast swap timing. The temporal language is style-native: whiteboard objects wobble, papyrus diagrams advance like a drafting carriage, future-minimal objects pulse and echo, and director-cut objects receive a short editorial lift. Topic-specific compositions are selected only when their complete matching evidence pattern is detected; otherwise the renderer uses a source-derived generic grammar without leaking concepts from another reel.

The current NVIDIA-versus-Amodei validation reuses one byte-identical 40.04-second Deepgram/Whisper master across the four requested aesthetics. The whiteboard now centers a hand-sketched downloadable-model sheet, open-door access doodle, diverging competition arrows, slider controls, escaping copies, and an attacker/defender balance instead of a generic hub of circles. Sparse long-gap motion retraces the active evidence mark; papyrus uses drafting rotation, future minimal uses signal pulse/echo, and director cut uses editorial lift. Current substantial-motion coverage is 30.5% whiteboard, 41.5% warm papyrus, 37.0% future minimal, and 42.5% director cut. Every style passed 41 / 41 media checks, retained 0.0601-second A/V drift and zero continuity resets, decoded fully, and passed stable plus motion-selected frame inspection. The accepted whiteboard follows two preserved failures at 20.0% and 23.5%; no QA threshold was weakened.

Generic causal stories use this persistent semantic renderer in all five styles. The default `hand_drawn` version uses a dark chalkboard palette, three-pass rough strokes, chalk dust, and aligned wobble emphasis; unrelated non-causal `hand_drawn` scenes continue to use the established sketch library. A controlled TLS 1.3 matrix reused one byte-identical narration master across every style and passed the causal motion and semantic-timing gates in each render. An unseen RFC-grounded DNS lesson exercises the generic path as `LOOKUP → DISPATCH → ROUTE → RESOLVE → STORE`, proving that the composition does not depend on a topic-specific scene. The latest spatial-journey matrix reused one byte-identical 91-word Deepgram/Whisper master across all five styles. Substantial-motion coverage measured 45.0% for hand drawn, 41.1% for whiteboard, 63.6% for warm papyrus, 62.3% for future minimal, and 51.0% for director cut. Every render retained 0.0201-second A/V drift, 21 valid semantic events, 16 motion witnesses, successful full decode, and clean representative-frame inspection.

Ordered generic mechanisms also receive a bounded extractive narration pass. It selects coherent, contiguous action clauses from each cited claim instead of narrating every qualifier verbatim; it never introduces content words that are absent from the hook or bound evidence. Complete specialized profiles such as TLS, Bayesian updating, and the open-weights debate remain unchanged. On the DNS validation, the pass reduced the script from 121 to 91 words and the Deepgram character count from 717 to 537. Thalia at `--voice-rate 190` then produced a 30.08-second reel at 181.5 WPM, with 1.10% independent-ASR WER, 0.0201-second A/V drift, 44.4% substantial-motion coverage, and successful full decode.

Cross-domain validation uses an MDN-grounded browser-navigation lesson rather than another DNS-like process. It exposed and fixed three generic failure modes: an extractive window could end in the middle of an enumeration, `verifies` missed the verification-role classifier, and a contextual prefix could make the visible stage label lag behind the narrated action. The accepted browser reel routes `LOOKUP → VERIFY → DISPATCH → TRANSFORM → TRANSFORM` without browser-specific scene code. Its 88-word Thalia master ran 32.64 seconds at 161.8 WPM with 1.14% independent-ASR WER, 0.0601-second A/V drift, 42.3% substantial-motion coverage, a 1.6-second longest static span, and successful full decode. The raw transcript recovered URL, IP, DNS, TLS, HTTPS, HTTP GET, HTML, DOM, and CSSOM.

TLS 1.3 now also has a stricter semantic handshake composition: persistent client and server actors exchange ClientHello and ServerHello packets, derive matching secrets, authenticate the server certificate and signature, verify the transcript with Finished messages, and finally move protected application data through the established channel. Longer idle spans receive restrained, labeled `HELLO`, `DERIVE`, `ENC`, `FIN`, or `DATA` transits in the direction implied by the active stage; the aligned emphasis clock still controls narration-specific object reactions. This composition is selected only when the cited claims contain the complete handshake evidence pattern. Partial TLS notes remain on the source-derived causal renderer instead of receiving unsupported protocol artwork.

## Install and verify

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[animation]'
.venv/bin/python -m unittest discover -s tests -v
```

Manim integration tests are opt-in with `CONTENTMAXXER_MANIM_INTEGRATION=1`. Cairo and Pango must also be available on the host (for example, `brew install pkg-config cairo pango` on macOS).

For the local Apple-Silicon voice path, use a separate Python 3.12 environment so the Manim environment can keep its own dependency set:

```bash
python3.12 -m venv .venv-tts
.venv-tts/bin/python -m pip install 'mlx-audio==0.4.6'
```

## Grounded workflow

```bash
contentmaxxer research "A sourced topic" \
  --job sourced_topic \
  --source-url https://example.com/reference \
  --source-file notes.md

contentmaxxer director "A sourced topic" \
  --job sourced_topic \
  --offline \
  --renderer auto \
  --hook-style question

# Local macOS narration with measured timing and word captions.
contentmaxxer director "A sourced topic" \
  --job sourced_topic \
  --offline \
  --renderer manim \
  --voice-provider say \
  --voice Samantha \
  --voice-rate 170

# Premium timestamped narration (uses ELEVENLABS_API_KEY).
contentmaxxer director "A sourced topic" \
  --job sourced_topic \
  --offline \
  --renderer manim \
  --voice-provider elevenlabs \
  --voice YOUR_ELEVENLABS_VOICE_ID

# Hosted Aura-2 narration (reads DEEPGRAM_API_KEY from the environment or .env.local).
contentmaxxer director "A sourced topic" \
  --job sourced_topic \
  --offline \
  --renderer manim \
  --voice-provider deepgram \
  --voice aura-2-thalia-en \
  --voice-rate 170

# Open-source, local Apple-Silicon narration with Qwen3-TTS through MLX-Audio.
# The first run downloads the selected model; later runs use the local cache.
contentmaxxer director "A sourced topic" \
  --job sourced_topic \
  --offline \
  --renderer manim \
  --voice-provider qwen3 \
  --voice Aiden \
  --voice-rate 165 \
  --voice-instruction "Warm, curious, conversational educational narrator. Speak only the supplied text once."

# Open-source local narration. Chatterbox is tested upstream on Python 3.11;
# use `pip install -e '.[animation,local-voice]'` in that environment.
contentmaxxer director "A sourced topic" \
  --job sourced_topic \
  --offline \
  --renderer manim \
  --voice-provider chatterbox \
  --voice-reference clean-voice-reference.wav

# Or import a finished narration track.
contentmaxxer director "A sourced topic" \
  --job sourced_topic \
  --offline \
  --renderer manim \
  --voice-provider file \
  --narration-file narration.wav

contentmaxxer slides "A sourced topic" \
  --job sourced_topic \
  --offline \
  --count 7 \
  --target 9:16 \
  --target 4:5

# Alternate code-native collage system; no AI-generated hero image.
contentmaxxer slides "A sourced topic" --offline --style paper-meme
```

Supported hook styles are `direct`, `question`, `contrarian`, `statistic`, `curiosity`, `story`, and `list`. A statistic hook is rejected unless at least one cited claim is numeric.

Without sufficient sources, `director` and `slides` write a blocked, ungrounded plan and stop before rendering. `--allow-ungrounded` is an explicit escape hatch for visibly speculative placeholders; such work fails the grounding QA gate by design.

`--voice-provider auto` preserves the existing order: configured ElevenLabs, then the external Qwen3/MLX environment, then Chatterbox, then macOS speech. Deepgram remains explicit opt-in until voice-quality testing justifies changing that default. Qwen generates bounded sentence/clause chunks and records retry diagnostics to reduce clipped endings. Deepgram and Qwen3 beat durations are measured from their actual WAV output, but their word timings are proportional estimates. The final AAC mux leaves extra true-peak headroom for codec overshoot. Use an independent ASR or listening pass before publishing.

For short educational reels using Deepgram Thalia, `--voice-rate 200` is the current tested high-energy setting. On the 103-word open-weights script it mapped to Aura speed `1.176`, produced a 40.04-second master (155.8 effective WPM), and retained the same independent-ASR word error rate as the slower 170 setting. This is script- and voice-specific guidance; the CLI default remains 170, and the provider stays explicit opt-in.

For a tighter five-stage mechanism script, `--voice-rate 190` is the better tested starting point. The 91-word DNS validation mapped to Aura speed `1.118` and landed at 181.5 WPM; its unprompted Whisper transcript recovered `IP address` correctly and differed only on the spelling of the pronounced homophone `cacheable`/`cashable`.

New proportional narrations use `--word-aligner auto`. When the configured MLX-Audio environment and Whisper model are already cached, Whisper cross-attention/DTW timestamps are mapped back to the exact grounded script. Auto never downloads an aligner model and preserves imported timing maps; use `--word-aligner mlx-whisper` to opt into a download or explicitly refine an imported master. Alignment must cover at least 95% of script words with at most 15% WER or the explicit mode fails. Auto records the rejection and keeps the measured proportional fallback.

For semantic Manim stories, captions and emphasis now have separate clocks. Stage entry supplies the opening motion; subsequent style-native emphasis starts on the first aligned semantic word inside each caption rather than at the caption-card boundary. Render metadata records scheduled, delayed, and invalid events, and mechanism, argument, and generic causal QA requires enough valid word-triggered events to cover the lesson.

Semantic Manim renders also produce `video/motion-contact-sheet.png`. Motion analysis selects the strongest change, a sustained low-amplitude change, and another distributed peak inside every beat, then adds the midpoint of the longest static interval. The labeled frames and timestamps are portable render evidence, and QA fails if a beat is under-sampled or the witness artifacts are missing. This complements the ordinary evenly distributed contact sheet and is intended to expose brief packet, label, or geometry collisions. The contract is verified on both the dark chalk TLS mechanism and the low-contrast warm-papyrus open-weights argument, including the papyrus-specific 0.18 motion threshold.

Semantic stories now have a separate encoded continuity gate. The compiler must declare `semantic_continuity`, and the finished MP4 is sampled at the settled midpoint of each beat. The analyzer crops to the central explanatory canvas, removes edges that persist in every sample as template/background structure, excludes the intentional hook-to-diagram transition, and measures how much beat-specific diagram ink survives into the next body beat. QA requires every eligible transition to contain enough measurable ink, at least 0.60 average and 0.65 median retained-edge ratios, and no more than one large reset in the standard five-beat lesson. The threshold intentionally permits a single justified semantic morph such as the Bayesian normalization step. The controlled browser-navigation rerender retained 0.8496 average and 0.8464 median dynamic edges with zero resets; the known gradient scene-replacement baseline measured 0.4592 average and 0.5614 median and fails.

The text layer follows the same continuity principle. Semantic lessons keep the opening question as one persistent header instead of replacing a large headline on every beat, and an unchanged source label is not re-faded. Captions begin as source-aligned phrases of up to six words; a trailing one- or two-word orphan may merge into the previous phrase when the result stays at most eight words and 3.2 seconds. Each style retains its own transition: chalk and whiteboard erase then write, papyrus cross-slides like a revised folio note, future minimal uses a restrained signal fade, and director cut uses an editorial lateral change. Hard QA limits caption churn to 32 transitions per minute, requires at least 1.7 seconds median caption dwell, permits at most 10% sub-0.65-second phrases for necessary technical triggers, and checks the encoded header pixels at every beat midpoint. The accepted browser chalk rewrite reduced caption states from 24 to 17 and measured 29.41 transitions per minute, 1.86-second median dwell, and 1.000 minimum/median encoded header retention. The replaced-headline baseline measured only 0.577 minimum and 0.765 median header retention and now fails. A byte-identical browser narration matrix then verified the new grammar in all five styles. Every MP4 passed full decode, synchronization, encoded title persistence, diagram continuity, motion, and representative-frame inspection. Motion coverage was 27.6% hand drawn, 25.2% whiteboard, 50.9% papyrus, 43.6% future minimal, and 34.4% director cut; all five retained zero diagram resets.

Generic causal lessons now finish with a visual answer instead of adding another narrated summary. During the final narration tail, a highlighted carrier sweeps from the first source-classified operation to the last over the complete accumulated route, then the persistent opening question and finished mechanism remain on screen for the loop. The payoff label is derived from the actual stage roles, such as `LOOKUP → TRANSFORM • ONE CONTINUOUS PATH`; it does not introduce topic-specific copy. A separate encoded gate inspects the final route canvas at 10 fps and requires ordered motion in both its upper and lower halves over at least 0.2 seconds. The prior browser ending had no upper-route motion in that window and fails. The accepted hand-drawn and warm-papyrus browser renders measured 4/4 active upper/lower frames over 0.7 seconds and 3/3 over 0.6 seconds, respectively. Both retained the byte-identical Thalia master, 0.0601-second A/V drift, zero diagram resets, clean full decode, and readable final captions.

Source-grounded feedback mechanisms extend that route instead of forcing every lesson into a one-way journey. The compiler requires evidence of expansion, correction, recurrence, and a shared state before it emits `source_feedback_loop_v1`; unrelated browser and DNS controls remain linear. The TCP congestion-control validation accumulates `PROBE → EXPAND → MODERATE → ADJUST → FEEDBACK`, then draws a return arc from the final state to the original probe. Encoded QA checks both the forward recap and the lower-to-upper-left return motion. A byte-identical 41.96-second narration master passed in three distinct compositions: hand drawn retained 0.8245 average diagram ink with 27.8% motion, warm papyrus retained 0.8501 with 53.3% motion, and future minimal retained 0.8644 with 46.7% motion. Every style recorded zero resets, at least four upper-left return frames across a 0.9–1.0-second loop, 0.0401-second A/V drift, clean full decode, and representative-frame inspection.

Closed physical cycles are detected separately from control feedback. `source_cycle_loop_v1` requires repeated state transformations, an explicit return-and-repeat claim, and a shared material across the forward and return stages; a similar source without recurrence stays linear. The DOE-grounded heat-pump validation groups ten ordered claims into five complete beats instead of truncating after the compressor, then accumulates evaporator, compressor, condenser, expansion valve, and the return to the evaporator on one persistent canvas. The fully evidenced `heat_pump_cycle_v1` profile uses distinct hand-drawn component glyphs, a refrigerant carrier, and a cold/low-pressure to hot/high-pressure legend. The accepted 43.72-second whiteboard render measured 34.2% substantial motion and 0.8744 average continuity; the byte-identical warm-papyrus stress test measured 61.2% and 0.8869. Both retained 28.82 caption transitions per minute, zero rapid captions, zero diagram resets, 0% independent-ASR WER, and 0.0801-second A/V drift.

TCP now receives an additional evidence-gated visual profile only when the cited source establishes the protocol identity, congestion window, slow start, acknowledgments, congestion avoidance, retransmission timeout, threshold, and in-flight data. The persistent hero state is an illustrated congestion window: packet slots expand under ACKs, a dashed threshold appears during gradual growth, loss visibly removes capacity, and recovery begins reopening the window. Stage landmarks use packet, growth, slope, loss, and ACK-return glyphs, while moving carriers are packets rather than generic dots. An incomplete TCP note, DNS, and browser navigation all remain on the generic process grammar. The accepted five-style semantic matrix preserves one byte-identical 41.96-second Deepgram master and 0.0401-second A/V drift throughout. Substantial motion measured 29.2% hand drawn, 27.4% whiteboard, 51.9% warm papyrus, 46.2% future minimal, and 36.8% director cut; average continuity ranged from 0.8212 to 0.8593, with zero resets in every style. Each encoded return loop supplied at least five upper-left frames over 0.9–1.0 seconds, passed all 42 pipeline checks, decoded fully, and passed representative-frame inspection.

Persistent hooks now preserve the complete editorial promise instead of inheriting the seven-word ellipsis used by ordinary beat headlines. Question hooks match the plan hook exactly; an intentionally concise specialized headline remains intact; and an overlong curiosity headline receives a compact topic-bound question, such as `What happens during a TLS 1.3 handshake?`. The Manim title layout balances and scales up to three complete lines without deleting words. Generic process diagrams no longer repeat a second truncated version of the topic below the title; that redundant line is replaced by the classified mechanism span, such as `LOOKUP → TRANSFORM`. Hard semantic-text QA rejects ellipses or a question/title mismatch and requires every sampled-frame title record to contain the same complete, non-truncated hook. In the controlled browser rerenders, all 8/8 sampled frames matched `How does a browser turn a URL into a page?`; encoded header minimum retention was 0.9993 in chalk and 1.000 in papyrus, with zero diagram resets and the byte-identical accepted narration.

Process landmarks now use source-bound action/object compression instead of cutting claim fragments with ellipses. Each label is derived from its own cited beat, keeps at least two source tokens, is limited to eight words, and is rendered completely in a scaled two-line region. Semantic QA rejects missing compressor records, weak source overlap, overlong labels, any landmark ellipsis, or a renderer that could silently truncate the result. The browser control now reads `request page • find server IP`, `verify HTTPS server • establish secure connection`, `send HTTP GET request`, `tokenize HTML • build DOM`, and `combine DOM + CSSOM • paint pixels`; the independent DNS control uses a different five-label vocabulary and passes the same gate. Both final MP4s preserve the complete hook, all five accumulated landmarks, zero diagram resets, full-route recap motion, and their previously accepted byte-identical Thalia narration masters.

To compare multiple visual styles with the exact same performance, import both the master WAV and its timing map:

```bash
contentmaxxer director "Your topic" \
  --voice-provider file \
  --narration-file path/to/voiceover.wav \
  --narration-timings path/to/timings.json
```

## Target profiles

Carousels are re-laid out for each profile rather than resized. Supported grouped targets are `9:16`, Instagram-native `3:4`, and `4:5`; platform-specific profiles include `tiktok`, `stories`, `reels`, `instagram`, and `linkedin`.

## GPT-5.6 set

```bash
contentmaxxer gpt56-set --output-dir jobs --renderer auto --count 7
```

This builds `gpt_5_6_family_tiers` and `gpt_5_6_capability_controls`, each with a reel and 9:16 plus 4:5 carousel variants. Their sources are locked to July 9, 2026 and point to the general-availability launch, current model docs, and GPT-5.6 System Card. If a source is unreachable, the command records that it used the packaged locked snapshot instead of pretending a network retrieval succeeded.

## Five-post creative test

```bash
contentmaxxer five-post-set --output-dir jobs --count 7
```

This builds the paper/meme clone, Fable 5 versus GPT-5.6 in both visual systems, and the model-economics angle in both systems. Every post exports 9:16, 3:4, and 4:5, with three cover tests per ratio. `paper_meme_v1` is entirely code-native: graph paper, marker typography, tape, receipts, doodles, and comparison cards, with no generated hero art.

## Job contract

Each completed job includes:

- source snapshots, normalized text, retrieval metadata, and SHA-256 digests;
- `claims.json`, content plans, and `citations.md`;
- a typed Manim spec and deterministic `scene.py`;
- reel MP4, burned caption rail, SRT, contact sheet, and scene-level citations;
- exact-count carousel PNGs and contact sheets per adapted target;
- portable `manifest.json` paths;
- initial and revised plans plus QA reports;
- `final-file-locations.md`.

QA is gate-based, not score-based: schema, grounding and citation coverage, dimensions, duration, caption rate, safe bounds, text size, truncation, overlap, density, blank or duplicate media, missing files, and manifest integrity must all pass after the single deterministic revision.

Carousel QA additionally requires 12 hook options, three angle options, three rendered cover candidates per target, concise cover/body copy, one idea per slide, a cover-to-payoff role progression, visual variety, a visible swipe cue, the selected visual theme, and a final engagement payoff.
