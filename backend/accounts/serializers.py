from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from rest_framework import serializers

from .models import ActivityLog, Role

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password"]

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with that email already exists.")
        return value

    def create(self, validated_data):
        role, _ = Role.objects.get_or_create(
            name="Standard User",
            defaults={"description": "Default role for new accounts."},
        )
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
            role=role,
        )


class UserSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source="role.name", read_only=True, default=None)
    permissions = serializers.SerializerMethodField()
    is_admin_role = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "role", "role_name",
            "permissions", "is_admin_role", "last_login",
        ]
        read_only_fields = ["username", "email", "role"]

    def get_permissions(self, obj):
        return sorted(obj.permission_codenames)


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SlugRelatedField(
        many=True,
        slug_field="codename",
        queryset=Permission.objects.all(),
        required=False,
    )

    class Meta:
        model = Role
        fields = ["id", "name", "description", "is_admin", "permissions", "created_at"]

    def validate_name(self, value):
        qs = Role.objects.filter(name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A role with this name already exists.")
        return value


class ActivityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityLog
        fields = [
            "id", "username", "action", "method", "path", "status_code",
            "ip_address", "detail", "created_at",
        ]
