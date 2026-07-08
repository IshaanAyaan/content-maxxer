.PHONY: setup doctor new render-nexus render package-nexus demo-video director-gradient director-nexus evaluate-nexus evaluate-demo evaluate-director-gradient evaluate-director-nexus test

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
	. .venv/bin/activate && content-maxxer director --slug gradient_descent_director --title "Gradient Descent" --idea "Gradient descent is how a model improves by reading the slope of the loss curve, taking a controlled downhill step, and repeating until it settles near a minimum." --format vertical --duration 32 --quality production --force

director-nexus:
	. .venv/bin/activate && content-maxxer director --slug nexus_director --title "Nexus" --idea "Nexus shows why two models can have the same pretraining loss but land in different optimization basins, and why downstream tasks care about the route through the landscape rather than only the score." --source-url "https://arxiv.org/pdf/2604.09258" --format vertical --duration 35 --quality production --force

evaluate-nexus:
	. .venv/bin/activate && content-maxxer evaluate nexus_explainer_h --format vertical --quality draft

evaluate-demo:
	. .venv/bin/activate && content-maxxer evaluate gradient_descent_simple --format vertical --quality draft

evaluate-director-gradient:
	. .venv/bin/activate && content-maxxer evaluate gradient_descent_director --format vertical --quality production --director

evaluate-director-nexus:
	. .venv/bin/activate && content-maxxer evaluate nexus_director --format vertical --quality production --director

test:
	. .venv/bin/activate && python -m unittest discover -s tests
