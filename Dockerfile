# Cloud Run Job image for the scheduled discovery pass (run_discovery.py).
# Deliberately not `pip install -r requirements.txt` — that also pulls in
# Playwright (unused by any adapter so far, and its Chromium download is
# large) and google-cloud-firestore (Cloud Run can't reach Firestore here
# at all, see storage/gcs_json.py's docstring — only google-cloud-storage
# is needed in this image). Keep this list in sync with what run_discovery's
# adapters actually import, not with the full dev requirements.txt.
FROM python:3.13-slim
WORKDIR /app
COPY src/ src/
RUN pip install --no-cache-dir \
    pydantic>=2.7 \
    httpx>=0.27 \
    beautifulsoup4>=4.12 \
    python-dotenv>=1.0 \
    google-cloud-storage>=2.16
ENV PYTHONPATH=/app/src
CMD ["python", "-m", "radiocomp.run_discovery"]
