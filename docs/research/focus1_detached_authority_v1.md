# Focus 1 detached checkpoint authority amendment

Amendment ID: `RAGWARRANT-FOCUS1-DETACHED-AUTHORITY-001`
Amendment type: `DETACHED_PINNED_CHECKPOINT_AUTHORITY`

## Purpose

Focus 1 was legitimately replayed onto the merged PR #28 RAGWarrant baseline.
Cherry-picking preserved the frozen content but not the original commit ancestry.
This nonscientific amendment allowed the immutable owner-review branch to prove
exact content equivalence for the canonical 36-path Focus 1 freeze without
adding a synthetic merge parent or replaying PR #27-era commits into that
branch. The immutable owner-review commit remains the historical authority.

The stacked PR B candidate intentionally does not claim that same exact
36-path digest. It preserves 35 historical paths and contains one separately
authorized nonscientific security correction at
`.github/workflows/research-full-closure.yml`. The historical authority and
the declared PR B compatibility delta are verified as distinct claims.

No scenario, truth, threshold, margin, risk, method, seed, result, confirmation
output, production behavior, or historical artifact changes in this amendment.
The amendment also binds the merged current-main `*.pdf binary` and
`*.docx binary` review rules alongside the four pre-existing research-only
whitespace exceptions; this is a nonscientific replay-portability binding.

## Explicit modes

`LINEAGE_CHECKPOINT` requires the checkpoint commit to exist and to be an
ancestor of the candidate commit. It reads the checkpoint and candidate blobs
from Git object storage and compares their frozen path sets, hashes, and
independently computed digests.

`DETACHED_PINNED_CHECKPOINT` does not require ancestry. It requires the exact
full ref `refs/tags/ragwarrant-focus1-freeze-v1-c771afc` to directly name an
annotated tag object whose declared target type is `commit` and whose direct
target is exactly:

```text
124836bcc2fba48373d7bd08f0087b23f2e41620
```

The detached record fixes the accepted digest to:

```text
c771afc2428e50f63e29ed29e603c0e3ab3e6355c17e3ba72694b5b8f411212e
```

Modes are selected explicitly by the tracked authority record. The verifier
does not fall back from lineage to detached authority, from detached to lineage
authority, or to the portable accepted-inventory test adapter. Unknown modes
fail closed.

## Verification contract

Authority-related Git commands run with `git --no-replace-objects` and a
sanitized environment. Any replacement ref or nonempty legacy graft file makes
verification fail. The verifier:

1. Resolves the canonical repository root without accepting an aliased root.
2. Resolves the candidate `HEAD` once to a commit object ID.
3. In detached mode, resolves only the exact full authority ref, requires a
   direct annotated tag object, and captures its raw tag-object ID.
4. Requires the tag object's direct `object` header to equal the pinned
   checkpoint and its direct `type` header to equal `commit`.
5. Reads the freeze generator, configuration, beacon declaration, and every
   frozen checkpoint blob directly from the pinned checkpoint object.
6. Reconstructs the canonical path inventory and accepted freeze manifest and
   independently reproduces the checkpoint digest.
7. Reads every candidate frozen blob from the captured candidate commit, not
   from mutable working-tree files.
8. Requires equal canonical path sets, equal per-path SHA-256 values, and an
   independently computed candidate digest equal to the accepted digest.
9. Re-resolves the authority ref and fails if its raw tag-object ID changed
   during verification.
10. Returns the computed candidate digest.

The accepted detached status is
`FOCUS1_AUTHORITY_VERIFIED_DETACHED`. Lineage success returns
`FOCUS1_AUTHORITY_VERIFIED_LINEAGE`.

The strict contract above remains the historical exact-equivalence contract.
On PR B it is expected to reject the current candidate because the closure
workflow changed. PR B instead requires both
`HISTORICAL_FOCUS1_AUTHORITY_VERIFIED` for immutable owner-review bytes and
`PR_B_DECLARED_COMPATIBILITY_DELTA_VERIFIED` for the exact one-path correction.
The delta record sets `complete_historical_byte_equivalence_claimed` to false.

## Trust boundary

Detached authority verifies byte equivalence for the immutable owner-review
materialization of the canonical frozen Focus 1 path set selected by the
accepted freeze algorithm. PR B's separate delta verifier does not turn the
modified candidate into that historical materialization. Neither verifier establishes
branch ancestry, whole-tree equality, scientific validity, result validity,
production readiness, or absence of unrelated changes.

The checkpoint commit SHA and accepted SHA-256 digest are the content
authority. The annotated tag is a required transport and reachability ref; its
ordinary name is mutable and is not sufficient by itself. A missing tag or a
tag that points elsewhere fails verification. This amendment does not
authenticate tag annotation metadata, tagger identity, or a signature, and it
does not detect recreation of a different annotated tag object pointing to the
same pinned checkpoint.

The verifier does not attest its own executable integrity. The reviewed source
commit, exact authority record, CI configuration and execution, Git
implementation and object store, and review of emitted evidence remain in the
trust model. The guarantee is repository-scoped and point-in-time; arbitrary
external copies and later administrative tag changes are outside its scope.

Publishing the authority tag makes the checkpoint and its ancestors reachable
through that tag. It does not add them to the owner-review branch ancestry or
the `origin/main..owner-review` commit range. The final reviewed tip must record
that the checkpoint and former PR #27 head are not branch ancestors and that no
merge commit was introduced for authority purposes.

## CI usage

CI must fetch full history and tags, verify the tag target exactly, install the
locked project dependencies, and verify both distinct claims:

```text
verify_historical_focus1_authority(Path.cwd())
verify_pr_b_declared_compatibility_delta(Path.cwd())
```

CI must require `HISTORICAL_FOCUS1_AUTHORITY_VERIFIED` and
`PR_B_DECLARED_COMPATIBILITY_DELTA_VERIFIED`. A checkout that lacks the required
tag or immutable owner-review/checkpoint objects fails closed, as does a
missing or retargeted tag, changed historical digest, additional frozen-path
difference, or unapproved closure-workflow byte.

## Claim boundary

This amendment is a provenance and clean-checkout portability change. It is not
a new statistical method, scientific result, validation run, FULL execution,
drand selection, deployment qualification, or production integration.
