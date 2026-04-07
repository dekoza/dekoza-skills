# Django-Allauth Installation And Wiring

Start here when the task is about first install, app enablement, URL wiring, site configuration, or deciding which allauth subpackages are actually present.

## Owns

- `INSTALLED_APPS` wiring for `allauth`, `allauth.account`, `allauth.socialaccount`, `allauth.mfa`, `allauth.usersessions`, `allauth.headless`, and `allauth.idp`
- URL inclusion and top-level setup boundaries
- Site configuration, email prerequisites, and app enablement boundaries

## Does Not Own

- Detailed signup/login behavior -> `references/account.md`
- Social provider behavior -> `references/socialaccount-core.md` or provider references
- API/token strategy details -> `references/headless.md`

## Core Setup Boundaries

- Verify which allauth subpackages are installed before giving guidance.
- Do not assume `socialaccount`, `mfa`, `usersessions`, `headless`, or `idp` are enabled in a project that only uses `account`.
- Treat `django.contrib.sites` and `SITE_ID` as a real configuration boundary when the project uses site-aware behavior or `SocialApp` records.
- Distinguish settings-based configuration from database-backed provider configuration.

## Checklist

1. Confirm which allauth apps are present in `INSTALLED_APPS`.
2. Confirm the project includes the relevant allauth URLs.
3. Confirm site configuration (`SITE_ID` and site records) when provider callbacks, email links, or domain-specific behavior are involved.
4. Confirm whether provider credentials live in settings or `SocialApp` records.
5. When headless, MFA, usersessions, or IdP mode are involved, verify that the matching subpackage is installed before discussing flows.
