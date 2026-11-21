# API image: FastAPI server + triage agent
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt
COPY agent agent
COPY server server
COPY seeds seeds
EXPOSE 8787
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8787"]
