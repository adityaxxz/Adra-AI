from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import SQLAlchemyError
import logging
import traceback


logger = logging.getLogger(__name__)


async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with consistent error response format."""
    logger.error(f"HTTP error: {exc.status_code} - {exc.detail}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "message": str(exc.detail),
            "status_code": exc.status_code,
            "path": str(request.url.path)
        }
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors."""
    logger.error(f"Validation error: {exc.errors()}")
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": True,
            "message": "Validation error",
            "details": exc.errors(),
            "path": str(request.url.path)
        }
    )


async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    """Handle database errors."""
    logger.error(f"Database error: {str(exc)}")
    logger.error(traceback.format_exc())
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": True,
            "message": "A database error occurred",
            "path": str(request.url.path)
        }
    )


async def generic_exception_handler(request: Request, exc: Exception):
    """Handle all other unhandled exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}")
    logger.error(traceback.format_exc())
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": True,
            "message": "An unexpected error occurred",
            "path": str(request.url.path)
        }
    )


async def not_found_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle 404 errors."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "error": True,
            "message": "Resource not found",
            "path": str(request.url.path)
        }
    )


class ErrorHandler:
    """Centralized error handling utilities."""
    
    @staticmethod
    def log_error(error: Exception, context: str = ""):
        """Log an error with context."""
        logger.error(f"{context}: {str(error)}")
        logger.error(traceback.format_exc())
    
    @staticmethod
    def create_error_response(
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict = None
    ) -> JSONResponse:
        """Create a standardized error response."""
        content = {
            "error": True,
            "message": message,
            "status_code": status_code
        }
        
        if details:
            content["details"] = details
        
        return JSONResponse(
            status_code=status_code,
            content=content
        )
