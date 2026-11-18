from rest_framework.views import exception_handler as drf_handler
from rest_framework.exceptions import APIException, ValidationError
from django.core.exceptions import ValidationError as DjangoValidationError


class Conflict(APIException):
    status_code = 409
    default_detail = "Kayıt değişti. Güncel sürümü yükleyip tekrar deneyin."
    default_code = "version_conflict"


def exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError("Geçersiz alan veya kayıt kimliği.")
    response = drf_handler(exc, context)
    if response is not None and isinstance(response.data, dict):
        response.data.setdefault(
            "code", getattr(exc, "default_code", "validation_error")
        )
    return response
