# Deliberately a development image, not a minimal production runtime.
FROM gcc:14.4.0-trixie
RUN apt-get update && apt-get install -y --no-install-recommends cmake git ca-certificates
WORKDIR /lab
COPY CMakeLists.txt cache_model.cpp cache_client.cpp ./
RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCOURSE12_WITH_HIREDIS=ON \
    && cmake --build build -j2 --target cache_client cache_model \
    && ctest --test-dir build --output-on-failure
USER 65534:65534
ENTRYPOINT ["/lab/build/cache_client"]
