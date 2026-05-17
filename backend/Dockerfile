FROM maven:3.9-eclipse-temurin-21 AS backend-build

WORKDIR /workspace/backend

COPY backend/pom.xml .
RUN mvn dependency:go-offline -B 2>/dev/null || true

COPY backend/src ./src
RUN mvn package -DskipTests -q

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS research-build

WORKDIR /workspace/src/research-service

COPY src/research-service/pyproject.toml src/research-service/uv.lock ./
RUN uv sync --frozen --no-dev

COPY src/research-service/app ./app

FROM eclipse-temurin:21-jre

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend-requirements.txt
RUN python3 -m venv /opt/backend-venv \
    && /opt/backend-venv/bin/python -m pip install --upgrade pip \
    && /opt/backend-venv/bin/python -m pip install --no-cache-dir -r backend-requirements.txt

COPY --from=backend-build /workspace/backend/target/*.jar /app/app.jar
COPY --from=research-build /workspace/src/research-service/.venv /app/src/research-service/.venv
COPY src/research-service/app /app/src/research-service/app

COPY backend/src/main/resources/python /app/backend-python
COPY scripts/start-backend-stack-combined.sh /app/start-backend-stack-combined.sh

RUN chmod +x /app/start-backend-stack-combined.sh

EXPOSE 8081

ENV JAVA_OPTS="-Xms128m -Xmx384m -XX:+UseContainerSupport -XX:MaxMetaspaceSize=128m -XX:+UseSerialGC"
ENV PATH="/opt/backend-venv/bin:/app/src/research-service/.venv/bin:${PATH}"
ENV PYTHON_BIN="/opt/backend-venv/bin/python"

ENTRYPOINT ["/app/start-backend-stack-combined.sh"]
