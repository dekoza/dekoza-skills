---
domain: reference-index
category: documentation
priority: high
scope: django-allauth
target_versions: "django-allauth latest docs/source snapshot verified on 2026-04-07"
last_verified: 2026-04-07
source_basis: official docs + source repository
---

# Django-Allauth Reference Index

Use this index to pick the smallest reference file that matches the task. Start with one file. Add a second only when neighboring subsystem boundaries or provider-specific behavior materially change the answer.

## Route Elsewhere

- Core Django framework behavior outside allauth extension points -> pair `django`
- Broad DRF API architecture unrelated to `allauth.headless` -> pair `drf`
- Pure status-code semantics -> pair `http-status-codes`

## Reference Guides

| Domain | File | Use For |
|---|---|---|
| Setup | `references/installation-and-wiring.md` | App wiring, URLs, sites, enablement boundaries |
| Regular accounts | `references/account.md` | Signup/login/email/password/phone flows |
| Social login | `references/socialaccount-core.md` | `SocialApp`, linking, disconnecting, adapters |
| Provider catalog | `references/providers-index.md` | Full provider surface by protocol family |
| Major providers | `references/providers-major.md` | Google, Apple, GitHub, Microsoft, OIDC, SAML |
| MFA | `references/mfa.md` | MFA install, configuration, forms, adapters |
| User sessions | `references/usersessions.md` | Session tracking and revocation |
| Headless | `references/headless.md` | API surface, CORS, token strategies |
| Identity provider | `references/idp-openid-connect.md` | OIDC IdP mode |
| Shared customization | `references/common-customization.md` | Templates, messages, admin, email, rate limits |
| Testing and troubleshooting | `references/testing-and-troubleshooting.md` | Tests, callback failures, site/provider diagnosis |
| Version notes | `references/version-notes.md` | Release-sensitive behavior |

## Common Task Routing

1. Decide which allauth subsystem owns the task.
2. Open one primary file.
3. Add a second file only when provider details or neighboring subsystem boundaries change the answer.

- Setup or first install -> `installation-and-wiring.md`
- Signup/login/email/password -> `account.md`
- Social login architecture -> `socialaccount-core.md`
- Provider discovery -> `providers-index.md`
- Google/Apple/GitHub/Microsoft/OIDC/SAML -> `providers-major.md`
- MFA/WebAuthn -> `mfa.md`
- Session tracking -> `usersessions.md`
- SPA/mobile/API auth -> `headless.md`
- OIDC provider mode -> `idp-openid-connect.md`
- Shared customization -> `common-customization.md`
- Failures and diagnosis -> `testing-and-troubleshooting.md`
- Release-sensitive questions -> `version-notes.md`
