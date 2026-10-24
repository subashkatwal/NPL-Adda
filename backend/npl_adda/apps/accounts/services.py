"""
Account creation and safe Google linking.

Linking rules (prevent account takeover and duplicates):
- A Google identity is matched by its stable ``sub``, never by email alone.
- New Google ``sub`` + no account with that email -> create a verified, password-less account.
- New Google ``sub`` + existing account with that email:
    * linked automatically only if that account's email is already verified or it has
      no password (it cannot have been registered by someone guessing the email);
    * otherwise refused (409): the owner must log in with their password and link
      Google from Settings, proving they control both.
- Disabled or soft-deleted accounts can never be signed into.
"""
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import SocialAccount, User

GOOGLE = SocialAccount.Provider.GOOGLE


class AuthConflict(Exception):
    def __init__(self, code, message, status=409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _profile_data(claims):
    return {"name": claims.get("name", "")[:120], "picture": claims.get("picture", "")[:500]}


def _ensure_usable(user):
    if user.deleted_at is not None or not user.is_active:
        raise AuthConflict("account_disabled", "This account is disabled.", 403)


def _touch(social, claims):
    social.email = claims["email"].lower()
    social.email_verified = bool(claims.get("email_verified"))
    social.extra_data = _profile_data(claims)
    social.last_used_at = timezone.now()
    social.save(update_fields=["email", "email_verified", "extra_data", "last_used_at", "updated_at"])


def _create_social(user, claims):
    try:
        with transaction.atomic():
            return SocialAccount.objects.create(
                user=user, provider=GOOGLE, uid=claims["sub"], email=claims["email"].lower(),
                email_verified=bool(claims.get("email_verified")), extra_data=_profile_data(claims),
                last_used_at=timezone.now(),
            )
    except IntegrityError:
        raise AuthConflict("google_already_linked", "This Google account is already linked to another account.")


@transaction.atomic
def sign_in_with_google(claims):
    """Returns (user, created)."""
    email = claims["email"].lower()
    social = SocialAccount.objects.select_related("user").filter(provider=GOOGLE, uid=claims["sub"]).first()
    if social:
        _ensure_usable(social.user)
        _touch(social, claims)
        return social.user, False

    existing = User.all_objects.select_for_update().filter(email__iexact=email).first()
    if existing:
        _ensure_usable(existing)
        if existing.email_verified_at is None and existing.has_usable_password():
            raise AuthConflict(
                "account_exists_unverified",
                "An account with this email already exists. Log in with your password, then link Google in Settings.",
            )
        _create_social(existing, claims)
        if not existing.avatar_url and claims.get("picture"):
            existing.avatar_url = claims["picture"][:500]
            existing.save(update_fields=["avatar_url", "updated_at"])
        return existing, False

    user = User.objects.create_user(
        email=email, password=None, display_name=claims.get("name", "")[:60],
        email_verified_at=timezone.now(), avatar_url=claims.get("picture", "")[:500],
    )  # password=None stores an unusable password: Google-only until the user sets one
    _create_social(user, claims)
    return user, True


@transaction.atomic
def link_google(user, claims):
    """Link a Google identity to the logged-in user (who has just proven control of it)."""
    social = SocialAccount.objects.filter(provider=GOOGLE, uid=claims["sub"]).first()
    if social and social.user_id != user.pk:
        raise AuthConflict("google_already_linked", "This Google account is already linked to another account.")
    if social:
        _touch(social, claims)
        return social
    if SocialAccount.objects.filter(provider=GOOGLE, user=user).exists():
        raise AuthConflict("google_already_set", "A different Google account is already linked. Unlink it first.")
    social = _create_social(user, claims)
    if claims["email"].lower() == user.email and user.email_verified_at is None:
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at", "updated_at"])
    return social


def unlink_google(user):
    if not user.has_usable_password():
        raise AuthConflict("last_sign_in_method", "Set a password before unlinking Google, or you'll be locked out.",
                           400)
    deleted = SocialAccount.objects.filter(provider=GOOGLE, user=user).delete()[0]
    return bool(deleted)
