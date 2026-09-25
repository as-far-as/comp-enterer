# Cloud Run Job image for the scheduled discovery pass (run_discovery.py).
# Deliberately not `pip install -r requirements.txt` — that also pulls in
# google-cloud-firestore (Cloud Run can't reach Firestore here at all, see
# storage/gcs_json.py's docstring — only google-cloud-storage is needed in
# this image). Keep this list in sync with what run_discovery's adapters
# actually import, not with the full dev requirements.txt.
#
# Based on Microsoft's own Playwright image, same already-solved pattern
# as Dockerfile.entry-execution: stations/talksport_widget.py needs a real
# browser to reach talkSPORT's entry-widget pricing (2026-09-08 — a
# competition page's own static/rendered HTML never has the price at all,
# it's delegated to a third-party iframe). This tag bakes in the Chromium
# binary + OS deps for the version below but NOT the `playwright` pip
# package itself (confirmed live via a Cloud Build probe when
# Dockerfile.entry-execution was built) — so it's still installed
# explicitly, just without needing its own browser download. The
# `playwright==` pin below MUST stay equal to the image tag's version or
# Playwright can't find the pre-baked browser executable at all.
FROM mcr.microsoft.com/playwright/python:v1.62.0-noble
WORKDIR /app
COPY src/ src/
RUN pip install --no-cache-dir \
    pydantic>=2.7 \
    httpx>=0.27 \
    beautifulsoup4>=4.12 \
    python-dotenv>=1.0 \
    google-cloud-storage>=2.16 \
    playwright==1.62.0
ENV PYTHONPATH=/app/src
CMD ["python", "-m", "radiocomp.run_discovery"]
