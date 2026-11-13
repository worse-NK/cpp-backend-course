FROM gcc:14.4.0-trixie
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates cmake ninja-build git pkg-config libcurl4-openssl-dev \
    libprotobuf-dev protobuf-compiler && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY CMakeLists.txt app.cpp metrics.hpp metrics_model.cpp ./
RUN cmake -S . -B /build -G Ninja -DCOURSE_WITH_OTEL=ON -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /build --parallel 2
USER 65534:65534
EXPOSE 8080
ENTRYPOINT ["/build/course_observe"]
