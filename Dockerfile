# Build from this folder: docker build -t my-bot .
# The match runs it with no network, a read-only root (writable /tmp), 1 CPU, 512 MB, and the map at /arena.

# --- stage 1: compile the C++ core
FROM python:3.13-slim AS build
RUN apt-get update \
 && apt-get install -y --no-install-recommends g++ make \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY core/ core/
RUN make -C core clean all

# --- stage 2: runtime (no compiler)
FROM python:3.13-slim
WORKDIR /bot
COPY *.py ./
COPY --from=build /src/core/libmech_core.so core/libmech_core.so
ENTRYPOINT ["python3", "-u", "/bot/bot.py"]
