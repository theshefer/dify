"""Legacy only_me / all_team / partial_members collaboration when RBAC is off.

Mirrors dataset collaboration checks for console apps and installed-app visibility.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from sqlalchemy import ColumnElement, delete, select
from sqlalchemy.orm import Session, scoped_session

from configs import dify_config
from models import Account, AppPermission
from models.account import TenantAccountRole
from models.enums import PermissionEnum
from models.model import App
from services.errors.base import NoPermissionError

logger = logging.getLogger(__name__)


def build_collaboration_visibility_filter(
    user_id: str, tenant_id: str, session: Session | scoped_session
) -> ColumnElement[bool] | None:
    """SQL visibility filter for only_me / all_team / partial_members when RBAC is off.

    Returns None when RBAC owns visibility (no legacy collaboration filter).
    """
    if dify_config.RBAC_ENABLED:
        return None

    permitted_app_ids = set(
        session.scalars(
            select(AppPermission.app_id).where(
                AppPermission.account_id == user_id,
                AppPermission.tenant_id == tenant_id,
                AppPermission.has_permission.is_(True),
            )
        ).all()
    )
    if permitted_app_ids:
        return sa.or_(
            App.permission == PermissionEnum.ALL_TEAM,
            sa.and_(
                App.permission == PermissionEnum.ONLY_ME,
                App.maintainer == user_id,
            ),
            sa.and_(
                App.permission == PermissionEnum.PARTIAL_TEAM,
                sa.or_(
                    App.maintainer == user_id,
                    App.id.in_(permitted_app_ids),
                ),
            ),
        )
    return sa.or_(
        App.permission == PermissionEnum.ALL_TEAM,
        sa.and_(
            App.permission.in_([PermissionEnum.ONLY_ME, PermissionEnum.PARTIAL_TEAM]),
            App.maintainer == user_id,
        ),
    )


def check_app_collaboration_permission(app: App, user: Account, session: Session | scoped_session) -> None:
    """Validate console app access for a user (mirrors dataset collaboration checks)."""
    if app.tenant_id != user.current_tenant_id:
        logger.debug("User %s does not have permission to access app %s", user.id, app.id)
        raise NoPermissionError("You do not have permission to access this app.")
    if dify_config.RBAC_ENABLED:
        return
    if user.current_role == TenantAccountRole.OWNER:
        return
    if app.permission == PermissionEnum.ONLY_ME and app.maintainer != user.id:
        logger.debug("User %s does not have permission to access app %s", user.id, app.id)
        raise NoPermissionError("You do not have permission to access this app.")
    if app.permission == PermissionEnum.PARTIAL_TEAM and app.maintainer != user.id:
        user_permission = session.scalar(
            select(AppPermission)
            .where(
                AppPermission.app_id == app.id,
                AppPermission.account_id == user.id,
                AppPermission.tenant_id == app.tenant_id,
                AppPermission.has_permission.is_(True),
            )
            .limit(1)
        )
        if not user_permission:
            logger.debug("User %s does not have permission to access app %s", user.id, app.id)
            raise NoPermissionError("You do not have permission to access this app.")


class AppPermissionService:
    @classmethod
    def get_app_partial_member_list(cls, app_id: str, session: Session | scoped_session) -> list[str]:
        return list(session.scalars(select(AppPermission.account_id).where(AppPermission.app_id == app_id)).all())

    @classmethod
    def update_partial_member_list(
        cls, tenant_id: str, app_id: str, user_list: list[dict[str, str]], session: Session | scoped_session
    ) -> None:
        session.execute(delete(AppPermission).where(AppPermission.app_id == app_id))
        permissions = [
            AppPermission(
                tenant_id=tenant_id,
                app_id=app_id,
                account_id=user["user_id"],
            )
            for user in user_list
        ]
        session.add_all(permissions)
        session.flush()

    @classmethod
    def check_permission(
        cls,
        user: Account,
        _app: App,
        _requested_permission: PermissionEnum | str | None,
        _requested_partial_member_list: list[dict[str, str]] | None,
        *,
        session: Session | scoped_session,
    ) -> None:
        del session  # reserved for future operator-style checks (parity with datasets)
        if not user.has_edit_permission:
            raise NoPermissionError("User does not have permission to edit this app.")

    @classmethod
    def clear_partial_member_list(cls, app_id: str, session: Session | scoped_session) -> None:
        session.execute(delete(AppPermission).where(AppPermission.app_id == app_id))
        session.flush()

    @classmethod
    def load_partial_members_map(cls, session: Session | scoped_session, *, apps: list[App] | list[str]) -> dict[str, list[str]]:
        app_ids: list[str] = []
        for item in apps:
            if isinstance(item, str):
                app_ids.append(item)
            elif getattr(item, "permission", None) == PermissionEnum.PARTIAL_TEAM:
                app_ids.append(str(item.id))
        if not app_ids:
            return {}

        partial_members_map: dict[str, list[str]] = {}
        partial_member_rows = session.execute(
            select(AppPermission.app_id, AppPermission.account_id).where(AppPermission.app_id.in_(app_ids))
        ).all()
        for app_id, account_id in partial_member_rows:
            partial_members_map.setdefault(str(app_id), []).append(str(account_id))
        return partial_members_map
