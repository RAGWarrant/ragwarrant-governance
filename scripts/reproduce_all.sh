#!/usr/bin/env bash
# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

python scripts/validate_publication_bundle.py
bash scripts/reproduce_dataset_matrix.sh
bash scripts/reproduce_multihop_confirmatory.sh
bash scripts/reproduce_crag_mock_api.sh
