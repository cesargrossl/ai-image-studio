FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 STREAMLIT_SERVER_HEADLESS=true
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app/
RUN useradd -m -u 10001 app && mkdir -p /data /home/app/.u2net && chown -R app:app /app /data /home/app
USER app
EXPOSE 8501
CMD ["streamlit", "run", "main.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.maxUploadSize=20", "--browser.gatherUsageStats=false"]
