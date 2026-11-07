from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="GEI API")

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
