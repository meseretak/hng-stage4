# SwiftDeploy — Full Class Guide

This document explains the entire project from scratch. What every file does, what every keyword means, and why each decision was made. Read this before your presentation.

---

## The Big Idea (Start Here)

Normally when you deploy an app, you manually write:
- A docker-compose.yml
- An nginx.conf
- A Dockerfile
- Environment variables

The problem: if you change one thing, you have to update multiple files. They get out of sync. Someone edits the wrong file.

**SwiftDeploy solves this by having ONE file — `manifest.yaml` — that describes everything. The CLI tool reads it and generates all the other files automatically.**

Think of it like this:
```
You describe WHAT you want  →  manifest.yaml
The tool figures out HOW    →  swiftdeploy CLI
The result is a running app →  docker containers
```

---

## The Files and What They Do

```
manifest.yaml          ← YOU write this. Describes the whole deployment.
swiftdeploy            ← The CLI tool. Reads manifest, does the work.
Dockerfile             ← Instructions to build the app image.
app/main.py            ← The actual web app (Flask).
templates/             ← Blueprint files. Filled in from manifest values.
  nginx.conf.j2        ← Nginx blueprint
  docker-compose.yml.j2 ← Docker Compose blueprint
nginx.conf             ← GENERATED. Never edit this by hand.
docker-compose.yml     ← GENERATED. Never edit this by hand.
```

---

## Part 1 — manifest.yaml Explained Line by Line

```yaml
services:
  app:
    image: swift-deploy-1-node:latest
    port: 3000
    mode: stable
    version: "1.0.0"
    restart: unless-stopped
    volumes:
      - app_logs:/app/logs

  nginx:
    image: nginx:latest
    port: 8080
    proxy_timeout: 30

network:
  name: swiftdeploy-net
  driver_type: bridge
```

**`services:`**
A section that lists all the containers we want to run. We have two: `app` and `nginx`.

**`app:`**
This is our Flask web application container.

**`image: swift-deploy-1-node:latest`**
The Docker image to use. `swift-deploy-1-node` is the name we gave it when we built it. `latest` means the most recent version. This image is built from our Dockerfile.

**`port: 3000`**
The port our Flask app listens on inside the container. This is internal — the outside world never connects to this directly.

**`mode: stable`**
Controls how the app behaves. Two options:
- `stable` — normal mode, no chaos
- `canary` — testing mode, adds extra headers, enables chaos endpoint

**`version: "1.0.0"`**
The app version. Gets injected into the container as an environment variable and returned in API responses.

**`restart: unless-stopped`**
If the container crashes, Docker automatically restarts it. `unless-stopped` means it restarts unless you manually stopped it.

**`volumes: - app_logs:/app/logs`**
Mounts a named volume called `app_logs` to the `/app/logs` folder inside the container. This means log files survive even if the container is deleted.

**`nginx:`**
The Nginx reverse proxy container. Sits in front of the app and handles all incoming traffic.

**`image: nginx:latest`**
Uses the official Nginx Docker image.

**`port: 8080`**
The port Nginx listens on. This IS exposed to the outside world. Users connect here.

**`proxy_timeout: 30`**
How many seconds Nginx waits for the app to respond before giving up and returning a timeout error.

**`network:`**
Defines the Docker network that connects the containers together.

**`name: swiftdeploy-net`**
The name of the network. Both containers join this network so they can talk to each other.

**`driver_type: bridge`**
The network type. `bridge` is the standard Docker network mode — containers on the same bridge network can communicate using their container names as hostnames.

---

## Part 2 — Dockerfile Explained Line by Line

```dockerfile
FROM python:3.12-alpine
```
**`FROM`** — Start from an existing base image. `python:3.12-alpine` is Python 3.12 on Alpine Linux. Alpine is a tiny Linux distro (~5MB). This keeps our image under 300MB as required.

```dockerfile
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
```
**`RUN`** — Execute a command during the build.
**`addgroup -S appgroup`** — Create a system group called `appgroup`. `-S` means system group (no login shell).
**`adduser -S appuser -G appgroup`** — Create a system user called `appuser` and add them to `appgroup`.
Why? Security. We never run apps as root inside containers.

```dockerfile
WORKDIR /app
```
**`WORKDIR`** — Set the working directory inside the container. All following commands run from `/app`.

```dockerfile
COPY app/requirements.txt .
RUN apk add --no-cache wget && pip install --no-cache-dir -r requirements.txt
```
**`COPY`** — Copy a file from your machine into the image.
**`apk add --no-cache wget`** — Install `wget` using Alpine's package manager (`apk`). `--no-cache` means don't store the package index (saves space). We need `wget` for the healthcheck command.
**`pip install --no-cache-dir -r requirements.txt`** — Install Python packages. `--no-cache-dir` saves space by not caching downloads.

Why copy requirements.txt first before the rest of the code? Docker caches each layer. If you copy requirements first and they haven't changed, Docker skips reinstalling packages on the next build. Faster builds.

```dockerfile
COPY app/ .
```
Copy the rest of the app code into `/app`.

```dockerfile
RUN mkdir -p /app/logs && chown -R appuser:appgroup /app
```
Create the logs directory and give ownership to `appuser`. Without this, the non-root user can't write logs.

```dockerfile
USER appuser
```
**`USER`** — Switch to the non-root user for all following commands and when the container runs. Security best practice.

```dockerfile
EXPOSE 3000
```
**`EXPOSE`** — Documents that the container listens on port 3000. This is informational only — it doesn't actually publish the port. Publishing is done in docker-compose.

```dockerfile
ENV MODE=stable
ENV APP_VERSION=1.0.0
ENV APP_PORT=3000
```
**`ENV`** — Set default environment variables. These can be overridden when the container starts (which docker-compose does).

```dockerfile
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:3000/healthz || exit 1
```
**`HEALTHCHECK`** — Docker will run this command every 10 seconds to check if the app is alive.
- `--interval=10s` — check every 10 seconds
- `--timeout=5s` — if no response in 5 seconds, count as failed
- `--start-period=10s` — wait 10 seconds after startup before checking (gives app time to boot)
- `--retries=3` — fail 3 times in a row before marking as unhealthy
- `wget -qO-` — make an HTTP request silently (`-q`) and print the response (`-O-`)
- `|| exit 1` — if wget fails, exit with code 1 (unhealthy)

```dockerfile
CMD ["gunicorn", "--bind", "0.0.0.0:3000", "--workers", "2", "--timeout", "60", "main:app"]
```
**`CMD`** — The command that runs when the container starts.
**`gunicorn`** — A production-grade Python web server (better than Flask's built-in server).
**`--bind 0.0.0.0:3000`** — Listen on all network interfaces on port 3000.
**`--workers 2`** — Run 2 worker processes to handle requests in parallel.
**`--timeout 60`** — Kill a worker if it takes more than 60 seconds to respond.
**`main:app`** — Load the `app` object from `main.py`.

---

## Part 3 — The Flask App (app/main.py) Explained

```python
MODE = os.getenv("MODE", "stable")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
APP_PORT = int(os.getenv("APP_PORT", "3000"))
```
**`os.getenv`** — Read environment variables. The second argument is the default if the variable isn't set. This is how the container knows which mode to run in — docker-compose injects `MODE` as an env var.

```python
_chaos = {"mode": None, "duration": 0, "rate": 0.0, "lock": threading.Lock()}
```
A dictionary that stores the current chaos state. `threading.Lock()` prevents two requests from modifying it at the same time (thread safety).

### The three endpoints:

**`GET /`** — Welcome message
```python
return jsonify({
    "message": "Welcome to SwiftDeploy API",
    "mode": MODE,
    "version": APP_VERSION,
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
})
```
Returns JSON with the current mode, version, and UTC timestamp. The grader checks that mode and version are present.

**`GET /healthz`** — Health check
```python
uptime = round(time.time() - START_TIME, 2)
return jsonify({"status": "ok", "mode": MODE, "version": APP_VERSION, "uptime_seconds": uptime})
```
`START_TIME` is set when the app starts. Subtracting it from `time.time()` gives uptime in seconds. Docker and swiftdeploy both poll this endpoint to know if the app is alive.

**`POST /chaos`** — Fault injection (canary only)
```python
if MODE != "canary":
    return jsonify({"error": "chaos endpoint only available in canary mode"}), 403
```
Returns 403 Forbidden if not in canary mode.

Three chaos modes:
- `slow` — `time.sleep(duration)` before responding. Simulates a slow database or network.
- `error` — `random.random() < rate` returns True ~50% of the time. Simulates flaky services.
- `recover` — resets everything back to normal.

### The response headers:
```python
@app.after_request
def after(response):
    if MODE == "canary":
        response.headers["X-Mode"] = "canary"
    response.headers["X-Deployed-By"] = "swiftdeploy"
    return response
```
**`@app.after_request`** — This function runs after every request, before the response is sent. It adds headers to every response. `X-Mode: canary` tells clients they're talking to the canary version. `X-Deployed-By: swiftdeploy` is added by both the app and Nginx.

---

## Part 4 — The Templates Explained

Templates use **Jinja2** syntax. `{{ variable }}` gets replaced with the actual value from manifest.yaml when `swiftdeploy init` runs.

### nginx.conf.j2

```nginx
upstream app_backend {
    server app:{{ app_port }};
}
```
**`upstream`** — Defines a group of backend servers. Here it's just one: our app container.
**`app`** — This is the container name. Docker's internal DNS resolves `app` to the app container's IP address because they're on the same network.
**`{{ app_port }}`** — Gets replaced with `3000` from the manifest.

```nginx
log_format swiftdeploy '$time_iso8601 | $status | ${request_time}s | $upstream_addr | $request';
```
Defines a custom log format named `swiftdeploy`. Each log line shows:
- `$time_iso8601` — timestamp in ISO format
- `$status` — HTTP status code (200, 404, 500, etc.)
- `${request_time}s` — how long the request took in seconds
- `$upstream_addr` — the backend server that handled it
- `$request` — the HTTP method and path

```nginx
proxy_connect_timeout {{ proxy_timeout }}s;
proxy_send_timeout    {{ proxy_timeout }}s;
proxy_read_timeout    {{ proxy_timeout }}s;
```
All three timeout values come from `nginx.proxy_timeout` in the manifest (30 seconds). If the app doesn't respond in time, Nginx returns a 504 error.

```nginx
add_header X-Deployed-By swiftdeploy always;
```
Adds the `X-Deployed-By` header to every response. `always` means add it even on error responses.

```nginx
proxy_pass_header X-Mode;
```
Forwards the `X-Mode` header from the app's response to the client. Without this, Nginx would strip custom headers.

```nginx
error_page 502 = @error502;
location @error502 {
    default_type application/json;
    return 502 '{"error":"Bad Gateway","code":502,"service":"app","contact":"ops@swiftdeploy.io"}';
}
```
When Nginx gets a 502 (app is down), instead of showing the default Nginx error page, it returns a JSON response. Same for 503 and 504.

### docker-compose.yml.j2

```yaml
expose:
  - "{{ app_port }}"
```
**`expose`** — Makes the port available to other containers on the same network, but NOT to the host machine. This is how we keep the app port internal.

```yaml
cap_drop:
  - ALL
cap_add:
  - NET_BIND_SERVICE
```
**`cap_drop: ALL`** — Remove all Linux capabilities from the container. Capabilities are special permissions (like being able to bind to ports below 1024, or change file ownership).
**`cap_add: NET_BIND_SERVICE`** — Add back only the capability to bind to network ports. The app needs this to listen on port 3000.

```yaml
security_opt:
  - no-new-privileges:true
```
Prevents the process inside the container from gaining more privileges than it started with. Even if someone exploits the app, they can't escalate to root.

```yaml
depends_on:
  app:
    condition: service_healthy
```
Nginx won't start until the app container passes its healthcheck. `service_healthy` means Docker waits for the healthcheck to return success, not just for the container to start.

---

## Part 5 — The CLI (swiftdeploy) Explained

### How init works

```python
with open(NGINX_TEMPLATE) as f:
    tmpl = Template(f.read())
nginx_out = tmpl.render(**ctx)
with open(NGINX_CONF, "w") as f:
    f.write(nginx_out)
```
1. Read the template file
2. Create a Jinja2 Template object
3. Call `.render(**ctx)` — replace all `{{ variable }}` placeholders with real values from the manifest
4. Write the result to `nginx.conf`

`**ctx` unpacks the dictionary so each key becomes a named argument. `ctx["app_port"]` becomes available as `{{ app_port }}` in the template.

### How validate works

**Check 3 — image exists:**
```python
result = subprocess.run(["docker", "image", "inspect", image], capture_output=True, text=True)
```
Runs `docker image inspect` and checks the return code. If the image doesn't exist, Docker returns a non-zero exit code.

**Check 4 — port not in use:**
```python
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
result_bind = sock.connect_ex(("127.0.0.1", int(ctx["nginx_port"])))
```
Tries to connect to the port. If it succeeds (returns 0), something is already listening there. Then checks if it's our own nginx container — if so, that's fine.

**Check 5 — nginx syntax:**
The tricky part: running `nginx -t` in a standalone container fails because it can't resolve the `app` hostname (no Docker network). The fix: temporarily replace `server app:3000` with `server 127.0.0.1:65535` just for the syntax check, then delete the temp file.

### How promote works

```python
cfg["services"]["app"]["mode"] = target_mode
with open(MANIFEST, "w") as f:
    yaml.dump(cfg, f, default_flow_style=False)
```
Loads the manifest as a Python dictionary, changes the mode value, and writes it back. `yaml.dump` converts the dictionary back to YAML format.

```python
result = subprocess.run(
    ["docker", "compose", "-f", COMPOSE_FILE, "up", "-d", "--no-deps", "app"],
)
```
**`--no-deps`** — Only restart the `app` service, not its dependencies (Nginx). This is a rolling restart — Nginx keeps running and serving traffic while the app restarts.

---

## Part 6 — The Full Flow, Step by Step

Here is exactly what happens when you run `./swiftdeploy deploy` from scratch:

**Step 1:** `swiftdeploy deploy` calls `cmd_init()` first

**Step 2:** `cmd_init()` reads `manifest.yaml` and extracts all values into a dictionary called `ctx`

**Step 3:** It renders `templates/nginx.conf.j2` with those values → writes `nginx.conf`

**Step 4:** It renders `templates/docker-compose.yml.j2` → writes `docker-compose.yml`

**Step 5:** `docker compose up -d --build` is called
- Docker reads `docker-compose.yml`
- Starts `swiftdeploy-app` container first
- Injects `MODE=stable`, `APP_VERSION=1.0.0`, `APP_PORT=3000` as environment variables
- Gunicorn starts, Flask app loads, begins listening on port 3000
- Docker runs the healthcheck: `wget -qO- http://localhost:3000/healthz`
- After 3 successful checks, container is marked **Healthy**

**Step 6:** Docker starts `swiftdeploy-nginx` (only after app is Healthy)
- Nginx reads the mounted `nginx.conf`
- Begins listening on port 8080
- All requests to port 8080 are proxied to `app:3000`

**Step 7:** `swiftdeploy` polls `http://localhost:8080/healthz` every 3 seconds
- When it gets a 200 response, prints "DEPLOY COMPLETE"

---

## Part 7 — Key Terms Glossary

| Term | What it means |
|---|---|
| **Declarative** | You describe the desired end state, not the steps to get there. The tool figures out the steps. |
| **Manifest** | A file that declares what you want. Like a shopping list for your infrastructure. |
| **Jinja2** | A Python templating engine. Lets you put `{{ variables }}` in text files that get filled in later. |
| **Reverse proxy** | A server (Nginx) that sits in front of your app and forwards requests to it. Clients talk to Nginx, not the app directly. |
| **Healthcheck** | A periodic test to verify a service is alive and working. |
| **Canary deployment** | Running a new version alongside the old one to test it with real traffic before full rollout. |
| **Chaos engineering** | Deliberately injecting failures to test how a system handles them. |
| **Alpine Linux** | A minimal Linux distribution (~5MB). Used as a base image to keep Docker images small. |
| **Gunicorn** | A production Python web server. More stable and performant than Flask's built-in server. |
| **Named volume** | A Docker-managed storage area that persists data even when containers are deleted. |
| **Bridge network** | A Docker network type that lets containers on the same host communicate using container names as hostnames. |
| **Linux capabilities** | Fine-grained permissions in Linux. Instead of full root access, you can grant only specific abilities. |
| **Non-root user** | Running a process as a regular user instead of root. Limits damage if the app is compromised. |
| **Environment variable** | A key-value pair injected into a process at runtime. Used to configure apps without hardcoding values. |
| **`expose` vs `ports`** | `expose` makes a port available to other containers only. `ports` publishes it to the host machine. |
| **Rolling restart** | Restarting one container while others keep running. Zero downtime. |
| **`upstream`** | In Nginx, a named group of backend servers to proxy requests to. |
| **`proxy_pass`** | Nginx directive that forwards the request to the upstream backend. |
| **Exit code** | A number a program returns when it finishes. 0 = success, anything else = failure. |

---

## Part 8 — What the Grader Will Test

1. **Delete `nginx.conf` and `docker-compose.yml`, run `./swiftdeploy init`** — both files must regenerate correctly from the manifest.

2. **Run `./swiftdeploy validate`** — all 5 checks must pass.

3. **Run `./swiftdeploy deploy`** — stack must come up and health check must pass within 60 seconds.

4. **Run `./swiftdeploy promote canary`** — mode must switch, `/healthz` must return `"mode": "canary"`.

5. **Run `./swiftdeploy promote stable`** — mode must switch back, `/healthz` must return `"mode": "stable"`.

6. **Check response headers** — `X-Deployed-By: swiftdeploy` must be present. `X-Mode: canary` must appear in canary mode.

7. **Check Nginx access logs** — must be in the required format.

8. **Check image size** — must be under 300MB.

9. **Check app port is not exposed** — `docker ps` should show only port 8080, not 3000.

---

## Part 9 — Screenshots You Need

Take these in order on the server:

```bash
# Screenshot 1 — validate
./swiftdeploy validate

# Screenshot 2 — deploy (teardown first for a clean run)
./swiftdeploy teardown --clean
docker rmi swift-deploy-1-node:latest
docker build -t swift-deploy-1-node:latest .
./swiftdeploy deploy

# Screenshot 3 — promote and healthz confirmation
./swiftdeploy promote canary
curl http://localhost:8080/healthz
./swiftdeploy promote stable
curl http://localhost:8080/healthz

# Screenshot 4 — generated file contents
cat nginx.conf
cat docker-compose.yml

# Screenshot 5 — nginx access logs
docker logs swiftdeploy-nginx
```
