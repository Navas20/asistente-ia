"""
SERVICES LAYER - Servicio de Chat
"""
import uuid
import logging
from typing import Optional, Generator

from data_layer.repositories import ConversationRepository
from services.llm_service import llm_service
from services.memory_service import memory_service

log = logging.getLogger("artenisa.chat")


class ChatService:
    """Servicio centralizado de chat"""
    
    def __init__(self):
        self.conv_repo = ConversationRepository()
    
    def create_conversation(self) -> str:
        """Crea una nueva conversación"""
        conv_id = str(uuid.uuid4())
        log.info(f"Nueva conversación creada: {conv_id}")
        return conv_id
    
    def add_user_message(self, conv_id: str, content: str):
        """Agrega un mensaje del usuario"""
        self.conv_repo.add_message(conv_id, "user", content)
        
        # Actualiza memoria reciente
        memory_service.merge_operational_context(conv_id, {
            "last_user_message": content,
            "last_message_type": "user"
        })
    
    def generate_response(self, conv_id: str, prompt: str, temperature: float = 0.85) -> str:
        """Genera una respuesta del asistente"""
        response = llm_service.generate(prompt, temperature)
        self.conv_repo.add_message(conv_id, "assistant", response)
        
        # Actualiza memoria
        memory_service.merge_operational_context(conv_id, {
            "last_assistant_message": response,
            "last_message_type": "assistant"
        })
        
        return response
    
    def stream_response(self, conv_id: str, prompt: str, temperature: float = 0.85) -> Generator[str, None, None]:
        """Genera una respuesta con streaming"""
        response_buffer = ""
        
        for chunk in llm_service.stream(prompt, temperature):
            response_buffer += chunk
            yield chunk
        
        # Guarda la respuesta completa
        if response_buffer:
            self.conv_repo.add_message(conv_id, "assistant", response_buffer)
            memory_service.merge_operational_context(conv_id, {
                "last_assistant_message": response_buffer,
                "last_message_type": "assistant"
            })
    
    def get_conversation_history(self, conv_id: str, limit: int = 20):
        """Obtiene el historial de conversación"""
        return self.conv_repo.get_messages(conv_id, limit)


# Instancia global
chat_service = ChatService()
