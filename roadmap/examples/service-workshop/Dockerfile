# syntax=docker/dockerfile:1
FROM debian:bookworm-slim AS build

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential ca-certificates cmake git libpq-dev ninja-build \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY CMakeLists.txt app.cpp storage*.cpp storage*.hpp ./
RUN cmake -S . -B /build -G Ninja \
      -DCMAKE_BUILD_TYPE=Release -DCOURSE_WITH_POSTGRES=ON \
      -DBUILD_SHARED_LIBS=OFF -DBUILD_TESTING=OFF \
    && cmake --build /build --target course_tasks --parallel 2

FROM debian:bookworm-slim AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl libpq5 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /build/course_tasks /usr/local/bin/course_tasks
USER 65532:65532
WORKDIR /tmp
ENV APP_BIND=0.0.0.0 APP_PORT=8080 APP_STORAGE=postgres
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["curl", "--fail", "--silent", "--show-error", "--connect-timeout", "1", "--max-time", "2", "http://127.0.0.1:8080/health/ready"]
ENTRYPOINT ["/usr/local/bin/course_tasks"]
