import asyncio
import os
import sys

# Добавляем родительскую папку в пути, чтобы импорты backend... работали
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.llm.provider import get_llm_provider


async def main():
    print("🤖 Инициализация провайдера...")
    try:
        provider = get_llm_provider()
        print(f"✅ Провайдер создан. Модель в конфиге: {provider._model_name}")

        print("⏳ Отправка тестового запроса в Qwen (это может занять до 10-20 секунд)...")
        result = await provider.complete(
            system_prompt="Ты — лаконичный корпоративный помощник.",
            user_prompt="Напиши один короткий тезис, зачем компании автоматизировать отчеты."
        )

        print("\n--- 💬 ОТВЕТ ОТ МОДЕЛИ ---")
        print(result.content)
        print("--------------------------")
        print(f"📊 Токены: Входные={result.prompt_tokens}, Выходные={result.completion_tokens}")
        print(f"⏱️ Время генерации: {result.latency_seconds} сек.")

    except Exception as e:
        print(f"\n❌ [ОШИБКА] Сбой при вызове локальной LLM:")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())