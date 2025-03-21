from fastapi import APIRouter
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/status")
async def status():
    logger.info("Status Endpoint")
    return {"message": "Hello World"}
