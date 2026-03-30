#!/usr/bin/env python3
"""Создание первого администратора.
Запуск: docker compose exec backend python scripts/create_admin.py
"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    from app.db.session import AsyncSessionLocal
    from app.models.models import User, UserRole
    from app.core.security import hash_password
    from sqlalchemy import select

    email    = os.getenv("ADMIN_EMAIL",    "admin@company.ru")
    username = os.getenv("ADMIN_USERNAME", "admin")
    password = os.getenv("ADMIN_PASSWORD", "Admin123!")

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.username == username))
        if existing.scalar_one_or_none():
            print(f"[!] Пользователь '{username}' уже существует")
            return
        admin = User(
            email=email, username=username,
            hashed_password=hash_password(password),
            role=UserRole.admin,
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        print(f"[OK] Admin создан: id={admin.id}")
        print(f"     username: {username}")
        print(f"     password: {password}")
        print("[!]  Смените пароль после первого входа!")

asyncio.run(main())
