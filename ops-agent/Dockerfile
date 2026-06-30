FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY data ./data
COPY eval ./eval
COPY scripts ./scripts

RUN pip install --no-cache-dir -U pip && pip install --no-cache-dir .

ENV BACKEND_MODE=mock \
    LLM_MODE=mock \
    EMBEDDINGS_PROVIDER=local-hash \
    CHECKPOINTER=memory

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
