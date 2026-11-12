# {{F-nnn}}: {{Feature title}}

| Field | Value |
|---|---|
| Feature ID | {{F-nnn}} |
| Execution wave | {{from plan.json}} |
| Hard dependencies | {{F-ids, or none}} |
| Source requirements | {{FR-001, BR-003, NFR-002 …}} |

## 1. Description
Purpose and scope, plus what is explicitly **not** part of this feature.

## 2. Business rules
Every row cites the requirement it comes from.

| Requirement | Rule (quoted from the FRD) | Enforcement (DB constraint / service / UI) |
|---|---|---|

## 3. Acceptance criteria
IDs are `AC-F{{nnn}}-01`, `-02`, and so on. Each criterion is in Given/When/Then form and links at least one of the feature's requirements. Every FR and BR of the feature has at least one criterion.

| ID | Criterion (Given/When/Then) | Requirements |
|---|---|---|
| AC-F{{nnn}}-01 | Given ..., when ..., then ... | FR-... |

## 4. Database
- Tables and columns introduced or changed (copied from `schema.sql`, including constraints and indexes)
- Migration name and order
- Seed or reference data

## 5. Backend
- Services and functions, with signatures
- Repositories
- Domain exceptions, and the error code each one maps to
- Authorization rules (role and ownership)

## 6. API
| operationId | Method and path | Roles | Request | Responses (codes) |
|---|---|---|---|---|

## 7. Frontend
- Screens (S-nnn), routes and roles
- Components
- Form fields and validation messages
- States: loading, empty, error, success

## 8. Security
Authentication and authorization specifics, data exposure rules, and audit events.

## 9. Non-functional requirements
The NFRs that apply, with measurable targets and how each is verified.

## 10. Dependencies
- Features
- Shared components and APIs it consumes

## 11. Test cases
IDs are `T-F{{nnn}}-01`, `-02`, and so on. Every acceptance criterion is covered by at least one test.

| ID | Level (unit/api/integration/e2e) | Scenario | Expected | Covers (AC) | Requirements |
|---|---|---|---|---|---|
| T-F{{nnn}}-01 | api | ... | ... | AC-F{{nnn}}-01 | FR-... |

## 12. Files by owner
Mark files that already exist with `(modify)`.

| Agent | Files to create or modify |
|---|---|
| database-dev | backend/app/models/… , backend/migrations/… |
| backend-dev | backend/app/services/… |
| api-dev | backend/app/api/… , backend/app/schemas/… |
| frontend-dev | frontend/src/pages/… |
| tester | backend/tests/api/test_f_nnn_….py |

## 13. Open items
`OPEN:` anything the spec could not resolve, for the SME agent to handle.
