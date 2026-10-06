from pydantic import BaseModel

class JobCreateInternal(BaseModel):
    name:str
    data:dict


class JobResponse(BaseModel):
    job_id:str
    name:str
    status:str

