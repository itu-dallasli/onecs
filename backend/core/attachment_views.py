"""Multipart transport stays separate from JSON-only domain mutations."""

from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from .attachments import (
    _current_actor, attachment_data, authorized_attachment, download_ready,
    private_path, purge_deleted_file, resource_for_actor, stage_upload,
)
from .models import Attachment
from .services import audit


class AttachmentSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    size = serializers.IntegerField(read_only=True)
    content_type = serializers.CharField(read_only=True)
    status = serializers.ChoiceField(choices=["PENDING_SCAN", "READY", "REJECTED", "DELETED"], read_only=True)
    scan_status = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class AttachmentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class AttachmentListSerializer(serializers.Serializer):
    results = AttachmentSerializer(many=True)
    count = serializers.IntegerField()


@extend_schema_view(
    create=extend_schema(request={"multipart/form-data": AttachmentUploadSerializer}, responses={201: AttachmentSerializer}),
    list=extend_schema(parameters=[
        OpenApiParameter("resource_type", OpenApiTypes.STR),
        OpenApiParameter("resource_id", OpenApiTypes.UUID),
    ], responses=AttachmentListSerializer),
    download=extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY}),
    destroy=extend_schema(request=None, responses={204: None}),
)
class AttachmentViewSet(viewsets.GenericViewSet):
    serializer_class = AttachmentSerializer
    queryset = Attachment.objects.none()
    parser_classes = [MultiPartParser, FormParser]

    def create(self, request):
        if set(request.data) - {"file"} or len(request.FILES.getlist("file")) != 1:
            raise ValidationError({"file": "Her istekte tek dosya seçin."})
        item = stage_upload(request.user, request.FILES.get("file"), request.headers.get("X-Request-ID"))
        return Response(attachment_data(item), status=201)

    def list(self, request):
        actor = _current_actor(request.user)
        resource_type = request.query_params.get("resource_type")
        resource_id = request.query_params.get("resource_id")
        if resource_type or resource_id:
            if not resource_type or not resource_id:
                raise ValidationError("Kayıt türü ve kimliği birlikte gönderilmelidir.")
            obj = resource_for_actor(actor, resource_type, resource_id)
            items = Attachment.objects.filter(resource_type=resource_type, resource_id=obj.pk)
        else:
            if getattr(actor, "_api_client", None):
                raise NotFound("Kayıt bulunamadı.")
            items = Attachment.objects.filter(uploaded_by=actor, resource_id__isnull=True)
        items = items.exclude(status="DELETED").order_by("created_at")
        return Response({"results": [attachment_data(item) for item in items], "count": items.count()})

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        item = authorized_attachment(request.user, pk)
        if not download_ready(item):
            raise ValidationError("Dosyanın güvenlik taraması henüz tamamlanmadı veya dosya kullanıma uygun değil.")
        try:
            handle = private_path(item.storage_key).open("rb")
        except OSError:
            raise NotFound("Dosya bulunamadı.")
        response = FileResponse(handle, as_attachment=True, filename=item.name, content_type=item.content_type)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "sandbox"
        return response

    def destroy(self, request, pk=None):
        actor = _current_actor(request.user)
        with transaction.atomic():
            try:
                item = Attachment.objects.select_for_update().filter(pk=pk, uploaded_by=actor, resource_id__isnull=True).exclude(status="DELETED").first()
            except (ValueError, TypeError, DjangoValidationError):
                item = None
            if item is None:
                raise NotFound("İlişkisiz dosya bulunamadı.")
            item.status = "DELETED"
            item.version += 1
            item.save(update_fields=["status", "version", "updated_at"])
            audit(actor, "attachment.staged.deleted", item)
            # Tombstone first; a failed unlink stays inaccessible and cleanup can retry.
            transaction.on_commit(lambda: purge_deleted_file(item.pk, item.storage_key), robust=True)
        return Response(status=204)
