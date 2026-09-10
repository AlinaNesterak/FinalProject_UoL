# Music Works Catalogue Portal — container image
#
# Reproducible deployment was a deliberate design goal from the start
# (Mathiak et al., 2020, identify containerisation as one of the more
# effective sustainability strategies for digital-humanities software,
# and single-institution/single-machine dependency as one of the causes
# of MerMEId's own decline). This image builds the database at container
# start and serves the API and web interface on port 8000.

FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (better layer caching on rebuilds)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application
COPY api/ ./api/
COPY transform/ ./transform/
COPY frontend/ ./frontend/
COPY data/ ./data/
COPY evaluation/ ./evaluation/

# Build the database at image build time, so the container starts instantly
# and works even if the data files never change between runs.
RUN python transform/pipeline.py data catalogue.db

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
