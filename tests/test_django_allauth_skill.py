from __future__ import annotations

import json
import shutil
from pathlib import Path

from scripts.validate_refs import validate_repo


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "skills" / "django-allauth"


def test_django_allauth_skill_references_resolve_in_isolation(tmp_path: Path) -> None:
    target_root = tmp_path / "skills" / "django-allauth"
    shutil.copytree(SKILL_ROOT, target_root)

    broken_references = validate_repo(tmp_path)

    assert broken_references == []


def test_django_allauth_skill_frontmatter_carries_version_basis() -> None:
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert "name: django-allauth" in skill_text
    assert "last_verified" in skill_text
    assert "source_basis" in skill_text
    assert (
        "docs/source snapshot" in skill_text
        or "official docs + source repository" in skill_text
    )


def test_django_allauth_skill_guardrails_cover_core_boundary_footguns() -> None:
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert "Verify installed allauth apps" in skill_text
    assert "socialaccount" in skill_text and "identity-provider" in skill_text
    assert "headless" in skill_text and "session" in skill_text
    assert (
        "extension point" in skill_text
        or "settings, adapters, forms, signals, templates" in skill_text
    )
    assert "provider-specific" in skill_text or "Do not guess provider" in skill_text
    assert "SocialApp" in skill_text
    assert "django.contrib.sites" in skill_text or "multi-site" in skill_text
    assert "version-notes.md" in skill_text
    assert "providers-index.md" in skill_text
    assert "settings, adapters, forms, signals, templates" in skill_text


def test_django_allauth_skill_routes_to_neighbor_skills_when_needed() -> None:
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert "`django`" in skill_text
    assert "`drf`" in skill_text
    assert "`http-status-codes`" in skill_text


def test_django_allauth_reference_index_covers_all_major_domains() -> None:
    index_text = (SKILL_ROOT / "references" / "REFERENCE.md").read_text(
        encoding="utf-8"
    )

    assert "installation-and-wiring.md" in index_text
    assert "account.md" in index_text
    assert "socialaccount-core.md" in index_text
    assert "providers-index.md" in index_text
    assert "providers-major.md" in index_text
    assert "mfa.md" in index_text
    assert "usersessions.md" in index_text
    assert "headless.md" in index_text
    assert "idp-openid-connect.md" in index_text
    assert "common-customization.md" in index_text
    assert "testing-and-troubleshooting.md" in index_text
    assert "version-notes.md" in index_text


def test_django_allauth_reference_files_cover_core_topics() -> None:
    installation_text = (
        SKILL_ROOT / "references" / "installation-and-wiring.md"
    ).read_text(encoding="utf-8")
    account_text = (SKILL_ROOT / "references" / "account.md").read_text(
        encoding="utf-8"
    )
    social_text = (SKILL_ROOT / "references" / "socialaccount-core.md").read_text(
        encoding="utf-8"
    )
    provider_index_text = (SKILL_ROOT / "references" / "providers-index.md").read_text(
        encoding="utf-8"
    )
    provider_major_text = (SKILL_ROOT / "references" / "providers-major.md").read_text(
        encoding="utf-8"
    )
    mfa_text = (SKILL_ROOT / "references" / "mfa.md").read_text(encoding="utf-8")
    usersessions_text = (SKILL_ROOT / "references" / "usersessions.md").read_text(
        encoding="utf-8"
    )
    headless_text = (SKILL_ROOT / "references" / "headless.md").read_text(
        encoding="utf-8"
    )
    idp_text = (SKILL_ROOT / "references" / "idp-openid-connect.md").read_text(
        encoding="utf-8"
    )
    common_text = (SKILL_ROOT / "references" / "common-customization.md").read_text(
        encoding="utf-8"
    )
    testing_text = (
        SKILL_ROOT / "references" / "testing-and-troubleshooting.md"
    ).read_text(encoding="utf-8")
    version_text = (SKILL_ROOT / "references" / "version-notes.md").read_text(
        encoding="utf-8"
    )

    assert "INSTALLED_APPS" in installation_text
    assert "SITE_ID" in installation_text or "django.contrib.sites" in installation_text
    assert "headless" in installation_text and "mfa" in installation_text
    assert "django.template.context_processors.request" in installation_text
    assert "allauth.account.auth_backends.AuthenticationBackend" in installation_text
    assert "allauth.account.middleware.AccountMiddleware" in installation_text
    assert "path('accounts/', include('allauth.urls'))" in installation_text
    assert "django.contrib.sessions.backends.signed_cookies" in installation_text

    assert "signup" in account_text.lower()
    assert "email" in account_text.lower()
    assert "adapter" in account_text.lower()
    assert "signal" in account_text.lower()
    assert "phone" in account_text.lower()
    assert "enumeration" in account_text.lower() or "rate limit" in account_text.lower()
    assert "ACCOUNT_SIGNUP_FORM_CLASS" in account_text
    assert "ACCOUNT_SIGNUP_FIELDS" in account_text
    assert "ACCOUNT_LOGIN_METHODS" in account_text
    assert "ACCOUNT_EMAIL_VERIFICATION" in account_text
    assert "ACCOUNT_PREVENT_ENUMERATION" in account_text
    assert "ACCOUNT_RATE_LIMITS" in account_text
    assert "authentication_step_completed" in account_text
    assert "email_confirmation_sent" in account_text
    assert "email_removed" in account_text

    assert "SocialApp" in social_text
    assert "provider" in social_text.lower()
    assert "connect" in social_text.lower() or "disconnect" in social_text.lower()
    assert "adapter" in social_text.lower()
    assert "signal" in social_text.lower()
    assert "SOCIALACCOUNT_ADAPTER" in social_text
    assert "SOCIALACCOUNT_PROVIDERS" in social_text
    assert "SOCIALACCOUNT_AUTO_SIGNUP" in social_text
    assert "SOCIALACCOUNT_EMAIL_AUTHENTICATION" in social_text
    assert "MultipleObjectsReturned" in social_text
    assert "pre_social_login" in social_text
    assert "social_account_removed" in social_text

    assert "OpenID Connect" in provider_index_text or "OIDC" in provider_index_text
    assert "SAML" in provider_index_text
    assert "Google" in provider_index_text
    assert "Apple" in provider_index_text
    assert "/accounts/<provider>/login/callback/" in provider_index_text
    assert "OAuth 2.0" in provider_index_text
    assert "OAuth 1.0a" in provider_index_text or "OAuth 1a" in provider_index_text
    assert "OpenID" in provider_index_text
    assert "Auth0" in provider_index_text
    assert "Keycloak" in provider_index_text
    assert "Okta" in provider_index_text
    assert "NetIQ" in provider_index_text or "Microfocus" in provider_index_text

    assert "Google" in provider_major_text
    assert "Apple" in provider_major_text
    assert "GitHub" in provider_major_text
    assert "Microsoft" in provider_major_text
    assert "OpenID Connect" in provider_major_text or "OIDC" in provider_major_text
    assert "SAML" in provider_major_text
    assert "Auth0" in provider_major_text or "Keycloak" in provider_major_text
    assert "OAUTH_PKCE_ENABLED" in provider_major_text
    assert "FETCH_USERINFO" in provider_major_text
    assert "access_type" in provider_major_text and "offline" in provider_major_text
    assert "certificate_key" in provider_major_text
    assert '"hidden": True' in provider_major_text or "hidden" in provider_major_text
    assert "GITHUB_URL" in provider_major_text
    assert "provider_id" in provider_major_text and "server_url" in provider_major_text
    assert "/accounts/oidc/{provider_id}/login/callback/" in provider_major_text
    assert "reject_idp_initiated_sso" in provider_major_text
    assert "attribute_mapping" in provider_major_text
    assert "/accounts/saml/<organization_slug>/acs/" in provider_major_text

    assert "WebAuthn" in mfa_text
    assert "adapter" in mfa_text.lower()
    assert "form" in mfa_text.lower()
    assert "allauth.mfa" in mfa_text
    assert "django-allauth-2fa" in mfa_text
    assert "get_totp_issuer" in mfa_text
    assert "generate_authenticator_name" in mfa_text

    assert "session" in usersessions_text.lower()
    assert "signal" in usersessions_text.lower()
    assert "adapter" in usersessions_text.lower()
    assert "django.contrib.humanize" in usersessions_text
    assert "allauth.usersessions" in usersessions_text
    assert "UserSessionsMiddleware" in usersessions_text
    assert "USERSESSIONS_TRACK_ACTIVITY" in usersessions_text
    assert "session_client_changed" in usersessions_text

    assert "CORS" in headless_text
    assert "JWT" in headless_text or "session token" in headless_text.lower()
    assert "token strategy" in headless_text.lower()
    assert "adapter" in headless_text.lower()
    assert "X-Session-Token" in headless_text
    assert "HEADLESS_JWT_ALGORITHM" in headless_text
    assert "HEADLESS_JWT_PRIVATE_KEY" in headless_text
    assert "HEADLESS_JWT_STATEFUL_VALIDATION_ENABLED" in headless_text
    assert "HEADLESS_JWT_ROTATE_REFRESH_TOKEN" in headless_text
    assert (
        "not truly stateless" in headless_text.lower()
        or "stateless" in headless_text.lower()
    )

    assert "identity provider" in idp_text.lower() or "IdP" in idp_text
    assert "OpenID Connect" in idp_text or "OIDC" in idp_text
    assert "client" in idp_text.lower()
    assert "socialaccount" in idp_text
    assert "allauth.idp.oidc" in idp_text
    assert "IDP_OIDC_PRIVATE_KEY" in idp_text
    assert 'path("", include("allauth.idp.urls"))' in idp_text
    assert "/.well-known/openid-configuration" in idp_text
    assert "/identity/o/api/token" in idp_text
    assert "IDP_OIDC_ACCESS_TOKEN_EXPIRES_IN" in idp_text
    assert "IDP_OIDC_USERINFO_ENDPOINT" in idp_text

    assert "template" in common_text.lower()
    assert "message" in common_text.lower()
    assert "admin" in common_text.lower()
    assert "email" in common_text.lower()
    assert "allauth/layouts/base.html" in common_text
    assert "allauth/layouts/entrance.html" in common_text
    assert "allauth/layouts/manage.html" in common_text
    assert "send_mail" in common_text
    assert "429.html" in common_text
    assert "ALLAUTH_TRUSTED_PROXY_COUNT" in common_text
    assert "ALLAUTH_TRUSTED_CLIENT_IP_HEADER" in common_text
    assert "DummyCache" in common_text

    assert "callback" in testing_text.lower()
    assert "site" in testing_text.lower()
    assert (
        "email confirmation" in testing_text.lower()
        or "email verification" in testing_text.lower()
    )
    assert "headless" in testing_text.lower()
    assert "SocialApp" in testing_text
    assert "settings" in testing_text.lower()
    assert "SITE_ID" in testing_text or "django.contrib.sites" in testing_text
    assert "token strategy" in testing_text.lower()
    assert "signed_cookies" in testing_text

    assert "release" in version_text.lower()
    assert "headless" in version_text.lower()
    assert "mfa" in version_text.lower()
    assert "usersessions" in version_text.lower()
    assert "65.13.0" in version_text
    assert "65.14.0" in version_text
    assert "65.15.0" in version_text
    assert "IDP" in version_text or "identity provider" in version_text.lower()
    assert "rate limit" in version_text.lower()


def test_django_allauth_skill_evals_cover_core_risk_areas() -> None:
    evals_path = SKILL_ROOT / "evals" / "evals.json"
    payload = json.loads(evals_path.read_text(encoding="utf-8"))

    assert payload["skill_name"] == "django-allauth"
    evals = payload["evals"]
    assert len(evals) >= 8
    assert len({item["id"] for item in evals}) == len(evals)

    prompts = [item["prompt"] for item in evals]

    assert any(
        "adapter" in prompt.lower() and "signup" in prompt.lower() for prompt in prompts
    )
    assert any(
        "SocialApp" in prompt or "provider" in prompt.lower() for prompt in prompts
    )
    assert any("OpenID Connect" in prompt or "OIDC" in prompt for prompt in prompts)
    assert any("headless" in prompt.lower() or "SPA" in prompt for prompt in prompts)
    assert any("MFA" in prompt or "WebAuthn" in prompt for prompt in prompts)
    assert any(
        "usersessions" in prompt.lower() or "session" in prompt.lower()
        for prompt in prompts
    )
    assert any(
        "callback" in prompt.lower() or "SITE_ID" in prompt for prompt in prompts
    )
    assert all(item["expectations"] and item["expected_output"] for item in evals)
    assert any(
        "settings or SocialApp" in prompt or "SocialApp" in prompt for prompt in prompts
    )
    assert any("JWT" in prompt and "X-Session-Token" in prompt for prompt in prompts)
    assert any(
        "identity provider" in prompt.lower() and "OpenID Connect" in prompt
        for prompt in prompts
    )


def test_django_allauth_evals_target_discriminating_failure_modes() -> None:
    evals_path = SKILL_ROOT / "evals" / "evals.json"
    payload = json.loads(evals_path.read_text(encoding="utf-8"))
    evals = payload["evals"]

    expectations = "\n".join(
        expectation for item in evals for expectation in item["expectations"]
    )

    assert (
        "settings, adapters, forms, signals, templates" in expectations
        or "existing extension point" in expectations
    )
    assert "SocialApp" in expectations
    assert "identity-provider" in expectations or "IdP" in expectations
    assert "headless" in expectations and (
        "session" in expectations.lower() or "JWT" in expectations
    )
    assert "release notes" in expectations.lower() or "version" in expectations.lower()
    assert (
        "provider-specific" in expectations.lower()
        or "do not guess" in expectations.lower()
    )
    assert "owning allauth surface" in expectations or "owning surface" in expectations
    assert (
        "settings-vs-database" in expectations
        or "settings-vs-SocialApp" in expectations
    )
    assert "X-Session-Token" in expectations or "session token" in expectations.lower()
