# CLA Assistant Setup

Status: `CLA_ASSISTANT_INSTALLATION_PENDING_HUMAN_ACTION`

CLA Assistant is an external GitHub App. Installation and signed-contributor record handling require repository-owner or organization-admin action. Do not fabricate installation or create a fake CI job that always succeeds.

## Setup Steps

1. Obtain counsel approval for the individual and corporate CLA text.
2. Publish the approved CLA text in the configured CLA Assistant storage location, commonly a GitHub Gist or repository file supported by the app.
3. Install the CLA Assistant GitHub App for `RAGWarrant/ragwarrant-governance`.
4. Authorize the repository in the app.
5. Configure the CLA document location.
6. Configure the required status-check name exactly as emitted by the app.
7. Add the CLA status check to the `main` branch protection or repository ruleset.
8. Test with a disposable outside-contributor PR.
9. Export or back up signed-contributor records according to the organization's records policy.

## Branch Protection Integration

Once the app is genuinely installed and verified, configure `main` so outside pull requests cannot merge unless the CLA status is successful.

## Records

Signed-contributor records are legal/administrative records. Do not commit private signature records, private email addresses, or app secrets to this repository.
