from pydantic import BaseModel, Field


class RandomizationInput(BaseModel):
 # run_id 由 URL 路径权威提供并在路由中回填，请求体无需携带
 run_id: int = Field(default=0, gt=0)
 replications: int = Field(default=2000, ge=100, le=100000, strict=True)
 seed: int | None = Field(default=None)
 timeout_seconds: float = Field(default=25.0, gt=0, le=120)
