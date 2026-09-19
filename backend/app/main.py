from fastapi import FastAPI

app=FastAPI(
    title="Fast HR API",
    description="Backend Api for Fast HR",
    version="1.0.0"
)

@app.get("/")
def root():
    return {"message": "Fast HR API is running"}