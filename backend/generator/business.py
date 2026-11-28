"""Phase 8 - application business logic.

Every approved functional requirement becomes one resource in the generated
app. This module decides which business behaviours that resource actually gets
(search, filtering, sorting, uploads, notifications, analytics, workflow,
payments, external integrations, user management) from the requirement's own
wording, then records the rules, endpoints, services, tables and tests that
implement it.

The resulting matrix is persisted on ``GeneratedBackend`` and served by the
generated app's ``/api/features/`` endpoint, so a requirement is either backed
by running code or carries a written reason for being incomplete.
"""

from __future__ import annotations

# Capability table. Order matters: it is the order shown in the UI and docs.
CAPABILITIES: dict[str, dict] = {
    "crud": {
        "label": "CRUD operations",
        "keywords": (),
        "rules": [
            "Every record is created, read, updated and deleted through the API.",
            "Writes run in a transaction; a duplicate name for the same owner is 409 duplicate_name.",
        ],
        "validations": ["name is required and at most 200 characters", "description is optional text"],
        "tests": ["test_owner_can_create_and_retrieve", "test_owner_can_update_and_delete"],
        "endpoints": ["GET /api/{route}/", "GET /api/{route}/{id}/"],
        "frontend": ["src/pages/ResourceListPage.tsx"],
    },
    "search": {
        "label": "Search",
        "keywords": ("search", "find", "look up", "lookup", "browse", "query"),
        "rules": ["List endpoints accept ?search= and match name/description (case-insensitive)."],
        "validations": ["unknown query parameters are ignored, never 500"],
        "tests": ["test_search_and_ordering"],
        "endpoints": ["GET /api/{route}/?search={term}"],
        "frontend": ["src/pages/ResourceListPage.tsx (search field)"],
    },
    "filter": {
        "label": "Filtering",
        "keywords": ("filter", "by status", "date range", "category", "segment", "between"),
        "rules": [
            "List endpoints accept ?created_after= and ?created_before= (ISO dates).",
            "List endpoints accept ?status= for the record lifecycle.",
        ],
        "validations": ["malformed dates are rejected with 400 validation_error"],
        "tests": ["test_date_range_filter"],
        "endpoints": ["GET /api/{route}/?created_after={date}&status={status}"],
        "frontend": ["src/pages/ResourceListPage.tsx (filter controls)"],
    },
    "sort": {
        "label": "Sorting",
        "keywords": ("sort", "order by", "ordering", "ranking", "priority list", "latest"),
        "rules": ["List endpoints accept ?ordering= over name, status, created_at, updated_at."],
        "validations": ["an unsupported ordering field falls back to the default order"],
        "tests": ["test_search_and_ordering"],
        "endpoints": ["GET /api/{route}/?ordering=-created_at"],
        "frontend": ["src/pages/ResourceListPage.tsx (sort selector)"],
    },
    "upload": {
        "label": "File uploads",
        "keywords": ("upload", "attachment", "file", "document", "image", "photo", "csv", "pdf"),
        "rules": ["One attachment per record is stored through the filesystem and served by URL."],
        "validations": [
            "allowed types: pdf, png, jpg, jpeg, txt, csv",
            "maximum size: 5 MB",
        ],
        "tests": ["test_attachment_upload_and_type_validation"],
        "endpoints": ["POST /api/{route}/ (multipart attachment)"],
        "frontend": ["src/pages/ResourceListPage.tsx (file input)"],
    },
    "notifications": {
        "label": "Notifications",
        "keywords": ("notif", "alert", "remind", "notify", "inbox"),
        "rules": [
            "Create, update, delete and status changes write a Notification row for the owner.",
            "Roles with can_view_all also receive notifications for records they can see.",
            "A user only reads and marks their own notifications.",
        ],
        "validations": ["notification ids outside the caller's inbox return 404"],
        "tests": ["test_owner_is_notified_on_create", "test_notifications_are_private_to_the_recipient"],
        "endpoints": [
            "GET /api/notifications/",
            "GET /api/notifications/unread_count/",
            "POST /api/notifications/{id}/read/",
            "POST /api/notifications/read_all/",
        ],
        "frontend": ["src/components/Notifications.tsx"],
    },
    "analytics": {
        "label": "Dashboard analytics",
        "keywords": ("dashboard", "analytic", "report", "statistic", "metric", "insight", "chart", "kpi", "trend"),
        "rules": [
            "GET /api/analytics/summary/ aggregates visible records per resource.",
            "Counts cover total, mine, created in the last 7 days and the lifecycle breakdown.",
        ],
        "validations": ["counts are scoped by the caller's role, never leaked across owners"],
        "tests": ["test_analytics_summary_matches_database"],
        "endpoints": ["GET /api/analytics/summary/"],
        "frontend": ["src/pages/Dashboard.tsx"],
    },
    "workflow": {
        "label": "Workflow automation",
        "keywords": (
            "approve", "approval", "publish", "workflow", "status", "review",
            "draft", "complete", "process",
        ),
        "rules": [
            "Records move draft -> active -> archived and back through explicit transitions.",
            "Only allowed transitions succeed; others are 400 invalid_transition.",
            "Every change writes a StatusEvent audit row and notifies the owner.",
        ],
        "validations": ["target status must be one of draft, active, archived"],
        "tests": ["test_status_transitions_follow_the_workflow", "test_history_records_every_transition"],
        "endpoints": [
            "POST /api/{route}/{id}/transition/",
            "GET /api/{route}/{id}/history/",
            "GET /api/{route}/?status={status}",
        ],
        "frontend": ["src/pages/ResourceListPage.tsx (status controls)"],
    },
    "payments": {
        "label": "Payment integration",
        "keywords": (
            "payment", "checkout", "invoice", "billing", "subscription",
            "stripe", "charge", "refund", "paid",
        ),
        "rules": [
            "POST /api/{route}/{id}/checkout/ calls the configured payment provider.",
            "The provider answer is recorded in ProviderEvent; success is recorded only for a 2xx.",
            "Without PAYMENT_PROVIDER_URL and PAYMENT_API_KEY the endpoint is 503 integration_not_configured and records nothing.",
        ],
        "validations": ["an unreachable provider is 502 provider_unreachable, never a success"],
        "tests": ["test_checkout_without_configuration_is_503", "test_checkout_provider_failure_is_recorded"],
        "endpoints": ["POST /api/{route}/{id}/checkout/"],
        "frontend": ["src/pages/ResourceListPage.tsx (payment action)"],
        "integration": {
            "name": "payments",
            "label": "Payment provider",
            "env": ["PAYMENT_PROVIDER_URL", "PAYMENT_API_KEY"],
            "reason": (
                "The checkout path and its failure handling are generated, but no provider "
                "credentials exist at generation time. Configure PAYMENT_PROVIDER_URL and "
                "PAYMENT_API_KEY to enable it; while unconfigured calls return 503 and no "
                "payment is simulated."
            ),
        },
    },
    "external_api": {
        "label": "External API integration",
        "keywords": (
            "integration", "external api", "third-party", "third party", "webhook",
            "import from", "sync with", "api integration", "external service",
        ),
        "rules": [
            "Outbound calls read EXTERNAL_API_URL and EXTERNAL_API_KEY from the environment.",
            "GET /api/integrations/ reports which integrations are configured; values are never returned.",
        ],
        "validations": ["unconfigured integrations are reported, never faked as working"],
        "tests": ["test_integration_status_lists_required_environment"],
        "endpoints": ["GET /api/integrations/"],
        "frontend": ["src/pages/Settings.tsx (integration status)"],
        "integration": {
            "name": "external_api",
            "label": "External API",
            "env": ["EXTERNAL_API_URL", "EXTERNAL_API_KEY"],
            "reason": (
                "The integration registry and its status endpoint are generated; the external "
                "endpoint and credentials are environment configuration. Until they are set, "
                "calls fail with 503 and no response is simulated."
            ),
        },
    },
    "user_management": {
        "label": "User and role management",
        "keywords": (
            "user management", "manage users", "role", "permission", "admin",
            "invite", "team", "member",
        ),
        "rules": [
            "Roles carry can_view_all, can_edit_others and can_manage_users flags.",
            "Only roles with can_manage_users may change another user's role.",
        ],
        "validations": ["a caller without can_manage_users gets 403 permission_denied"],
        "tests": ["test_admin_can_assign_roles_but_standard_user_cannot"],
        "endpoints": ["PATCH /api/users/{id}/role/"],
        "frontend": ["src/pages/Settings.tsx"],
    },
}

CONFIGURATION_CAPABILITIES = {"payments", "external_api"}


def detect_capabilities(title: str, description: str = "") -> list[str]:
    """Ordered capability ids implemented for a requirement."""
    text = f"{title} {description or ''}".lower()
    found = ["crud"]
    for cap_id, cap in CAPABILITIES.items():
        if cap_id == "crud":
            continue
        if any(keyword in text for keyword in cap["keywords"]):
            found.append(cap_id)
    return found


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def endpoints_for(capabilities: list[str], route: str) -> list[str]:
    endpoints: list[str] = []
    for cap_id in capabilities:
        for template in CAPABILITIES[cap_id]["endpoints"]:
            endpoints.append(template.format(route=route, id="{id}", term="{term}", date="{date}", status="{status}"))
    return _dedupe(endpoints)


def analyse(project, resources) -> dict:
    """Build the business-logic matrix for a project's approved requirements.

    ``resources`` is the list of ``ResourceSpec`` the backend engine planned,
    so requirement ids, routes and class names stay in one place.
    """
    specs = {spec.rid: spec for spec in resources}
    approved = project.requirements.filter(status="approved", req_type="functional").order_by("rid")
    features: list[dict] = []

    for req in approved:
        spec = specs.get(req.rid)
        if spec is None:
            continue
        capabilities = detect_capabilities(req.title, req.description)
        labels = [CAPABILITIES[c]["label"] for c in capabilities]
        endpoints = endpoints_for(capabilities, spec.route)
        rules = _dedupe([rule for c in capabilities for rule in CAPABILITIES[c]["rules"]])
        validations = _dedupe([rule for c in capabilities for rule in CAPABILITIES[c]["validations"]])
        tests = _dedupe([name for c in capabilities for name in CAPABILITIES[c]["tests"]])
        frontend = _dedupe([comp for c in capabilities for comp in CAPABILITIES[c]["frontend"]])

        services = [
            f"services.create_{spec.resource}",
            f"services.update_{spec.resource}",
            f"services.delete_{spec.resource}",
            "services.transition_status",
        ]
        tables = [spec.route, "status_event"]
        operations = [
            "SELECT/INSERT/UPDATE/DELETE on the record table",
            "INSERT status_event, UPDATE status",
        ]
        if "workflow" in capabilities:
            operations.append("Guarded transitions draft -> active -> archived with an audit row")
        if "notifications" in capabilities:
            services.append("services.notify_record")
            tables.append("notification")
            operations.append("INSERT notification")
        if "analytics" in capabilities:
            services.append("services.analytics_summary")
            operations.append("COUNT/GROUP BY over the rows the caller may see")
        if "payments" in capabilities:
            services.append("services.request_checkout")
            tables.append("provider_event")
            operations.append("INSERT provider_event only after a real provider answer")

        integration = next(
            (
                CAPABILITIES[c]["integration"]
                for c in capabilities
                if c in CAPABILITIES and "integration" in CAPABILITIES[c]
            ),
            None,
        )
        needs_config = [c for c in capabilities if c in CONFIGURATION_CAPABILITIES]
        features.append(
            {
                "rid": req.rid,
                "title": req.title,
                "priority": req.priority,
                "resource": spec.route,
                "capabilities": [{"id": c, "label": CAPABILITIES[c]["label"]} for c in capabilities],
                "capability_labels": labels,
                "frontend": frontend,
                "service": services,
                "tables": tables,
                "operations": operations,
                "endpoints": endpoints,
                "rules": rules,
                "validations": validations,
                "tests": tests,
                "status": "configuration_required" if needs_config else "implemented",
                "reason": integration["reason"] if integration else "",
                "integration": integration,
            }
        )

    return {"features": features, "summary": summarise(features)}


def summarise(features: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for feature in features:
        for cap in feature["capabilities"]:
            counts[cap["id"]] = counts.get(cap["id"], 0) + 1
    return {
        "total": len(features),
        "implemented": sum(1 for f in features if f["status"] == "implemented"),
        "configuration_required": sum(
            1 for f in features if f["status"] == "configuration_required"
        ),
        "capabilities": counts,
    }


def summary_text(summary: dict) -> str:
    """One line for docs: totals plus configuration-required count."""
    return (
        f"{summary['total']} approved requirements: {summary['implemented']} fully implemented, "
        f"{summary['configuration_required']} implemented with an integration configuration required."
    )
