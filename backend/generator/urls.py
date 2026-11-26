from django.urls import path

from .views import (
    GenerateBackendView,
    GenerateFrontendView,
    GeneratedBackendDetailView,
    GeneratedFrontendDetailView,
)

urlpatterns = [
    path(
        "projects/<int:project_pk>/generate-backend/",
        GenerateBackendView.as_view(),
        name="generate-backend",
    ),
    path(
        "projects/<int:project_pk>/generated-backend/",
        GeneratedBackendDetailView.as_view(),
        name="generated-backend-detail",
    ),
    path(
        "projects/<int:project_pk>/generate-frontend/",
        GenerateFrontendView.as_view(),
        name="generate-frontend",
    ),
    path(
        "projects/<int:project_pk>/generated-frontend/",
        GeneratedFrontendDetailView.as_view(),
        name="generated-frontend-detail",
    ),
]
