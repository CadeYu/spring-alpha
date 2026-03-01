## ---- Stage 1: Build with Maven ----
FROM maven:3.9-eclipse-temurin-21 AS build

WORKDIR /app

# Copy pom first for dependency caching
COPY pom.xml .
RUN mvn dependency:go-offline -B 2>/dev/null || true

# Copy source and build
COPY src ./src
RUN mvn package -DskipTests -q

## ---- Stage 2: Runtime (JRE only) ----
FROM eclipse-temurin:21-jre-alpine

WORKDIR /app

# Install curl for healthcheck
RUN apk add --no-cache curl

COPY --from=build /app/target/*.jar app.jar

EXPOSE 8081

ENV JAVA_OPTS="-Xms256m -Xmx512m -XX:+UseContainerSupport -XX:MaxRAMPercentage=75.0"

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
