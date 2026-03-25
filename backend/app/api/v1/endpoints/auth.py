"""
Эндпоинты авторизации: логин, регистрация, текущий пользователь.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.logging import get_logger
from app.core.security import create_access_token, hash_password, verify_password
from app.models.models import AuditLog, User
from app.schemas.schemas import TokenResponse, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
) -> TokenResponse:
    """Логин по username + password. Возвращает JWT."""
    result = await db.execute(
        select(User).where(User.username == form_data.username)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        logger.warning("login_failed", username=form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Учётная запись отключена",
        )

    token = create_access_token({"sub": user.id, "role": user.role.value})

    # Аудит
    db.add(AuditLog(user_id=user.id, action="login", resource_type="user"))
    await db.commit()

    logger.info("login_success", user_id=user.id, role=user.role)
    return TokenResponse(access_token=token)


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: DbSession) -> User:
    """
    Регистрация нового пользователя (роль — user).
    В prod-окружении можно закрыть или ограничить только для admin.
    """
    # Проверяем уникальность
    existing = await db.execute(
        select(User).where(
            (User.email == payload.email) | (User.username == payload.username)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с таким email или username уже существует",
        )

    user = User(
        email=payload.email,
        username=payload.username,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("user_registered", user_id=user.id, email=payload.email)
    return user


@router.get("/me", response_model=UserRead)
async def get_me(current_user: CurrentUser) -> User:
    """Информация о текущем пользователе."""
    return current_user
