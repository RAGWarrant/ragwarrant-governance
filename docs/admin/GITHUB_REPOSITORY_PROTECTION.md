# GitHub Repository Protection

Status: `BRANCH_PROTECTION_SETUP_PENDING_ADMIN_ACTION`

The GitHub API did not return an active `main` branch-protection record during this review, and repository rulesets returned an empty list. This document provides exact setup steps rather than claiming protection is enabled.

## Recommended `main` Protection

Configure `main` to require:

- pull request before merge;
- at least one approval;
- CODEOWNER approval for owned files;
- conversations resolved;
- required status checks:
  - `CI / validate`;
  - `Publication Check / publication-check`;
  - license/header validation;
  - brand validation;
  - open-core boundary validation;
  - CLA Assistant check once genuinely installed;
- no force pushes;
- no branch deletion.

## Release Tag Protection

Protect release tags matching `v*` against deletion and force-update where GitHub supports tag protection or repository rulesets.

## CLA Assistant

Do not add a fake CLA job. Once CLA Assistant is installed and verified, add the actual CLA Assistant status check to the required checks.

## Verification

After setup, query and record the active branch-protection or ruleset configuration in `deployment_review/open_core_foundation/preflight.json`.
