# Presidio Analyzer with the French spaCy model and the custom French recognizers, on top of the official
# image, which only ships en_core_web_lg. The NLP and recognizer configuration of config/presidio/ is copied in
# (build context `config`), so the published image runs on its own on Kubernetes; compose.yaml also mounts it,
# so changing it locally needs a restart, not a rebuild.
FROM mcr.microsoft.com/presidio-analyzer:2.2.362

ARG FR_MODEL_URL=https://github.com/explosion/spacy-models/releases/download/fr_core_news_lg-3.8.0/fr_core_news_lg-3.8.0-py3-none-any.whl
ARG FR_MODEL_SHA256=da5bf7fc860af64293d88638b4416b3de3a29005b785bfff67d09b06c77345de

# The base image installs its packages as root and runs as user 1001.
USER root
RUN pip install --no-deps "fr_core_news_lg @ ${FR_MODEL_URL}#sha256=${FR_MODEL_SHA256}"
USER 1001

COPY pii_recognizers /app/pii_recognizers
COPY server.py /app/server.py
COPY --from=config . /config
ENV ANALYZER_CONF_FILE=/config/analyzer.yaml \
    NLP_CONF_FILE=/config/nlp.yaml \
    RECOGNIZER_REGISTRY_CONF_FILE=/config/recognizers.yaml

# Same command as the base image's entrypoint.sh, with server.py as the app: it imports pii_recognizers
# before the recognizer registry is read.
CMD ["sh", "-c", "exec poetry run gunicorn -w \"$WORKERS\" -b \"0.0.0.0:$PORT\" \"server:create_app()\""]
