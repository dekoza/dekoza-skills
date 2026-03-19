---
domain: reference-index
category: documentation
priority: high
---

# Django 6.0 Reference Index

Use this index to pick the smallest reference file that matches the task.

## Package Guides

| Domain | File | Use For |
|---|---|---|
| Models & ORM | `references/models-orm.md` | Model definitions, querysets, filtering, optimization, migrations, and field patterns |
| Views & URLs | `references/views-urls.md` | Function-based and class-based views, URL routing, URL reversal, and view decorators |
| Templates | `references/templates.md` | Template syntax, template tags, template filters, template inheritance, and rendering |
| Forms & Validation | `references/forms-validation.md` | Form creation, validation, form rendering, error handling, and form widgets |
| Admin | `references/admin.md` | Admin customization, ModelAdmin configuration, admin actions, filters, and search |
| Auth & Security | `references/auth-security.md` | Authentication, permissions, decorators, CSRF, security headers, and password hashing |
| Settings & Config | `references/settings-config.md` | Django settings, environment variables, app configuration, and secret management |
| Testing | `references/testing.md` | Unit tests, integration tests, E2E tests with Playwright, fixtures, factories, and test utilities |
| Middleware & Signals | `references/middleware-signals.md` | Middleware creation, request/response cycle, signals, receivers, and event patterns |
| Architecture | `references/architecture.md` | Project structure, app organization, service patterns, circular imports, and design patterns |
| Async & Tasks | `references/async-tasks.md` | Async views, async ORM, async tasks, Celery integration, and background jobs |
| Django 6.0 Features | `references/django6-new.md` | Django 6.0 new features, deprecations, breaking changes, and migration guide |
| Internals | `references/internals.md` | Django internals, metaprogramming, descriptor protocol, and framework deep-dive |

## Common Task Routing

- Writing or updating models: read `references/models-orm.md`
- Building views or routing URLs: read `references/views-urls.md`
- Creating or extending templates: read `references/templates.md`
- Building forms or adding validation: read `references/forms-validation.md`
- Customizing Django admin: read `references/admin.md`
- Implementing authentication or permissions: read `references/auth-security.md`
- Configuring settings or environment: read `references/settings-config.md`
- Writing tests (unit, integration, or E2E): read `references/testing.md`
- Creating middleware or handling signals: read `references/middleware-signals.md`
- Understanding project structure or patterns: read `references/architecture.md`
- Building async views or background tasks: read `references/async-tasks.md`
- Using Django 6.0 new features: read `references/django6-new.md`
- Deep-diving into Django internals: read `references/internals.md`

## Suggested Reading Order

1. Start with this file to understand available domains.
2. Identify the domain matching your task from the Common Task Routing section.
3. Open the single most relevant reference file.
4. Open additional files only if your task spans multiple domains (e.g., models + admin customization).
