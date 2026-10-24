from django.contrib.auth import password_validation
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from ..models import GuestSession, User

SAFE_GUEST_METADATA_KEYS = {"locale", "client", "app_version"}


class UserSerializer(serializers.ModelSerializer):
    has_password = serializers.SerializerMethodField(help_text="False for Google-only accounts.")
    providers = serializers.SerializerMethodField(help_text="Linked external sign-in providers, e.g. ['google'].")

    class Meta:
        model = User
        fields = ("id", "email", "username", "display_name", "avatar_url", "email_verified_at", "date_joined",
                  "last_seen_at", "is_staff", "has_password", "providers")
        read_only_fields = ("id", "email", "avatar_url", "email_verified_at", "date_joined", "last_seen_at",
                            "is_staff")

    @extend_schema_field(serializers.BooleanField())
    def get_has_password(self, obj):
        return obj.has_usable_password()

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_providers(self, obj):
        return list(obj.social_accounts.values_list("provider", flat=True))


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"}, max_length=128)


class GoogleCredentialSerializer(serializers.Serializer):
    credential = serializers.CharField(max_length=4096, help_text="ID token from Google Identity Services.")


class SessionStateSerializer(serializers.Serializer):
    authenticated = serializers.BooleanField()
    user = UserSerializer(allow_null=True)


class AuthResultSerializer(UserSerializer):
    created = serializers.BooleanField(read_only=True, help_text="True when a new account was created.")

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ("created",)


class AuthErrorSerializer(serializers.Serializer):
    code = serializers.CharField()
    detail = serializers.CharField()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ("id", "email", "password", "username", "display_name")
        read_only_fields = ("id",)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.all_objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs):
        password_validation.validate_password(attrs["password"], User(email=attrs.get("email")))
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class GuestSessionCreateSerializer(serializers.Serializer):
    metadata = serializers.DictField(child=serializers.CharField(max_length=100), required=False)

    def validate_metadata(self, value):
        unknown = set(value) - SAFE_GUEST_METADATA_KEYS
        if unknown:
            raise serializers.ValidationError(f"Unsupported keys: {sorted(unknown)}")
        return value


class GuestSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuestSession
        fields = ("id", "expires_at", "revoked_at", "last_seen_at", "metadata", "created_at")
        read_only_fields = fields


class GuestSessionIssuedSerializer(GuestSessionSerializer):
    token = serializers.CharField(read_only=True, help_text="Raw guest token; shown once. Send as X-Guest-Token.")

    class Meta(GuestSessionSerializer.Meta):
        fields = ("token",) + GuestSessionSerializer.Meta.fields
        read_only_fields = fields


class GuestClaimSerializer(serializers.Serializer):
    guest_token = serializers.CharField(write_only=True)
