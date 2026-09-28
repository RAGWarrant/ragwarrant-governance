# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

import pytest

torch = pytest.importorskip("torch")


@pytest.mark.gpu
def test_cuda_available_for_gpu_smoke():
    assert torch.cuda.is_available()

