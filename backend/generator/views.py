from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from projects.models import Project, TraceLink

from .engine import generate_backend
from .frontend_engine import generate_frontend
from .models import GeneratedBackend, GeneratedFrontend
from .serializers import (
    GeneratedBackendSerializer,
    GeneratedFrontendSerializer,
)


def _get_owned_project(request, project_pk) -> Project:
    return get_object_or_404(Project, pk=project_pk, owner=request.user)


class GenerateBackendView(APIView):
    """POST /api/projects/<id>/generate-backend/ — generate the DRF backend.

    Only approved projects can be generated; generation is idempotent: a
    re-run replaces the stored artifacts and TraceLinks.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, project_pk):
        project = _get_owned_project(request, project_pk)
        if project.status != Project.Status.APPROVED:
            return Response(
                {"detail": "Only approved projects can be generated."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not project.requirements.filter(status="approved", req_type="functional").exists():
            return Response(
                {"detail": "Add at least one approved functional requirement first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = generate_backend(project, request.user)
        generation, _ = GeneratedBackend.objects.update_or_create(
            project=project,
            defaults={
                "status": result["status"],
                "resources": result["resources"],
                "artifacts": result["artifacts"],
                "tests_passed": result["tests_passed"],
                "test_output": result["test_output"],
                "databases_tested": result["databases_tested"],
                "generated_by": request.user,
            },
        )

        # Refresh the requirement trace links for this generation.
        TraceLink.objects.filter(
            requirement__project=project,
            kind__in=[TraceLink.Kind.BACKEND, TraceLink.Kind.TEST],
            artifact__startswith="backendapp.",
        ).delete()
        for res in result["resources"]:
            req = project.requirements.get(rid=res["rid"])
            TraceLink.objects.create(
                requirement=req,
                kind=TraceLink.Kind.BACKEND,
                artifact=f"backendapp.views.{res['class_name']}ViewSet",
                description=", ".join(res["endpoints"]),
            )
            TraceLink.objects.create(
                requirement=req,
                kind=TraceLink.Kind.TEST,
                artifact=f"backendapp.tests.{res['class_name']}APITests",
                test_passed=result["tests_passed"],
            )

        return Response(GeneratedBackendSerializer(generation).data, status=status.HTTP_201_CREATED)


class GenerateFrontendView(APIView):
    """POST /api/projects/<id>/generate-frontend/ — generate the React/TS app.

    Same gate as the backend engine: only approved projects with at least one
    approved functional requirement. Idempotent: a re-run replaces the stored
    artifacts and TraceLinks.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, project_pk):
        project = _get_owned_project(request, project_pk)
        if project.status != Project.Status.APPROVED:
            return Response(
                {"detail": "Only approved projects can be generated."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not project.requirements.filter(status="approved", req_type="functional").exists():
            return Response(
                {"detail": "Add at least one approved functional requirement first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = generate_frontend(project, request.user)
        generation, _ = GeneratedFrontend.objects.update_or_create(
            project=project,
            defaults={
                "status": result["status"],
                "pages": result["pages"],
                "artifacts": result["artifacts"],
                "build_passed": result["build_passed"],
                "build_output": result["build_output"],
                "generated_by": request.user,
            },
        )

        TraceLink.objects.filter(
            requirement__project=project,
            kind=TraceLink.Kind.FRONTEND,
            artifact__startswith="frontendapp.",
        ).delete()
        for page in result["pages"]:
            req = project.requirements.get(rid=page["rid"])
            TraceLink.objects.create(
                requirement=req,
                kind=TraceLink.Kind.FRONTEND,
                artifact=f"frontendapp.{page['component']}",
                description=f"/{page['route']} -> {page['api_base']} (build_passed={result['build_passed']})",
            )

        return Response(GeneratedFrontendSerializer(generation).data, status=status.HTTP_201_CREATED)


class GeneratedBackendDetailView(APIView):
    """GET /api/projects/<id>/generated-backend/ — last generation for a project."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_pk):
        project = _get_owned_project(request, project_pk)
        generation = getattr(project, "generated_backend", None)
        if generation is None:
            return Response(
                {"detail": "No backend has been generated for this project yet."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(GeneratedBackendSerializer(generation).data)


class GeneratedFrontendDetailView(APIView):
    """GET /api/projects/<id>/generated-frontend/ — last generation for a project."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_pk):
        project = _get_owned_project(request, project_pk)
        generation = getattr(project, "generated_frontend", None)
        if generation is None:
            return Response(
                {"detail": "No frontend has been generated for this project yet."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(GeneratedFrontendSerializer(generation).data)
