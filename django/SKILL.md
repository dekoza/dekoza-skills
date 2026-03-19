---
name: django
description: "Use when tasks involve Django models, views, URLs, templates, forms, admin, auth, middleware, signals, settings, testing, or project architecture. Covers Django 6.0 framework patterns, gotchas, and internals."
---

# Django 6.0 Framework Reference

Use this skill for Django 6.0 framework implementation and integration. Django is a high-level Python web framework that encourages rapid development and clean, pragmatic design. This skill covers the core framework patterns, ORM, views, templates, forms, admin, authentication, testing, and internal architecture. Read only the reference files needed for the task.

## Quick Start

1. Identify the domain of the task (models, views, URLs, templates, forms, admin, auth, testing, or architecture).
2. Open the matching file from `references/`.
3. Implement using Django conventions and best practices for version 6.0.
4. Validate using Django's testing framework and ensure migrations are included.

## Critical Rules

1. **Model field verification** - Always read the actual model definition before writing queries or test fixtures. Do not guess field names.
2. **select_related/prefetch_related** - Use `.select_related()` for FK and `.prefetch_related()` for M2M to prevent N+1 queries. This is the #1 Django performance bug.
3. **distinct() after M2M filtering** - Always call `.distinct()` after filtering through M2M or reverse FK relations to prevent duplicate rows.
4. **auto_now=True bypass** - Fields with `auto_now=True` cannot be set via `.save()`. Use `.objects.filter().update(field=value)` to override.
5. **TemplateResponse over render()** - Prefer `TemplateResponse` in views that need middleware compatibility. `render()` bypasses middleware context modification.
6. **URL patterns are hierarchical** - Child URLconf should NOT repeat parent prefix. Catch-all patterns (`path("")`) must be LAST in `urlpatterns`.
7. **Circular import prevention** - Use PEP 562 lazy `__getattr__` in `__init__.py` or place deferred imports inside functions with `# Circular import:` comments.
8. **Cross-context imports via public API** - Import from public interface (`from apps.context import Symbol`), never from internal modules (`from apps.context.models import Symbol`).
9. **Test fixtures and migrations** - Check model constraints and field types before writing test fixtures. Use `update_or_create()` to avoid unique constraint violations.
10. **Form validation at the model level** - Django forms inherit model validation. Always define custom validation in model `clean()` and form `clean_*()` methods.

## Reference Map

| File | Domain | Patterns |
|------|--------|----------|
| models-orm.md | Models & ORM | 25 |
| views-urls.md | Views & URLs | 24 |
| templates.md | Templates | 21 |
| forms-validation.md | Forms & Validation | 21 |
| admin.md | Admin | 18 |
| auth-security.md | Auth & Security | 16 |
| settings-config.md | Settings & Config | 16 |
| testing.md | Testing | 17 |
| middleware-signals.md | Middleware & Signals | 18 |
| architecture.md | Architecture | 20 |
| async-tasks.md | Async & Tasks | 16 |
| django6-new.md | Django 6.0 Features | 14 |
| internals.md | Internals | 10 |

## Task Routing

- **Defining models, querysets, migrations, or ORM optimization** -> `references/models-orm.md`
- **Building views, URL routing, or class-based views** -> `references/views-urls.md`
- **Creating or extending templates** -> `references/templates.md`
- **Building forms, validation, or form rendering** -> `references/forms-validation.md`
- **Customizing Django admin** -> `references/admin.md`
- **Authentication, permissions, or security patterns** -> `references/auth-security.md`
- **Settings, configuration, or environment-specific setup** -> `references/settings-config.md`
- **Writing tests (unit, integration, or E2E)** -> `references/testing.md`
- **Middleware, signals, or request/response cycle** -> `references/middleware-signals.md`
- **Project structure, patterns, or architectural decisions** -> `references/architecture.md`
- **Async views, tasks, celery, or background jobs** -> `references/async-tasks.md`
- **Django 6.0 new features or deprecations** -> `references/django6-new.md`
- **Django internals, metaprogramming, or deep framework behavior** -> `references/internals.md`


