.PHONY: setup doctor new render-nexus render package-nexus demo-video evaluate-nexus evaluate-demo test

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

evaluate-nexus:
	. .venv/bin/activate && content-maxxer evaluate nexus_explainer_h --format vertical --quality draft

evaluate-demo:
	. .venv/bin/activate && content-maxxer evaluate gradient_descent_simple --format vertical --quality draft

test:
	. .venv/bin/activate && python -m unittest discover -s tests
