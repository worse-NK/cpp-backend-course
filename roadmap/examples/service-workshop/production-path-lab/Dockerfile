FROM gcc:14.4.0-trixie AS build
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
 && apt-get update \
 && apt-get install -y --no-install-recommends cmake ninja-build pkg-config libsodium-dev \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY CMakeLists.txt common.hpp common.cpp api.cpp messaging.cpp main.cpp ./
RUN cmake -S . -B /build -G Ninja -DCMAKE_BUILD_TYPE=Release \
 && cmake --build /build --parallel 2
RUN /build/production_path self-test

FROM debian:trixie-20261027-slim
COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
 && apt-get -o Acquire::https::CaInfo=/etc/ssl/certs/ca-certificates.crt update \
 && apt-get -o Acquire::https::CaInfo=/etc/ssl/certs/ca-certificates.crt install -y --no-install-recommends ca-certificates libpq5 libsodium23 libstdc++6 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --no-create-home path_app
COPY --from=build /build/production_path /usr/local/bin/production_path
USER 10001:10001
ENTRYPOINT ["/usr/local/bin/production_path"]
CMD ["api"]
