"""
API Router - Chat endpoints
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
import logging

from app.models import ChatRequest, ChatResponse
from security.auth import verify_token
from security.audit import audit_service
from services import chat_service

log = logging.getLogger("artenisa.api.chat")

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    token: str = Depends(verify_token)
):
    """Endpoint de chat sin streaming"""
    
    # Crear conversación si no existe
    conv_id = request.conversation_id or chat_service.create_conversation()
    
    # Agregar mensaje del usuario
    chat_service.add_user_message(conv_id, request.message)
    
    # Generar respuesta
    response = chat_service.generate_response(
        conv_id,
        request.message,
        temperature=0.85
    )
    
    # Log de auditoría
    audit_service.log_action(0, "api", "chat", conv_id, "ok")
    
    return ChatResponse(
        conversation_id=conv_id,
        role="assistant",
        content=response,
        timestamp=__import__('datetime').datetime.now(__import__('datetime').timezone.utc)
    )


@router.post("/chat/stream")
async def chat_stream_endpoint(
    request: ChatRequest,
    token: str = Depends(verify_token)
):
    """Endpoint de chat con streaming"""
    
    # Crear conversación si no existe
    conv_id = request.conversation_id or chat_service.create_conversation()
    
    # Agregar mensaje del usuario
    chat_service.add_user_message(conv_id, request.message)
    
    # Generar respuesta con streaming
    def generate():
        yield f'data: {{"conversation_id": "{conv_id}"}}\n\n'
        
        for chunk in chat_service.stream_response(conv_id, request.message):
            yield f'data: {{"chunk": "{chunk}"}}\n\n'
        
        yield 'data: [DONE]\n\n'
    
    # Log de auditoría
    audit_service.log_action(0, "api", "chat/stream", conv_id, "ok")
    
    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/chat/history/{conversation_id}")
async def get_history_endpoint(
    conversation_id: str,
    limit: int = Query(20, le=100),
    token: str = Depends(verify_token)
):
    """Obtiene el historial de una conversación"""
    
    history = chat_service.get_conversation_history(conversation_id, limit)
    
    audit_service.log_action(0, "api", "chat/history", conversation_id, "ok")
    
    return {
        "conversation_id": conversation_id,
        "messages": history,
        "count": len(history)
    }
