ARG TESTCASE_IMAGE
FROM ${TESTCASE_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    VENV_PATH=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN uv venv $VENV_PATH \
 && uv pip install pyyaml pip

COPY validate.py /ssebench/validate.py

WORKDIR /ssebench

ENTRYPOINT ["python3", "-u", "validate.py"]