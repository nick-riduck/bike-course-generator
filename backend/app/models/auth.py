from pydantic import BaseModel

class LoginRequest(BaseModel):
    id_token: str
