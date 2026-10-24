from django.contrib.auth import authenticate, login, logout
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import NotAuthenticated, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.fanengagement.identity import get_guest_session
from apps.fanengagement.services import migrate_guest_to_user
from apps.fanengagement.v1.serializers import FanProfileSerializer

from .. import google
from .. import services as account_services
from ..models import GuestSession, User
from .serializers import (
    AuthErrorSerializer,
    AuthResultSerializer,
    GoogleCredentialSerializer,
    GuestClaimSerializer,
    GuestSessionCreateSerializer,
    GuestSessionIssuedSerializer,
    GuestSessionSerializer,
    LoginSerializer,
    RegisterSerializer,
    SessionStateSerializer,
    UserSerializer,
)

TAGS = ["accounts"]


MODEL_BACKEND = "django.contrib.auth.backends.ModelBackend"
csrf_protected = method_decorator(csrf_protect, name="dispatch")


def auth_error(code, detail, status_code):
    return Response({"code": code, "detail": detail}, status=status_code)


def start_session(request, user):
    """Log the user in with a server-side session (rotates the session key)."""
    login(request._request, user, backend=MODEL_BACKEND)
    user.last_seen_at = timezone.now()
    user.save(update_fields=["last_seen_at"])


@extend_schema(tags=TAGS, responses=SessionStateSerializer)
@method_decorator(ensure_csrf_cookie, name="dispatch")
class SessionView(APIView):
    """Current auth state (200 even when logged out). Also sets the csrftoken cookie for the SPA."""

    permission_classes = [AllowAny]

    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        return Response({"authenticated": bool(user), "user": UserSerializer(user).data if user else None})


@extend_schema(tags=TAGS, responses={201: UserSerializer})
@csrf_protected
class RegisterView(generics.CreateAPIView):
    """Create an email/password account and start a session."""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "auth_register"
    throttle_classes = [ScopedRateThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        start_session(request, user)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=TAGS, request=LoginSerializer, responses={200: UserSerializer, 401: AuthErrorSerializer})
@csrf_protected
class LoginView(APIView):
    """Email/password login; starts a session. Same error for unknown email and wrong password."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "auth"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        user = authenticate(request._request, email=email, password=serializer.validated_data["password"])
        if user is None:
            candidate = User.objects.filter(email__iexact=email).first()
            if candidate and not candidate.has_usable_password() and candidate.social_accounts.exists():
                return auth_error("use_google", "This account signs in with Google.", 401)
            return auth_error("invalid_credentials", "Invalid email or password.", 401)
        start_session(request, user)
        return Response(UserSerializer(user).data)


@extend_schema(tags=TAGS, request=None, responses={204: None})
@csrf_protected
class LogoutView(APIView):
    """End the session server-side. Safe to call when already logged out."""

    permission_classes = [AllowAny]

    def post(self, request):
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=TAGS, request=GoogleCredentialSerializer,
               responses={200: AuthResultSerializer, 201: AuthResultSerializer, 400: AuthErrorSerializer,
                          409: AuthErrorSerializer, 503: AuthErrorSerializer})
@csrf_protected
class GoogleLoginView(APIView):
    """Sign in (or sign up) with a Google ID token verified server-side."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "auth"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request):
        serializer = GoogleCredentialSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            claims = google.verify_google_token(serializer.validated_data["credential"])
            user, created = account_services.sign_in_with_google(claims)
        except (google.GoogleAuthError, account_services.AuthConflict) as exc:
            return auth_error(exc.code, exc.message, exc.status)
        start_session(request, user)
        return Response({**UserSerializer(user).data, "created": created}, status=201 if created else 200)


@extend_schema(tags=TAGS)
class GoogleLinkView(APIView):
    """POST links a Google account to the logged-in user; DELETE unlinks it (requires a password)."""

    permission_classes = [IsAuthenticated]
    throttle_scope = "auth"
    throttle_classes = [ScopedRateThrottle]

    @extend_schema(request=GoogleCredentialSerializer, responses={200: UserSerializer, 409: AuthErrorSerializer})
    def post(self, request):
        serializer = GoogleCredentialSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            claims = google.verify_google_token(serializer.validated_data["credential"])
            account_services.link_google(request.user, claims)
        except (google.GoogleAuthError, account_services.AuthConflict) as exc:
            return auth_error(exc.code, exc.message, exc.status)
        return Response(UserSerializer(request.user).data)

    @extend_schema(request=None, responses={200: UserSerializer, 400: AuthErrorSerializer})
    def delete(self, request):
        try:
            account_services.unlink_google(request.user)
        except account_services.AuthConflict as exc:
            return auth_error(exc.code, exc.message, exc.status)
        return Response(UserSerializer(request.user).data)


@extend_schema(tags=TAGS)
class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch"]

    def get_object(self):
        user = self.request.user
        user.last_seen_at = timezone.now()
        user.save(update_fields=["last_seen_at"])
        return user


@extend_schema(tags=TAGS)
class GuestSessionCreateView(APIView):
    """Start an anonymous session. The raw token is returned once; store it client-side."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(request=GuestSessionCreateSerializer, responses={201: GuestSessionIssuedSerializer})
    def post(self, request):
        serializer = GuestSessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session, raw = GuestSession.issue(metadata=serializer.validated_data.get("metadata"))
        session.token = raw
        return Response(GuestSessionIssuedSerializer(session).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=TAGS)
class CurrentGuestSessionView(APIView):
    """Validate the X-Guest-Token header and return the session."""

    permission_classes = []  # authorisation is the guest token itself, checked below

    @extend_schema(responses=GuestSessionSerializer)
    def get(self, request):
        session = get_guest_session(request)
        if session is None:
            raise NotAuthenticated("Send a valid X-Guest-Token header.")
        return Response(GuestSessionSerializer(session).data)


@extend_schema(tags=TAGS)
class RevokeGuestSessionView(APIView):
    permission_classes = []  # authorisation is the guest token itself, checked below

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        session = get_guest_session(request)
        if session is None:
            raise NotAuthenticated("Send a valid X-Guest-Token header.")
        session.revoke()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=TAGS)
class ClaimGuestSessionView(APIView):
    """Move a guest's fan profile and activity into the logged-in account, then revoke the guest session."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=GuestClaimSerializer, responses=FanProfileSerializer)
    def post(self, request):
        serializer = GuestClaimSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = GuestSession.authenticate(serializer.validated_data["guest_token"])
        if session is None:
            raise ValidationError({"guest_token": "Invalid, expired or revoked guest session."})
        profile = migrate_guest_to_user(session, request.user)
        return Response(FanProfileSerializer(profile, context={"request": request}).data if profile else {})
