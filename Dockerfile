# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder
WORKDIR /build
COPY . .
# Builds a wheel for README Doctor and for each of its dependencies.
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.12-slim
LABEL org.opencontainers.image.title="README Doctor" \
      org.opencontainers.image.description="Find README instructions that no longer match a repository" \
      org.opencontainers.image.source="https://github.com/elieh999/readme-doctor" \
      org.opencontainers.image.licenses="MIT"

RUN useradd --create-home --uid 10001 doctor
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir --no-index --find-links /wheels readme-doctor \
    && rm -rf /wheels

USER doctor
# Mount the repository to inspect here, read only:
#   docker run --rm -v "$PWD:/repository:ro" readme-doctor check /repository
WORKDIR /repository
ENTRYPOINT ["readme-doctor"]
CMD ["--help"]
