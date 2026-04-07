# Django-Allauth Identity Provider (OpenID Connect)

Use this file when django-allauth is acting as the OpenID Connect provider.

## Owns

- Identity provider configuration when allauth is the OIDC server
- Client registration, client integration, and IdP-specific URL or view guidance
- OpenID Connect provider terminology and boundaries

## Boundary Rules

- This is not the same thing as logging in with an external OpenID Connect provider via `socialaccount`.
- Keep client, URL/view, and integration guidance in IdP terms.
- When the user's real problem is enterprise SSO against an external provider, route back to `references/providers-major.md`.

## Read This First For

- "How do I configure django-allauth as an identity provider?"
- "Which client settings matter when allauth serves OpenID Connect?"
- "Is this an IdP problem or a `socialaccount` consumer-login problem?"

## Routing

- Logging in against an external OpenID Connect provider -> `references/providers-major.md`
- Generic social login architecture -> `references/socialaccount-core.md`
- Release-sensitive identity provider behavior -> `references/version-notes.md`
