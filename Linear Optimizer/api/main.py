"""
Linear Optimizer API
Сервис для взаимодействия с базой данных Altawin
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import uvicorn

from modules.routes import router

# Загрузка переменных окружени
load_dotenv()

# Создание приложения
app = FastAPI(
    title="Linear Optimizer API",
    description="API для работы с линейной оптимизацией профилей",
    version="1.0.0"
)

# Настройка CORS для работы с клиентом
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение роутов
app.include_router(router, prefix="/api")

@app.get("/")
async def root():
    return {
        "service": "Linear Optimizer API",
        "status": "running",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001) 