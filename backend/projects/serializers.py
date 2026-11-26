from rest_framework import serializers

from .models import ApprovalEvent, Project, Requirement, TraceLink


class TraceLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = TraceLink
        fields = ["id", "requirement", "kind", "artifact", "description", "test_passed"]


class RequirementSerializer(serializers.ModelSerializer):
    trace_links = TraceLinkSerializer(many=True, read_only=True)

    class Meta:
        model = Requirement
        fields = [
            "id", "project", "rid", "title", "description", "req_type", "priority",
            "status", "approved_by", "approved_at", "trace_links", "created_at", "updated_at",
        ]
        read_only_fields = ["status", "approved_by", "approved_at", "project"]


class ApprovalEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = ApprovalEvent
        fields = ["id", "requirement", "actor_username", "action", "comment", "created_at"]


class ProjectSerializer(serializers.ModelSerializer):
    requirement_count = serializers.IntegerField(read_only=True)
    approved_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Project
        fields = [
            "id", "name", "description", "status", "requirement_count",
            "approved_count", "created_at", "updated_at",
        ]
        read_only_fields = ["status"]


class ProjectDetailSerializer(ProjectSerializer):
    requirements = RequirementSerializer(many=True, read_only=True)
    approval_events = ApprovalEventSerializer(many=True, read_only=True)

    class Meta(ProjectSerializer.Meta):
        fields = ProjectSerializer.Meta.fields + ["requirements", "approval_events"]
