FROM golang:1.22-alpine AS builder

WORKDIR /app

# Install git (needed by go mod tidy to resolve VCS deps)
RUN apk add --no-cache git ca-certificates

COPY go.mod ./
# Generate go.sum at build time — no need to commit it
RUN go mod tidy

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o gateway .

FROM alpine:3.20
RUN apk add --no-cache ca-certificates
WORKDIR /app
COPY --from=builder /app/gateway .

EXPOSE 8080
CMD ["./gateway"]
