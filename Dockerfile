FROM python:3.12-slim
WORKDIR /opt/finagent
COPY requirements-lock.txt requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements-lock.txt
COPY src ./src
RUN pip install --no-deps . && useradd --uid 10001 --create-home app && mkdir /data && chown app:app /data
ENV FINAGENT_DIRECTORY=/data
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["uvicorn", "finagent.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
