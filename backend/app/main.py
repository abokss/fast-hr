from fastapi import FastAPI

from .routers.candidates import router as candidates_router
from .routers.resumes import router as resumes_router
from .routers.vacancies import router as vacancies_router


app = FastAPI(
    title="Fast HR API",
    description="Backend API for Fast HR",
    version="1.0.0",
)
app.include_router(candidates_router)
app.include_router(resumes_router)
app.include_router(vacancies_router)


@app.get("/")
def root():
    return {"message": "Fast HR API is running"}
