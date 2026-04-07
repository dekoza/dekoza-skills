# Django-Allauth Provider Index

Use this file to route provider questions across the full documented provider catalog without pretending every provider needs a full standalone manual.

## How To Use This File

1. Identify the provider family: OAuth 2.0, OAuth 1.0a, OpenID Connect, SAML, OpenID, or a custom protocol.
2. Use this file to confirm whether the provider is documented by allauth.
3. Route major or failure-prone providers to `references/providers-major.md`.

## Provider Families To Index

- OpenID Connect family and related enterprise providers
- SAML
- Mainstream OAuth providers such as Google, Apple, GitHub, Microsoft
- The rest of the documented provider catalog grouped by protocol family

## Rules

- Do not invent provider-specific callback, scope, or claim behavior.
- When a provider is not deeply covered here, say that only the documented allauth surface is safe to assume.
- Use `providers-major.md` when the task is about Google, Apple, GitHub, Microsoft, OpenID Connect, SAML, or an enterprise OIDC setup.

## Routing By Family

- OpenID Connect: use this file for catalog-level routing, then move to `references/providers-major.md` for OpenID Connect, enterprise OIDC, Auth0-class, or Keycloak-class setups.
- SAML: use `references/providers-major.md` when the question is about assertion consumer URLs, entity IDs, tenant-specific metadata, or multi-site deployment boundaries.
- Mainstream OAuth providers: use `references/providers-major.md` for Google, Apple, GitHub, and Microsoft because callback alignment, verified-email assumptions, and provider-console configuration mistakes are common.
- Other OAuth 2.0 and OAuth 1.0a providers: stay grounded in the documented allauth provider surface and `SocialApp` or settings configuration. Do not invent extra callback, scope, or claim requirements.
- OpenID or custom-protocol providers: only assume the documented allauth integration points. If the task needs protocol details beyond allauth's docs, say that upstream provider documentation is required.

## Catalog View

- OpenID Connect family: OpenID Connect plus enterprise-provider variants represented through allauth's provider model.
- SAML: SAML-based providers supported through allauth's SAML surface.
- Major OAuth providers: Google, Apple, GitHub, Microsoft.
- Other documented OAuth providers: treat them as part of the broader provider catalog, grouped by protocol family instead of pretending each one needs a separate deep guide here.

## Boundary Reminders

- Many production failures are not truly provider-specific; they are `SocialApp`, settings-vs-database, `django.contrib.sites`, or callback URL alignment problems.
- Do not confuse external-provider consumer login under `socialaccount` with django-allauth identity-provider mode under `allauth.idp`.
