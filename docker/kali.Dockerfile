FROM kalilinux/kali-rolling

ARG DEBIAN_FRONTEND=noninteractive

# Install the current runtime tools plus later-phase binaries in one layer.
# Only tools present in kali_server.py's allowlist can be executed through the API.
RUN apt-get update && apt-get install -y --no-install-recommends \
    aircrack-ng \
    ca-certificates \
    curl \
    dnsutils \
    git \
    gobuster \
    hashcat \
    hydra \
    iputils-ping \
    john \
    libcap2-bin \
    metasploit-framework \
    netcat-openbsd \
    nikto \
    nmap \
    python3 \
    python3-dev \
    python3-fastapi \
    python3-pip \
    python3-pydantic \
    python3-uvicorn \
    sqlmap \
    theharvester \
    whois \
    wpscan \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash toolrunner \
    && /sbin/setcap cap_net_raw,cap_net_admin=eip /usr/bin/nmap

COPY backend/kali_server.py /app/kali_server.py

WORKDIR /app
USER toolrunner

EXPOSE 9001

CMD ["python3", "-m", "uvicorn", "kali_server:app", "--host", "0.0.0.0", "--port", "9001"]
