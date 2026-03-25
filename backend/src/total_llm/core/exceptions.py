from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class AppException(Exception):
    def __init__(self, detail: str, error_code: str = "APP_ERROR", status_code: int = 400):
        self.detail = detail
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(detail)


class NotFoundError(AppException):
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(detail, error_code="NOT_FOUND", status_code=status.HTTP_404_NOT_FOUND)


class ValidationError(AppException):
    def __init__(self, detail: str = "Validation failed"):
        super().__init__(detail, error_code="VALIDATION_ERROR", status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)


class ExternalServiceError(AppException):
    def __init__(self, detail: str = "External service unavailable"):
        super().__init__(detail, error_code="EXTERNAL_SERVICE_ERROR", status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


class RAGError(AppException):
    def __init__(self, detail: str = "RAG pipeline error"):
        super().__init__(detail, error_code="RAG_ERROR", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VLMError(AppException):
    def __init__(self, detail: str = "VLM processing error"):
        super().__init__(detail, error_code="VLM_ERROR", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeviceControlError(AppException):
    def __init__(self, detail: str = "Device control error"):
        super().__init__(detail, error_code="DEVICE_CONTROL_ERROR", status_code=status.HTTP_400_BAD_REQUEST)


class AuthError(AppException):
    def __init__(self, detail: str = "Authentication error"):
        super().__init__(detail, error_code="AUTH_ERROR", status_code=status.HTTP_401_UNAUTHORIZED)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.error_code, "message": exc.detail}},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_SERVER_ERROR", "message": str(exc)}},
        )
