from __future__ import annotations

from typing import Optional

from fastapi import Request

from app.services import auth


def current_user(request: Request) -> Optional[dict]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return auth.get_user_by_id(int(user_id))
