# Open Core Architecture

Status: `PUBLIC_CORE_DEFINED_ENTERPRISE_PLANNED`

## Community Core

RAGWarrant Community/Core is Apache-2.0 and vendor-neutral. It includes:

- governance decision engine;
- promotion, refusal, blocked, and inconclusive logic;
- public schemas;
- artifact integrity checks;
- CLI entry points;
- generic evaluator input contracts;
- generic CSV/JSON adapters;
- public-mini reproduction;
- vendor-neutral deployment contracts;
- generic container image support;
- general audit-event schema;
- scientific and research harnesses where licensing permits.

## Enterprise Responsibilities

Enterprise-only capabilities are not represented as shipped unless marked `IMPLEMENTED`.

| Capability | Status | Boundary |
| --- | --- | --- |
| SSO integrations | `PLANNED` | Enterprise-only integration layer |
| Enterprise RBAC | `PLANNED` | Enterprise authorization provider |
| Directory/group mapping | `PLANNED` | Enterprise identity adapter |
| Commercial native evaluator connectors | `PLANNED` | Enterprise connector packages |
| Managed policy registry | `PLANNED` | Enterprise backend service |
| Enterprise audit-evidence packs | `PLANNED` | Enterprise export tooling |
| Support tooling | `CONTRACTUAL_SERVICE` | Support agreement scope |
| Hardened/LTS release channel | `PLANNED` | Separate enterprise release process |
| Commercial upgrade tooling | `PLANNED` | Enterprise packaging |
| Organization controls | `PLANNED` | Enterprise admin layer |
| Enterprise deployment policies | `PLANNED` | Enterprise deployment docs/config |
| Commercial support/SLA materials | `CONTRACTUAL_SERVICE` | Order form or support agreement |

## Interface Boundary

Proprietary modules should depend on the Apache core through stable interfaces rather than copying public source:

- `EvaluatorEvidenceAdapter`
- `IdentityProvider`
- `AuthorizationProvider`
- `AuditPackExporter`
- `PolicyRegistryBackend`
- `EnterpriseConnector`

The Apache core must not be weakened to create enterprise value. Essential security fixes should remain available to the public core.

## Enterprise Repository Status

The target enterprise repository is blocked pending ownership and commercial-authority confirmation. No proprietary implementation is committed to this public repository.
