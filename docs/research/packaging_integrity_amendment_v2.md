# Packaging integrity amendment 002

Amendment ID: `RAGWARRANT-PACKAGING-INTEGRITY-002`

Amendment type: `TRUST_ROOT_REBINDING_AND_PATH_CONTAINMENT_HARDENING`

This is a nonscientific correction to the packaging-portability verifier. It
does not change a benchmark scenario, truth, threshold, margin, risk, sample
size, seed, method, estimand, result, or original confirmation output. It does
not run simulation, FULL, or drand.

## Closed rebinding authority

The authorized rebinding paths are an exact, explicitly enumerated set in the
packaging records and verifier. The verifier requires exact set equality,
canonical repository-relative POSIX spelling, the accepted prior identity (or
the literal `NEW_FILE` authority), amendment 002, the exact change category,
and `NONE` for both scientific and result impact. It rejects extra, missing,
duplicate, case-alias, wildcard, prefix, absolute, drive-qualified, UNC,
traversal, linked, junction-backed, reparse-backed, malformed, or scientific
entries. The authority is not derived from Git status, staged paths, current
changes, untracked files, workspace hashes, or a glob.

## Focus 1 trust root

The authority is checkpoint commit
`124836bcc2fba48373d7bd08f0087b23f2e41620` together with accepted digest
`c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e`.
The strict packaging verifier reads the checkpoint generator and all frozen
input bytes through raw Git blob access, reconstructs the accepted 36-path
inventory and digest, and then independently compares the candidate bytes
against those hashes. For shallow clean-checkout tests, a separate adapter
uses the fixed checkpoint-derived 36-path hash inventory, proves that inventory
reproduces the accepted digest, and compares current bytes before materializing
an operating-system-temporary manifest. That adapter does not define authority
from the current workspace, replace the production freeze verifier, or return
the accepted digest unconditionally.

The strict CLI fails closed with `FOCUS1_AUTHORITY_CHECKPOINT_MISSING` when a
shallow checkout omits the checkpoint object. The raw-blob reproduction test
therefore requires full history, while the accepted-inventory digest and
candidate-byte comparisons remain mandatory clean-checkout tests.

The digest binds only the fields selected by the accepted freeze algorithm and
the frozen path/hash inventory. It does not independently establish scientific
validity, output integrity, FULL execution status, or drand status.

## Filesystem containment

The canonical repository root comes from `git rev-parse --show-toplevel` and
must be supplied directly, without a symlink, junction, mount-point alias, or
other reparse surrogate. Authority paths are fixed repository-relative paths.
Every component is checked with `lstat`; Windows Python 3.11 uses file
attributes and reparse tags instead of `Path.is_junction()`.

Authority JSON is opened once in binary read-only mode. The verifier hashes
and parses the same captured bytes and compares path and open-handle metadata
where the platform exposes it. The two primary ignored authority files are:

- `.local_data/research_review/confirmation_amendment/ORIGINAL_MATERIALIZATION_INVENTORY.json`
- `.local_data/research_review/confirmation_amendment/confirmation_provenance_amendment_v1.json`

The materialization verifier is explicitly bound to the repository root whose
tracked packaging record was verified. It does not search outside that root
and does not claim global uniqueness or control over arbitrary external
copies.

## Trust boundary

The verifier does not cryptographically attest its own executable source.
The reviewed Git commit SHA and CI execution are part of the trust model. The
checkpoint and accepted digest provide the independent Focus 1 data authority;
the packaging verifier compares candidate bytes to that authority. Final
packaging still requires code review and the supported test gates.
