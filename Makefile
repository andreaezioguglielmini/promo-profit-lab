.PHONY: install test lint demo data analyze eval eval-live

install:
	pip install -e ".[app,dev]"

test:
	pytest -q

lint:
	ruff check src tests app

data:
	promolab simulate data/synthetic/demo

analyze:
	promolab analyze data/synthetic/demo --trace

demo:
	streamlit run app/streamlit_app.py

eval:
	python -m promolab.evals --policy scripted

eval-live:
	python -m promolab.evals --policy claude
