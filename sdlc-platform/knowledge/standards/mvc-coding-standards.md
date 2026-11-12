# MVC architecture and programming standards

These standards are mandatory for every generated application:
- The architect copies them into `02-spec/coding-standards.md`, adding stack-specific tooling.
- Every developer agent follows them.
- The `nfr-reviewer` and `security-auditor` agents report violations.
- `tools/layer_check.py` enforces the layer dependency rules on Python and TypeScript/JavaScript code.

## 1. Layers (MVC + Service + Repository)

| Layer | Responsibility | Must NOT |
|---|---|---|
| **Model** | Persistence entities (ORM models), their fields, relations and constraints | Contain HTTP code, call services, or contain workflow logic |
| **Repository** | Data access: queries and persistence for one aggregate or model | Contain business rules or HTTP concerns |
| **Service** | Business logic: rules, calculations, transactions, authorization decisions | Import controllers or HTTP/framework request objects, or return HTTP responses |
| **Controller** | HTTP boundary: parse and validate input (DTOs), call one or more services, map results and domain errors to responses | Contain business rules, run queries, or access repositories or the ORM directly |
| **DTO / Schema** | Request and response contracts, matching the OpenAPI spec | Contain logic beyond validation |
| **View** (frontend) | Pages and screens: compose components, bind to controller hooks and state | Call `fetch`/HTTP directly, or contain business rules |
| **Component** (frontend) | Reusable presentational UI | Call APIs; data comes in through props |
| **Frontend service / API client** | Typed calls to the backend API | Render UI |

**Allowed dependency direction:**
`Controller → Service → Repository → Model`. DTOs may be used by controllers and services. `core/` (config, security, db session, errors) may be used by every layer.

## 2. Default folder structure

The architect adapts this structure to the chosen stack, keeping the same layers.

```
app/
  backend/
    app/
      controllers/     # HTTP endpoints, one module per resource (e.g. leave_controller.py)
      services/        # business logic (leave_service.py)
      repositories/    # data access (leave_repository.py)
      models/          # ORM entities (leave_request.py)
      schemas/         # DTOs: request/response models (leave_schemas.py)
      core/            # config, security, db session, error envelope, logging
      main.py          # app factory and router registration only
    migrations/
    tests/  unit/  api/  system/  security/
  frontend/
    src/
      views/           # pages / screens (LeaveApplyView.tsx)
      components/      # reusable presentational components
      controllers/     # hooks or state that connect views to services (useLeaveRequests.ts)
      services/        # API client modules (leaveService.ts) on top of api/client.ts
      api/client.ts    # shared HTTP client (auth header, error envelope)
      types/           # shared TS types generated from or mirroring the OpenAPI schemas
      utils/
```

Equivalent structures for other stacks:
- **Spring Boot:** `controller/`, `service/`, `repository/`, `model/` (entity), `dto/` and `config/` under the base package.
- **ASP.NET Core MVC:** `Controllers/`, `Services/`, `Repositories/`, `Models/`, `DTOs/` and `Views/` (if server-rendered).
- **Express/NestJS:** `controllers/`, `services/`, `repositories/`, `models/` (or `entities/`) and `dto/`.
- **Angular frontend:** `views/` (routed components), `components/`, `services/` and `models/`.

## 3. Naming conventions

| Item | Python | TypeScript / Java / C# |
|---|---|---|
| Files | `snake_case.py`, with a suffix by layer: `_controller`, `_service`, `_repository` | `PascalCase` for classes and components (`LeaveService.ts`), `camelCase` for functions and hooks |
| Classes | `PascalCase` (`LeaveService`) | `PascalCase` |
| Functions and variables | `snake_case` | `camelCase` |
| Constants | `UPPER_SNAKE_CASE` | `UPPER_SNAKE_CASE` |
| DB tables and columns | `snake_case`, plural table names | same |
| REST paths | `/api/v1/<plural-kebab-noun>` | same |

## 4. Programming standards

- **Formatting and linting.** Use the stack's standard toolchain, configured in the repository and run in CI:
  - Python: PEP 8 via `ruff` (lint and format) and `mypy` for type hints.
  - TypeScript: `eslint` plus `prettier`, with `strict` mode in tsconfig.
  - Java: Checkstyle (Google style).
  - C#: `dotnet format`.
- **Types.** Public functions are fully type-annotated, with no implicit `any` in TypeScript.
- **Single responsibility.** One class per responsibility. Functions stay at 50 lines or fewer, with a cyclomatic complexity of 10 or less.
- **Dependency injection.** Controllers receive services, and services receive repositories, through the framework's DI or constructor injection. Services never construct their own dependencies.
- **Errors.** Services raise typed domain exceptions. One central handler maps them to the error envelope `{code, message, details}`. Bare `except:` is never allowed, and errors are never silently swallowed.
- **Validation.** Validate at the controller boundary with DTOs. Business-rule validation lives in the service.
- **Transactions.** Multi-step writes run in a single transaction, owned by the service layer.
- **Security.**
  - No secrets in code; configuration comes from the environment.
  - Use parameterized queries or the ORM only.
  - Hash passwords with bcrypt or argon2.
  - Enforce authorization in the service layer as well as the controller.
- **Logging.** Use structured logging through `core/logging`. Never log passwords, tokens or personal data.
- **Configuration.** Use a single settings module or object. No magic numbers; business limits come from configuration or the database.
- **Comments and docs.** Each public service method gets a docstring or JSDoc that names the requirement IDs it implements (`Implements: FR-007, BR-002`).
- **Tests.**
  - Unit tests cover services.
  - API tests cover controllers.
  - Test names reference test-case IDs (`test_T_F004_03_rejects_overlap`).
  - Target at least 80% line coverage on services.
- **Commits.** One commit per agent step, with the message format `F-nnn: <agent>: <summary>`.
