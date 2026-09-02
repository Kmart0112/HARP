FROM apache/superset:latest

USER root

# PostgreSQL driver for SQLAlchemy
# Superset uses /app/.venv/lib/... on PYTHONPATH in this image, but it doesn't ship with /app/.venv/bin/pip.
# Install the driver into that site-packages directory explicitly.
RUN mkdir -p /app/.venv/lib/python3.10/site-packages \
	&& /usr/local/bin/python -m pip install --no-cache-dir --target /app/.venv/lib/python3.10/site-packages psycopg2-binary

USER superset
