.PHONY: test test-rag test-rag-retrieval test-rag-coverage test-graph test-api test-simulator graph-paths scenarios demo eval build up down k8s-dry-run impact install-hooks pre-commit-check

PY = cd ops-agent && .venv/bin/python
SIM_PY = $(PY)

test:
	$(PY) -m pytest tests/ -q

test-rag-retrieval:
	$(PY) -m pytest tests/test_rag.py tests/test_hybrid_retrieval.py \
	  tests/rag_eval/test_retrieval_golden.py tests/rag_eval/test_retrieve_runbooks_node.py \
	  tests/rag_eval/test_golden_select.py -q

test-rag-coverage:
	$(PY) -m pytest tests/test_runbook_match_policy.py tests/test_diagnosis_confidence_policy.py tests/test_eval_schemas.py \
	  tests/test_rag_integration.py tests/rag_eval/test_coverage_golden.py \
	  tests/rag_eval/test_real_llm_smoke.py -q

test-rag: test-rag-retrieval test-rag-coverage

test-graph:
	cd ops-agent && CHECKPOINTER=memory LLM_MODE=mock .venv/bin/python -m pytest tests/graph_paths/ -q

test-api:
	$(PY) -m pytest tests/test_eval.py tests/test_tracing.py tests/test_health.py -q

test-simulator:
	cd ops-backend-simulator && ../ops-agent/.venv/bin/python -m pytest tests/ -q

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

impact-staged:
	python3 scripts/change_impact.py --staged

pre-commit-check:
	python3 scripts/change_impact.py --staged --run

install-hooks:
	git config core.hooksPath .githooks
	chmod +x .githooks/pre-commit
	@echo "Installed: git core.hooksPath=.githooks (pre-commit runs path-based tests)"
