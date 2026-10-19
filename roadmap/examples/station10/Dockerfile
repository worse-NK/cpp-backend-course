FROM debian:bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ cmake make && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY CMakeLists.txt main.cpp ./
RUN cmake -S . -B /build -DCMAKE_BUILD_TYPE=Release \
 && cmake --build /build --parallel 2 \
 && ctest --test-dir /build --output-on-failure --no-tests=error

FROM debian:bookworm-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY --from=build /build/gate_check /usr/local/bin/gate_check
USER 65532:65532
ENTRYPOINT ["/usr/local/bin/gate_check"]
