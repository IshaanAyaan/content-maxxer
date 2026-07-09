.PHONY: setup doctor new render-nexus render package-nexus demo-video director-gradient director-nexus director-llm slides-llm slides-nexus slides-agents evaluate-nexus evaluate-demo evaluate-director-gradient evaluate-director-nexus evaluate-director-llm evaluate-slides-llm evaluate-slides-nexus evaluate-slides-agents test

setup:
	python3 -m venv .venv
	. .venv/bin/activate && pip install -e .

doctor:
	. .venv/bin/activate && content-maxxer doctor

new:
	. .venv/bin/activate && content-maxxer new demo_explainer --title "Demo Explainer" --source-url "https://example.com/source.pdf"

render-nexus:
	. .venv/bin/activate && content-maxxer render nexus_explainer_h --quality draft

render:
	. .venv/bin/activate && content-maxxer render demo_explainer --quality draft

package-nexus:
	. .venv/bin/activate && content-maxxer package nexus_explainer_h --format vertical --duration 25 --quality draft

demo-video:
	. .venv/bin/activate && content-maxxer make-video --slug gradient_descent_simple --title "Gradient Descent" --idea "Gradient descent improves a model by taking small downhill steps." --format vertical --duration 22 --quality draft --force

director-gradient:
	. .venv/bin/activate && content-maxxer director --slug gradient_descent_director --title "Gradient Descent" --idea "Gradient descent is how a model improves by reading the slope of the loss curve, taking a controlled downhill step, and repeating until it settles near a minimum." --format vertical --duration 32 --speed 1.75 --quality production --force

director-nexus:
	. .venv/bin/activate && content-maxxer director --slug nexus_director --title "Nexus" --idea "Nexus shows why two models can have the same pretraining loss but land in different optimization basins, and why downstream tasks care about the route through the landscape rather than only the score." --source-url "https://arxiv.org/pdf/2604.09258" --format vertical --duration 35 --speed 1.75 --quality production --force

director-llm:
	. .venv/bin/activate && content-maxxer director --slug large_language_models_director --title "How Large Language Models Work" --idea "Explain how large language models work: text becomes tokens, tokens become vectors, attention mixes context, transformer layers refine meaning, the model predicts the next token, and repeating that loop creates an answer." --format vertical --duration 48 --speed 1.75 --quality production --force

slides-llm:
	. .venv/bin/activate && content-maxxer slides --slug large_language_models_slides --title "How Large Language Models Work" --idea "Explain how large language models work: text becomes tokens, tokens become vectors, attention mixes context, transformer layers refine meaning, the model predicts the next token, and repeating that loop creates an answer." --platform tiktok --quality production --force

slides-nexus:
	. .venv/bin/activate && content-maxxer slides --slug nexus_slides --title "Nexus" --idea "Nexus shows why two models can have the same pretraining loss but land in different optimization basins, and why downstream tasks care about the route through the landscape rather than only the score." --source-url "https://arxiv.org/pdf/2604.09258" --platform tiktok --quality production --force

slides-agents:
	. .venv/bin/activate && content-maxxer slides --slug ai_agents_reliability_slides --title "AI Agents Are Not Employees Yet" --idea "Explain why AI agents are overhyped: benchmark scores are improving, but real-world reliability still depends on consistency, robustness, cost, predictable failure, and human supervision." --source-url "https://hai.stanford.edu/ai-index/2026-ai-index-report/technical-performance" --platform tiktok --quality production --force

evaluate-nexus:
	. .venv/bin/activate && content-maxxer evaluate nexus_explainer_h --format vertical --quality draft

evaluate-demo:
	. .venv/bin/activate && content-maxxer evaluate gradient_descent_simple --format vertical --quality draft

evaluate-director-gradient:
	. .venv/bin/activate && content-maxxer evaluate gradient_descent_director --format vertical --quality production --director

evaluate-director-nexus:
	. .venv/bin/activate && content-maxxer evaluate nexus_director --format vertical --quality production --director

evaluate-director-llm:
	. .venv/bin/activate && content-maxxer evaluate large_language_models_director --format vertical --quality production --director

evaluate-slides-llm:
	. .venv/bin/activate && content-maxxer evaluate-slides large_language_models_slides --platform tiktok --quality production

evaluate-slides-nexus:
	. .venv/bin/activate && content-maxxer evaluate-slides nexus_slides --platform tiktok --quality production

evaluate-slides-agents:
	. .venv/bin/activate && content-maxxer evaluate-slides ai_agents_reliability_slides --platform tiktok --quality production

test:
	. .venv/bin/activate && python -m unittest discover -s tests
