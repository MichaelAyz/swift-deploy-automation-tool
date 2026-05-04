# SwiftDeploy Automation Tool

SwiftDeploy is a declarative, infrastructure-as-code CLI automation tool designed to manage a Docker Compose stack. Rather than writing complex Nginx and Docker Compose files by hand, you define your desired state in a single `manifest.yaml` file, and SwiftDeploy handles the rest. 

It manages a Python API service and an Nginx reverse proxy, complete with health checks, zero-downtime canary promotions, and chaos engineering testing capabilities.

## Prerequisites
- **Docker & Docker Compose**: Must be installed and running.
- **Python 3**: Required to run the `swiftdeploy` CLI tool.
- **Linux/macOS/WSL**: Expected environment for execution.

## Setup Instructions

1. **Clone the repository and enter the directory:**
   ```bash
   git clone <your-repo-url>
   cd swift-deploy-automation-tool
   ```

2. **Make the CLI tool executable:**
   ```bash
   chmod +x swiftdeploy
   ```

3. **Build the Docker Image:**
   Before deploying, you must build the lightweight Python API image locally. The manifest expects it to be tagged as `swift-deploy-1-node:latest`.
   ```bash
   docker build -t swift-deploy-1-node:latest .
   ```

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Service info — mode, version, timestamp |
| `/healthz` | GET | Liveness check — status and uptime |
| `/chaos` | POST | Canary mode only — simulate degraded behaviour |

### Chaos modes
```bash
# Slow mode — sleep N seconds before responding
curl -X POST http://localhost:8080/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode":"slow","duration":3}'

# Error mode — return 500 on ~50% of requests  
curl -X POST http://localhost:8080/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode":"error","rate":0.5}'

# Recover — clear all chaos
curl -X POST http://localhost:8080/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode":"recover"}'
```

---

## How It Works

`manifest.yaml` is the single source of truth. `swiftdeploy init` 
reads every field from it and renders the Nginx and Docker Compose 
configs from templates using simple `{{PLACEHOLDER}}` substitution. 
The grader can delete generated files and re-run `./swiftdeploy init` 
to reproduce them identically.

All traffic enters through Nginx on port 8080. The app container 
on port 3000 is never exposed directly. Both containers share the 
`swiftdeploy-net` bridge network.

---

## Subcommand Walkthrough

Run `./swiftdeploy <subcommand>` to interact with the tool.

### 1. `init`
**Usage:** `./swiftdeploy init`
Reads the `manifest.yaml` file and automatically generates the complex `nginx.conf` and `docker-compose.yml` configuration files directly in your root directory.

### 2. `validate`
**Usage:** `./swiftdeploy validate`
Runs a suite of pre-flight checks to ensure the deployment will be successful before it even starts. It checks:
- If `manifest.yaml` exists and contains valid YAML.
- If all required configuration fields are present.
- If the required Docker image (`swift-deploy-1-node:latest`) is built and available locally.
- If the requested Nginx host port is currently free.
- If the generated `nginx.conf` is syntactically valid (contains all required directives and balanced braces).

### 3. `deploy`
**Usage:** `./swiftdeploy deploy`
The primary deployment command. It automates the full lifecycle:
1. Calls `init` to ensure configurations are up to date.
2. Brings up the Nginx and API containers in the background using Docker Compose.
3. Actively polls the `/healthz` endpoint through Nginx, blocking the terminal until the stack reports as healthy (or fails after a 60-second timeout).

### 4. `promote`
**Usage:** `./swiftdeploy promote [canary | stable]`
Safely switches the deployment mode of the application.
- Updates the `mode` field inside `manifest.yaml` in-place.
- Regenerates the configuration files.
- Gracefully restarts **only** the API app container (leaving Nginx running) to apply the new environment variables.
- Verifies the new mode is active by checking the `/healthz` and root `/` endpoints.

*Note: Canary mode automatically injects `X-Mode: canary` into headers and unlocks the `/chaos` POST endpoint for testing degraded behaviors.*

### 5. `teardown`
**Usage:** `./swiftdeploy teardown [--clean]`
Stops the running stack and removes all associated Docker containers, networks, and volumes safely. 
- If you append the `--clean` flag (`./swiftdeploy teardown --clean`), it will also delete the auto-generated `nginx.conf` and `docker-compose.yml` files from your root folder, leaving your workspace completely pristine.
