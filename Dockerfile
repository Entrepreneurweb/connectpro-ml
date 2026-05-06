FROM python:3.11-slim

WORKDIR /app

# Dependances systeme pour LightFM (compilation C)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Installer les dependances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY src/ ./src/
#COPY .env* ./

# Creer le dossier pour les modeles LightFM
RUN mkdir -p /app/models

# Telecharger le modele sentence-transformers au build (evite le telechargement au runtime)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "connectpro_ml.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]