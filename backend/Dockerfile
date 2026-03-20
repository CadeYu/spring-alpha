## ---- Stage 1: Build with Maven ----
FROM maven:3.9-eclipse-temurin-21 AS build

WORKDIR /app

# Copy pom first for dependency caching
COPY pom.xml .
RUN mvn dependency:go-offline -B 2>/dev/null || true

# Copy source and build
COPY src ./src
RUN mvn package -DskipTests -q

## ---- Stage 2: Runtime ----
##
## Render's Docker runtime was missing `python3`, which breaks the Yahoo
## enrichment helper invoked by YahooFinanceMarketDataService. We intentionally
## use the Debian-based Temurin image here instead of Alpine because Python
## wheels (pandas/numpy/yfinance transitive deps) are much more reliable on it.
FROM eclipse-temurin:21-jre

WORKDIR /app

# Install runtime dependencies for:
# - health checks (`curl`)
# - Yahoo Finance helper (`python3`, `pip`, `venv`)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --upgrade pip \
    && /opt/venv/bin/python -m pip install --no-cache-dir -r requirements.txt

COPY --from=build /app/target/*.jar app.jar

EXPOSE 8081

ENV JAVA_OPTS="-Xms128m -Xmx384m -XX:+UseContainerSupport -XX:MaxMetaspaceSize=128m -XX:+UseSerialGC"
ENV PATH="/opt/venv/bin:${PATH}"
ENV PYTHON_BIN="/opt/venv/bin/python"

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
