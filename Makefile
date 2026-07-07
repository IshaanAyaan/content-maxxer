.PHONY: setup doctor new render-nexus render

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
