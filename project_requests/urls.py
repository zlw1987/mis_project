"""URL routes for the project_requests app (Phase 2B + Phase 3D-1 + Phase 3D-2)."""

from django.urls import path

from . import views

app_name = "project_requests"

urlpatterns = [
    # Phase 4B: Dashboard
    path("dashboard/", views.ProjectRequestDashboardView.as_view(), name="dashboard"),
    # List
    path("", views.ProjectRequestListView.as_view(), name="list"),
    # Create
    path("new/", views.ProjectRequestCreateView.as_view(), name="create"),
    # Detail
    path("<int:pk>/", views.ProjectRequestDetailView.as_view(), name="detail"),
    # Edit draft
    path("<int:pk>/edit/", views.ProjectRequestEditDraftView.as_view(), name="edit"),
    # Attachment upload
    path(
        "<int:pk>/attachments/upload/",
        views.ProjectRequestAttachmentUploadView.as_view(),
        name="attachment_upload",
    ),
    # Attachment download (permission-checked)
    path(
        "attachments/<int:attachment_id>/download/",
        views.ProjectRequestAttachmentDownloadView.as_view(),
        name="attachment_download",
    ),
    # Phase 3D-1: Approve/Reject
    path(
        "<int:pk>/approve/",
        views.project_request_approve,
        name="approve",
    ),
    path(
        "<int:pk>/reject/",
        views.project_request_reject,
        name="reject",
    ),
    # Phase 3D-2: Assign/Claim
    path(
        "<int:pk>/assign/",
        views.project_request_assign,
        name="assign",
    ),
    path(
        "<int:pk>/claim/",
        views.project_request_claim,
        name="claim",
    ),
    # Phase 3D-3: Execution Workflow
    path(
        "<int:pk>/start/",
        views.project_request_start,
        name="start",
    ),
    path(
        "<int:pk>/hold/",
        views.project_request_hold,
        name="hold",
    ),
    path(
        "<int:pk>/resume/",
        views.project_request_resume,
        name="resume",
    ),
    path(
        "<int:pk>/complete/",
        views.project_request_complete,
        name="complete",
    ),
]
