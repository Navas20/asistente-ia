FROM ollama/ollama:latest

RUN apt update && apt install -y \
    python3-pip python3-venv python3-pyaudio \
    nmap curl wget netcat-openbsd dnsutils whois \
    && rm -rf /var/lib/apt/lists/*

RUN ollama serve & sleep 3 && ollama pull whiterabbitneo:7b

COPY modelfiles/personal.modelfile /root/.ollama/modelfiles/personal.modelfile
RUN ollama create personal -f /root/.ollama/modelfiles/personal.modelfile

WORKDIR /app
COPY backend/ /app/
RUN pip3 install --no-cache-dir -r requirements.txt

RUN mkdir -p data/uploads data/audio

EXPOSE 8000

COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
