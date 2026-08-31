# RAGWarrant research packaging-portability amendment v1

## Identity

- Amendment ID: `RAGWARRANT-RESEARCH-PACKAGING-PORTABILITY-001`
- Amendment type: `NONSCIENTIFIC_PACKAGING_AND_CLEAN_CHECKOUT_TEST_PORTABILITY`
- Machine-readable record: `configs/research/packaging_portability_amendment_v1.json`

This amendment resolves two packaging defects: Git classified the intentional
final blank line in two frozen YAML files as `blank-at-eof`, and two research
test modules required an ignored workspace materialization during ordinary
clean-checkout testing.

## Scientific and result boundary

The amendment changes no scientific input, scenario, truth, threshold,
margin, method, seed, result, interpretation rule, or confirmation output. It
does not rerun simulation. Focus 1 remains bound to
`c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e`,
the v1 baseline remains bound to
`bf3b3331b623afbdaed295919b3ac945c10692f6`, and the original confirmation
output set remains bound to
`a6ff12e61dc800be65c089cdb7cbe8aca68339a53af08d6ac1bbc95db8a57493`.

The two frozen YAML files retain their original bytes and hashes:

- `configs/research/fixed_sample_multi_risk_warrant_v2.yaml`:
  `9ea78712a5ab0cee58982cec0cd2d69bc363d2c3c084d9507e54416dc18d1238`
- `configs/research/fixed_sample_multi_risk_warrant_v2_iut_holm.yaml`:
  `b396bff282fb80ee2c9258caec1342862417b3dc92d3c30f208d9009267a1566`

## Git whitespace contract

The root `.gitattributes` file assigns `whitespace=-blank-at-eof` to exactly
those two paths. Complete candidate-tree qualification also identified the
same packaging-only condition in two already frozen confirmation inputs. Their
bytes are preserved under equally narrow exact-path rules:

- `docs/research/operational_contract_template.md`:
  `8a0b3a1162713b17221af68437f7dd0792c76dd09d07557233aa716a4572212a`
- `src/ragwarrant/research/joint_power_confirmation.py`:
  `d86f10a0d0267a170c40c01d912ca625e906244ef3f7ecfdc4ada82ebf5c8164`

No general file class is exempted. The four rules do not disable textual
diffs, trailing-space checks, other whitespace checks, or repository-wide
whitespace review. All four files remain text-reviewable. An isolated Git
negative control must continue to reject an unrelated staged
trailing-whitespace defect.

## Test portability contract

Ordinary research tests use generated `tmp_path` fixtures. These fixtures are
small, synthetic, test-only, and are never scientific evidence. They contain
no copied confirmation output, private data, secret, licensed data, or host
absolute path. No committed scientific-output fixture is required.

The accepted v1 and v2 Focus 2 integration modules retain their original
bytes and hashes. At collection time, clean-checkout test plumbing binds those
modules to a generated operating-system-temporary manifest constructed from
the accepted checkpoint-derived, fixed 36-path hash inventory. The adapter
first reproduces the accepted Focus 1 digest from that immutable inventory and
then compares every current file with it. This remains usable in a shallow
clean checkout where the checkpoint object itself is absent. The strict
packaging audit separately requires the checkpoint Git object and reproduces
the same inventory and digest from raw checkpoint blobs. The unchanged
production freeze verifier validates the temporary manifest; no test
replacement returns the accepted digest as a constant. The adapter never
reads or copies the ignored local freeze manifest. This preserves the accepted
test modules and runs their portable behavioral coverage without creating
`.local_data`.

The strict CLI reports `FOCUS1_AUTHORITY_CHECKPOINT_MISSING` and fails closed
when its checkpoint object is unavailable. Its raw-checkpoint reproduction
test runs in a full-history checkout and skips with an explicit reason in a
shallow checkout; fixed-inventory portable authority and tamper coverage remain
mandatory in either case.
Three public-beacon tests that actually execute the ignored pinned Node BLS
client are skipped only when that optional local dependency is absent; all
other public-beacon tests still run in a clean checkout.

Tests that inspect the actual ignored confirmation materialization are marked
`workspace_materialization`. They obtain its exact root only from
`RAGWARRANT_CONFIRMATION_MATERIALIZATION_ROOT`, run read-only, and skip with a
precise reason when the variable is absent. An invalid, alternate, or
noncanonical configured root fails closed. These tests do not create, repair,
rewrite, or delete the materialization.

Portable clean-checkout command:

```powershell
Remove-Item Env:RAGWARRANT_CONFIRMATION_MATERIALIZATION_ROOT -ErrorAction SilentlyContinue
python -m pytest -q tests/research
```

```sh
env -u RAGWARRANT_CONFIRMATION_MATERIALIZATION_ROOT python -m pytest -q tests/research
```

Explicit read-only workspace-materialization command:

```powershell
$env:RAGWARRANT_CONFIRMATION_MATERIALIZATION_ROOT = (Resolve-Path ".local_data/research_review/joint_power_confirmation_v1").Path
python -m pytest -q -m workspace_materialization tests/research
Remove-Item Env:RAGWARRANT_CONFIRMATION_MATERIALIZATION_ROOT
```

```sh
RAGWARRANT_CONFIRMATION_MATERIALIZATION_ROOT="$(pwd)/.local_data/research_review/joint_power_confirmation_v1" \
  python -m pytest -q -m workspace_materialization tests/research
```

## Additive hash rebinding

The machine-readable amendment record binds an exact closed set of changed
tests, pytest configuration, Git policy, verifier, and portability documents
from the accepted prior hash (or the literal `NEW_FILE`) to the replacement
hash. Every entry is bound to amendment
`RAGWARRANT-PACKAGING-INTEGRITY-002`, an exact change category, and
`scientific_impact: NONE` / `result_impact: NONE`. Extra, missing, aliased,
wildcard, prefix, and scientific-input rebindings fail closed. The immutable
historical inventories and freeze records retain their original hashes and
semantics; they are not rewritten.

The machine record cannot bind its own bytes without creating a circular hash.
Its hash is therefore bound by the local research package manifest after the
logical commits are created.

## Verification boundary

The amendment-aware verifier is read-only. In a clean checkout it verifies the
checkpoint-derived Focus 1 authority, tracked authorities, YAML hashes, exact
Git-attribute rules, and closed additive hash bindings. When explicitly given
the ignored materialization root, it binds that root to the already verified
Git workspace, rejects symlink/junction/reparse aliases, and hashes and parses
each authority JSON from one contained read-only open handle. It also verifies
the preserved original output paths, sizes, hashes, deterministic output-set
hash, and unchanged bytes without treating the updated portable test files as
original confirmation outputs.

The checkpoint commit and accepted digest are the Focus 1 authority. The
verifier compares candidate bytes against that authority, but does not
cryptographically attest its own executable source. The reviewed Git commit
and CI execution remain part of the trust model. No global integrity claim is
made for arbitrary external copies.

This amendment does not upgrade any statistical, power, provenance,
production-readiness, or real-world-validation claim.
