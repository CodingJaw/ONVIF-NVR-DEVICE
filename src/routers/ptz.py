"""PTZ control endpoints."""

from fastapi import APIRouter, Depends

from src.security import require_roles

router = APIRouter(
    prefix="/ptz",
    tags=["ptz"],
    dependencies=[Depends(require_roles(["operator", "admin"]))],
)


@router.post("/move")
def continuous_move(pan: float = 0.0, tilt: float = 0.0, zoom: float = 0.0) -> dict[str, float]:
    return {"pan": pan, "tilt": tilt, "zoom": zoom, "status": "moving"}


@router.post("/stop")
def stop_move() -> dict[str, str]:
    return {"status": "stopped"}

