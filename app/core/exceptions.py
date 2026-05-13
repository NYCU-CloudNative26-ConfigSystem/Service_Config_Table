from fastapi import HTTPException, status


class ConfigEntryNotFoundError(HTTPException):
    def __init__(self, entry_id: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Config entry '{entry_id}' not found.",
        )


class ConfigEntryForbiddenError(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify this config entry.",
        )


class InvalidKeyIDError(HTTPException):
    def __init__(self, key_id: str):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Key ID '{key_id}' does not exist in Config Service.",
        )


class InvalidValueIDError(HTTPException):
    def __init__(self, value_id: str):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Value ID '{value_id}' does not exist in Config Service.",
        )


class InvalidTokenError(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
