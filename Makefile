.PHONY: test test-rag test-graph graph-paths scenarios demo eval build up down k8s-dry-run impact

PY = cd ops-agent && .venv/bin/python

test:
	$(PY) -m pytest tests/ -q

test-rag:
	$(PY) -m pytest tests/test_rag.py tests/test_runbook_eval_policy.py \
	  tests/test_hybrid_retrieval.py tests/test_rag_integration.py tests/rag_eval/ -q

test-graph:
	cd ops-agent && CHECKPOINTER=memory LLM_MODE=mock .venv/bin/python -m pytest tests/graph_paths/ -q

graph-paths: test-graph

scenarios:
	cd ops-agent && CHECKPOINTER=memory LLM_MODE=real .venv/bin/python scripts/run_scenarios.py --scenarios all

demo:
	cd ops-agent && CHECKPOINTER=memory .venv/bin/python scripts/demo.py

eval:
	cd ops-agent && CHECKPOINTER=memory .venv/bin/python eval/run_eval.py

build:
	docker compose -f deploy/docker-compose.yml build

up:
	docker compose -f deploy/docker-compose.yml up -d

down:
	docker compose -f deploy/docker-compose.yml down

k8s-dry-run:
	kubectl apply --dry-run=client -f deploy/k8s/

impact:
	python3 scripts/change_impact.py
