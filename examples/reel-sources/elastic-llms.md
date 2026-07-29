# Elastic LLMs: one model, many sizes

Google's Gemma 3n is built on the MatFormer (Matryoshka Transformer) architecture, a nested transformer for elastic inference in which a larger model contains smaller, fully functional versions of itself, the way Matryoshka dolls nest inside each other.

During MatFormer training of Gemma 3n's E4B model, a smaller E2B sub-model is simultaneously optimized inside it, so developers can download either the main E4B model or the already-extracted standalone E2B sub-model, which offers up to 2x faster inference.

The model sizes are named for effective parameters: E2B and E4B have raw parameter counts of 5 billion and 8 billion respectively, but architectural innovations let them run with a memory footprint comparable to traditional 2B and 4B models, operating in as little as 2GB (E2B) and 3GB (E4B) of memory.

Between the two endpoints, a method called Mix-n-Match creates a spectrum of custom-sized models from the one trained E4B model by adjusting the feed-forward hidden dimension per layer (from 8192 to 16384) and selectively skipping some layers, so a developer can slice a size tuned to specific hardware constraints without any retraining.

Google says the MatFormer architecture also paves the way for elastic execution, where a single deployed model could dynamically switch between the E4B and E2B inference paths on the fly, but states this capability is not part of the launched implementations, so it remains a stated direction rather than a shipped feature.

NVIDIA's Flextron research applies the same many-in-one idea to existing models: it systematically transforms an already-trained LLM into an elastic model with nested elastic MLP and elastic attention layers, supports user-defined latency and accuracy targets at inference with no additional fine-tuning, and its sample-efficient training used only 7.63% of the tokens consumed in the original pretraining.

The consequence of this direction is that the traditional practice of training a separate model for every deployment size is being replaced by one training run that yields a whole family of models, though each elastic system still has to prove its sliced sub-models match separately trained models of the same size on quality.

Primary reference: Google Developers Blog, "Introducing Gemma 3n: The developer guide," June 26, 2025, https://developers.googleblog.com/en/introducing-gemma-3n-developer-guide/

Primary reference: Devvrit et al., "MatFormer: Nested Transformer for Elastic Inference," arXiv, 2023, https://arxiv.org/abs/2310.07707

Primary reference: Cai et al. (NVIDIA), "Flextron: Many-in-One Flexible Large Language Model," arXiv, 2024, https://arxiv.org/abs/2406.10260
