# Docker Fundamentals

A beginner's guide to Docker — what containers are, why they exist, and the
commands you'll actually use.

## The problem Docker solves

"It works on my machine" is the classic software problem: an app runs fine
for one developer but breaks for another, or breaks in production, because
of differences in OS version, installed libraries, environment variables,
or dependency versions.

Docker solves this by packaging an application **together with everything
it needs to run** — code, runtime, system libraries, configuration — into a
single unit called a **container**. That container runs identically on your
laptop, a teammate's laptop, and a production server, because it's not
relying on whatever happens to already be installed there.

## Containers vs. virtual machines

A common point of confusion — containers are *not* the same as virtual
machines, and they're much lighter weight:

| | Virtual Machine | Container |
|---|---|---|
| What it includes | Full OS (kernel + everything) | Just the app + its dependencies |
| Startup time | Minutes | Seconds (often less) |
| Size | GBs | Often tens/hundreds of MBs |
| Isolation | Very strong (separate kernel) | Process-level (shares host kernel) |
| Resource overhead | High | Low |

A VM simulates an entire computer. A container is just an isolated process
running on your existing OS, with its own filesystem, network, and process
space — but sharing the host machine's kernel underneath. That's why
containers start almost instantly and use a fraction of the resources.

## Two core concepts: images and containers

This is the most important distinction in Docker:

- **Image** — a read-only *template*. It's the packaged blueprint: your
  code + dependencies + configuration, frozen into a file. Think of it like
  a class in programming, or a recipe.
- **Container** — a *running instance* of an image. Think of it like an
  object (an instance of that class), or the actual dish you cooked from
  the recipe.

You build one image, and can run many containers from it simultaneously —
each an independent, isolated instance.

```
Dockerfile  →  docker build  →  Image  →  docker run  →  Container(s)
(instructions)                 (template)                (running process)
```

## The Dockerfile

A `Dockerfile` is a text file with step-by-step instructions for building an
image. A minimal example for a Python app:

```dockerfile
FROM python:3.13-slim          # start from a base image with Python installed

WORKDIR /app                   # set the working directory inside the container

COPY requirements.txt .        # copy just this file first
RUN pip install -r requirements.txt   # install dependencies (cached if requirements.txt unchanged)

COPY . .                       # copy the rest of the application code

CMD ["python", "main.py"]      # the command that runs when the container starts
```

Key instructions:

| Instruction | What it does |
|---|---|
| `FROM` | The base image to start from (e.g. an OS + language runtime already set up) |
| `WORKDIR` | Sets the working directory for subsequent instructions |
| `COPY` | Copies files from your machine into the image |
| `RUN` | Executes a command *while building* the image (e.g. installing packages) |
| `ENV` | Sets an environment variable inside the container |
| `EXPOSE` | Documents which port the app listens on (doesn't actually publish it) |
| `CMD` | The default command to run when a container starts from this image |

**Why `COPY requirements.txt` before `COPY . .`?** Docker caches each layer.
If only your application code changes (not dependencies), Docker can reuse
the cached "install dependencies" layer instead of reinstalling everything
— much faster rebuilds.

## Building and running

```bash
# Build an image from a Dockerfile in the current directory, tag it "myapp"
docker build -t myapp .

# Run a container from that image
docker run myapp

# Run in the background (detached), map host port 8000 to container port 8000
docker run -d -p 8000:8000 myapp

# Run interactively with a shell, for debugging
docker run -it myapp /bin/bash
```

### Port mapping: `-p host:container`

A container's ports are isolated by default — nothing outside can reach
them. `-p 8000:8000` means "forward requests to port 8000 on my machine to
port 8000 inside the container." The two numbers don't have to match:
`-p 3000:8000` would expose the container's port 8000 as port 3000 on your
machine.

## Managing containers and images

```bash
docker ps                  # list running containers
docker ps -a                # list ALL containers, including stopped ones
docker images                # list downloaded/built images

docker stop <container_id>   # gracefully stop a running container
docker rm <container_id>     # remove a stopped container
docker rmi <image_id>        # remove an image

docker logs <container_id>          # view a container's output
docker logs -f <container_id>       # follow logs live (like tail -f)

docker exec -it <container_id> /bin/bash   # open a shell inside a running container
```

`docker ps` only shows *running* containers — a very common beginner
confusion is running `docker ps` after a container crashed and seeing
nothing. Use `docker ps -a` to see stopped/crashed ones too, then
`docker logs` to see why it crashed.

## Volumes: persisting data

Containers are **ephemeral** by default — when you remove a container, any
data it wrote (e.g. a database's files) is gone with it. Volumes solve this
by mapping a directory inside the container to a location that survives
independently of the container's lifecycle.

```bash
# named volume, managed by Docker
docker run -v mydata:/app/data myapp

# bind mount — maps to a specific folder on your machine
docker run -v /Users/me/localfolder:/app/data myapp
```

Use a named volume for things like database storage (Docker manages where
it physically lives). Use a bind mount when you want to edit files on your
own machine and have the container see the changes immediately — handy
during development.

## Networking basics

By default, Docker containers can't reach each other unless they're on the
same network. When you use Docker Compose (below), it automatically creates
a shared network for all the services in your project, and containers can
reach each other **by service name** — e.g. an `api` container can connect
to `redis://redis:6379`, where `redis` resolves via Docker's internal DNS to
the `redis` container's IP, no manual configuration needed.

## Docker Compose: running multiple containers together

Most real applications aren't a single container — you typically have an
API, a database, a cache, maybe a frontend, all running together. Writing
out a `docker run` command for each, by hand, every time, doesn't scale.

**Docker Compose** lets you describe your entire multi-container application
in one YAML file, and bring it all up (or down) with a single command.

A minimal example:

```yaml
# docker-compose.yml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

```bash
docker compose up          # build (if needed) and start everything
docker compose up -d       # same, but detached (background)
docker compose down        # stop and remove everything
docker compose logs -f     # follow logs from all services
docker compose ps          # list running services in this project
```

Compose handles building images from `Dockerfile`s referenced by `build:`,
pulling pre-built images referenced by `image:`, creating the shared
network, and starting services in dependency order (via `depends_on`).

Note: there are two Compose command styles you'll see — the newer
`docker compose` (a plugin, space-separated) and the older standalone
`docker-compose` (hyphenated) binary. They do the same thing; which one is
available depends on how Docker was installed on that particular machine.

## Quick reference

```bash
docker build -t <name> .              # build an image from a Dockerfile
docker run <image>                    # run a container
docker run -d -p 8000:8000 <image>    # run detached, with port mapping
docker ps / docker ps -a              # list running / all containers
docker logs <container>               # view output
docker exec -it <container> bash      # shell into a running container
docker stop / rm <container>          # stop / remove a container
docker images / docker rmi <image>    # list / remove images

docker compose up -d                  # start a multi-container app
docker compose down                   # stop and remove it
docker compose logs -f                # follow logs from all services
```

## What's next

Once containers make sense, the natural next step is how they get built and
shipped automatically whenever code changes — that's what a CI/CD pipeline
does, covered in
[ci-cd/ci-cd-pipeline-explained.md](../ci-cd/ci-cd-pipeline-explained.md)
once it exists.
