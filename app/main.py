from fastapi import FastAPI

app = FastAPI(title="Geo Measurement API")


@app.get("/health")
def health():
    return {"status": "ok"}
