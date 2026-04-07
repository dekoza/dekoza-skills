# Django-Allauth Major Providers

Use this file for providers and protocols where configuration mistakes are common and expensive.

## Covered In Depth

- Google
- Apple
- GitHub
- Microsoft
- OpenID Connect
- SAML
- Enterprise OIDC setups such as Auth0- or Keycloak-class integrations when they are represented by allauth's provider model

## What Each Section Must Capture

1. Configuration shape in allauth terms.
2. Common callback or redirect mismatch failures.
3. Scope, claims, or verified-email assumptions when upstream docs mention them.
4. Multi-site or multi-tenant pitfalls where applicable.

## Boundary Rules

- Keep provider guidance grounded in documented allauth behavior.
- Do not collapse enterprise OIDC consumer setup into IdP mode.
- When a provider question is really about `SocialApp`, sites, or callback routing, say so directly.

## Google

- Configuration shape: verify whether credentials live in provider settings or database-backed `SocialApp` records, and confirm the correct site association when `django.contrib.sites` is in play.
- Common failures: redirect URI mismatch, callback URL using the wrong domain, or production site records pointing at a different host than the provider console allows.
- Assumptions to verify: do not promise scopes, claims, or verified-email semantics beyond what upstream docs and allauth docs state.
- Multi-site pitfall: one Google app can appear broken only on some domains when the active site or callback host does not match the configured `SocialApp`.

## Apple

- Configuration shape: keep the allauth-side provider configuration separate from Apple console setup and verify that the configured callback target matches the deployed site.
- Common failures: callback mismatch, wrong service identifiers, or environment drift between local and production domains.
- Assumptions to verify: do not invent email or claim behavior; only repeat documented allauth and upstream Apple requirements.
- Multi-site pitfall: Apple login is especially brittle when callback routing is copied across environments without checking the active site domain.

## GitHub

- Configuration shape: confirm provider credentials, `SocialApp` placement, and the current site mapping before blaming generic OAuth behavior.
- Common failures: callback URL mismatch, stale credentials in admin vs settings, or the wrong site record being active.
- Assumptions to verify: only assert scope and verified-email behavior when upstream docs mention it.
- Multi-site pitfall: one GitHub OAuth app often gets reused across domains incorrectly; callback alignment breaks first.

## Microsoft

- Configuration shape: treat Microsoft login as a provider-configuration problem first, including credential storage, site mapping, and callback registration.
- Common failures: redirect mismatch, tenant-specific console setup drift, and credentials bound to a different deployment host.
- Assumptions to verify: do not guess claims, tenant behavior, or verified-email semantics that allauth does not document.
- Multi-site pitfall: tenant and site mismatches can look like intermittent login failures across environments.

## OpenID Connect

- Configuration shape: this is consumer social login through `socialaccount`, not allauth acting as an identity provider. Verify the allauth provider model, credential placement, issuer-related configuration, and site mapping.
- Common failures: callback mismatch, wrong issuer metadata, stale credentials, or mixing provider-console configuration with allauth IdP assumptions.
- Assumptions to verify: scopes, claims, and email-verification assumptions must come from upstream provider docs plus the documented allauth surface.
- Multi-site pitfall: enterprise deployments often fail only on one tenant or domain because callback URLs and site records drift apart.

## SAML

- Configuration shape: keep the allauth SAML consumer configuration distinct from any idea that django-allauth is acting as the identity provider.
- Common failures: callback or assertion-consumer URL mismatch, stale metadata, wrong entity ID, or site/domain drift between environments.
- Assumptions to verify: only state claim or attribute mapping behavior that the docs actually support.
- Multi-site pitfall: SAML setups often break at the boundary between site records, environment-specific metadata, and tenant-specific IdP configuration.

## Enterprise OIDC

- This covers Auth0-class or Keycloak-class integrations when they are represented by allauth's OpenID Connect provider model.
- Treat these as consumer login setups under `socialaccount`; do not collapse them into allauth IdP mode.
- Most failures are still boundary failures: `SocialApp` placement, settings-vs-database drift, callback registration, site mapping, tenant-specific issuer metadata, and environment-specific redirect hosts.
- When the real problem is multi-tenant site routing or callback alignment, say that directly instead of inventing provider magic.

## Escalation Rules

- If the question is mostly about credential placement, site records, or callback routing, pair this file with `references/socialaccount-core.md` or `references/installation-and-wiring.md`.
- If the question is about django-allauth acting as the provider, route to `references/idp-openid-connect.md` instead of answering from a consumer-provider perspective.
