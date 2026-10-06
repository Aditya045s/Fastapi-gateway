from pydantic import BaseModel,Field


class JobCreate(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    data:dict


class JobResponse(BaseModel):
    job_id:str
    name:str
    status:str
    