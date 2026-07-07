# AI Shorts Research

Date: 2026-07-07

## Goal

Build a repeatable AI-assisted workflow for Instagram Reels, TikTok, and YouTube Shorts that turns papers and technical concepts into strong short explainer videos, with your own voice, reliable captions, and low-friction publishing.

## Executive summary

The strongest approach for this repo is a hybrid pipeline:

1. Use an LLM for research extraction, hook generation, scripting, and storyboard planning.
2. Use Manim for the truth-sensitive parts: equations, diagrams, loss landscapes, architecture visuals, data flow, and anything that must stay technically faithful.
3. Use Remotion as the packaging layer for social video: 9:16 layout, captions, progress bars, branded end cards, chapter cards, thumbnails, and batch rendering.
4. Use your own real voice or a controlled clone for narration, then use ASR plus alignment for captions.
5. Use `ffmpeg` as the final export and transcode layer.
6. Automate YouTube first, then TikTok and Instagram once the content format is stable.

This is better than going all-in on text-to-video or avatar tools because educational paper explainers live or die on fidelity and pacing, not just visual novelty.

## What the research says

### 1. The winning structure is hook-first and scene-based

Recent paper-to-video research does not start from one giant summary. PaperTok uses an iterative workflow that begins with a compelling hook, then script, voiceover style, scenes, captions, and a credit screen. Users keep control scene by scene and can regenerate until the storyboard works. That is very close to the direction we want for Content Maxxer.

### 2. Human-in-the-loop matters

PaperTok explicitly argues that the real value of generative AI is not replacing the whole creative process, but enabling richer human-in-the-loop collaboration. For this repo, that means the model should draft hooks, scripts, visuals, and captions, but you should still approve claims, tone, and final edits.

### 3. Educational reels can genuinely work

ReelsEd, an LLM-generated short-form educational video system, reported better engagement, quiz performance, and task efficiency than long-form video in a user study, without increasing cognitive load. That is a good sign for a paper-explainer channel, but only if the reels are structured and pedagogically clean.

### 4. Segmenting and signaling are not optional

Educational video research consistently supports segmenting and signaling. A 2018 meta-analysis covering 95 studies found signaling effects are supported across many settings. In practice, that means:

- one clear claim per beat;
- explicit labels, arrows, and callouts;
- fewer competing elements on screen;
- shorter scene units instead of one dense continuous narration;
- deliberate emphasis on the exact object, term, or motion you want the viewer to track.

### 5. Shorts are strong for reach, but weaker for depth-heavy categories

A 2024 YouTube Shorts study found Shorts generally attract more views and likes per view than regular videos, but do not outperform regular videos nearly as much in education. Another 2024 study of 250 large creators found that after short-form adoption, long-form views and engagement decreased on those channels.

My read: shorts should be the discovery engine, not the entire media strategy. Build the system so each short can also point to a longer thread, deck, article, repo, or full video later.

## Methodologies compared

### 1. Manim-first explainer pipeline

Best for:

- papers;
- ML systems;
- mathematical concepts;
- algorithms;
- anything requiring precise diagrams.

Strengths:

- highest technical fidelity;
- distinctive look;
- code reviewable and reproducible;
- works well for reusable scene libraries.

Weaknesses:

- slower to produce;
- harder to make feel native to social by itself;
- needs a packaging layer for captions, hooks, and vertical formatting.

Verdict:

Keep this as the core explanation engine.

### 2. Remotion-first social template pipeline

Best for:

- branded repeatable shorts;
- batch rendering;
- multi-format exports;
- thumbnail generation;
- A/B testing titles, subtitles, and layouts.

Strengths:

- programmatic video in React;
- reusable templates with props;
- easier social-native packaging than pure Manim;
- good fit for editors, automations, and rendering in bulk.

Weaknesses:

- worse than Manim for technical diagrams unless you build those primitives;
- another runtime and mental model.

Verdict:

Use Remotion as the composition and packaging layer around Manim clips, captions, and narration.

### 3. Avatar-first pipeline

Best for:

- face-led explainers;
- presenter content;
- multi-language localization;
- very fast production.

Strengths:

- quick iteration;
- strong if the brand is personality-driven;
- API-friendly products exist.

Weaknesses:

- can feel generic fast;
- technical diagrams still need a separate visual lane;
- trust can drop if the avatar feels uncanny.

Verdict:

Optional later. Not the primary lane for paper explainers.

### 4. Text-to-video or image-to-video-first pipeline

Best for:

- intro hooks;
- ambient B-roll;
- concept mood pieces;
- highly stylized inserts.

Strengths:

- fast novelty;
- impressive visual hooks;
- useful for transitions and nonliteral visuals.

Weaknesses:

- weak factual control;
- poor for equations, architecture, and research claims;
- hard to maintain visual consistency without extra work.

Verdict:

Use sparingly for hooks and cutaways, not for the core explanation.

### 5. Hybrid recommended pipeline

Recommended default:

- LLM for research and script.
- Manim for core scenes.
- Remotion for layout, subtitles, pacing polish, and exports.
- Your voice or a voice clone for narration.
- `ffmpeg` for finishing and transcodes.

This is the best balance of truthfulness, style, and scale.

## Tooling landscape

### Core visual stack

`Manim Community`

- Official docs show a mature animation framework, example gallery, and a voiceover guide.
- It is the best fit for precise educational visuals.
- It already matches your Nexus example.

`manim-voiceover`

- Official Manim docs point to the `manim-voiceover` plugin.
- It supports recording your own voice during rendering or using generated voices directly in Python.
- Good for timing animation to narration early in the pipeline.

`Remotion`

- Remotion explicitly positions itself as reusable video templates plus app and automation workflows.
- The `renderMedia()` API gives a clean programmatic rendering path.
- This is the strongest layer for turning raw explainer clips into social-native outputs.

`MoviePy`

- Still useful as a Python-native automation tool for trims, concatenation, and simple compositing.
- Good utility layer, but not the final opinionated packaging system.

`ffmpeg`

- Keep `ffmpeg` as the final low-level render/export engine.
- Use it for codec control, loudness normalization, crop variants, burn-in captions, contact sheets, and platform-specific exports.

### Speech, captions, and voice

`OpenAI speech-to-text`

- The current API supports `gpt-4o-transcribe`, `gpt-4o-mini-transcribe`, and a diarized model.
- Strong choice for transcription, draft captions, and narration QA.

`Whisper`

- Still a strong open-source default for multilingual ASR.
- Good fallback if you want local processing.

`WhisperX`

- Strong upgrade when you need word-level timestamps and cleaner caption timing.
- Especially useful for karaoke-style word highlights or tightly synced subtitle animation.

`OpenAI text-to-speech`

- Good narration quality, but these are built-in voices, not your own cloned voice.
- Best used for prototyping, drafts, or non-branded voices.

`ElevenLabs voice cloning`

- Fastest path to a polished clone of your own voice.
- Official docs separate Instant Voice Cloning from Professional Voice Cloning, with PVC being more accurate and customizable.

`Coqui TTS`

- Best open-source general-purpose TTS toolkit in the current landscape.
- Useful if you want local control and experimentation with voice cloning or multilingual workflows.

`F5-TTS`

- Promising open-source clone/generation option with CLI and finetune flows.
- Important caveat: the code is MIT, but pretrained models are under CC-BY-NC according to the repo, so commercial use needs a careful read.

### Optional AI video lanes

`Veo 3.1`

- Official Google docs say Veo 3.1 supports native audio, image-based direction, and video extension.
- Useful for highly specific hook shots or stylized intros, not as the main explanatory layer.

`HeyGen`

- Production-ready avatar and translation APIs.
- Good if you later want a presenter lane or localization lane.

## Publishing and channel operations

### YouTube

YouTube is the best first automation target.

- The official upload guide supports scripted uploads with OAuth 2.0 and metadata control.
- As of December 8, 2025, square or vertical uploads up to three minutes are categorized as Shorts.

This makes YouTube the easiest place to start fully automated publishing from the repo.

### TikTok

TikTok is publishable, but the workflow is more productized.

- TikTok's Content Posting API supports both direct posting and draft upload.
- The Direct Post flow can upload from local files or pull from a URL.
- TikTok also offers Creative Center and Creator tools that emphasize hooks, top-performing examples, and post-level diagnosis.

My read: automate export and prefill, then choose between direct post and draft flow depending how much last-mile editing you want in-app.

### Instagram Reels

Meta has official Reels Publishing and Instagram Content Publishing docs for Graph API workflows. Based on Meta's official docs surfaced in search, the Reels flow is a staged upload/publish process and the Instagram publishing docs cover reels as single media posts.

My read: this is doable, but should come after YouTube and TikTok because it is more account- and app-setup-sensitive.

## What people building these systems seem to agree on

Across official creator resources, current research, and open-source tool stacks, the consistent themes are:

- hooks matter disproportionately;
- scene segmentation beats one long summary;
- generated drafts need human review for factuality and tone;
- captions are not optional;
- strong educational shorts use explicit signaling, not just flashy motion;
- platform-native packaging matters as much as the explanation itself;
- shorts are great top-of-funnel, but weak as the only durable asset.

## Recommended stack for Content Maxxer

### Best current default

- `Research + script`: LLM plus paper parser.
- `Core visuals`: Manim.
- `Voice`: your recorded voice first, ElevenLabs PVC second, F5-TTS or Coqui only if we want local cloning.
- `Captions`: OpenAI speech-to-text or WhisperX for timing precision.
- `Packaging`: Remotion.
- `Finishing`: `ffmpeg`.
- `Publishing`: YouTube API first, TikTok API second, Instagram Reels API third.

### Why not only Manim

Pure Manim can make beautiful explainers, but it is not enough for a social channel by itself. You still need:

- caption animation;
- 9:16-safe layouts;
- titles and end cards;
- waveform or progress UI;
- thumbnail extraction;
- batch variant exports;
- publishing metadata.

That is exactly why Remotion belongs in the stack.

### Why not only text-to-video

Paper explainers fail when the visuals are ambiguous. AI video models are better used for tasteful hooks and transitions than for explaining optimizer geometry or paper figures.

## Recommended workflow upgrade

### Phase 1: make one great short reliably

1. Parse paper and extract abstract, claims, figures, equations, and hook candidates.
2. Generate three hook options.
3. Approve one hook and one takeaway sentence.
4. Build a five-beat script:
   hook, setup, mechanism, implementation, takeaway.
5. Map beats to scenes.
6. Render technical scenes in Manim.
7. Record your real voice or clone your voice from an approved sample.
8. Generate subtitles and align them to words.
9. Package in Remotion for 9:16, including captions and CTA.
10. Export with `ffmpeg`.
11. Upload to YouTube automatically and prepare TikTok/Instagram payloads.

### Phase 2: speed and scale

1. Build reusable scene components for common patterns:
   model box, data streams, before/after, loss curve, ablation grid, paper figure frame.
2. Add title card, subtitle, and end card templates in Remotion.
3. Add caption styling presets.
4. Add thumbnail generation and title suggestion.
5. Add platform-specific copy generation:
   title, caption, hashtags, CTA.

### Phase 3: channel system

1. Add a publishing queue.
2. Add A/B hook tracking.
3. Add a library of previous claims, visuals, and narration snippets.
4. Add slide-deck generation from the same research pack.

## Repo implications

Content Maxxer should evolve from "prompt plus scene file" into:

- `research pack`
- `hook generator`
- `script + storyboard builder`
- `manim scene renderer`
- `voice + caption pipeline`
- `remotion social packager`
- `distribution + publish layer`

That is the correct shape for a serious paper-explainer channel.

## Immediate implementation plan

1. Add a `distribution.md` template to each content job for per-platform title, caption, CTA, and hashtags.
2. Add a `voice.md` or `narration.md` file to each job for spoken script and clone/source notes.
3. Add a Remotion app inside the repo for vertical packaging.
4. Add caption generation and alignment commands.
5. Add a `publish` command that starts with YouTube.

## Sources

- Manim docs: [docs.manim.community](https://docs.manim.community/en/stable/)
- Manim voiceover guide: [Adding Voiceovers to Videos](https://docs.manim.community/en/stable/guides/add_voiceovers.html)
- Remotion homepage: [remotion.dev](https://www.remotion.dev/)
- Remotion render API: [renderMedia()](https://www.remotion.dev/docs/renderer/render-media)
- MoviePy docs: [zulko.github.io/moviepy](https://zulko.github.io/moviepy/)
- OpenAI speech-to-text: [developers.openai.com/api/docs/guides/speech-to-text](https://developers.openai.com/api/docs/guides/speech-to-text)
- OpenAI text-to-speech: [developers.openai.com/api/docs/guides/text-to-speech](https://developers.openai.com/api/docs/guides/text-to-speech)
- Whisper repo: [github.com/openai/whisper](https://github.com/openai/whisper)
- WhisperX repo: [github.com/m-bain/whisperx](https://github.com/m-bain/whisperx)
- ElevenLabs voice cloning docs: [elevenlabs.io/docs/eleven-creative/voices/voice-cloning](https://elevenlabs.io/docs/eleven-creative/voices/voice-cloning)
- Coqui TTS repo: [github.com/coqui-ai/TTS](https://github.com/coqui-ai/TTS)
- F5-TTS repo: [github.com/SWivid/F5-TTS](https://github.com/SWivid/F5-TTS)
- Gemini video docs: [ai.google.dev/gemini-api/docs/video](https://ai.google.dev/gemini-api/docs/video)
- HeyGen developer docs: [developers.heygen.com](https://developers.heygen.com/)
- YouTube upload API guide: [developers.google.com/youtube/v3/guides/uploading_a_video](https://developers.google.com/youtube/v3/guides/uploading_a_video)
- YouTube Shorts help: [support.google.com/youtube/answer/15424877](https://support.google.com/youtube/answer/15424877?hl=en)
- TikTok Content Posting API overview: [developers.tiktok.com/products/content-posting-api](https://developers.tiktok.com/products/content-posting-api/)
- TikTok Content Posting API guide: [developers.tiktok.com/doc/content-posting-api-get-started](https://developers.tiktok.com/doc/content-posting-api-get-started)
- TikTok Creative Center: [ads.tiktok.com/help/article/creative-center](https://ads.tiktok.com/help/article/creative-center?lang=en)
- TikTok Video Assistant: [seller-us.tiktok.com Video Assistant](https://seller-us.tiktok.com/university/essay?knowledge_id=4940922363217678)
- TikTok Good Quality Guide: [seller-us.tiktok.com Good Quality Video Guide](https://seller-us.tiktok.com/university/essay?knowledge_id=4963086610204471)
- Meta Reels Publishing API: [developers.facebook.com/documentation/video-api/guides/reels-publishing](https://developers.facebook.com/documentation/video-api/guides/reels-publishing)
- Meta Instagram Content Publishing: [developers.facebook.com/documentation/instagram-platform/content-publishing](https://developers.facebook.com/documentation/instagram-platform/content-publishing)
- PaperTok (CHI 2026): [arXiv HTML](https://arxiv.org/html/2601.18218v1)
- ReelsEd / The Reel Deal (2025): [arXiv HTML](https://arxiv.org/html/2509.05962v1)
- Shorts vs. Regular Videos on YouTube (2024): [arXiv HTML](https://arxiv.org/html/2403.00454v1)
- Shorts on the Rise (2024): [arXiv HTML](https://arxiv.org/html/2402.18208v1)
- Signaling meta-analysis (2018): [ScienceDirect abstract](https://www.sciencedirect.com/science/article/pii/S1747938X17300581)
