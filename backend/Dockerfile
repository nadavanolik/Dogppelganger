# syntax=docker/dockerfile:1

# ---- Export stage: turn CLIP into an ONNX graph, then throw PyTorch away ----
#
# This stage installs ~2GB of PyTorch and downloads the CLIP checkpoint purely
# to run scripts/export_encoder.py. Nothing from it reaches the final image
# except the two files it produces, so the runtime container gets the model
# without ever containing a deep-learning framework — which is the difference
# between an image the VM pulls in seconds and one it pulls in minutes.
#
# The layer order matters: requirements-ml.txt is copied on its own so the
# expensive pip install is cached and only redone when those pins change.
FROM python:3.12-slim AS encoder

WORKDIR /build
ENV PYTHONUNBUFFERED=1

COPY requirements-ml.txt .
RUN pip install --no-cache-dir -r requirements-ml.txt

# Only what export_encoder.py actually imports, so editing a router doesn't
# invalidate this layer and re-run a multi-minute export.
COPY app/ml/attributes.py app/ml/encoder.py app/ml/preprocess.py app/ml/vectors.py app/ml/__init__.py ./app/ml/
COPY scripts/export_encoder.py ./scripts/
RUN python scripts/export_encoder.py --out /export


# ---- Runtime stage: FastAPI, onnxruntime, no PyTorch ----
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1

# opencv needs libGL/libglib even in its headless build.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The exported encoder (~350MB) and the baked attribute prompts. Copied after
# the source so a code change doesn't invalidate the export stage's cache.
COPY --from=encoder /export/ ./app/ml/assets/

EXPOSE 5000
# Single worker on purpose: the WebSocket connection registry is in-memory,
# so all live sockets must live in one process (scale later via Redis pub/sub).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]
