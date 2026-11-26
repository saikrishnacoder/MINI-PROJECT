from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ProjectViewSet, RequirementViewSet

router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="projects")

project_requirements = RequirementViewSet.as_view({
    "get": "list",
    "post": "create",
})
project_requirement_detail = RequirementViewSet.as_view({
    "get": "retrieve",
    "patch": "partial_update",
    "delete": "destroy",
    "post": "approve",  # overridden below
})

urlpatterns = [
    path(
        "projects/<int:project_pk>/requirements/",
        project_requirements,
        name="project-requirements",
    ),
    path(
        "projects/<int:project_pk>/requirements/<int:pk>/",
        project_requirement_detail,
        name="project-requirement-detail",
    ),
    path(
        "projects/<int:project_pk>/requirements/<int:pk>/approve/",
        RequirementViewSet.as_view({"post": "approve"}),
        name="requirement-approve",
    ),
    path(
        "projects/<int:project_pk>/requirements/<int:pk>/reject/",
        RequirementViewSet.as_view({"post": "reject"}),
        name="requirement-reject",
    ),
    *router.urls,
]
