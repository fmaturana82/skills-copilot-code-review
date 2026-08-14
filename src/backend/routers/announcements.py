"""
Announcement endpoints for the High School Management System API.
"""

from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"],
)


class AnnouncementCreate(BaseModel):
    """Payload for creating or updating an announcement."""

    message: str = Field(..., min_length=1, max_length=280)
    start_date: Optional[str] = None
    expiration_date: str

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Announcement message is required.")
        return cleaned

    @field_validator("start_date")
    @classmethod
    def validate_start_date(cls, value: Optional[str]) -> Optional[str]:
        if value in (None, ""):
            return None
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("start_date must be in YYYY-MM-DD format.") from exc
        return value

    @field_validator("expiration_date")
    @classmethod
    def validate_expiration_date(cls, value: str) -> str:
        if not value:
            raise ValueError("expiration_date is required.")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("expiration_date must be in YYYY-MM-DD format.") from exc
        return value

    @property
    def is_active(self) -> bool:
        today = date.today()
        start = date.fromisoformat(self.start_date) if self.start_date else None
        expiration = date.fromisoformat(self.expiration_date)

        if start and start > today:
            return False
        return expiration >= today


def _ensure_teacher(username: Optional[str]) -> Dict[str, Any]:
    """Validate that a signed-in teacher or admin is making a change."""
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required for this action")

    teacher = teachers_collection.find_one({"_id": username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def _serialize_announcement(announcement: Dict[str, Any]) -> Dict[str, Any]:
    serialized = dict(announcement)
    serialized["id"] = str(serialized.pop("_id"))
    return serialized


def _is_active(announcement: Dict[str, Any]) -> bool:
    today = date.today()
    start = announcement.get("start_date")
    expiration = announcement.get("expiration_date")

    if not expiration:
        return False

    expiration_date = date.fromisoformat(expiration)
    if start and start:
        try:
            if date.fromisoformat(start) > today:
                return False
        except ValueError:
            return False

    return expiration_date >= today


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def list_announcements() -> List[Dict[str, Any]]:
    """Retrieve all announcements, ordered by most recent expiration date first."""
    announcements = []
    for announcement in announcements_collection.find({}).sort("expiration_date", 1):
        announcements.append(_serialize_announcement(announcement))
    return announcements


@router.get("/active", response_model=List[Dict[str, Any]])
def list_active_announcements() -> List[Dict[str, Any]]:
    """Return only announcements that are currently active."""
    active_announcements = [
        _serialize_announcement(doc)
        for doc in announcements_collection.find({})
        if _is_active(doc)
    ]
    return sorted(active_announcements, key=lambda item: (item.get("start_date") or "", item.get("expiration_date") or ""))


@router.post("", response_model=Dict[str, Any])
def create_announcement(payload: AnnouncementCreate, teacher_username: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Create a new announcement. Requires an authenticated teacher or admin."""
    _ensure_teacher(teacher_username)

    announcement_id = f"announcement-{len(list(announcements_collection.find({}))) + 1}"
    document = {
        "_id": announcement_id,
        "message": payload.message,
        "start_date": payload.start_date,
        "expiration_date": payload.expiration_date,
        "created_by": teacher_username,
    }

    announcements_collection.insert_one(document)
    return _serialize_announcement(document)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementCreate,
    teacher_username: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Update an existing announcement. Requires an authenticated teacher or admin."""
    _ensure_teacher(teacher_username)

    existing = announcements_collection.find_one({"_id": announcement_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    update_data = {
        "message": payload.message,
        "start_date": payload.start_date,
        "expiration_date": payload.expiration_date,
        "created_by": teacher_username,
    }

    announcements_collection.update_one({"_id": announcement_id}, {"$set": update_data})
    updated = announcements_collection.find_one({"_id": announcement_id})
    return _serialize_announcement(updated)


@router.delete("/{announcement_id}", response_model=Dict[str, str])
def delete_announcement(announcement_id: str, teacher_username: Optional[str] = Query(None)) -> Dict[str, str]:
    """Delete an announcement. Requires an authenticated teacher or admin."""
    _ensure_teacher(teacher_username)

    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
