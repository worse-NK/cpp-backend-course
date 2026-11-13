FROM gcc:14.4.0-trixie AS build
WORKDIR /src
# The release header is copied from a checked local dependency directory.
# See README.txt: its archive has a documented SHA-256, no curl-pipe-shell.
COPY httplib.h app.cpp ./
RUN g++ -std=c++20 -O2 -static-libstdc++ -static-libgcc -pthread -Wall -Wextra -Wpedantic \
      -DCPPHTTPLIB_HEADER_MAX_LENGTH=4096 \
      -DCPPHTTPLIB_HEADER_MAX_COUNT=32 \
      -DCPPHTTPLIB_REQUEST_URI_MAX_LENGTH=512 app.cpp -o /server
FROM debian:trixie-20261027-slim
COPY --from=build /server /app/server
USER 65532:65532
EXPOSE 8080
STOPSIGNAL SIGTERM
ENTRYPOINT ["/app/server"]
