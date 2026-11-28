"""Phase 4 - Backend Development Engine.

Turns an approved project's approved functional requirements into a real,
runnable DRF app - models, serializers, JWT auth, role-based permissions, a
service layer with transactions, a structured error handler, file uploads,
search/filtering, docs and tests. Every generated resource is traced back to
its requirement id, and the generated suite is executed against SQLite and, when
a MySQL server is reachable, against MySQL as well.

The generation plan and the harness results are validated through the pydantic
models in ``schemas.py`` before anything is written or persisted.
"""
import json
import os
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

from . import business, templates
from .schemas import GenerationPlan, GenerationResult, HarnessRun, ResourceSpec

# Phrases stripped from the front of a requirement title to find the resource.
_FILLER_PREFIXES = [
    "users should be able to",
    "user should be able to",
    "users can be able to",
    "users can",
    "user can",
    "the system shall",
    "system shall",
    "the system should",
    "system should",
    "the user can",
    "the application shall",
    "the application should",
    "i want to",
    "we want to",
    "ability to",
    "allow",
    "allows",
]

_STOP_WORDS = {"a", "an", "the", "to", "be", "of", "and", "or", "in", "on", "for", "with", "my", "our"}


def derive_resource(title: str) -> str:
    """Deterministically map a requirement title to a snake_case resource name."""
    text = title.lower().strip().rstrip(".")
    for filler in _FILLER_PREFIXES:
        if text.startswith(filler):
            text = text[len(filler):].strip()
            break
    words = [w for w in re_split(text) if w]
    words = [w for w in words if w not in _STOP_WORDS][:3] or ["item"]
    return "_".join(words)


def re_split(text: str) -> list[str]:
    import re

    return re.split(r"[^a-z0-9]+", text)


def class_name(resource: str) -> str:
    return "".join(w.capitalize() for w in resource.split("_"))


def _resource_specs(project) -> list[ResourceSpec]:
    approved = project.requirements.filter(status="approved")
    functional = [r for r in approved if r.req_type == "functional"]

    specs: list[ResourceSpec] = []
    seen: set[str] = set()
    for req in functional:
        base = derive_resource(req.title)
        n = 2
        route = base
        while route in seen:
            route = f"{base}_{n}"
            n += 1
        seen.add(route)
        capabilities = business.detect_capabilities(req.title, req.description)
        endpoints = [
            f"GET /api/{route}/",
            f"POST /api/{route}/",
            f"GET /api/{route}/{{id}}/",
            f"PATCH /api/{route}/{{id}}/",
            f"PUT /api/{route}/{{id}}/",
            f"DELETE /api/{route}/{{id}}/",
        ]
        if "workflow" in capabilities:
            endpoints += [
                f"POST /api/{route}/{{id}}/transition/",
                f"GET /api/{route}/{{id}}/history/",
            ]
        if "payments" in capabilities:
            endpoints.append(f"POST /api/{route}/{{id}}/checkout/")
        specs.append(
            ResourceSpec(
                rid=req.rid,
                title=req.title,
                priority=req.priority,
                resource=base,
                route=route,
                class_name=class_name(base),
                capabilities=capabilities,
                endpoints=endpoints,
            )
        )
    return specs


def _build_artifacts(
    plan: GenerationPlan,
    project_name: str,
    databases_tested: list[str],
    feature_matrix: dict | None = None,
) -> dict:
    resources = plan.resources
    features = (feature_matrix or {}).get("features", [])
    summary = (feature_matrix or {}).get("summary", {})
    return {
        "manage.py": templates.manage_py(),
        "settings.py": templates.settings_py(),
        "requirements.txt": templates.requirements_txt(),
        ".env.example": templates.env_example(),
        "backendapp/__init__.py": "",
        "backendapp/apps.py": templates.apps_py(),
        "backendapp/config.py": templates.config_py(),
        "backendapp/models.py": templates.models_py(resources),
        "backendapp/serializers.py": templates.serializers_py(resources),
        "backendapp/permissions.py": templates.permissions_py(),
        "backendapp/services.py": templates.services_py(resources),
        "backendapp/integrations.py": templates.integrations_py(),
        "backendapp/features.py": templates.features_py(features, summary),
        "backendapp/exceptions.py": templates.exceptions_py(),
        "backendapp/middleware.py": templates.middleware_py(),
        "backendapp/pagination.py": templates.pagination_py(),
        "backendapp/filters.py": templates.filters_py(),
        "backendapp/roles.py": templates.roles_py(),
        "backendapp/signals.py": templates.signals_py(),
        "backendapp/auth_views.py": templates.auth_views_py(),
        "backendapp/views.py": templates.views_py(resources),
        "backendapp/urls.py": templates.urls_py(resources),
        "backendapp/tests.py": templates.tests_py(resources),
        "backendapp/docs.md": templates.docs_md(
            project_name, resources, databases_tested, features, summary
        ),
        "backendapp/requirements_map.json": json.dumps(
            [r.model_dump() for r in resources], indent=2
        ),
    }


def _mysql_env() -> dict:
    """Connection settings for the local MySQL/MariaDB used by the harness run."""
    return {
        "host": os.environ.get("SPECFORGE_MYSQL_HOST", "127.0.0.1"),
        "port": int(os.environ.get("SPECFORGE_MYSQL_PORT") or 3306),
        "user": os.environ.get("SPECFORGE_MYSQL_USER", "root"),
        "password": os.environ.get("SPECFORGE_MYSQL_PASSWORD") or "root",
    }


@lru_cache(maxsize=1)
def mysql_available() -> bool:
    """True when a MySQL/MariaDB server answers and is not opted out."""
    if os.environ.get("SPECFORGE_SKIP_MYSQL_TESTS") == "1":
        return False
    try:
        import pymysql

        conn = pymysql.connect(connect_timeout=3, **_mysql_env())
        conn.close()
        return True
    except Exception:
        return False


def _mysql_execute(statements: list[str]) -> None:
    import pymysql

    conn = pymysql.connect(connect_timeout=3, **_mysql_env())
    try:
        with conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
        conn.commit()
    finally:
        conn.close()


def _run_harness(
    harness_dir: Path, database: str = "sqlite", project_id: int = 0, timeout: int = 240
) -> tuple[bool, str]:
    """Run the generated app's real test suite on the selected database."""
    env = os.environ.copy()
    database_name = f"specforge_gen_{project_id}"
    if database == "mysql":
        config = _mysql_env()
        env.update(
            {
                "GENERATED_DB_ENGINE": "mysql",
                "MYSQL_DATABASE": database_name,
                "MYSQL_HOST": str(config["host"]),
                "MYSQL_PORT": str(config["port"]),
                "MYSQL_USER": str(config["user"]),
                "MYSQL_PASSWORD": str(config["password"]),
            }
        )
        # Django opens the configured database before creating test_<name>.
        _mysql_execute([f"CREATE DATABASE IF NOT EXISTS `{database_name}`"])
    else:
        env.update(
            {
                "GENERATED_DB_ENGINE": "sqlite",
                "SQLITE_PATH": str(harness_dir / "harness.sqlite3"),
            }
        )

    commands = [[sys.executable, "manage.py", "makemigrations", "backendapp"]]
    commands.append([sys.executable, "manage.py", "test", "backendapp", "-v", "2", "--noinput"])
    output_parts = [f"# database: {database}"]
    try:
        for cmd in commands:
            try:
                proc = subprocess.run(
                    cmd, cwd=harness_dir, capture_output=True, text=True, timeout=timeout, env=env
                )
                output_parts.append(f"$ {' '.join(cmd[1:])}\n{proc.stdout}\n{proc.stderr}")
                if proc.returncode != 0:
                    return False, "\n---\n".join(output_parts)
            except subprocess.TimeoutExpired:
                output_parts.append(f"$ {' '.join(cmd[1:])}\nTIMED OUT after {timeout}s")
                return False, "\n---\n".join(output_parts)
        return True, "\n---\n".join(output_parts)
    finally:
        if database == "mysql":
            try:
                _mysql_execute([f"DROP DATABASE IF EXISTS `{database_name}`"])
            except Exception:
                pass


def generate_backend(project, user) -> dict:
    """Build the generated app for an approved project and run its tests.

    Returns a validated dict:
    {status, resources, artifacts, tests_passed, test_output, databases_tested,
     harness_dir}
    """
    plan = GenerationPlan(project_id=project.id, resources=_resource_specs(project))
    feature_matrix = business.analyse(project, plan.resources)
    artifacts = _build_artifacts(plan, project.name, ["sqlite"], feature_matrix)

    harness_dir = Path(tempfile.mkdtemp(prefix=f"specforge_backend_{project.id}_"))
    for rel, content in artifacts.items():
        target = harness_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    runs: list[HarnessRun] = []
    sqlite_passed, sqlite_output = _run_harness(harness_dir, "sqlite", project.id)
    runs.append(HarnessRun(database="sqlite", passed=sqlite_passed, output=sqlite_output))

    if sqlite_passed and mysql_available():
        mysql_passed, mysql_output = _run_harness(harness_dir, "mysql", project.id, timeout=300)
        runs.append(HarnessRun(database="mysql", passed=mysql_passed, output=mysql_output))

    databases_tested = [run.database for run in runs if run.passed]
    tests_passed = all(run.passed for run in runs)

    result = GenerationResult(
        project_id=project.id,
        status="success" if tests_passed else "failed",
        resources=plan.resources,
        tests_passed=tests_passed,
        databases_tested=databases_tested or ["sqlite"],
        outputs=runs,
    )

    docs = templates.docs_md(
        project.name,
        plan.resources,
        result.databases_tested,
        feature_matrix["features"],
        feature_matrix["summary"],
    )
    artifacts["backendapp/docs.md"] = docs
    (harness_dir / "backendapp/docs.md").write_text(docs, encoding="utf-8")

    artifacts["harness_dir"] = str(harness_dir)
    return {
        "status": result.status,
        "resources": [r.model_dump() for r in result.resources],
        "artifacts": artifacts,
        "tests_passed": result.tests_passed,
        "features": feature_matrix["features"],
        "feature_summary": feature_matrix["summary"],
        "test_output": "\n\n".join(
            f"===== {run.database} =====\n{run.output}" for run in runs
        ),
        "databases_tested": result.databases_tested,
        "harness_dir": str(harness_dir),
    }
