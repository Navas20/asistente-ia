FROM python:3.11-slim

# Instalar dependencias del sistema necesarias para el backend
RUN apt update && apt install -y \
    python3-pip python3-venv python3-pyaudio \
    nmap curl wget netcat-openbsd dnsutils whois \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar el backend e instalar los requerimientos de Python
COPY backend/ /app/
RUN pip3 install --no-cache-dir -r requirements.txt

# Crear directorios para datos, subidas y audios
RUN mkdir -p data/uploads data/audio

EXPOSE 8000

# Configurar el script de inicio
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
