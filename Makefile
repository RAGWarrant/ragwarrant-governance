.PHONY: setup test reproduce-crag reproduce-multihop reproduce-public-mini tables figures validate-brand validate-open-core validate-publication validate-deployment-readiness docker-build docker-validate docker-run-public-mini docker-compose-public-mini docker-run-external-evaluator-demo clean

setup:
	pip install --require-hashes -r requirements-dev.lock
	pip install -e .

test:
	pytest -q tests/publication

reproduce-crag:
	bash scripts/reproduce_crag_mock_api.sh

reproduce-multihop:
	bash scripts/reproduce_multihop_confirmatory.sh

reproduce-public-mini:
	python3 scripts/run_public_mini_reproduction.py --config configs/experiments/ragwarrant_public_mini_reproduction_v1.yaml --output-root artifacts/public_mini_reproduction --force
	python3 scripts/validate_publication_bundle.py
	python3 scripts/validate_brand_consistency.py

reproduce-dataset-matrix:
	bash scripts/reproduce_dataset_matrix.sh

tables:
	python scripts/make_tables.py

figures:
	python scripts/make_figures.py

validate-brand:
	python scripts/validate_brand_consistency.py

validate-open-core:
	python scripts/validate_license_headers.py
	python scripts/validate_open_core_boundary.py

validate-publication:
	python scripts/validate_publication_bundle.py
	python scripts/validate_brand_consistency.py
	python scripts/validate_license_headers.py
	python scripts/validate_open_core_boundary.py

validate-deployment-readiness:
	python scripts/validate_deployment_readiness.py --config configs/experiments/ragwarrant_deployment_readiness_v1.yaml --output-root artifacts/deployment_readiness --force

docker-build:
	docker build -t ragwarrant-governance:local .

docker-validate:
	docker run --rm ragwarrant-governance:local validate-bundle

docker-run-public-mini:
	mkdir -p docker_outputs
	docker run --rm -v "$$(pwd)/docker_outputs:/outputs" ragwarrant-governance:local run-governance-job --config configs/jobs/public_mini_governance_job.yaml --output-root /outputs --decision-out /outputs/promotion_decision.json

docker-compose-public-mini:
	mkdir -p docker_outputs
	docker compose -f docker/compose.public-mini.yml up --build --abort-on-container-exit --exit-code-from ragwarrant-public-mini

docker-run-external-evaluator-demo:
	mkdir -p docker_outputs
	docker run --rm -v "$$(pwd)/docker_outputs:/outputs" ragwarrant-governance:local run-external-evaluator-demo --output-root /outputs/external_evaluator_adapters

package-for-approval:
	bash scripts/package_for_approval.sh

clean:
	rm -rf .pytest_cache __pycache__
