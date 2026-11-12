---
name: set-tech-stack
description: Phase 1 - ask the user for the project's technology stack (frontend, backend, database, deployment), confirm any stack stated in the CRD, and record it in 01-frd/tech-stack.json. MVC is the default pattern. Runs automatically inside /generate-frd; use directly to change the stack before FRD approval.
argument-hint: "[your name]"
disable-model-invocation: true
---
Capture the technology stack decision for the active project. Arguments: `$ARGUMENTS`. `P = ../projects/<id>`.

## 1. Preconditions
- Run `python tools/gate.py crd-parsed`. Stop if it fails.
- If `P/01-frd/approval.json` has decision `approved`, the stack is locked with the FRD. Tell the user that changing it requires `/revise-frd`, then a re-approval, then this command. Stop.

## 2. Find what the CRD already says
Grep `P/01-frd/crd.md` (case-insensitive) for technology mentions, for example: java, spring, .net, c#, python, django, fastapi, flask, node, express, nest, react, angular, vue, next, php, laravel, postgres, mysql, sql server, oracle, mongo, azure, aws, gcp, docker, kubernetes, on-prem, sso, ldap, active directory, mobile, browser.
Note the matching C-IDs.

## 3. Ask the user
Use the AskUserQuestion tool in **one call with 4 questions**:
- If the CRD stated a technology, put that option first, labelled "(stated in CRD)".
- Otherwise put the default first, labelled "(Recommended)".

| Question | Options |
|---|---|
| Backend language and framework? | Python + FastAPI (Recommended); Java + Spring Boot; C# + ASP.NET Core; Node.js + NestJS (TypeScript) |
| Frontend framework? | React + TypeScript (Vite) (Recommended); Angular + TypeScript; Vue 3 + TypeScript; Server-rendered MVC views (no SPA) |
| Database? | PostgreSQL (Recommended); MySQL; SQL Server; Oracle |
| Deployment target? | Docker + docker-compose (Recommended); Cloud PaaS (Azure/AWS/GCP); On-premise server; Decide later (Docker by default) |

The user may type a custom answer through "Other".

**Architecture pattern.** The default is **MVC (Model–View–Controller) with Service and Repository layers**, and the platform enforces it with `tools/layer_check.py`. Ask a fifth question in a second call **only** in these cases:
- the chosen framework has its own strong convention: Django (MVT), Rails, Next.js/Nuxt app router, Laravel with its own structure
- the project is an imported existing app (`P/00-discovery/project-facts.json` exists)

| Question | Options |
|---|---|
| Architecture pattern? | MVC with Service + Repository layers (Recommended); The framework's own convention (`framework-native`, or `MVT` for Django); Keep the existing app's structure (`existing`) |

If the user picks anything other than MVC, record a one-sentence `pattern_rationale`.

If the user's answer to any question is unclear, ask a single follow-up question.

## 4. Derive the rest
Fill in standard companions for the chosen stack, without asking the user:

| Stack | ORM and migrations | Tests | Lint and format |
|---|---|---|---|
| FastAPI | SQLAlchemy 2 + Alembic | pytest | ruff + mypy |
| Spring Boot | JPA/Hibernate + Flyway | JUnit 5 + MockMvc | Checkstyle |
| ASP.NET Core | EF Core + EF migrations | xUnit | dotnet format |
| NestJS | TypeORM or Prisma | Jest | ESLint + Prettier |

- **Frontend:** Vitest or Jest for unit tests, Playwright for end-to-end tests, and ESLint + Prettier.
- **Authentication:** JWT with company email and password, unless the CRD mentions SSO, LDAP or Active Directory. In that case, use OIDC/SSO and add a constraint saying that integration details need confirming.

## 5. Write the decision
1. Write `P/01-frd/tech-stack.json`, following `schemas/tech-stack.schema.json`:
   - `source`: `crd_confirmed_by_user` if the user confirmed a CRD-stated choice, otherwise `user`
   - `crd_sources`: the C-IDs from step 2
   - `confirmed_by`: the name from `$ARGUMENTS`, or ask for it
   - `confirmed_at`: the current ISO timestamp
   - `architecture_pattern`: `"MVC"` unless the user chose otherwise, in which case also set `pattern_rationale`
   - `forbidden`: technologies the CRD or the user rules out, if any
   - `coding_standards`: `["knowledge/standards/mvc-coding-standards.md", "<stack lint/format tools>"]`
   - `constraints`: anything else from the CRD, such as hosting, browser support or existing systems
2. Run `python tools/validate.py tech-stack P/01-frd/tech-stack.json` until it reports VALID.
3. Show the user a 6-line summary of the stack.
4. If an FRD version already exists, tell the user to run `/revise-frd "tech stack updated"` so that FRD sections 19–20 reflect the change.
