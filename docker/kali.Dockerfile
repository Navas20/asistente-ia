FROM kalilinux/kali-rolling

RUN apt update && apt install -y \
    nmap \
    python3 \
    python3-pip \
    netcat-openbsd \
    curl \
    libcap2-bin \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash toolrunner && /sbin/setcap cap_net_raw,cap_net_admin=eip /usr/bin/nmap

COPY backend/kali_server.py /app/kali_server.py

RUN pip3 install fastapi uvicorn --break-system-packages

USER toolrunner
WORKDIR /app

EXPOSE 9001

CMD ["python3", "-m", "uvicorn", "kali_server:app", "--host", "0.0.0.0", "--port", "9001"]
