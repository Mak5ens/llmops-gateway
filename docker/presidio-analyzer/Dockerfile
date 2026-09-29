# Presidio Analyzer with the French spaCy model on top of the official image, which only ships en_core_web_lg.
# The NLP and recognizer configuration is mounted from config/presidio/ by compose.yaml, so changing it needs
# a restart, not a rebuild.
FROM mcr.microsoft.com/presidio-analyzer:2.2.362

ARG FR_MODEL_URL=https://github.com/explosion/spacy-models/releases/download/fr_core_news_lg-3.8.0/fr_core_news_lg-3.8.0-py3-none-any.whl
ARG FR_MODEL_SHA256=da5bf7fc860af64293d88638b4416b3de3a29005b785bfff67d09b06c77345de

# The base image installs its packages as root and runs as user 1001.
USER root
RUN pip install --no-deps "fr_core_news_lg @ ${FR_MODEL_URL}#sha256=${FR_MODEL_SHA256}"
USER 1001
