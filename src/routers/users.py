"""User management CRUD endpoints secured by admin role."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.security import require_roles
from src.users import User, UserStore, get_user_store


class UserCreate(BaseModel):
    username: str
    password: str = Field(min_length=1)
    roles: list[str] = Field(default_factory=lambda: ["viewer"])


class UserUpdate(BaseModel):
    password: str | None = Field(default=None)
    roles: list[str] | None = None


class UserResponse(BaseModel):
    username: str
    roles: list[str]

    @classmethod
    def from_user(cls, user: User) -> "UserResponse":
        return cls(username=user.username, roles=sorted(user.roles))


router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_roles(["admin"]))],
)


def _get_store() -> UserStore:
    return get_user_store()


@router.get("/", response_model=list[UserResponse])
def list_users(store: UserStore = Depends(_get_store)) -> list[UserResponse]:
    return [UserResponse.from_user(user) for user in store.list_users()]


@router.get("/{username}", response_model=UserResponse)
def get_user(username: str, store: UserStore = Depends(_get_store)) -> UserResponse:
    user = store.get_user(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse.from_user(user)


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
def create_user(payload: UserCreate, store: UserStore = Depends(_get_store)) -> UserResponse:
    try:
        user = store.add_user(payload.username, payload.password, payload.roles)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return UserResponse.from_user(user)


@router.put("/{username}", response_model=UserResponse)
def update_user(
    username: str, payload: UserUpdate, store: UserStore = Depends(_get_store)
) -> UserResponse:
    try:
        user = store.update_user(username, password=payload.password, roles=payload.roles)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return UserResponse.from_user(user)


@router.delete("/{username}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(username: str, store: UserStore = Depends(_get_store)) -> None:
    try:
        store.delete_user(username)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

