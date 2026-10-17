from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Service

router = APIRouter()


@router.get("/media/servicos/{service_id}/{revision}.jpg", include_in_schema=False)
def service_photo(request: Request, service_id: int, revision: str, db: Session = Depends(get_db)):
    service = db.get(Service, service_id)
    is_admin = request.session.get("admin") is True
    if (not service or not service.image_revision or service.image_revision != revision
            or not (service.active or is_admin) or not service.image_data):
        raise HTTPException(status_code=404, detail="Foto não encontrada.")
    return Response(
        content=service.image_data, media_type="image/jpeg",
        headers={"Cache-Control": "no-store" if is_admin else "private, max-age=3600"},
    )
