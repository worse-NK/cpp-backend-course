# syntax=docker/dockerfile:1
FROM debian:bookworm-slim AS build
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential ca-certificates cmake git libpq-dev ninja-build \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY CMakeLists.txt client.cpp ./
RUN cmake -S . -B /build -G Ninja -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /build --parallel 2

FROM debian:bookworm-slim AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl libpq5 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /build/release_v1 /build/release_v2 /usr/local/bin/
USER 65532:65532
WORKDIR /tmp
CMD ["/usr/local/bin/release_v1", "show"]
