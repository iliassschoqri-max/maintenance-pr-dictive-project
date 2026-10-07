FROM apache/airflow:2.6.0
COPY --chown=airflow:0 requirements.txt /tmp/requirements-pfa.txt
RUN pip install --no-cache-dir --user -r /tmp/requirements-pfa.txt
