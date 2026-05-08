"""QR code generation endpoint."""

from __future__ import annotations

import io
from enum import Enum

from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel

router = APIRouter(prefix="/v1/qr", tags=["qr"])


class QRFormat(str, Enum):
    png = "png"
    svg = "svg"


class QRRequest(BaseModel):
    data: str
    size: int = 256
    format: QRFormat = QRFormat.png


class QRMetadata(BaseModel):
    data: str
    size: int
    format: str
    byte_length: int


@router.post("/generate", response_model=QRMetadata)
async def generate_qr_metadata(req: QRRequest) -> QRMetadata:
    """Generate a QR code and return metadata. Use /generate/image for the binary."""
    img_bytes = _render_qr(req.data, req.size, req.format)
    return QRMetadata(
        data=req.data,
        size=req.size,
        format=req.format.value,
        byte_length=len(img_bytes),
    )


@router.get("/generate/image")
async def generate_qr_image(
    data: str = Query(..., description="Content to encode"),
    size: int = Query(256, ge=64, le=2048, description="Image size in pixels"),
    fmt: QRFormat = Query(QRFormat.png, alias="format", description="Output format"),
) -> Response:
    """Generate a QR code image."""
    img_bytes = _render_qr(data, size, fmt)
    media = "image/png" if fmt == QRFormat.png else "image/svg+xml"
    return Response(content=img_bytes, media_type=media)


def _render_qr(data: str, size: int, fmt: QRFormat) -> bytes:
    """Render a QR code to bytes."""
    import qrcode
    from qrcode.image.styledpil import StyledPilImage

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=2)
    qr.add_data(data)
    qr.make(fit=True)

    if fmt == QRFormat.svg:
        from qrcode.image.svg import SvgPathImage

        img = qr.make_image(image_factory=SvgPathImage)
        buf = io.BytesIO()
        img.save(buf)
        return buf.getvalue()

    img = qr.make_image(image_factory=StyledPilImage, module_drawer=None)
    img = img.resize((size, size))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
