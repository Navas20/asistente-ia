FROM ollama/ollama:0.33.3

RUN mv /usr/lib/ollama/llama-server /usr/lib/ollama/llama-server.real

COPY llama-server /usr/lib/ollama/llama-server

RUN chmod +x /usr/lib/ollama/llama-server