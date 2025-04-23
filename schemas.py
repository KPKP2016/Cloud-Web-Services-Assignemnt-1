#create a schema for your login details using the code below

from pydantic import BaseModel 
class AuthDetails(BaseModel):
    username: str 
    password: str  