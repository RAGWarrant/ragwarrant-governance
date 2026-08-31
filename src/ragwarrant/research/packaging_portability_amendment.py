"""Read-only verification for the research packaging-portability amendment.

This module verifies tracked packaging policy and additive hash bindings.  It
does not import or invoke benchmark simulation, evidence generation, FULL,
drand, a network client, or workflow code.  Verification of the ignored
confirmation materialization is opt-in and delegates only to the qualified
read-only provenance verifier after taking a byte-level snapshot.
"""

from __future__ import annotations

import hashlib
import ast
import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Mapping, Sequence


AMENDMENT_ID = "RAGWARRANT-RESEARCH-PACKAGING-PORTABILITY-001"
AMENDMENT_TYPE = "NONSCIENTIFIC_PACKAGING_AND_CLEAN_CHECKOUT_TEST_PORTABILITY"
SCHEMA_VERSION = "ragwarrant_research_packaging_portability_amendment.v1"
DEFAULT_RECORD_PATH = "configs/research/packaging_portability_amendment_v1.json"
INTEGRITY_RECORD_PATH = "configs/research/packaging_integrity_amendment_v2.json"

INTEGRITY_AMENDMENT_ID = "RAGWARRANT-PACKAGING-INTEGRITY-002"
INTEGRITY_AMENDMENT_TYPE = (
    "TRUST_ROOT_REBINDING_AND_PATH_CONTAINMENT_HARDENING"
)
FOCUS1_CHECKPOINT_COMMIT = "124836bcc2fba48373d7bd08f0087b23f2e41620"
FOCUS1_DETACHED_AUTHORITY_AMENDMENT_ID = (
    "RAGWARRANT-FOCUS1-DETACHED-AUTHORITY-001"
)
FOCUS1_DETACHED_AUTHORITY_AMENDMENT_TYPE = "DETACHED_PINNED_CHECKPOINT_AUTHORITY"
FOCUS1_AUTHORITY_RECORD_PATH = (
    "configs/research/focus1_detached_authority_v1.json"
)
FOCUS1_AUTHORITY_REF = "refs/tags/ragwarrant-focus1-freeze-v1-c771afc"
FOCUS1_AUTHORITY_PARENT_RECORD_SHA256 = (
    "8e8e00752f0f573df8b51943c9fc05acd8cfa754822e1fe81b5c44609e801183"
)
FOCUS1_AUTHORITY_REBOUND_PATH = (
    "src/ragwarrant/research/packaging_portability_amendment.py"
)
FOCUS1_AUTHORITY_PRIOR_VERIFIER_SHA256 = (
    "2a23b19965b551f79a8fc715167973db3435874832ab5dd86035bd4bb0b442db"
)
FOCUS1_AUTHORITY_REBOUND_TEST_PATH = (
    "tests/research/test_packaging_portability_amendment.py"
)
FOCUS1_AUTHORITY_PRIOR_TEST_SHA256 = (
    "4d85418c6a3e1dad8149da6be5210e64ec000555a93f8b1ee2b6bf0c66e51058"
)
FOCUS1_AUTHORITY_REBOUND_GITATTRIBUTES_PATH = ".gitattributes"
FOCUS1_AUTHORITY_PRIOR_GITATTRIBUTES_SHA256 = (
    "ad661a962b8ff9f6d834833c0a6995e96a26bc6ff0cd6f2bc0445916458f9e37"
)
FOCUS1_AUTHORITY_REBOUND_V1_GUARD_TEST_PATH = (
    "tests/research/test_focus2_v2_benchmark_integration.py"
)
FOCUS1_AUTHORITY_PRIOR_V1_GUARD_TEST_SHA256 = (
    "8609a9ceebff2caea3fde1c343e3aa39ae425300c6be71b0336f252ff7d0fd24"
)
FOCUS1_AUTHORITY_REBOUND_EVIDENCE_PLANNER_TEST_PATH = (
    "tests/research/test_evidence_budget_planner.py"
)
FOCUS1_AUTHORITY_PRIOR_EVIDENCE_PLANNER_TEST_SHA256 = (
    "6e931e3c2ac2f9fc5fb59cde675513b51118d9da907ed097e12a7c71633b5f8a"
)
FOCUS1_AUTHORITY_REBOUND_STRATIFIED_TEST_PATH = (
    "tests/research/test_stratified_joint_warrant_power.py"
)
FOCUS1_AUTHORITY_PRIOR_STRATIFIED_TEST_SHA256 = (
    "a6f738edcbbc20570243a7e5b4eb599202968ddc01a385ec33b9b67d8a403fb4"
)
FOCUS1_AUTHORITY_REBOUND_CONFIRMATION_TEST_PATH = (
    "tests/research/test_joint_power_confirmation.py"
)
FOCUS1_AUTHORITY_PRIOR_CONFIRMATION_TEST_SHA256 = (
    "de883b6ca7d6fd60545b1383360a6246c84c3e00d1615ac05f07bb7ffda8d0ef"
)
LINEAGE_CHECKPOINT = "LINEAGE_CHECKPOINT"
DETACHED_PINNED_CHECKPOINT = "DETACHED_PINNED_CHECKPOINT"

# Accepted 36-path inventory independently reconstructed from raw blobs at the
# checkpoint.  It keeps clean-checkout test plumbing independent of Git history
# depth while the packaging verifier itself still audits the checkpoint object.
FOCUS1_CHECKPOINT_INPUT_SHA256: Mapping[str, str] = {
    ".github/drand-verifier/package-lock.json": "956b72022cf6f01d30be2c31a077e02200dc741f5730818e8608f31ee86fe80e",
    ".github/drand-verifier/package.json": "f0b0cc73ba14fa249f97c60b83a9fcccb6099c0c69c925c18421cbada942f2d9",
    ".github/drand-verifier/historical_quicknet_round_1.json": "67cd42b915a87e08070004e110985b2b46fc215b85dcc2a4fbeb9d7fe3a5e85c",
    ".github/drand-verifier/verify_historical_fixture.mjs": "850c4091586ed6a2dd2c50caaa653e118b6ef3656a0f2a82f93744beca1bab6d",
    ".github/drand-verifier/verify_github_oidc.mjs": "e836c609f0fe2a114ae8e723301739d7eff645b0a695528bb2ec67e05beecc57",
    ".github/drand-verifier/verify_quicknet.mjs": "230bc859ebf17b80351f4e755153cda22e0c7321ff40c4869d5898e36f567ff3",
    ".github/drand-verifier/verify_receipt_signature.mjs": "13c89b8bd8dd2eb12d5eedb8945aa90db13599dff2b5b90b9c049dbe705e1bf3",
    ".github/workflows/research-full-closure.yml": "a0ffdcec1c5b173469b7c54439330406c8336f618e4420a1a4d1b3d544ea56e6",
    ".github/workflows/research-full-execute.yml": "d3e30030cd910425bb9eee2b0eb90d70442cec7d0897dd36c5ee2a3fb1691a89",
    ".github/workflows/research-full-reconciler.yml": "9ee392238f4ec1a5a8835a08c457d685aeb8f86253d7adb0c1edf21d554bd130",
    ".github/workflows/research-full-seal.yml": "94b4df4a32839318487506f16b0cb2c226261d29844c2a0a8f203907f187206a",
    "configs/research/false_promotion_benchmark_v1.yaml": "4469bb06123796cb71103c2ec0b105e444167fe2b7e538193288ba22d916920a",
    "docs/research/false_promotion_benchmark_full_entropy_drand_amendment.md": "14618686523a420f840b810e3107d177c6299fb1eb9e4a35d01bf4d3b68c577f",
    "docs/research/false_promotion_benchmark_protocol.md": "6d661b06d49f31d40ac21a5cc0516e9f61c6e084514c1ac1838b36f6693686ad",
    "docs/research/false_promotion_benchmark_seed_schedule_v2_amendment.md": "9ffcb40dae4e8740e6f944d817e3f9a384d3ce53c4c2c3fa154bc91895447628",
    "docs/research/fixed_sample_promotion_warrant_design.md": "c11d0c530462d1f86d104c7250d8f1884ff6d8831a2594b6c0173fa950af93c3",
    "scripts/build_full_publication_closure.py": "47c367acb451bdb0b5811be9d170a80f284a1d2b07ae5c8ee2396efef4bcd3e2",
    "scripts/generate_benchmark_freeze_manifest.py": "f6c4d5cc7a886daba43760b97b540f078d5eb113f8ba02c4baa4fe7918bf9105",
    "scripts/generate_seed_schedule_v2_manifest.py": "f0f09638bac4f6d2c04384fae71db0187393234fa554512d25aecd0bb7ec63f4",
    "scripts/prepare_full_beacon_seal.py": "0d0f626dc59033295d2e2c74e212b098be5b28e7bbad27c35c3c560373c97f6d",
    "scripts/run_false_promotion_benchmark.py": "763fa4d52e7019afa323394eeff5e0b6e22b9f480df763aa55a96e8f1f560471",
    "scripts/run_sealed_full_benchmark.py": "bdff85b39009338b4c916afdd2260ecc8549645da5a29be56c8ef598874ffe47",
    "src/ragwarrant/research/benchmark.py": "b5d2f6e293812109da0467415c26c99f68c78e6032e35a17169bd51e369d70b0",
    "src/ragwarrant/research/methods.py": "fa92da3f06e6faefd77f0c84b07c66dbf1a6024edced86735ced8ea1250b77c1",
    "src/ragwarrant/research/public_beacon.py": "ee17e10f8747b931da09c0745b1d2b6eeb547e4ce4622efba6a581e01e41c2a3",
    "src/ragwarrant/research/reporting.py": "56bec0ef53012f6ebd35387f5e2717659153b354b228cf9f034076215be2203f",
    "src/ragwarrant/research/seed_schedule.py": "1083c32e750b87f3b4876b6685d9cf25a97d0b765181af03f3a2ac60c4411aba",
    "src/ragwarrant/research/simulator.py": "39a4e7ffee0670d57dd58f7c49126a3e9834f7672c05adec3a4a5063bc8f852d",
    "src/ragwarrant/research/types.py": "2cd9e4285aa978a029562d2545f49bc48893199c2595a15e8307e59f06443c2e",
    "tests/research/test_benchmark_controls.py": "db9e58304fbfc46541ba0276d25a82f385824aa3a5f2fe6f1adb7e6c08d3c7d4",
    "tests/research/test_benchmark_reproducibility.py": "8b37dd4e9b6b64857f5363e9525239fd1af679ae0972dd0f7920243a78ec54e3",
    "tests/research/test_method_contract.py": "314182deec71c5cd3b0f6d4467720ccf2bae98c0d8745e7741bcc67aecab9a3d",
    "tests/research/test_output_contract.py": "0e331305c7e695e76279dc3757588150f4aff26d9fefc890f19c78e8c404d6ac",
    "tests/research/test_public_beacon_entropy.py": "b12134ca00aed52aaf19e6b0ef0151a8792c02bf18063355ecd0dcd214010e66",
    "tests/research/test_seed_schedule_v2.py": "af5232bae9ab8a81d5b946afe28b3bbce2d497dab5b72ba609b6686f5ff3638e",
    "tests/research/test_simulator_truth.py": "920fcd653e551f3c86be012ce9abf4b11b9160ef1142df133dcee8eaea4f8665",
}

FOCUS1_DIGEST = "c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e"
V1_FROZEN_COMMIT = "bf3b3331b623afbdaed295919b3ac945c10692f6"
ORIGINAL_OUTPUT_SET_SHA256 = (
    "a6ff12e61dc800be65c089cdb7cbe8aca68339a53af08d6ac1bbc95db8a57493"
)

FROZEN_YAML_SHA256 = {
    "configs/research/fixed_sample_multi_risk_warrant_v2.yaml": (
        "9ea78712a5ab0cee58982cec0cd2d69bc363d2c3c084d9507e54416dc18d1238"
    ),
    "configs/research/fixed_sample_multi_risk_warrant_v2_iut_holm.yaml": (
        "b396bff282fb80ee2c9258caec1342862417b3dc92d3c30f208d9009267a1566"
    ),
}
PRESERVED_BLANK_EOF_INPUT_SHA256 = {
    "docs/research/operational_contract_template.md": (
        "8a0b3a1162713b17221af68437f7dd0792c76dd09d07557233aa716a4572212a"
    ),
    "src/ragwarrant/research/joint_power_confirmation.py": (
        "d86f10a0d0267a170c40c01d912ca625e906244ef3f7ecfdc4ada82ebf5c8164"
    ),
}
REQUIRED_WHITESPACE_ATTRIBUTE = "whitespace=-blank-at-eof"
REQUIRED_GITATTRIBUTES_RULES = {
    path: REQUIRED_WHITESPACE_ATTRIBUTE
    for path in {**FROZEN_YAML_SHA256, **PRESERVED_BLANK_EOF_INPUT_SHA256}
}

# This authority is deliberately explicit and closed.  It is not derived from
# Git status, untracked files, globs, staged paths, or current workspace hashes.
# Accepted replacement hashes remain in the signed-off amendment record and
# are checked against current bytes.  The verifier source itself is ultimately
# trusted through the reviewed Git commit and CI execution; this module does
# not claim to cryptographically attest its own executable source.
AUTHORIZED_REBINDING_METADATA: Mapping[str, Mapping[str, Any]] = {
    ".gitattributes": {
        "prior_path": ".gitattributes",
        "prior_sha256": "fcd6699b9b87914dc5b92aa5e986696b883c6c24a7722d6bfde3679b8213c66c",
        "change_category": "GIT_WHITESPACE_POLICY",
    },
    "pyproject.toml": {
        "prior_path": "pyproject.toml",
        "prior_sha256": "e816c8eb3aff7ba6454e63f81f11636c310f47c630d8021e305bd58655c48d45",
        "change_category": "PYTEST_MARKER_REGISTRATION",
    },
    "tests/research/conftest.py": {
        "prior_path": None,
        "prior_sha256": None,
        "change_category": "OPTIONAL_LOCAL_DEPENDENCY_PORTABILITY",
    },
    "tests/research/test_joint_power_confirmation.py": {
        "prior_path": "tests/research/test_joint_power_confirmation.py",
        "prior_sha256": "a76ea9bfac13a433d81b72756dbe7d795f26f911d38c6e19e162f5a2e3f39fab",
        "change_category": "CLEAN_CHECKOUT_TEST_PORTABILITY",
    },
    "tests/research/test_confirmation_provenance_amendment.py": {
        "prior_path": "tests/research/test_confirmation_provenance_amendment.py",
        "prior_sha256": "14d5fbebba40b2773a3cb710c0686fda9fedb0b42d5c53c023f396d489bb9a8c",
        "change_category": "CLEAN_CHECKOUT_TEST_PORTABILITY",
    },
    "src/ragwarrant/research/packaging_portability_amendment.py": {
        "prior_path": None,
        "prior_sha256": None,
        "change_category": "ADDITIVE_READ_ONLY_VERIFIER",
    },
    "scripts/verify_packaging_portability.py": {
        "prior_path": None,
        "prior_sha256": None,
        "change_category": "ADDITIVE_READ_ONLY_VERIFICATION_COMMAND",
    },
    "tests/research/test_packaging_portability_amendment.py": {
        "prior_path": None,
        "prior_sha256": None,
        "change_category": "PORTABILITY_VERIFIER_TESTS",
    },
    "docs/research/packaging_portability_amendment_v1.md": {
        "prior_path": None,
        "prior_sha256": None,
        "change_category": "PORTABILITY_PROTOCOL_DOCUMENTATION",
    },
    "docs/research/packaging_integrity_amendment_v2.md": {
        "prior_path": None,
        "prior_sha256": None,
        "change_category": "PACKAGING_INTEGRITY_DOCUMENTATION",
    },
}
REQUIRED_REBINDING_PATHS = frozenset(AUTHORIZED_REBINDING_METADATA)

# These accepted replacement hashes are independent constants for every
# non-executable authority entry.  The verifier implementation and its record
# cannot non-circularly authenticate themselves; they are intentionally bound
# by the reviewed Git commit/CI trust model documented by amendment 002.
AUTHORIZED_REPLACEMENT_SHA256: Mapping[str, str] = {
    ".gitattributes": "ad661a962b8ff9f6d834833c0a6995e96a26bc6ff0cd6f2bc0445916458f9e37",
    "pyproject.toml": "30e47dc1ae5f43011ad79293120b01f1d68fa325ddadaedfea1f3c8d2822ab35",
    "tests/research/conftest.py": "846d97e00cb9576b301f9c91ce5a519723d94033c5ff1180cca63eadb2a4e384",
    "tests/research/test_joint_power_confirmation.py": "de883b6ca7d6fd60545b1383360a6246c84c3e00d1615ac05f07bb7ffda8d0ef",
    "tests/research/test_confirmation_provenance_amendment.py": "a4585f69fe65c784af4714adcbe2a369d0576f854ca5d5c93d9bf02d81994f0e",
    "scripts/verify_packaging_portability.py": "20eca83905cade2f723f50f1fbd6e2a5352574524b8091ddf47ecde0320065fa",
    "tests/research/test_packaging_portability_amendment.py": "4d85418c6a3e1dad8149da6be5210e64ec000555a93f8b1ee2b6bf0c66e51058",
    "docs/research/packaging_portability_amendment_v1.md": "c54fbb2ee0ed129d70e0250cc3e7e47d4d5a844c49ddc45ee7caa21c318cdfbf",
    "docs/research/packaging_integrity_amendment_v2.md": "93a980f600bb18fb2806e4f9eb6b55f39826cceddc150e6043a064a6dfbb1e53",
}

PROHIBITED_REBINDING_PREFIXES = (
    "artifacts/",
    "results/",
    "src/ragwarrant/research/fixed_sample_warrant",
    "src/ragwarrant/research/simulator.py",
    "src/ragwarrant/research/methods.py",
    "src/ragwarrant/research/benchmark.py",
    "configs/research/false_promotion_benchmark",
    "configs/research/seed",
)

PACKAGING_PORTABILITY_VERIFIED = "PACKAGING_PORTABILITY_VERIFIED"
PACKAGING_PORTABILITY_INCOMPLETE = "PACKAGING_PORTABILITY_INCOMPLETE"
PACKAGING_PORTABILITY_HASH_MISMATCH = "PACKAGING_PORTABILITY_HASH_MISMATCH"
PACKAGING_PORTABILITY_POLICY_MISMATCH = "PACKAGING_PORTABILITY_POLICY_MISMATCH"
PACKAGING_PORTABILITY_WORKSPACE_MISMATCH = (
    "PACKAGING_PORTABILITY_WORKSPACE_MISMATCH"
)
PACKAGING_REBINDING_UNAUTHORIZED_PATH = "PACKAGING_REBINDING_UNAUTHORIZED_PATH"
PACKAGING_REBINDING_EXTRA_AUTHORITY_ENTRY = (
    "PACKAGING_REBINDING_EXTRA_AUTHORITY_ENTRY"
)

FOCUS1_AUTHORITY_VERIFIED = "FOCUS1_AUTHORITY_VERIFIED"
FOCUS1_AUTHORITY_VERIFIED_LINEAGE = "FOCUS1_AUTHORITY_VERIFIED_LINEAGE"
FOCUS1_AUTHORITY_VERIFIED_DETACHED = "FOCUS1_AUTHORITY_VERIFIED_DETACHED"
FOCUS1_AUTHORITY_CHECKPOINT_MISSING = "FOCUS1_AUTHORITY_CHECKPOINT_MISSING"
FOCUS1_AUTHORITY_TAG_MISSING = "FOCUS1_AUTHORITY_TAG_MISSING"
FOCUS1_AUTHORITY_TAG_NOT_ANNOTATED = "FOCUS1_AUTHORITY_TAG_NOT_ANNOTATED"
FOCUS1_AUTHORITY_TAG_TARGET_MISMATCH = "FOCUS1_AUTHORITY_TAG_TARGET_MISMATCH"
FOCUS1_AUTHORITY_COMMIT_MISSING = "FOCUS1_AUTHORITY_COMMIT_MISSING"
FOCUS1_AUTHORITY_OBJECT_TYPE_INVALID = "FOCUS1_AUTHORITY_OBJECT_TYPE_INVALID"
FOCUS1_AUTHORITY_CHECKPOINT_DIGEST_MISMATCH = (
    "FOCUS1_AUTHORITY_CHECKPOINT_DIGEST_MISMATCH"
)
FOCUS1_AUTHORITY_CANDIDATE_PATH_SET_MISMATCH = (
    "FOCUS1_AUTHORITY_CANDIDATE_PATH_SET_MISMATCH"
)
FOCUS1_AUTHORITY_CANDIDATE_BLOB_MISMATCH = (
    "FOCUS1_AUTHORITY_CANDIDATE_BLOB_MISMATCH"
)
FOCUS1_AUTHORITY_CANDIDATE_DIGEST_MISMATCH = (
    "FOCUS1_AUTHORITY_CANDIDATE_DIGEST_MISMATCH"
)
FOCUS1_AUTHORITY_REPLACE_OBJECT_REJECTED = (
    "FOCUS1_AUTHORITY_REPLACE_OBJECT_REJECTED"
)
FOCUS1_AUTHORITY_MODE_INVALID = "FOCUS1_AUTHORITY_MODE_INVALID"
FOCUS1_AUTHORITY_PATH_SET_MISMATCH = "FOCUS1_AUTHORITY_PATH_SET_MISMATCH"
FOCUS1_AUTHORITY_BLOB_MISMATCH = "FOCUS1_AUTHORITY_BLOB_MISMATCH"
FOCUS1_AUTHORITY_DIGEST_MISMATCH = "FOCUS1_AUTHORITY_DIGEST_MISMATCH"
FOCUS1_AUTHORITY_MANIFEST_INVALID = "FOCUS1_AUTHORITY_MANIFEST_INVALID"
FOCUS1_AUTHORITY_UNTRUSTED_SOURCE = "FOCUS1_AUTHORITY_UNTRUSTED_SOURCE"

AUTHORITY_PATH_VERIFIED = "AUTHORITY_PATH_VERIFIED"
AUTHORITY_PATH_OUTSIDE_REPOSITORY = "AUTHORITY_PATH_OUTSIDE_REPOSITORY"
AUTHORITY_PATH_ALIAS_REJECTED = "AUTHORITY_PATH_ALIAS_REJECTED"
AUTHORITY_PATH_TRAVERSAL_REJECTED = "AUTHORITY_PATH_TRAVERSAL_REJECTED"
AUTHORITY_PATH_SYMLINK_REJECTED = "AUTHORITY_PATH_SYMLINK_REJECTED"
AUTHORITY_PATH_JUNCTION_REJECTED = "AUTHORITY_PATH_JUNCTION_REJECTED"
AUTHORITY_PATH_REPARSE_POINT_REJECTED = "AUTHORITY_PATH_REPARSE_POINT_REJECTED"
AUTHORITY_PATH_NOT_REGULAR_FILE = "AUTHORITY_PATH_NOT_REGULAR_FILE"
AUTHORITY_PATH_CHANGED_DURING_READ = "AUTHORITY_PATH_CHANGED_DURING_READ"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_REPARSE_POINT_ATTRIBUTE = 0x400
_IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
_IO_REPARSE_TAG_SYMLINK = 0xA000000C

_EXPECTED_DECLARATIONS = {
    "scientific_input_changed": False,
    "scenario_changed": False,
    "truth_changed": False,
    "threshold_or_margin_changed": False,
    "method_changed": False,
    "seed_changed": False,
    "result_changed": False,
    "original_confirmation_output_changed": False,
    "simulation_rerun": False,
    "amendment_scope": "GIT_WHITESPACE_POLICY_AND_TEST_PORTABILITY_ONLY",
    "test_hashes_rebound_additively": True,
    "frozen_yaml_bytes_and_hashes_unchanged": True,
}


@dataclass(frozen=True)
class VerificationResult:
    """Machine-readable result of a packaging-portability verification."""

    status: str
    ok: bool
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ok": self.ok,
            "message": self.message,
            "details": dict(self.details),
        }


class PortabilityVerificationError(ValueError):
    """Fail-closed validation error with a stable machine-readable status."""

    def __init__(
        self,
        status: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.details = dict(details or {})

    def as_result(self) -> VerificationResult:
        return VerificationResult(
            status=self.status,
            ok=False,
            message=str(self),
            details=self.details,
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_INCOMPLETE,
            f"{label} must be a lowercase SHA-256 digest.",
        )
    return value


def _canonical_relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_INCOMPLETE,
            f"{label} must be a non-empty repository-relative path.",
        )
    windows = PureWindowsPath(value)
    normalized = value.replace("\\", "/")
    if windows.drive or windows.root or normalized.startswith("/"):
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_POLICY_MISMATCH,
            f"{label} must not be absolute or drive-qualified.",
        )
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise PortabilityVerificationError(
            AUTHORITY_PATH_TRAVERSAL_REJECTED,
            f"{label} contains an empty, dot, or traversal component.",
        )
    if any(
        ":" in part or part.endswith((" ", "."))
        for part in parts
    ):
        raise PortabilityVerificationError(
            AUTHORITY_PATH_ALIAS_REJECTED,
            f"{label} contains a platform-aliasing path component.",
        )
    canonical = PurePosixPath(*parts).as_posix()
    if canonical != value:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_POLICY_MISMATCH,
            f"{label} must use canonical repository-relative POSIX spelling.",
            details={"canonical_path": canonical},
        )
    return canonical


def _is_link_or_reparse(file_stat: os.stat_result) -> bool:
    return stat.S_ISLNK(file_stat.st_mode) or bool(
        getattr(file_stat, "st_file_attributes", 0) & _REPARSE_POINT_ATTRIBUTE
    )


def _link_or_reparse_status(file_stat: os.stat_result) -> str | None:
    if stat.S_ISLNK(file_stat.st_mode):
        return AUTHORITY_PATH_SYMLINK_REJECTED
    if not (
        getattr(file_stat, "st_file_attributes", 0) & _REPARSE_POINT_ATTRIBUTE
    ):
        return None
    tag = getattr(file_stat, "st_reparse_tag", None)
    if tag == _IO_REPARSE_TAG_SYMLINK:
        return AUTHORITY_PATH_SYMLINK_REJECTED
    if tag == _IO_REPARSE_TAG_MOUNT_POINT:
        return AUTHORITY_PATH_JUNCTION_REJECTED
    return AUTHORITY_PATH_REPARSE_POINT_REJECTED


def _raise_if_link_or_reparse(path: Path, file_stat: os.stat_result) -> None:
    status = _link_or_reparse_status(file_stat)
    if status is not None:
        raise PortabilityVerificationError(
            status,
            f"Authority path component is a forbidden link or reparse point: {path}.",
            details={"path": str(path)},
        )


def _validate_unaliased_absolute_path(path: Path) -> None:
    """Reject link/junction/reparse aliases before any path is resolved."""

    if not path.is_absolute():
        raise PortabilityVerificationError(
            AUTHORITY_PATH_ALIAS_REJECTED,
            "Repository root must be supplied as a canonical absolute path.",
        )
    absolute = Path(os.path.abspath(os.fspath(path)))
    chain = list(reversed(absolute.parents)) + [absolute]
    for component in chain:
        try:
            file_stat = os.lstat(component)
        except FileNotFoundError as exc:
            raise PortabilityVerificationError(
                AUTHORITY_PATH_OUTSIDE_REPOSITORY,
                f"Authority path does not exist: {component}.",
            ) from exc
        _raise_if_link_or_reparse(component, file_stat)


def _canonical_git_repository_root(supplied_root: Path) -> Path:
    """Return only the direct, unaliased Git root for the supplied workspace."""

    _validate_unaliased_absolute_path(supplied_root)
    supplied_absolute = Path(os.path.abspath(os.fspath(supplied_root)))
    try:
        command = subprocess.run(
            ["git", "--no-replace-objects", "rev-parse", "--show-toplevel"],
            cwd=supplied_absolute,
            env=_authority_git_environment(),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PortabilityVerificationError(
            AUTHORITY_PATH_OUTSIDE_REPOSITORY,
            "The supplied repository root is not inside an accessible Git worktree.",
        ) from exc
    git_root_lexical = Path(os.path.abspath(command.stdout.strip()))
    _validate_unaliased_absolute_path(git_root_lexical)
    if os.path.normpath(os.fspath(supplied_absolute)) != os.path.normpath(
        os.fspath(git_root_lexical)
    ):
        raise PortabilityVerificationError(
            AUTHORITY_PATH_ALIAS_REJECTED,
            "Only the canonical Git root may be supplied; aliases and subpaths are rejected.",
            details={
                "supplied_root": str(supplied_absolute),
                "canonical_git_root": str(git_root_lexical),
            },
        )
    resolved = git_root_lexical.resolve(strict=True)
    if os.path.normcase(os.fspath(resolved)) != os.path.normcase(
        os.fspath(git_root_lexical)
    ):
        raise PortabilityVerificationError(
            AUTHORITY_PATH_ALIAS_REJECTED,
            "Canonical Git root changes identity when resolved.",
        )
    return git_root_lexical


def _require_exact_child_case(parent: Path, component: str, label: str) -> None:
    try:
        names = [entry.name for entry in os.scandir(parent)]
    except OSError as exc:
        raise PortabilityVerificationError(
            AUTHORITY_PATH_OUTSIDE_REPOSITORY,
            f"Cannot enumerate {label}: {exc}",
        ) from exc
    if component in names:
        return
    if any(name.casefold() == component.casefold() for name in names):
        raise PortabilityVerificationError(
            AUTHORITY_PATH_ALIAS_REJECTED,
            f"{label} uses a case alias instead of the on-disk spelling.",
        )


def _resolve_repository_file(repository_root: Path, relative_path: str) -> Path:
    canonical = _canonical_relative_path(relative_path, "path")
    root = repository_root
    current = root
    for component in PurePosixPath(canonical).parts:
        _require_exact_child_case(current, component, canonical)
        current = current / component
        try:
            file_stat = os.lstat(current)
        except FileNotFoundError as exc:
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_INCOMPLETE,
                f"Required tracked path is missing: {canonical}.",
                details={"path": canonical},
            ) from exc
        _raise_if_link_or_reparse(current, file_stat)
    resolved = current.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PortabilityVerificationError(
            AUTHORITY_PATH_OUTSIDE_REPOSITORY,
            f"Tracked path escapes the repository root: {canonical}.",
        ) from exc
    file_stat = os.lstat(current)
    if not stat.S_ISREG(file_stat.st_mode):
        raise PortabilityVerificationError(
            AUTHORITY_PATH_NOT_REGULAR_FILE,
            f"Required tracked path is not a regular file: {canonical}.",
        )
    return current


@dataclass(frozen=True)
class LoadedAuthorityFile:
    """Bytes, identity, and digest captured through one read-only open handle."""

    relative_path: str
    path: Path
    raw: bytes
    size_bytes: int
    sha256: str


def _metadata_identity(file_stat: os.stat_result) -> tuple[int, int, int, int]:
    return (
        int(file_stat.st_dev),
        int(file_stat.st_ino),
        int(file_stat.st_size),
        int(getattr(file_stat, "st_mtime_ns", int(file_stat.st_mtime * 1e9))),
    )


def _read_repository_file_once(
    repository_root: Path,
    relative_path: str,
) -> LoadedAuthorityFile:
    """Validate containment, then hash and parse only the bytes from one handle."""

    canonical = _canonical_relative_path(relative_path, "authority_path")
    path = _resolve_repository_file(repository_root, canonical)
    path_before = os.lstat(path)
    _raise_if_link_or_reparse(path, path_before)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PortabilityVerificationError(
            AUTHORITY_PATH_CHANGED_DURING_READ,
            f"Authority file could not be opened safely: {canonical}: {exc}",
        ) from exc
    try:
        opened_before = os.fstat(descriptor)
        if not stat.S_ISREG(opened_before.st_mode):
            raise PortabilityVerificationError(
                AUTHORITY_PATH_NOT_REGULAR_FILE,
                f"Authority path is not a regular file: {canonical}.",
            )
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        opened_after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        path_after = os.lstat(path)
    except FileNotFoundError as exc:
        raise PortabilityVerificationError(
            AUTHORITY_PATH_CHANGED_DURING_READ,
            f"Authority file disappeared during verification: {canonical}.",
        ) from exc
    if (
        _metadata_identity(path_before) != _metadata_identity(opened_before)
        or _metadata_identity(opened_before) != _metadata_identity(opened_after)
        or _metadata_identity(opened_after) != _metadata_identity(path_after)
    ):
        raise PortabilityVerificationError(
            AUTHORITY_PATH_CHANGED_DURING_READ,
            f"Authority file identity changed during verification: {canonical}.",
        )
    raw = b"".join(chunks)
    return LoadedAuthorityFile(
        relative_path=canonical,
        path=path,
        raw=raw,
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def _parse_loaded_json(
    loaded: LoadedAuthorityFile,
    label: str,
) -> dict[str, Any]:
    try:
        raw_text = loaded.raw.decode("utf-8")
    except UnicodeError as exc:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_INCOMPLETE,
            f"{label} is not valid UTF-8: {exc}",
        ) from exc
    parsed = _json_without_duplicate_keys(raw_text)
    if not isinstance(parsed, dict):
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_INCOMPLETE,
            f"{label} must be a JSON object.",
        )
    return parsed


_AUTHORITY_GIT_ENVIRONMENT_DENYLIST = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_NAMESPACE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_REPLACE_REF_BASE",
        "GIT_WORK_TREE",
    }
)


def _authority_git_environment() -> dict[str, str]:
    """Return a stable Git environment that cannot redirect authority inputs."""

    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in _AUTHORITY_GIT_ENVIRONMENT_DENYLIST
    }
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    return environment


def _git_no_replace(
    repository_root: Path,
    arguments: Sequence[str],
    *,
    check: bool = False,
    text: bool = False,
) -> subprocess.CompletedProcess[Any]:
    """Run one authority Git command without replacement-object influence."""

    return subprocess.run(
        ["git", "--no-replace-objects", *arguments],
        cwd=repository_root,
        env=_authority_git_environment(),
        check=check,
        capture_output=True,
        text=text,
    )


def _reject_git_object_substitution(repository_root: Path) -> None:
    """Fail closed on replace refs or legacy grafts in the authority repository."""

    replacements = _git_no_replace(
        repository_root,
        ["for-each-ref", "--format=%(refname)", "refs/replace/"],
        check=True,
        text=True,
    ).stdout.splitlines()
    if replacements:
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_REPLACE_OBJECT_REJECTED,
            "Git replacement refs are forbidden during Focus 1 authority verification.",
            details={"replace_refs": sorted(replacements)},
        )
    common_dir_raw = _git_no_replace(
        repository_root,
        ["rev-parse", "--git-common-dir"],
        check=True,
        text=True,
    ).stdout.strip()
    common_dir = Path(common_dir_raw)
    if not common_dir.is_absolute():
        common_dir = repository_root / common_dir
    grafts_path = common_dir / "info" / "grafts"
    try:
        graft_bytes = grafts_path.read_bytes()
    except FileNotFoundError:
        graft_bytes = b""
    if graft_bytes.strip():
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_REPLACE_OBJECT_REJECTED,
            "Legacy Git grafts are forbidden during Focus 1 authority verification.",
            details={"grafts_path": str(grafts_path)},
        )


def _git_blob(
    repository_root: Path,
    commit: str,
    relative_path: str,
    *,
    missing_status: str = FOCUS1_AUTHORITY_MANIFEST_INVALID,
    source_label: str = "Checkpoint",
) -> bytes:
    canonical = _canonical_relative_path(relative_path, "checkpoint_path")
    try:
        return _git_no_replace(
            repository_root,
            ["cat-file", "blob", f"{commit}:{canonical}"],
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PortabilityVerificationError(
            missing_status,
            f"{source_label} blob is unavailable: {canonical}.",
            details={"path": canonical, "commit": commit},
        ) from exc


def _checkpoint_frozen_paths(generator_blob: bytes) -> tuple[str, ...]:
    try:
        syntax = ast.parse(generator_blob.decode("utf-8"))
    except (UnicodeError, SyntaxError) as exc:
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_MANIFEST_INVALID,
            "Checkpoint freeze generator is not parseable UTF-8 Python.",
        ) from exc
    for statement in syntax.body:
        if not isinstance(statement, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "FROZEN_PATHS"
            for target in statement.targets
        ):
            continue
        try:
            value = ast.literal_eval(statement.value)
        except (TypeError, ValueError) as exc:
            raise PortabilityVerificationError(
                FOCUS1_AUTHORITY_MANIFEST_INVALID,
                "Checkpoint FROZEN_PATHS is not a static tuple.",
            ) from exc
        if not isinstance(value, tuple) or not value:
            break
        paths = tuple(
            _canonical_relative_path(item, "checkpoint FROZEN_PATHS entry")
            for item in value
        )
        if len(paths) != len(set(paths)):
            raise PortabilityVerificationError(
                FOCUS1_AUTHORITY_MANIFEST_INVALID,
                "Checkpoint FROZEN_PATHS contains duplicate paths.",
            )
        return paths
    raise PortabilityVerificationError(
        FOCUS1_AUTHORITY_MANIFEST_INVALID,
        "Checkpoint freeze generator has no accepted static FROZEN_PATHS tuple.",
    )


def _checkpoint_yaml_scalar(blob: bytes, key: str) -> str | int:
    try:
        text = blob.decode("utf-8")
    except UnicodeError as exc:
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_MANIFEST_INVALID,
            "Checkpoint benchmark configuration is not UTF-8.",
        ) from exc
    matches = re.findall(rf"(?m)^{re.escape(key)}:\s*([^#\r\n]+?)\s*$", text)
    if len(matches) != 1:
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_MANIFEST_INVALID,
            f"Checkpoint benchmark configuration does not define exactly one {key}.",
        )
    value = matches[0].strip().strip('"\'')
    return int(value) if value.isdecimal() else value


def _checkpoint_full_entropy_protocol(blob: bytes) -> str:
    try:
        syntax = ast.parse(blob.decode("utf-8"))
    except (UnicodeError, SyntaxError) as exc:
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_MANIFEST_INVALID,
            "Checkpoint beacon source is not parseable UTF-8 Python.",
        ) from exc
    for statement in syntax.body:
        if not isinstance(statement, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "FULL_ENTROPY_PROTOCOL"
            for target in statement.targets
        ):
            continue
        value = ast.literal_eval(statement.value)
        if isinstance(value, str) and value:
            return value
    raise PortabilityVerificationError(
        FOCUS1_AUTHORITY_MANIFEST_INVALID,
        "Checkpoint beacon source does not declare FULL_ENTROPY_PROTOCOL.",
    )


def _focus1_manifest_payload(
    *,
    benchmark_protocol_version: str,
    seed_schedule_version: int,
    full_entropy_protocol: str,
    input_hashes: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "benchmark_protocol_version": benchmark_protocol_version,
        "seed_schedule_version": seed_schedule_version,
        "full_entropy_protocol": full_entropy_protocol,
        "protocol_version": "focus1_freeze_review_v1",
        "scenario_version": "false_promotion_benchmark_v1_scenarios",
        "method_interface_version": "promotion_method_evaluate_method_decision_v1",
        "estimands": [
            "P(at least one unsafe candidate is promoted in a trial)",
            "P(at least one unsafe candidate is certified in a trial)",
            "P(false block in a trial)",
            "P(correct promotion in a trial)",
            "P(correct no-safe-candidate block in a trial)",
            "operational regret conditional on safe selection",
        ],
        "candidate_truth_definition": (
            "Every enabled overall-quality, protected-group-quality, safety-violation, "
            "execution-failure, and insufficient-evidence threshold passes under exact "
            "configured population parameters. Cost and latency are operational objectives."
        ),
        "event_definitions": {
            "false_promotion": "A deployable method selects a candidate that is not truly promotion-safe.",
            "false_certification": "A certified set contains at least one candidate that is not truly promotion-safe.",
            "false_block": "At least one truly safe candidate exists and the method promotes none.",
            "operational_regret": "Selected safe candidate objective minus the optimal truly safe candidate objective.",
        },
        "estimator_definitions": {
            "event_rate": "event count divided by fixed Monte Carlo trial count within each scenario/sample-size/method cell",
            "monte_carlo_interval": "two-sided 95% Wilson binomial interval for Monte Carlo event-rate uncertainty",
            "mean_certified_set_size": "arithmetic mean over method-trials in one cell",
            "mean_operational_regret": "arithmetic mean conditional on safe selections with defined regret",
        },
        "enabled_risk_definitions": [
            "overall_quality_delta_vs_incumbent",
            "quality_delta_by_group",
            "safety_violation_probability",
            "execution_failure_probability",
            "insufficient_evidence_probability",
        ],
        "input_hashes": dict(input_hashes),
    }


def _focus1_digest(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def verify_focus1_portable_authority(repository_root: Path) -> dict[str, Any]:
    """Verify current bytes against the accepted checkpoint-derived inventory.

    This clean-checkout adapter does not require the historical commit object.
    Its fixed inventory must itself reproduce the accepted digest, so changing
    both candidate bytes and an inventory entry cannot retain authority without
    a SHA-256 preimage/collision.  The stricter packaging audit below still
    requires and verifies the raw checkpoint Git blobs.
    """

    root = Path(os.path.abspath(os.fspath(repository_root)))
    _validate_unaliased_absolute_path(root)
    manifest = _focus1_manifest_payload(
        benchmark_protocol_version="false_promotion_benchmark_v1",
        seed_schedule_version=2,
        full_entropy_protocol="DRAND_QUICKNET_FUTURE_ROUND_V1",
        input_hashes=FOCUS1_CHECKPOINT_INPUT_SHA256,
    )
    expected_digest = _focus1_digest(manifest)
    if expected_digest != FOCUS1_DIGEST:
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_DIGEST_MISMATCH,
            "Checkpoint-derived portable inventory cannot reproduce the accepted digest.",
            details={"expected": FOCUS1_DIGEST, "computed": expected_digest},
        )
    mismatches: list[str] = []
    observed_hashes: dict[str, str] = {}
    for path, expected_hash in FOCUS1_CHECKPOINT_INPUT_SHA256.items():
        try:
            loaded = _read_repository_file_once(root, path)
        except PortabilityVerificationError as exc:
            if exc.status == PACKAGING_PORTABILITY_INCOMPLETE:
                raise PortabilityVerificationError(
                    FOCUS1_AUTHORITY_PATH_SET_MISMATCH,
                    f"Required Focus 1 file is missing: {path}.",
                ) from exc
            raise
        observed_hashes[path] = loaded.sha256
        if loaded.sha256 != expected_hash:
            mismatches.append(path)
    observed_manifest = _focus1_manifest_payload(
        benchmark_protocol_version="false_promotion_benchmark_v1",
        seed_schedule_version=2,
        full_entropy_protocol="DRAND_QUICKNET_FUTURE_ROUND_V1",
        input_hashes=observed_hashes,
    )
    observed_digest = _focus1_digest(observed_manifest)
    if mismatches:
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_BLOB_MISMATCH,
            "Candidate Focus 1 bytes differ from the accepted checkpoint inventory.",
            details={"mismatched_paths": mismatches, "observed_digest": observed_digest},
        )
    if observed_digest != FOCUS1_DIGEST:
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_DIGEST_MISMATCH,
            "Candidate Focus 1 digest differs from the accepted authority.",
        )
    authoritative_manifest = dict(manifest)
    authoritative_manifest["benchmark_freeze_digest"] = expected_digest
    return {
        "status": FOCUS1_AUTHORITY_VERIFIED,
        "authority_source": "CHECKPOINT_DERIVED_ACCEPTED_INVENTORY",
        "checkpoint_commit": FOCUS1_CHECKPOINT_COMMIT,
        "frozen_path_count": len(FOCUS1_CHECKPOINT_INPUT_SHA256),
        "expected_digest": expected_digest,
        "observed_digest": observed_digest,
        "manifest": authoritative_manifest,
    }


def _lineage_authority_record() -> dict[str, Any]:
    return {
        "schema_version": "ragwarrant_focus1_detached_authority.v1",
        "amendment_id": FOCUS1_DETACHED_AUTHORITY_AMENDMENT_ID,
        "amendment_type": FOCUS1_DETACHED_AUTHORITY_AMENDMENT_TYPE,
        "authority_mode": LINEAGE_CHECKPOINT,
        "authority_ref": None,
        "authority_commit": FOCUS1_CHECKPOINT_COMMIT,
        "accepted_digest": FOCUS1_DIGEST,
        "lineage_required": True,
        "content_equivalence_required": True,
        "trust_boundary": {
            "verifier_self_attestation": False,
            "reviewed_git_commit_and_ci_required": True,
            "tag_name_alone_is_authority": False,
            "global_external_copy_integrity_claimed": False,
        },
        "declarations": {
            "scientific_input_changed": False,
            "result_changed": False,
            "bridge_merge_created": False,
            "old_rebrand_history_replayed": False,
            "simulation_rerun": False,
            "full_executed": False,
            "drand_accessed": False,
        },
    }


def _load_focus1_authority_record(repository_root: Path) -> dict[str, Any]:
    loaded = _read_repository_file_once(repository_root, FOCUS1_AUTHORITY_RECORD_PATH)
    record = _parse_loaded_json(loaded, "Focus 1 detached-authority record")
    required = {
        "schema_version",
        "amendment_id",
        "amendment_type",
        "parent_authority",
        "authority_mode",
        "authority_ref",
        "authority_commit",
        "accepted_digest",
        "lineage_required",
        "content_equivalence_required",
        "hash_rebindings",
        "trust_boundary",
        "declarations",
    }
    if set(record) != required:
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_MODE_INVALID,
            "Focus 1 authority record has an invalid exact schema.",
        )
    if (
        record["schema_version"] != "ragwarrant_focus1_detached_authority.v1"
        or record["amendment_id"] != FOCUS1_DETACHED_AUTHORITY_AMENDMENT_ID
        or record["amendment_type"] != FOCUS1_DETACHED_AUTHORITY_AMENDMENT_TYPE
        or record["authority_commit"] != FOCUS1_CHECKPOINT_COMMIT
        or record["accepted_digest"] != FOCUS1_DIGEST
        or record["content_equivalence_required"] is not True
    ):
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_MODE_INVALID,
            "Focus 1 authority identity differs from the accepted amendment.",
        )
    parent_loaded = _read_repository_file_once(repository_root, INTEGRITY_RECORD_PATH)
    if record["parent_authority"] != {
        "path": INTEGRITY_RECORD_PATH,
        "sha256": FOCUS1_AUTHORITY_PARENT_RECORD_SHA256,
    } or parent_loaded.sha256 != FOCUS1_AUTHORITY_PARENT_RECORD_SHA256:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_HASH_MISMATCH,
            "Detached authority does not bind the accepted packaging-integrity record.",
        )
    rebindings = record["hash_rebindings"]
    required_rebinding_fields = {
        "prior_path",
        "prior_sha256",
        "new_path",
        "new_sha256",
        "amendment_id",
        "change_category",
        "reason",
        "scientific_impact",
        "result_impact",
    }
    approved_rebindings = {
        FOCUS1_AUTHORITY_REBOUND_PATH: {
            "prior_sha256": FOCUS1_AUTHORITY_PRIOR_VERIFIER_SHA256,
            "change_category": "DETACHED_AUTHORITY_VERIFIER",
            "reason": (
                "Add explicit lineage and detached pinned-checkpoint verification "
                "without changing scientific inputs or results."
            ),
        },
        FOCUS1_AUTHORITY_REBOUND_TEST_PATH: {
            "prior_sha256": FOCUS1_AUTHORITY_PRIOR_TEST_SHA256,
            "change_category": "COMMIT_BLOB_AUTHORITY_TEST",
            "reason": (
                "Update the accepted authority test to tamper committed candidate "
                "bytes and assert explicit checkpoint/candidate failure statuses."
            ),
        },
        FOCUS1_AUTHORITY_REBOUND_GITATTRIBUTES_PATH: {
            "prior_sha256": FOCUS1_AUTHORITY_PRIOR_GITATTRIBUTES_SHA256,
            "change_category": "CURRENT_MAIN_GITATTRIBUTES_PRESERVATION",
            "reason": (
                "Preserve the merged current-main PDF and DOCX binary-review rules "
                "alongside the four narrow research whitespace rules."
            ),
        },
        FOCUS1_AUTHORITY_REBOUND_V1_GUARD_TEST_PATH: {
            "prior_sha256": FOCUS1_AUTHORITY_PRIOR_V1_GUARD_TEST_SHA256,
            "change_category": "DETACHED_REPLAY_INTEGRITY_TEST",
            "reason": (
                "Compare frozen v1 files with the accepted v1 commit while "
                "comparing historical protected paths with the current-main replay base."
            ),
        },
        FOCUS1_AUTHORITY_REBOUND_EVIDENCE_PLANNER_TEST_PATH: {
            "prior_sha256": FOCUS1_AUTHORITY_PRIOR_EVIDENCE_PLANNER_TEST_SHA256,
            "change_category": "DETACHED_REPLAY_HASH_CHAIN",
            "reason": (
                "Rebind the evidence-planner integrity test to the accepted "
                "current-main replay guard hash."
            ),
        },
        FOCUS1_AUTHORITY_REBOUND_STRATIFIED_TEST_PATH: {
            "prior_sha256": FOCUS1_AUTHORITY_PRIOR_STRATIFIED_TEST_SHA256,
            "change_category": "DETACHED_REPLAY_HASH_CHAIN",
            "reason": (
                "Rebind the stratified-design integrity test to the accepted "
                "evidence-planner test hash."
            ),
        },
        FOCUS1_AUTHORITY_REBOUND_CONFIRMATION_TEST_PATH: {
            "prior_sha256": FOCUS1_AUTHORITY_PRIOR_CONFIRMATION_TEST_SHA256,
            "change_category": "DETACHED_REPLAY_HASH_CHAIN",
            "reason": (
                "Rebind the confirmation integrity test to the accepted "
                "stratified-design test hash."
            ),
        },
    }
    if not isinstance(rebindings, list) or len(rebindings) != len(
        approved_rebindings
    ) or any(
        not isinstance(entry, dict) or set(entry) != required_rebinding_fields
        for entry in rebindings
    ):
        raise PortabilityVerificationError(
            PACKAGING_REBINDING_EXTRA_AUTHORITY_ENTRY,
            "Detached authority has an invalid exact additive rebinding set.",
        )
    seen_rebindings: set[str] = set()
    for rebinding in rebindings:
        rebound_path = _canonical_relative_path(
            rebinding["new_path"], "detached authority rebinding path"
        )
        if rebound_path in seen_rebindings or rebound_path not in approved_rebindings:
            raise PortabilityVerificationError(
                PACKAGING_REBINDING_UNAUTHORIZED_PATH,
                "Detached authority rebinding includes a duplicate or unauthorized path.",
            )
        seen_rebindings.add(rebound_path)
        approved = approved_rebindings[rebound_path]
        replacement_hash = _require_sha256(
            rebinding["new_sha256"], "detached authority replacement hash"
        )
        if rebinding != {
            "prior_path": rebound_path,
            "prior_sha256": approved["prior_sha256"],
            "new_path": rebound_path,
            "new_sha256": replacement_hash,
            "amendment_id": FOCUS1_DETACHED_AUTHORITY_AMENDMENT_ID,
            "change_category": approved["change_category"],
            "reason": approved["reason"],
            "scientific_impact": "NONE",
            "result_impact": "NONE",
        }:
            raise PortabilityVerificationError(
                PACKAGING_REBINDING_UNAUTHORIZED_PATH,
                "Detached authority rebinding differs from its approved authority.",
            )
        actual_hash = _read_repository_file_once(repository_root, rebound_path).sha256
        if actual_hash != replacement_hash:
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_HASH_MISMATCH,
                "Detached-authority replacement bytes differ from the additive rebinding.",
                details={
                    "path": rebound_path,
                    "expected": replacement_hash,
                    "actual": actual_hash,
                },
            )
    expected_trust_boundary = {
        "verifier_self_attestation": False,
        "reviewed_git_commit_and_ci_required": True,
        "tag_name_alone_is_authority": False,
        "global_external_copy_integrity_claimed": False,
    }
    expected_declarations = {
        "scientific_input_changed": False,
        "result_changed": False,
        "bridge_merge_created": False,
        "old_rebrand_history_replayed": False,
        "simulation_rerun": False,
        "full_executed": False,
        "drand_accessed": False,
    }
    if (
        record["trust_boundary"] != expected_trust_boundary
        or record["declarations"] != expected_declarations
    ):
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_MODE_INVALID,
            "Focus 1 authority trust boundary or declarations changed.",
        )
    mode = record["authority_mode"]
    if mode == LINEAGE_CHECKPOINT:
        valid_mode_fields = (
            record["authority_ref"] is None
            and record["lineage_required"] is True
        )
    elif mode == DETACHED_PINNED_CHECKPOINT:
        valid_mode_fields = (
            record["authority_ref"] == FOCUS1_AUTHORITY_REF
            and record["lineage_required"] is False
        )
    else:
        valid_mode_fields = False
    if not valid_mode_fields:
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_MODE_INVALID,
            "Focus 1 authority mode or its required fields are invalid.",
        )
    return record


def _focus1_authority_rebinding_overrides(
    record: Mapping[str, Any],
) -> dict[str, tuple[str, str]]:
    return {
        str(rebinding["new_path"]): (
            str(rebinding["prior_sha256"]),
            str(rebinding["new_sha256"]),
        )
        for rebinding in record["hash_rebindings"]
        if str(rebinding["new_path"]) in REQUIRED_REBINDING_PATHS
    }


def _effective_workspace_rebindings(
    parent_rebindings: Sequence[Mapping[str, Any]],
    detached_record: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Compose original-to-portable and portable-to-detached hash bindings."""

    effective = [dict(binding) for binding in parent_rebindings]
    if detached_record is None:
        return effective
    positions = {
        str(binding["new_path"]): index for index, binding in enumerate(effective)
    }
    for detached_binding in detached_record["hash_rebindings"]:
        path = str(detached_binding["new_path"])
        position = positions.get(path)
        if position is None:
            positions[path] = len(effective)
            effective.append(dict(detached_binding))
            continue
        parent_binding = effective[position]
        if parent_binding["new_sha256"] != detached_binding["prior_sha256"]:
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_HASH_MISMATCH,
                "Detached workspace rebinding does not continue its parent hash chain.",
                details={"path": path},
            )
        parent_binding["new_sha256"] = detached_binding["new_sha256"]
    return effective


def _git_object_type(
    repository_root: Path,
    object_id: str,
    *,
    missing_status: str,
) -> str:
    completed = _git_no_replace(
        repository_root,
        ["cat-file", "-t", object_id],
        text=True,
    )
    if completed.returncode != 0:
        raise PortabilityVerificationError(
            missing_status,
            f"Required Git object is unavailable: {object_id}.",
        )
    return completed.stdout.strip()


def _resolve_candidate_commit(repository_root: Path) -> str:
    completed = _git_no_replace(
        repository_root,
        ["rev-parse", "--verify", "HEAD^{commit}"],
        text=True,
    )
    if completed.returncode != 0:
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_OBJECT_TYPE_INVALID,
            "Candidate HEAD cannot be resolved to one commit.",
        )
    candidate_commit = completed.stdout.strip()
    if not _GIT_SHA1_RE.fullmatch(candidate_commit) or _git_object_type(
        repository_root,
        candidate_commit,
        missing_status=FOCUS1_AUTHORITY_OBJECT_TYPE_INVALID,
    ) != "commit":
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_OBJECT_TYPE_INVALID,
            "Candidate authority object is not a commit.",
        )
    return candidate_commit


def _resolve_exact_annotated_authority_tag(repository_root: Path) -> str:
    completed = _git_no_replace(
        repository_root,
        ["show-ref", "--verify", "--hash", "--", FOCUS1_AUTHORITY_REF],
        text=True,
    )
    if completed.returncode != 0:
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_TAG_MISSING,
            f"Required Focus 1 authority tag is missing: {FOCUS1_AUTHORITY_REF}.",
        )
    tag_object = completed.stdout.strip()
    if not _GIT_SHA1_RE.fullmatch(tag_object):
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_TAG_MISSING,
            "Focus 1 authority ref did not resolve to one raw object ID.",
        )
    if _git_object_type(
        repository_root,
        tag_object,
        missing_status=FOCUS1_AUTHORITY_TAG_MISSING,
    ) != "tag":
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_TAG_NOT_ANNOTATED,
            "Focus 1 authority ref must directly name an annotated tag object.",
        )
    raw_tag = _git_no_replace(
        repository_root,
        ["cat-file", "tag", tag_object],
        check=True,
    ).stdout
    try:
        headers = raw_tag.split(b"\n\n", 1)[0].decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_TAG_NOT_ANNOTATED,
            "Focus 1 annotated-tag headers are not valid UTF-8.",
        ) from exc
    header_values: dict[str, str] = {}
    for line in headers:
        key, separator, value = line.partition(" ")
        if separator and key in {"object", "type", "tag"}:
            if key in header_values:
                raise PortabilityVerificationError(
                    FOCUS1_AUTHORITY_TAG_NOT_ANNOTATED,
                    "Focus 1 annotated tag contains duplicate authority headers.",
                )
            header_values[key] = value
    if header_values.get("type") != "commit":
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_OBJECT_TYPE_INVALID,
            "Focus 1 annotated tag must point directly to a commit object.",
        )
    if header_values.get("object") != FOCUS1_CHECKPOINT_COMMIT:
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_TAG_TARGET_MISMATCH,
            "Focus 1 authority tag target differs from the pinned checkpoint commit.",
            details={
                "expected": FOCUS1_CHECKPOINT_COMMIT,
                "actual": header_values.get("object"),
            },
        )
    return tag_object


def _verify_authority_tag_unchanged(repository_root: Path, tag_object: str) -> None:
    completed = _git_no_replace(
        repository_root,
        ["show-ref", "--verify", "--hash", "--", FOCUS1_AUTHORITY_REF],
        text=True,
    )
    if completed.returncode != 0 or completed.stdout.strip() != tag_object:
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_TAG_TARGET_MISMATCH,
            "Focus 1 authority tag changed during verification.",
        )


def _verify_focus1_authority_contract(
    repository_root: Path,
    record: Mapping[str, Any],
    *,
    observed_paths: Sequence[str] | None = None,
) -> dict[str, Any]:
    root = _canonical_git_repository_root(repository_root)
    _reject_git_object_substitution(root)
    mode = record["authority_mode"]
    checkpoint_commit = str(record["authority_commit"])
    accepted_digest = str(record["accepted_digest"])
    if (
        checkpoint_commit != FOCUS1_CHECKPOINT_COMMIT
        or accepted_digest != FOCUS1_DIGEST
        or record.get("content_equivalence_required") is not True
    ):
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_MODE_INVALID,
            "Focus 1 authority contract changed the pinned commit or digest.",
        )
    tag_object: str | None = None
    if mode == DETACHED_PINNED_CHECKPOINT:
        if (
            record.get("authority_ref") != FOCUS1_AUTHORITY_REF
            or record.get("lineage_required") is not False
        ):
            raise PortabilityVerificationError(
                FOCUS1_AUTHORITY_MODE_INVALID,
                "Detached authority requires the exact pinned tag and no lineage fallback.",
            )
        tag_object = _resolve_exact_annotated_authority_tag(root)
    elif mode == LINEAGE_CHECKPOINT:
        if record.get("authority_ref") is not None or record.get(
            "lineage_required"
        ) is not True:
            raise PortabilityVerificationError(
                FOCUS1_AUTHORITY_MODE_INVALID,
                "Lineage authority requires ancestry and no detached tag ref.",
            )
    else:
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_MODE_INVALID,
            f"Unknown Focus 1 authority mode: {mode!r}.",
        )
    checkpoint_type = _git_object_type(
        root,
        checkpoint_commit,
        missing_status=FOCUS1_AUTHORITY_COMMIT_MISSING,
    )
    if checkpoint_type != "commit":
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_OBJECT_TYPE_INVALID,
            "Pinned Focus 1 authority object is not a commit.",
        )
    candidate_commit = _resolve_candidate_commit(root)
    if mode == LINEAGE_CHECKPOINT:
        ancestry = _git_no_replace(
            root,
            ["merge-base", "--is-ancestor", checkpoint_commit, candidate_commit],
        )
        if ancestry.returncode != 0:
            raise PortabilityVerificationError(
                FOCUS1_AUTHORITY_UNTRUSTED_SOURCE,
                "Lineage mode requires the accepted Focus 1 checkpoint as an ancestor.",
            )
    generator_path = "scripts/generate_benchmark_freeze_manifest.py"
    generator_blob = _git_blob(root, checkpoint_commit, generator_path)
    frozen_paths = _checkpoint_frozen_paths(generator_blob)
    expected_hashes = {
        path: hashlib.sha256(_git_blob(root, checkpoint_commit, path)).hexdigest()
        for path in frozen_paths
    }
    if expected_hashes != dict(FOCUS1_CHECKPOINT_INPUT_SHA256):
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_CHECKPOINT_DIGEST_MISMATCH,
            "Checkpoint blobs differ from the accepted checkpoint-derived inventory.",
        )
    config_blob = _git_blob(
        root,
        checkpoint_commit,
        "configs/research/false_promotion_benchmark_v1.yaml",
    )
    beacon_blob = _git_blob(
        root,
        checkpoint_commit,
        "src/ragwarrant/research/public_beacon.py",
    )
    manifest = _focus1_manifest_payload(
        benchmark_protocol_version=str(
            _checkpoint_yaml_scalar(config_blob, "protocol_version")
        ),
        seed_schedule_version=int(
            _checkpoint_yaml_scalar(config_blob, "seed_schedule_version")
        ),
        full_entropy_protocol=_checkpoint_full_entropy_protocol(beacon_blob),
        input_hashes=expected_hashes,
    )
    expected_digest = _focus1_digest(manifest)
    if expected_digest != accepted_digest:
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_CHECKPOINT_DIGEST_MISMATCH,
            "Checkpoint blobs cannot reproduce the accepted Focus 1 digest.",
            details={"expected": accepted_digest, "computed": expected_digest},
        )
    candidate_paths = tuple(frozen_paths if observed_paths is None else observed_paths)
    try:
        canonical_candidate_paths = tuple(
            _canonical_relative_path(path, "observed Focus 1 path")
            for path in candidate_paths
        )
    except PortabilityVerificationError as exc:
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_CANDIDATE_PATH_SET_MISMATCH,
            "Candidate Focus 1 path inventory is not canonical.",
        ) from exc
    if len(canonical_candidate_paths) != len(set(canonical_candidate_paths)) or set(
        canonical_candidate_paths
    ) != set(frozen_paths):
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_CANDIDATE_PATH_SET_MISMATCH,
            "Candidate Focus 1 path set differs from the checkpoint authority.",
            details={
                "missing": sorted(set(frozen_paths) - set(canonical_candidate_paths)),
                "extra": sorted(set(canonical_candidate_paths) - set(frozen_paths)),
            },
        )
    observed_hashes: dict[str, str] = {}
    mismatches: list[str] = []
    for path in frozen_paths:
        candidate_blob = _git_blob(
            root,
            candidate_commit,
            path,
            missing_status=FOCUS1_AUTHORITY_CANDIDATE_PATH_SET_MISMATCH,
            source_label="Candidate commit",
        )
        observed_hashes[path] = hashlib.sha256(candidate_blob).hexdigest()
        if observed_hashes[path] != expected_hashes[path]:
            mismatches.append(path)
    observed_manifest = _focus1_manifest_payload(
        benchmark_protocol_version=manifest["benchmark_protocol_version"],
        seed_schedule_version=manifest["seed_schedule_version"],
        full_entropy_protocol=manifest["full_entropy_protocol"],
        input_hashes=observed_hashes,
    )
    observed_digest = _focus1_digest(observed_manifest)
    if mismatches:
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_CANDIDATE_BLOB_MISMATCH,
            "Candidate commit Focus 1 bytes differ from checkpoint Git blobs.",
            details={"mismatched_paths": mismatches, "observed_digest": observed_digest},
        )
    if observed_digest != accepted_digest:
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_CANDIDATE_DIGEST_MISMATCH,
            "Candidate commit Focus 1 digest differs from the accepted authority.",
            details={"expected": accepted_digest, "computed": observed_digest},
        )
    if tag_object is not None:
        _verify_authority_tag_unchanged(root, tag_object)
    authoritative_manifest = dict(manifest)
    authoritative_manifest["benchmark_freeze_digest"] = expected_digest
    verified_status = (
        FOCUS1_AUTHORITY_VERIFIED_DETACHED
        if mode == DETACHED_PINNED_CHECKPOINT
        else FOCUS1_AUTHORITY_VERIFIED_LINEAGE
    )
    return {
        "status": verified_status,
        "authority_mode": mode,
        "authority_ref": record["authority_ref"],
        "authority_tag_object": tag_object,
        "checkpoint_commit": checkpoint_commit,
        "candidate_commit": candidate_commit,
        "lineage_required": bool(record["lineage_required"]),
        "frozen_path_count": len(frozen_paths),
        "expected_digest": expected_digest,
        "observed_digest": observed_digest,
        "manifest": authoritative_manifest,
    }


def verify_focus1_authority(
    repository_root: Path,
    *,
    observed_paths: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Verify the explicit lineage or detached Focus 1 authority contract."""

    root = _canonical_git_repository_root(repository_root)
    record = _load_focus1_authority_record(root)
    return _verify_focus1_authority_contract(
        root,
        record,
        observed_paths=observed_paths,
    )


def verify_focus1_checkpoint_authority(
    repository_root: Path,
    *,
    observed_paths: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper preserving the pre-amendment generic status."""

    root = _canonical_git_repository_root(repository_root)
    if root.joinpath(*FOCUS1_AUTHORITY_RECORD_PATH.split("/")).is_file():
        verified = verify_focus1_authority(root, observed_paths=observed_paths)
    else:
        verified = _verify_focus1_authority_contract(
            root,
            _lineage_authority_record(),
            observed_paths=observed_paths,
        )
    compatible = dict(verified)
    compatible["authority_status"] = verified["status"]
    compatible["status"] = FOCUS1_AUTHORITY_VERIFIED
    return compatible


def _json_without_duplicate_keys(raw: str) -> Any:
    def build(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise PortabilityVerificationError(
                    PACKAGING_PORTABILITY_INCOMPLETE,
                    f"Duplicate JSON key is forbidden: {key!r}.",
                )
            result[key] = value
        return result

    try:
        return json.loads(raw, object_pairs_hook=build)
    except PortabilityVerificationError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_INCOMPLETE,
            f"Amendment record is not valid UTF-8 JSON: {exc}",
        ) from exc


def _load_record(
    repository_root: Path, record_path: str
) -> tuple[dict[str, Any], LoadedAuthorityFile]:
    loaded = _read_repository_file_once(repository_root, record_path)
    parsed = _parse_loaded_json(loaded, "Amendment record")
    required = {
        "schema_version",
        "amendment_id",
        "amendment_type",
        "frozen_authorities",
        "frozen_yaml_files",
        "gitattributes_rules",
        "hash_rebindings",
        "declarations",
    }
    if set(parsed) != required:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_INCOMPLETE,
            "Amendment record does not have the exact required top-level schema.",
            details={
                "missing": sorted(required - set(parsed)),
                "extra": sorted(set(parsed) - required),
            },
        )
    return parsed, loaded


def _load_integrity_record(
    repository_root: Path,
    *,
    parent_record: Mapping[str, Any],
    parent_loaded: LoadedAuthorityFile,
) -> tuple[dict[str, Any], LoadedAuthorityFile]:
    loaded = _read_repository_file_once(repository_root, INTEGRITY_RECORD_PATH)
    parsed = _parse_loaded_json(loaded, "Packaging-integrity amendment record")
    required = {
        "schema_version",
        "amendment_id",
        "amendment_type",
        "parent_amendment_id",
        "parent_record",
        "focus1_authority",
        "authorized_rebinding_paths",
        "authorized_rebindings_sha256",
        "authority_json_paths",
        "trust_boundary",
        "declarations",
    }
    if set(parsed) != required:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_INCOMPLETE,
            "Packaging-integrity record has an invalid exact schema.",
        )
    if (
        parsed["schema_version"] != "ragwarrant_packaging_integrity_amendment.v2"
        or parsed["amendment_id"] != INTEGRITY_AMENDMENT_ID
        or parsed["amendment_type"] != INTEGRITY_AMENDMENT_TYPE
        or parsed["parent_amendment_id"] != AMENDMENT_ID
    ):
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_POLICY_MISMATCH,
            "Packaging-integrity amendment identity differs from authority 002.",
        )
    if parsed["parent_record"] != {
        "path": DEFAULT_RECORD_PATH,
        "sha256": parent_loaded.sha256,
    } or parent_loaded.relative_path != DEFAULT_RECORD_PATH:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_HASH_MISMATCH,
            "Packaging-integrity record does not bind the exact parent record bytes.",
        )
    if parsed["focus1_authority"] != {
        "checkpoint_commit": FOCUS1_CHECKPOINT_COMMIT,
        "accepted_digest": FOCUS1_DIGEST,
    }:
        raise PortabilityVerificationError(
            FOCUS1_AUTHORITY_UNTRUSTED_SOURCE,
            "Packaging-integrity record changed the immutable Focus 1 authority.",
        )
    parent_rebindings = parent_record.get("hash_rebindings")
    if not isinstance(parent_rebindings, list):
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_INCOMPLETE,
            "Parent packaging record has no rebinding list.",
        )
    parent_rebinding_hash = hashlib.sha256(
        json.dumps(
            parent_rebindings,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    if (
        parsed["authorized_rebinding_paths"] != sorted(REQUIRED_REBINDING_PATHS)
        or parsed["authorized_rebindings_sha256"] != parent_rebinding_hash
    ):
        raise PortabilityVerificationError(
            PACKAGING_REBINDING_EXTRA_AUTHORITY_ENTRY,
            "Packaging-integrity and parent rebinding authorities differ.",
        )
    if parsed["authority_json_paths"] != [
        ".local_data/research_review/confirmation_amendment/ORIGINAL_MATERIALIZATION_INVENTORY.json",
        ".local_data/research_review/confirmation_amendment/confirmation_provenance_amendment_v1.json",
    ]:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_POLICY_MISMATCH,
            "Packaging-integrity record changed the two fixed authority JSON locations.",
        )
    if parsed["trust_boundary"] != {
        "verifier_self_attestation": False,
        "reviewed_git_commit_and_ci_required": True,
        "global_external_copy_integrity_claimed": False,
    }:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_POLICY_MISMATCH,
            "Packaging-integrity trust boundary is not the reviewed limited claim.",
        )
    if parsed["declarations"] != {
        "scientific_input_changed": False,
        "result_changed": False,
        "original_confirmation_output_changed": False,
        "simulation_rerun": False,
        "full_executed": False,
        "drand_accessed": False,
    }:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_POLICY_MISMATCH,
            "Packaging-integrity declarations differ from the nonscientific scope.",
        )
    return parsed, loaded


def _verify_authorities(record: Mapping[str, Any]) -> None:
    if record.get("schema_version") != SCHEMA_VERSION:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_INCOMPLETE,
            "Packaging-portability schema version is not recognized.",
        )
    if record.get("amendment_id") != AMENDMENT_ID:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_POLICY_MISMATCH,
            "Amendment ID differs from the authorized amendment.",
        )
    if record.get("amendment_type") != AMENDMENT_TYPE:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_POLICY_MISMATCH,
            "Amendment type differs from the authorized amendment.",
        )
    authorities = record.get("frozen_authorities")
    if not isinstance(authorities, dict) or set(authorities) != {
        "focus1_digest",
        "v1_hash",
        "original_confirmation_output_set_sha256",
    }:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_INCOMPLETE,
            "Frozen authorities do not have the exact required schema.",
        )
    expected = {
        "focus1_digest": FOCUS1_DIGEST,
        "v1_hash": V1_FROZEN_COMMIT,
        "original_confirmation_output_set_sha256": ORIGINAL_OUTPUT_SET_SHA256,
    }
    for key, expected_value in expected.items():
        actual = authorities.get(key)
        if key == "v1_hash":
            valid_shape = isinstance(actual, str) and bool(_GIT_SHA1_RE.fullmatch(actual))
        else:
            valid_shape = isinstance(actual, str) and bool(_SHA256_RE.fullmatch(actual))
        if not valid_shape or actual != expected_value:
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_HASH_MISMATCH,
                f"Frozen authority {key} differs from the accepted value.",
                details={"expected": expected_value, "actual": actual},
            )
    if record.get("declarations") != _EXPECTED_DECLARATIONS:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_POLICY_MISMATCH,
            "Nonscientific amendment declarations differ from the authorized scope.",
        )


def _verify_frozen_yamls(repository_root: Path, record: Mapping[str, Any]) -> None:
    declarations = record.get("frozen_yaml_files")
    if not isinstance(declarations, list) or len(declarations) != 2:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_INCOMPLETE,
            "Exactly two frozen YAML declarations are required.",
        )
    by_path: dict[str, str] = {}
    for index, entry in enumerate(declarations):
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_INCOMPLETE,
                f"frozen_yaml_files[{index}] has an invalid schema.",
            )
        path = _canonical_relative_path(entry["path"], f"frozen_yaml_files[{index}].path")
        if path in by_path:
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_INCOMPLETE,
                f"Duplicate frozen YAML declaration: {path}.",
            )
        by_path[path] = _require_sha256(
            entry["sha256"], f"frozen_yaml_files[{index}].sha256"
        )
    if by_path != FROZEN_YAML_SHA256:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_HASH_MISMATCH,
            "Frozen YAML declarations differ from the accepted exact-byte hashes.",
            details={"expected": FROZEN_YAML_SHA256, "actual": by_path},
        )
    for path, expected_hash in FROZEN_YAML_SHA256.items():
        actual_hash = sha256_file(_resolve_repository_file(repository_root, path))
        if actual_hash != expected_hash:
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_HASH_MISMATCH,
                f"Frozen YAML bytes changed: {path}.",
                details={"path": path, "expected": expected_hash, "actual": actual_hash},
            )


def _verify_gitattributes(repository_root: Path, record: Mapping[str, Any]) -> None:
    declared_rules = record.get("gitattributes_rules")
    if declared_rules != REQUIRED_GITATTRIBUTES_RULES:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_POLICY_MISMATCH,
            "Declared Git whitespace rules are not the exact narrow preserved-byte exceptions.",
        )
    for path, expected_hash in PRESERVED_BLANK_EOF_INPUT_SHA256.items():
        actual_hash = sha256_file(_resolve_repository_file(repository_root, path))
        if actual_hash != expected_hash:
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_HASH_MISMATCH,
                f"Preserved confirmation-input bytes changed: {path}.",
                details={"path": path, "expected": expected_hash, "actual": actual_hash},
            )
    attributes_path = _resolve_repository_file(repository_root, ".gitattributes")
    seen: dict[str, int] = {path: 0 for path in REQUIRED_GITATTRIBUTES_RULES}
    for line_number, raw_line in enumerate(
        attributes_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tokens = stripped.split()
        pattern, attributes = tokens[0], tokens[1:]
        whitespace_tokens = [
            token
            for token in attributes
            if token in {"-whitespace", "!whitespace", "whitespace"}
            or token.startswith("whitespace=")
        ]
        if not whitespace_tokens:
            continue
        if pattern not in REQUIRED_GITATTRIBUTES_RULES:
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_POLICY_MISMATCH,
                "A non-authorized path has a Git whitespace-attribute override.",
                details={"line": line_number, "pattern": pattern},
            )
        if tokens != [pattern, REQUIRED_GITATTRIBUTES_RULES[pattern]]:
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_POLICY_MISMATCH,
                "Preserved-byte whitespace exception is broader than blank-at-eof only.",
                details={"line": line_number, "tokens": tokens},
            )
        seen[pattern] += 1
    if any(count != 1 for count in seen.values()):
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_POLICY_MISMATCH,
            "Each preserved path requires exactly one narrow whitespace exception.",
            details={"rule_counts": seen},
        )


def _verify_hash_rebindings(
    repository_root: Path,
    record: Mapping[str, Any],
    *,
    additive_overrides: Mapping[str, tuple[str, str]] | None = None,
) -> int:
    bindings = record.get("hash_rebindings")
    if not isinstance(bindings, list):
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_INCOMPLETE,
            "hash_rebindings must be a list.",
        )
    required_fields = {
        "prior_path",
        "prior_sha256",
        "new_path",
        "new_sha256",
        "amendment_id",
        "change_category",
        "reason",
        "scientific_impact",
        "result_impact",
    }
    seen: set[str] = set()
    seen_casefold: set[str] = set()
    for index, entry in enumerate(bindings):
        if not isinstance(entry, dict) or set(entry) != required_fields:
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_INCOMPLETE,
                f"hash_rebindings[{index}] has an invalid schema.",
            )
        new_path = _canonical_relative_path(
            entry["new_path"], f"hash_rebindings[{index}].new_path"
        )
        folded = new_path.casefold()
        if new_path in seen:
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_INCOMPLETE,
                f"Duplicate replacement hash binding: {new_path}.",
            )
        if folded in seen_casefold:
            raise PortabilityVerificationError(
                AUTHORITY_PATH_ALIAS_REJECTED,
                f"Case-alias replacement hash binding is forbidden: {new_path}.",
            )
        if new_path not in AUTHORIZED_REBINDING_METADATA:
            scientific = new_path in FROZEN_YAML_SHA256 or any(
                new_path.startswith(prefix)
                for prefix in PROHIBITED_REBINDING_PREFIXES
            )
            status = (
                PACKAGING_REBINDING_UNAUTHORIZED_PATH
                if scientific
                else PACKAGING_REBINDING_EXTRA_AUTHORITY_ENTRY
            )
            raise PortabilityVerificationError(
                status,
                f"Hash rebinding is not authorized for path: {new_path}.",
                details={"path": new_path},
            )
        seen.add(new_path)
        seen_casefold.add(folded)
        new_hash = _require_sha256(
            entry["new_sha256"], f"hash_rebindings[{index}].new_sha256"
        )
        expected = AUTHORIZED_REBINDING_METADATA[new_path]
        prior_path = entry["prior_path"]
        prior_hash = entry["prior_sha256"]
        if expected["prior_path"] is None:
            if prior_path is not None or prior_hash != "NEW_FILE":
                raise PortabilityVerificationError(
                    PACKAGING_PORTABILITY_INCOMPLETE,
                    f"New path {new_path} must use null prior_path and explicit NEW_FILE authority.",
                )
        else:
            canonical_prior = _canonical_relative_path(
                prior_path, f"hash_rebindings[{index}].prior_path"
            )
            if (
                canonical_prior != expected["prior_path"]
                or prior_hash != expected["prior_sha256"]
            ):
                raise PortabilityVerificationError(
                    PACKAGING_PORTABILITY_HASH_MISMATCH,
                    f"Prior authority for {new_path} differs from the closed allowlist.",
                )
            _require_sha256(prior_hash, f"hash_rebindings[{index}].prior_sha256")
        if entry["amendment_id"] != INTEGRITY_AMENDMENT_ID:
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_POLICY_MISMATCH,
                f"Hash rebinding for {new_path} is not bound to amendment 002.",
            )
        if entry["scientific_impact"] != "NONE" or entry["result_impact"] != "NONE":
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_POLICY_MISMATCH,
                "Every portability hash rebinding must declare no scientific/result impact.",
            )
        if entry["change_category"] != expected["change_category"]:
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_POLICY_MISMATCH,
                f"Hash rebinding for {new_path} has an unknown or unauthorized category.",
            )
        if not isinstance(entry["reason"], str) or not entry["reason"].strip():
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_INCOMPLETE,
                "Every hash rebinding requires a non-empty reason.",
            )
        actual_hash = sha256_file(_resolve_repository_file(repository_root, new_path))
        independently_bound = AUTHORIZED_REPLACEMENT_SHA256.get(new_path)
        if independently_bound is not None and new_hash != independently_bound:
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_HASH_MISMATCH,
                f"Replacement authority for {new_path} differs from the accepted hash.",
                details={
                    "path": new_path,
                    "expected": independently_bound,
                    "actual_authority": new_hash,
                },
            )
        override = (additive_overrides or {}).get(new_path)
        if override is not None:
            prior_authority, replacement_authority = override
            if new_hash != prior_authority or actual_hash != replacement_authority:
                raise PortabilityVerificationError(
                    PACKAGING_PORTABILITY_HASH_MISMATCH,
                    f"Additive replacement authority does not match tracked bytes: {new_path}.",
                    details={
                        "path": new_path,
                        "parent_authority": new_hash,
                        "expected_parent": prior_authority,
                        "actual": actual_hash,
                        "replacement_authority": replacement_authority,
                    },
                )
        elif actual_hash != new_hash:
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_HASH_MISMATCH,
                f"Replacement hash does not match tracked bytes: {new_path}.",
                details={"path": new_path, "expected": new_hash, "actual": actual_hash},
            )
    actual_paths = set(seen)
    authorized_paths = set(REQUIRED_REBINDING_PATHS)
    extra = sorted(actual_paths - authorized_paths)
    if extra:
        raise PortabilityVerificationError(
            PACKAGING_REBINDING_EXTRA_AUTHORITY_ENTRY,
            "The amendment record contains extra rebinding authority entries.",
            details={"extra_rebindings": extra},
        )
    missing = sorted(authorized_paths - actual_paths)
    if missing:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_INCOMPLETE,
            "Required portability replacements are not all additively rebound.",
            details={"missing_rebindings": missing},
        )
    unknown_overrides = sorted(set(additive_overrides or {}) - actual_paths)
    if unknown_overrides:
        raise PortabilityVerificationError(
            PACKAGING_REBINDING_EXTRA_AUTHORITY_ENTRY,
            "Detached authority rebinding does not correspond to a parent binding.",
            details={"extra_rebindings": unknown_overrides},
        )
    return len(bindings)


def _snapshot_regular_files(root: Path) -> dict[str, tuple[int, str]]:
    snapshot: dict[str, tuple[int, str]] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        file_stat = os.lstat(path)
        if _is_link_or_reparse(file_stat):
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
                "Workspace materialization contains a symlink, junction, or reparse point.",
            )
        if stat.S_ISDIR(file_stat.st_mode):
            continue
        if not stat.S_ISREG(file_stat.st_mode):
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
                "Workspace materialization contains a non-regular file.",
            )
        relative = path.relative_to(root).as_posix()
        snapshot[relative] = (file_stat.st_size, sha256_file(path))
    return snapshot


def _load_json_path(
    repository_root: Path,
    relative_path: str,
    label: str,
) -> tuple[dict[str, Any], LoadedAuthorityFile]:
    loaded = _read_repository_file_once(repository_root, relative_path)
    return _parse_loaded_json(loaded, label), loaded


def _output_set_hash(entries: Sequence[Mapping[str, Any]]) -> str:
    normalized = [
        {
            "path": entry["path"],
            "size_bytes": entry["size_bytes"],
            "sha256": entry["sha256"],
        }
        for entry in sorted(entries, key=lambda item: str(item["path"]))
    ]
    payload = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_file_declaration(entry: Any, label: str) -> dict[str, Any]:
    if not isinstance(entry, dict) or set(entry) != {"path", "size_bytes", "sha256"}:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
            f"{label} has an invalid file-declaration schema.",
        )
    path = _canonical_relative_path(entry["path"], f"{label}.path")
    size = entry["size_bytes"]
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
            f"{label}.size_bytes must be a non-negative integer.",
        )
    digest = _require_sha256(entry["sha256"], f"{label}.sha256")
    return {"path": path, "size_bytes": size, "sha256": digest}


def _verify_declared_file(
    repository_root: Path,
    entry: Mapping[str, Any],
    *,
    label: str,
) -> LoadedAuthorityFile:
    declaration = _require_file_declaration(dict(entry), label)
    loaded = _read_repository_file_once(repository_root, declaration["path"])
    if (
        loaded.size_bytes != declaration["size_bytes"]
        or loaded.sha256 != declaration["sha256"]
    ):
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
            f"{label} bytes differ from the preserved declaration.",
            details={
                "path": declaration["path"],
                "expected_size": declaration["size_bytes"],
                "actual_size": loaded.size_bytes,
                "expected_sha256": declaration["sha256"],
                "actual_sha256": loaded.sha256,
            },
        )
    return loaded


def _rebindings_by_preserved_path(
    hash_rebindings: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for binding in hash_rebindings:
        prior_path = binding.get("prior_path")
        new_path = binding.get("new_path")
        if not isinstance(prior_path, str) or prior_path != new_path:
            continue
        if prior_path in result:
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
                f"Duplicate workspace rebinding for preserved path: {prior_path}.",
            )
        result[prior_path] = binding
    return result


def _verify_preserved_or_rebound_file(
    repository_root: Path,
    entry: Mapping[str, Any],
    rebindings: Mapping[str, Mapping[str, Any]],
    *,
    label: str,
) -> str:
    declaration = _require_file_declaration(dict(entry), label)
    path = _resolve_repository_file(repository_root, declaration["path"])
    actual_size = path.stat().st_size
    actual_hash = sha256_file(path)
    if actual_size == declaration["size_bytes"] and actual_hash == declaration["sha256"]:
        return "PRESERVED_EXACTLY"
    binding = rebindings.get(declaration["path"])
    if (
        binding is None
        or binding.get("prior_sha256") != declaration["sha256"]
        or binding.get("new_sha256") != actual_hash
        or binding.get("scientific_impact") != "NONE"
        or binding.get("result_impact") != "NONE"
    ):
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
            f"{label} changed without an exact additive old-to-new hash binding.",
            details={
                "path": declaration["path"],
                "preserved_sha256": declaration["sha256"],
                "actual_sha256": actual_hash,
            },
        )
    return "ADDITIVELY_REBOUND_NONSCIENTIFIC"


def _verify_workspace_contract(
    repository_root: Path,
    materialization_root: Path,
    before: Mapping[str, tuple[int, str]],
    hash_rebindings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    materialization_relative = materialization_root.relative_to(repository_root).as_posix()
    amendment_relative = (
        PurePosixPath(materialization_relative).parent / "confirmation_amendment"
    ).as_posix()
    inventory_relative_path = (
        PurePosixPath(amendment_relative) / "ORIGINAL_MATERIALIZATION_INVENTORY.json"
    ).as_posix()
    inventory, inventory_loaded = _load_json_path(
        repository_root,
        inventory_relative_path,
        "Original materialization inventory",
    )
    expected_inventory_scalars = {
        "focus1_digest": FOCUS1_DIGEST,
        "v1_frozen_commit": V1_FROZEN_COMMIT,
        "canonical_output_root": materialization_relative,
        "materialization_scope": "AUTHORITATIVE_WITHIN_DECLARED_REPOSITORY_WORKSPACE",
    }
    for key, expected in expected_inventory_scalars.items():
        if inventory.get(key) != expected:
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
                f"Original inventory field {key} differs from the qualified authority.",
            )
    output_set = inventory.get("output_set_hash")
    if not isinstance(output_set, dict) or output_set.get("sha256") != ORIGINAL_OUTPUT_SET_SHA256:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_HASH_MISMATCH,
            "Original inventory output-set hash differs from the accepted authority.",
        )
    if output_set.get("file_policy") != "EXACT_DECLARED_FILE_SET_NO_EXTRA_FILES":
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
            "Original output-set policy is not exact-file-set verification.",
        )
    raw_outputs = inventory.get("original_outputs")
    if not isinstance(raw_outputs, list) or not raw_outputs:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
            "Original inventory has no output declarations.",
        )
    outputs = [
        _require_file_declaration(entry, f"original_outputs[{index}]")
        for index, entry in enumerate(raw_outputs)
    ]
    if _output_set_hash(outputs) != ORIGINAL_OUTPUT_SET_SHA256:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_HASH_MISMATCH,
            "Declared original output set no longer reproduces its accepted hash.",
        )
    canonical_prefix = expected_inventory_scalars["canonical_output_root"] + "/"
    expected_snapshot: dict[str, tuple[int, str]] = {}
    for entry in outputs:
        if not entry["path"].startswith(canonical_prefix):
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
                "An original output is outside the canonical materialization root.",
            )
        relative = entry["path"][len(canonical_prefix) :]
        if not relative:
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
                "Original output declaration names the output directory itself.",
            )
        expected_snapshot[relative] = (entry["size_bytes"], entry["sha256"])
    if dict(before) != expected_snapshot:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
            "Materialization bytes do not match the exact declared original output set.",
            details={
                "expected_files": sorted(expected_snapshot),
                "actual_files": sorted(before),
            },
        )

    rebindings = _rebindings_by_preserved_path(hash_rebindings)
    raw_inputs = inventory.get("original_inputs")
    if not isinstance(raw_inputs, list) or not raw_inputs:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
            "Original inventory has no input declarations.",
        )
    input_statuses = {
        _require_file_declaration(entry, f"original_inputs[{index}]")["path"]: (
            _verify_preserved_or_rebound_file(
                repository_root,
                entry,
                rebindings,
                label=f"original_inputs[{index}]",
            )
        )
        for index, entry in enumerate(raw_inputs)
    }

    provenance_relative_path = (
        PurePosixPath(amendment_relative) / "confirmation_provenance_amendment_v1.json"
    ).as_posix()
    provenance, provenance_loaded = _load_json_path(
        repository_root,
        provenance_relative_path,
        "Confirmation provenance record",
    )
    if provenance.get("source_output_set_sha256") != ORIGINAL_OUTPUT_SET_SHA256:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_HASH_MISMATCH,
            "Confirmation provenance record changed the primary output-set authority.",
        )
    source_inventory = provenance.get("source_inventory")
    if not isinstance(source_inventory, dict):
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
            "Confirmation provenance record omits its source inventory binding.",
        )
    inventory_relative = inventory_loaded.relative_path
    if (
        source_inventory.get("path") != inventory_relative
        or source_inventory.get("sha256") != inventory_loaded.sha256
    ):
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
            "Confirmation provenance source-inventory binding changed.",
        )

    freeze_declaration = provenance.get("reviewed_implementation_freeze")
    if not isinstance(freeze_declaration, dict):
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
            "Confirmation provenance record omits its reviewed freeze binding.",
        )
    freeze_loaded = _verify_declared_file(
        repository_root,
        freeze_declaration,
        label="reviewed_implementation_freeze",
    )
    freeze = _parse_loaded_json(freeze_loaded, "Reviewed implementation freeze")
    for key, expected in {
        "focus1_digest": FOCUS1_DIGEST,
        "v1_frozen_commit": V1_FROZEN_COMMIT,
        "original_output_set_sha256": ORIGINAL_OUTPUT_SET_SHA256,
        "materialization_scope": "AUTHORITATIVE_WITHIN_DECLARED_REPOSITORY_WORKSPACE",
        "simulation_rerun": False,
        "scientific_design_inputs_changed": False,
    }.items():
        if freeze.get(key) != expected:
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
                f"Reviewed implementation freeze field {key} changed.",
            )
    raw_frozen_files = freeze.get("frozen_files")
    if not isinstance(raw_frozen_files, list) or not raw_frozen_files:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
            "Reviewed implementation freeze has no frozen-file declarations.",
        )
    freeze_statuses = {
        _require_file_declaration(entry, f"frozen_files[{index}]")["path"]: (
            _verify_preserved_or_rebound_file(
                repository_root,
                entry,
                rebindings,
                label=f"frozen_files[{index}]",
            )
        )
        for index, entry in enumerate(raw_frozen_files)
    }

    registry_declaration = provenance.get("registry")
    if not isinstance(registry_declaration, dict):
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
            "Confirmation provenance record omits its registry binding.",
        )
    registry_loaded = _verify_declared_file(
        repository_root, registry_declaration, label="registry"
    )
    registry = _parse_loaded_json(registry_loaded, "Canonical materialization registry")
    for key, expected in {
        "focus1_digest": FOCUS1_DIGEST,
        "v1_frozen_commit": V1_FROZEN_COMMIT,
        "source_output_set_sha256": ORIGINAL_OUTPUT_SET_SHA256,
        "canonical_output_root": expected_inventory_scalars["canonical_output_root"],
        "canonical_materialization_id": inventory.get("canonical_materialization_id"),
        "materialization_scope": "AUTHORITATIVE_WITHIN_DECLARED_REPOSITORY_WORKSPACE",
        "registry_state": "IMPORTED_EXISTING_ORIGINAL",
        "simulation_executed_by_amendment": False,
    }.items():
        if registry.get(key) != expected:
            raise PortabilityVerificationError(
                PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
                f"Canonical materialization registry field {key} changed.",
            )
    if (
        registry.get("source_inventory_path") != inventory_relative
        or registry.get("source_inventory_sha256") != inventory_loaded.sha256
    ):
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
            "Canonical registry source-inventory binding changed.",
        )
    return {
        "status": "CONFIRMATION_PROVENANCE_VERIFIED",
        "output_set_sha256": ORIGINAL_OUTPUT_SET_SHA256,
        "file_count": len(before),
        "bytes_unchanged": True,
        "additively_rebound_inputs": sorted(
            path
            for path, status in {**input_statuses, **freeze_statuses}.items()
            if status == "ADDITIVELY_REBOUND_NONSCIENTIFIC"
        ),
        "authority_json_1": {
            "status": AUTHORITY_PATH_VERIFIED,
            "path": inventory_loaded.relative_path,
            "sha256": inventory_loaded.sha256,
        },
        "authority_json_2": {
            "status": AUTHORITY_PATH_VERIFIED,
            "path": provenance_loaded.relative_path,
            "sha256": provenance_loaded.sha256,
        },
        "reviewed_freeze_sha256": freeze_loaded.sha256,
        "registry_sha256": registry_loaded.sha256,
    }


def verify_workspace_materialization_read_only(
    materialization_root: Path,
    *,
    repository_root: Path,
    hash_rebindings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Verify the explicit ignored materialization without changing any bytes."""

    if not materialization_root.is_absolute():
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
            "Workspace materialization root must be supplied as an absolute path.",
        )
    root = _canonical_git_repository_root(repository_root)
    _validate_unaliased_absolute_path(materialization_root)
    materialization_absolute = Path(os.path.abspath(os.fspath(materialization_root)))
    try:
        materialization_absolute.relative_to(root)
    except ValueError as exc:
        raise PortabilityVerificationError(
            AUTHORITY_PATH_OUTSIDE_REPOSITORY,
            "Workspace materialization must be inside the verified repository root.",
        ) from exc
    if not materialization_absolute.is_dir():
        raise PortabilityVerificationError(
            AUTHORITY_PATH_OUTSIDE_REPOSITORY,
            "Workspace materialization root must be an existing directory.",
        )
    before = _snapshot_regular_files(materialization_absolute)
    try:
        details = _verify_workspace_contract(
            root,
            materialization_absolute,
            before,
            hash_rebindings,
        )
    finally:
        after = _snapshot_regular_files(materialization_absolute)
    if before != after:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_WORKSPACE_MISMATCH,
            "Read-only provenance verification changed original materialization bytes.",
        )
    if details.get("output_set_sha256") != ORIGINAL_OUTPUT_SET_SHA256:
        raise PortabilityVerificationError(
            PACKAGING_PORTABILITY_HASH_MISMATCH,
            "Workspace output-set hash differs from the accepted authority.",
        )
    return details


def verify_packaging_portability(
    repository_root: Path,
    *,
    record_path: str = DEFAULT_RECORD_PATH,
    workspace_materialization_root: Path | None = None,
) -> VerificationResult:
    """Verify tracked portability bindings and optional ignored materialization."""

    try:
        root = _canonical_git_repository_root(repository_root)
        record_path = _canonical_relative_path(record_path, "record_path")
        if record_path != DEFAULT_RECORD_PATH:
            raise PortabilityVerificationError(
                AUTHORITY_PATH_ALIAS_REJECTED,
                "Only the canonical packaging-portability authority record path is accepted.",
                details={
                    "expected": DEFAULT_RECORD_PATH,
                    "actual": record_path,
                },
            )
        detached_record_path = root.joinpath(*FOCUS1_AUTHORITY_RECORD_PATH.split("/"))
        detached_record = (
            _load_focus1_authority_record(root)
            if detached_record_path.is_file()
            else None
        )
        focus1_authority = verify_focus1_checkpoint_authority(root)
        record, record_loaded = _load_record(root, record_path)
        integrity_record, integrity_loaded = _load_integrity_record(
            root,
            parent_record=record,
            parent_loaded=record_loaded,
        )
        _verify_authorities(record)
        _verify_frozen_yamls(root, record)
        _verify_gitattributes(root, record)
        binding_count = _verify_hash_rebindings(
            root,
            record,
            additive_overrides=(
                _focus1_authority_rebinding_overrides(detached_record)
                if detached_record is not None
                else None
            ),
        )
        workspace_details: Mapping[str, Any]
        if workspace_materialization_root is None:
            workspace_details = {
                "status": "NOT_REQUESTED",
                "bytes_unchanged": None,
            }
        else:
            workspace_details = verify_workspace_materialization_read_only(
                workspace_materialization_root,
                repository_root=root,
                hash_rebindings=_effective_workspace_rebindings(
                    record["hash_rebindings"], detached_record
                ),
            )
        return VerificationResult(
            status=PACKAGING_PORTABILITY_VERIFIED,
            ok=True,
            message="Packaging-portability amendment verified read-only.",
            details={
                "amendment_id": AMENDMENT_ID,
                "integrity_amendment_id": INTEGRITY_AMENDMENT_ID,
                "record_path": record_path,
                "record_sha256": record_loaded.sha256,
                "integrity_record_path": integrity_loaded.relative_path,
                "integrity_record_sha256": integrity_loaded.sha256,
                "focus1_authority": {
                    key: value
                    for key, value in focus1_authority.items()
                    if key != "manifest"
                },
                "frozen_yaml_sha256": dict(FROZEN_YAML_SHA256),
                "preserved_blank_eof_input_sha256": dict(
                    PRESERVED_BLANK_EOF_INPUT_SHA256
                ),
                "hash_rebinding_count": binding_count,
                "workspace_materialization": dict(workspace_details),
                "simulation_rerun": False,
            },
        )
    except PortabilityVerificationError as exc:
        return exc.as_result()


__all__ = [
    "AMENDMENT_ID",
    "AMENDMENT_TYPE",
    "DEFAULT_RECORD_PATH",
    "FOCUS1_DIGEST",
    "FOCUS1_AUTHORITY_RECORD_PATH",
    "FOCUS1_AUTHORITY_REF",
    "FOCUS1_AUTHORITY_VERIFIED_DETACHED",
    "FOCUS1_AUTHORITY_VERIFIED_LINEAGE",
    "FOCUS1_CHECKPOINT_COMMIT",
    "FROZEN_YAML_SHA256",
    "ORIGINAL_OUTPUT_SET_SHA256",
    "PRESERVED_BLANK_EOF_INPUT_SHA256",
    "PACKAGING_PORTABILITY_HASH_MISMATCH",
    "PACKAGING_PORTABILITY_INCOMPLETE",
    "PACKAGING_PORTABILITY_POLICY_MISMATCH",
    "PACKAGING_PORTABILITY_VERIFIED",
    "PACKAGING_PORTABILITY_WORKSPACE_MISMATCH",
    "PortabilityVerificationError",
    "REQUIRED_GITATTRIBUTES_RULES",
    "REQUIRED_REBINDING_PATHS",
    "SCHEMA_VERSION",
    "V1_FROZEN_COMMIT",
    "VerificationResult",
    "sha256_file",
    "verify_focus1_checkpoint_authority",
    "verify_focus1_authority",
    "verify_focus1_portable_authority",
    "verify_packaging_portability",
    "verify_workspace_materialization_read_only",
]
