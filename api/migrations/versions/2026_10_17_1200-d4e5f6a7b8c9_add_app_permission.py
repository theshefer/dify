"""add app permission and app_permissions table

Revision ID: d4e5f6a7b8c9
Revises: 0cc3158b50b0
Create Date: 2026-10-17 12:00:00.000000

Mirrors dataset collaboration permissions for console apps (chatflows,
workflows, agent apps). Existing apps keep all_team_members visibility;
new apps default to only_me in application code.
"""

import sqlalchemy as sa
from alembic import op

import models as models

# revision identifiers, used by Alembic.
revision = "d4e5f6a7b8c9"
down_revision = "0cc3158b50b0"
branch_labels = None
depends_on = None


def _is_pg(conn):
    return conn.dialect.name == "postgresql"


def upgrade():
    conn = op.get_bind()

    with op.batch_alter_table("apps", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "permission",
                sa.String(length=255),
                nullable=False,
                server_default="all_team_members",
            )
        )

    if _is_pg(conn):
        op.create_table(
            "app_permissions",
            sa.Column(
                "id", models.types.StringUUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False
            ),
            sa.Column("app_id", models.types.StringUUID(), nullable=False),
            sa.Column("account_id", models.types.StringUUID(), nullable=False),
            sa.Column("tenant_id", models.types.StringUUID(), nullable=False),
            sa.Column("has_permission", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column(
                "created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.PrimaryKeyConstraint("id", name="app_permission_pkey"),
        )
    else:
        op.create_table(
            "app_permissions",
            sa.Column("id", models.types.StringUUID(), nullable=False),
            sa.Column("app_id", models.types.StringUUID(), nullable=False),
            sa.Column("account_id", models.types.StringUUID(), nullable=False),
            sa.Column("tenant_id", models.types.StringUUID(), nullable=False),
            sa.Column("has_permission", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.current_timestamp(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id", name="app_permission_pkey"),
        )

    with op.batch_alter_table("app_permissions", schema=None) as batch_op:
        batch_op.create_index("idx_app_permissions_app_id", ["app_id"], unique=False)
        batch_op.create_index("idx_app_permissions_account_id", ["account_id"], unique=False)
        batch_op.create_index("idx_app_permissions_tenant_id", ["tenant_id"], unique=False)


def downgrade():
    with op.batch_alter_table("app_permissions", schema=None) as batch_op:
        batch_op.drop_index("idx_app_permissions_tenant_id")
        batch_op.drop_index("idx_app_permissions_account_id")
        batch_op.drop_index("idx_app_permissions_app_id")
    op.drop_table("app_permissions")

    with op.batch_alter_table("apps", schema=None) as batch_op:
        batch_op.drop_column("permission")
