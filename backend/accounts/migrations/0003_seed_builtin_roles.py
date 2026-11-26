"""Seed the three built-in roles: Admin, Manager, Standard User."""

from django.db import migrations


PERMISSION_PREFIXES = {
    "Manager": ["add_project", "change_project", "view_project", "add_requirement", "change_requirement", "view_requirement", "view_generatedbackend", "view_generatedfrontend"],
    "Standard User": ["view_project", "add_requirement", "change_requirement", "view_requirement"],
}


def seed_roles(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Permission = apps.get_model("auth", "Permission")

    admin, _ = Role.objects.get_or_create(
        name="Admin", defaults={"description": "Full control, manages roles and users."}
    )
    admin.is_admin = True
    admin.save(update_fields=["is_admin"])

    for name, prefixes in PERMISSION_PREFIXES.items():
        role, _ = Role.objects.get_or_create(
            name=name,
            defaults={"description": f"{name} role with curated permissions."},
        )
        perms = Permission.objects.filter(codename__in=prefixes)
        role.permissions.set(perms)


def remove_roles(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Role.objects.filter(name__in=["Admin", "Manager", "Standard User"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_activitylog_role_user_role"),
    ]

    operations = [
        migrations.RunPython(seed_roles, remove_roles),
    ]
