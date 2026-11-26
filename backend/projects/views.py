from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import ApprovalEvent, Project, Requirement
from .serializers import (
    ProjectDetailSerializer,
    ProjectSerializer,
    RequirementSerializer,
)


class IsOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if isinstance(obj, Requirement):
            obj = obj.project
        return obj.owner_id == request.user.id


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]

    def get_queryset(self):
        return Project.objects.filter(owner=self.request.user).annotate(
            requirement_count=Count("requirements"),
            approved_count=Count("requirements", filter=Q(status="approved")),
        )

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProjectDetailSerializer
        return ProjectSerializer

    @action(detail=True, methods=["post"])
    def submit_for_approval(self, request, pk=None):
        project = self.get_object()
        if project.status != Project.Status.DRAFT:
            return Response({"detail": "Only draft projects can be submitted."}, status=400)
        if not project.requirements.exists():
            return Response({"detail": "Add at least one requirement first."}, status=400)
        project.status = Project.Status.PENDING_APPROVAL
        project.save(update_fields=["status"])
        project.requirements.filter(status=Requirement.Status.DRAFT).update(
            status=Requirement.Status.PENDING
        )
        ApprovalEvent.objects.create(
            project=project, actor=request.user, action=ApprovalEvent.Action.SUBMIT
        )
        return Response(self.get_serializer(self._fresh(project)).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        project = self.get_object()
        if project.status != Project.Status.PENDING_APPROVAL:
            return Response({"detail": "Project is not pending approval."}, status=400)
        project.status = Project.Status.APPROVED
        project.save(update_fields=["status"])
        project.requirements.filter(status=Requirement.Status.PENDING).update(
            status=Requirement.Status.APPROVED, approved_by=request.user, approved_at=timezone.now()
        )
        ApprovalEvent.objects.create(
            project=project, actor=request.user, action=ApprovalEvent.Action.APPROVE,
            comment=request.data.get("comment", ""),
        )
        return Response(self.get_serializer(self._fresh(project)).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        project = self.get_object()
        if project.status != Project.Status.PENDING_APPROVAL:
            return Response({"detail": "Project is not pending approval."}, status=400)
        project.status = Project.Status.DRAFT
        project.save(update_fields=["status"])
        project.requirements.filter(status=Requirement.Status.PENDING).update(
            status=Requirement.Status.DRAFT
        )
        ApprovalEvent.objects.create(
            project=project, actor=request.user, action=ApprovalEvent.Action.REJECT,
            comment=request.data.get("comment", ""),
        )
        return Response(self.get_serializer(self._fresh(project)).data)

    def _fresh(self, project):
        return self.get_queryset().get(pk=project.pk)

    @action(detail=True, methods=["get"])
    def traceability(self, request, pk=None):
        project = self.get_object()
        rows = []
        for req in project.requirements.all():
            links = list(req.trace_links.all())
            tests = [t for t in links if t.kind == "test"]
            rows.append({
                "rid": req.rid,
                "title": req.title,
                "status": req.status,
                "priority": req.priority,
                "links": [
                    {"kind": t.kind, "artifact": t.artifact, "test_passed": t.test_passed}
                    for t in links
                ],
                "tested": bool(tests),
                "tests_passing": all(t.test_passed for t in tests) if tests else None,
            })
        summary = {
            "total": len(rows),
            "approved": sum(1 for r in rows if r["status"] == "approved"),
            "with_trace_links": sum(1 for r in rows if r["links"]),
            "with_tests": sum(1 for r in rows if r["tested"]),
            "tests_all_passing": sum(1 for r in rows if r["tested"] and r["tests_passing"]),
        }
        return Response({"project": project.name, "summary": summary, "requirements": rows})


class RequirementViewSet(viewsets.ModelViewSet):
    serializer_class = RequirementSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]

    def get_queryset(self):
        return Requirement.objects.select_related("project").filter(
            project__owner=self.request.user, project_id=self.kwargs.get("project_pk")
        )

    def perform_create(self, serializer):
        project = Project.objects.get(
            pk=self.kwargs["project_pk"], owner=self.request.user
        )
        if project.status == Project.Status.APPROVED:
            # Approved requirements are immutable; new ones start back in draft.
            project.status = Project.Status.DRAFT
            project.save(update_fields=["status"])
        rid = serializer.validated_data.get("rid")
        if Requirement.objects.filter(project=project, rid=rid).exists():
            raise ValidationError({"rid": ["This requirement ID already exists in the project."]})
        serializer.save(project=project)

    @action(detail=True, methods=["post"])
    def approve(self, request, project_pk=None, pk=None):
        requirement = self.get_object()
        requirement.status = Requirement.Status.APPROVED
        requirement.approved_by = request.user
        requirement.approved_at = timezone.now()
        requirement.save(update_fields=["status", "approved_by", "approved_at"])
        ApprovalEvent.objects.create(
            project=requirement.project, requirement=requirement, actor=request.user,
            action=ApprovalEvent.Action.APPROVE, comment=request.data.get("comment", ""),
        )
        return Response(self.get_serializer(requirement).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, project_pk=None, pk=None):
        requirement = self.get_object()
        requirement.status = Requirement.Status.REJECTED
        requirement.approved_by = request.user
        requirement.approved_at = timezone.now()
        requirement.save(update_fields=["status", "approved_by", "approved_at"])
        ApprovalEvent.objects.create(
            project=requirement.project, requirement=requirement, actor=request.user,
            action=ApprovalEvent.Action.REJECT, comment=request.data.get("comment", ""),
        )
        return Response(self.get_serializer(requirement).data)
