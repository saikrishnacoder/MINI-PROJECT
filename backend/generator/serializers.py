from rest_framework import serializers

from projects.models import Project

from .models import GeneratedBackend, GeneratedFrontend


class GeneratedBackendSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = GeneratedBackend
        fields = [
            "id", "project", "project_name", "status", "resources", "artifacts",
            "tests_passed", "test_output", "databases_tested", "features",
            "feature_summary", "generated_at", "created_at",
        ]
        read_only_fields = fields


class GenerationRequestSerializer(serializers.Serializer):
    """Body is optional; present for future generation options (e.g. app name)."""


class GeneratedFrontendSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = GeneratedFrontend
        fields = [
            "id", "project", "project_name", "status", "pages", "artifacts",
            "build_passed", "build_output", "generated_at", "created_at",
        ]
        read_only_fields = fields
