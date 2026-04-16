#PGADMIN_DEFAULT_EMAIL     PGADMIN_DEFAULT_PASSWORD
# from fastapi import FastAPI

# app = FastAPI(title="ConnectPro ML")


# @app.get("/")
# def read_root():
#     return {"message": "Hello from ConnectPro ML service"}

from contextlib import asynccontextmanager
from fastapi import FastAPI
#from app.database import create_pool, close_pool
#from app.items import router as items_router
from connectpro_ml.persistence.Database import create_pool, close_pool
from  connectpro_ml.persistence.Items import router as items_router

 
 
@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_pool()
    yield
    await close_pool()
 
 
app = FastAPI(title="Recommendation Service", lifespan=lifespan)
app.include_router(items_router, prefix="/api/v1")
 
 
@app.get("/health")
async def health():
    return {"status": "ok"}
 