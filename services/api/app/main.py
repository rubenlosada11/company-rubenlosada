from fastapi import FastAPI

app = FastAPI(
    title="TrackFlow API",
    description="Directorio de proveedores de TrackFlow (USA + Spain).",
    version="0.1.0",
)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
