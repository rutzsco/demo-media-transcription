from fastapi import APIRouter
from pydantic import BaseModel
from app.services.transcription_service import TranscriptionService
import asyncio
router = APIRouter()

transcription_service = TranscriptionService()

class WorkflowInput(BaseModel):
    filePath: str

@router.post("/workflow")
async def run_workflow(request: WorkflowInput):
    """
    POST endpoint for executing a Semantic Kernel workflow.
    """
    transcript = await transcription_service.get_transcription(request.filePath)
    return {"result": transcript}
