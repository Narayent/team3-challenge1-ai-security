# Shared image for both apps; code is bind-mounted by docker-compose.
FROM python:3.11-slim

# libglib2.0 is needed by opencv-python-headless at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
        "numpy==1.26.4" \
        "flask==3.0.3" \
        "opencv-python-headless==4.10.0.84" \
        "werkzeug==3.0.3"

RUN useradd --create-home --uid 10001 labuser
WORKDIR /app
USER labuser

CMD ["python", "lab_access_api.py"]
