# Django-Allauth Social Accounts Core

Use this file for third-party account architecture, `SocialApp`, provider configuration, linking/disconnecting flows, social forms, social signals, adapters, and advanced socialaccount usage.

## Owns

- Social login concepts and configuration
- `SocialApp` and provider configuration boundaries
- Linking, disconnecting, signup handoff, verified-email assumptions, adapters, forms, and signals

## Boundary Rules

- `socialaccount` is consumer mode: logging in with an external provider.
- Do not confuse this with `allauth.idp`, where django-allauth acts as the identity provider.
- Verify whether provider configuration lives in settings or database-backed `SocialApp` records.
- Treat multi-site behavior as a real source of production-only failures.

## Read This First For

- "How do I configure Google/GitHub/etc. login in allauth?"
- "Why does provider login work on one domain but not another?"
- "How do connect and disconnect flows behave?"

## Routing

- Full provider catalog -> `references/providers-index.md`
- Google, Apple, GitHub, Microsoft, OIDC, SAML -> `references/providers-major.md`
- OIDC provider mode -> `references/idp-openid-connect.md`
