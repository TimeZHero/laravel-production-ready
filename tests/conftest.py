"""
Test fixtures for Laravel Docker image integration tests.

Scaffolds a Laravel app, builds Docker images for all ENGINE x TARGET
combinations, and provides container fixtures for test modules.
"""

import os
import shutil
import subprocess
import tempfile
import time

import docker
import pytest
import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENGINES = ["fpm", "roadrunner", "swoole"]
TARGETS = ["production", "development"]
COMBOS = [(e, t) for e in ENGINES for t in TARGETS]

IMAGE_PREFIX = "laravel-test"
PROJECT_DIR = os.path.join(os.path.dirname(__file__), "..")

CONTAINER_STARTUP_TIMEOUT = 120  # seconds
HEALTHCHECK_POLL_INTERVAL = 3   # seconds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def image_tag(engine: str, target: str) -> str:
    return f"{IMAGE_PREFIX}:{engine}-{target}"


def _docker_client() -> docker.DockerClient:
    return docker.from_env(timeout=300)


def _composer(workdir: str, command: str):
    """Run a composer command in a throwaway container with workdir bind-mounted."""
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{workdir}:/app",
        "-w", "/app",
        "composer:latest",
        "sh", "-c", command,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(
            f"composer command failed:\n{result.stdout}\n{result.stderr}"
        )


def _docker_build(path: str, tag: str, target: str, engine: str):
    """Build a Docker image using the CLI (BuildKit-compatible)."""
    cmd = [
        "docker", "build",
        "--tag", tag,
        "--target", target,
        "--build-arg", f"ENGINE={engine}",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"docker build failed for {tag}:\n{result.stdout}\n{result.stderr}"
        )


def _wait_for_container(container, timeout: int = CONTAINER_STARTUP_TIMEOUT):
    """Wait for a container to become healthy or raise on timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        container.reload()
        health = container.attrs.get("State", {}).get("Health", {})
        status = health.get("Status", "")
        if status == "healthy":
            return
        if container.status in ("exited", "dead"):
            logs = container.logs(tail=50).decode(errors="replace")
            raise RuntimeError(
                f"Container {container.short_id} died. Status: {container.status}\n"
                f"Logs:\n{logs}"
            )
        time.sleep(HEALTHCHECK_POLL_INTERVAL)

    logs = container.logs(tail=80).decode(errors="replace")
    raise TimeoutError(
        f"Container {container.short_id} did not become healthy within {timeout}s.\n"
        f"Logs:\n{logs}"
    )


def _exec_in_container(container, cmd: str, user: str = "root") -> str:
    """Execute a command in a running container and return stdout."""
    exit_code, output = container.exec_run(cmd, user=user)
    return output.decode(errors="replace")


# ---------------------------------------------------------------------------
# Session fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def docker_client():
    client = _docker_client()
    yield client
    client.close()


@pytest.fixture(scope="session")
def laravel_app():
    """
    Scaffold a fresh Laravel app in a temp directory and prepare it for
    all engine types. Returns the path to the build context.
    """
    tmpdir = tempfile.mkdtemp(prefix="laravel-test-")

    try:
        print(f"\n==> Scaffolding Laravel app in {tmpdir}")

        # 1. Create Laravel project
        _composer(tmpdir, "composer create-project --no-interaction --prefer-dist laravel/laravel .")

        # 2. Copy our Docker configs into the Laravel app
        for item in ("Dockerfile", "confs", "scripts"):
            src = os.path.join(PROJECT_DIR, item)
            dst = os.path.join(tmpdir, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)

        # Copy .dockerignore
        dockerignore_src = os.path.join(PROJECT_DIR, "editor", ".dockerignore")
        if os.path.exists(dockerignore_src):
            shutil.copy2(dockerignore_src, os.path.join(tmpdir, ".dockerignore"))

        # 3. Install octane + RoadRunner packages
        _composer(
            tmpdir,
            "composer require -W --ignore-platform-reqs "
            "laravel/octane spiral/roadrunner-cli spiral/roadrunner-http "
            "--no-interaction",
        )

        # 4. Create .env (array driver = in-memory, no DB extension needed)
        with open(os.path.join(tmpdir, ".env"), "w") as f:
            f.write(
                "APP_NAME=LaravelTest\n"
                "APP_ENV=testing\n"
                "APP_KEY=base64:dGVzdGtleWZvcnRlc3RpbmcxMjM0NTY3ODkwYWJjZGU=\n"
                "APP_DEBUG=true\n"
                "DB_CONNECTION=null\n"
                "LOG_CHANNEL=stderr\n"
                "SESSION_DRIVER=file\n"
                "CACHE_STORE=array\n"
                "QUEUE_CONNECTION=sync\n"
            )

        # 5. Create packages directory (Dockerfile COPY expects it)
        os.makedirs(os.path.join(tmpdir, "packages"), exist_ok=True)

        # 7. Install npm dependencies (chokidar needed for octane --watch in dev)
        subprocess.run(
            ["npm", "install"], cwd=tmpdir,
            capture_output=True, text=True, timeout=120,
        )
        subprocess.run(
            ["npm", "install", "--save-dev", "chokidar"], cwd=tmpdir,
            capture_output=True, text=True, timeout=60,
        )

        # 8. Patch start-container.sh: skip migrations (no real DB in tests)
        #    and skip filament:optimize (not installed)
        script = os.path.join(tmpdir, "scripts", "start-container.sh")
        with open(script, "r") as f:
            content = f.read()
        content = content.replace(
            "php artisan migrate --force --isolated",
            "php artisan migrate --force --isolated 2>/dev/null || true",
        )
        content = content.replace(
            "php artisan filament:optimize",
            "php artisan filament:optimize 2>/dev/null || true",
        )
        with open(script, "w") as f:
            f.write(content)

        yield tmpdir
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="session")
def docker_images(docker_client, laravel_app):
    """Build all 8 Docker images (ENGINE x TARGET)."""
    built_tags = []

    for engine in ENGINES:
        for target in TARGETS:
            tag = image_tag(engine, target)
            print(f"\n==> Building {tag}")
            try:
                _docker_build(laravel_app, tag, target, engine)
                built_tags.append(tag)
                print(f"    OK: {tag}")
            except RuntimeError as e:
                pytest.fail(str(e))

    yield built_tags

    for tag in built_tags:
        try:
            docker_client.images.remove(tag, force=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Container management
# ---------------------------------------------------------------------------

class ContainerInfo:
    """Holds a running container and metadata for tests."""

    def __init__(self, container, engine: str, target: str, base_url: str):
        self.container = container
        self.engine = engine
        self.target = target
        self.base_url = base_url

    @property
    def is_octane(self) -> bool:
        return self.engine in ("roadrunner", "swoole", "openswoole")

    @property
    def is_fpm(self) -> bool:
        return self.engine == "fpm"

    @property
    def is_production(self) -> bool:
        return self.target == "production"

    @property
    def is_development(self) -> bool:
        return self.target == "development"

    def exec(self, cmd: str, user: str = "root") -> str:
        return _exec_in_container(self.container, cmd, user=user)

    def exec_as_app_user(self, cmd: str) -> str:
        return _exec_in_container(self.container, cmd, user="")

    def get(self, path: str, **kwargs) -> requests.Response:
        return requests.get(f"{self.base_url}{path}", timeout=10, **kwargs)

    @property
    def combo_id(self) -> str:
        return f"{self.engine}-{self.target}"


@pytest.fixture(scope="session")
def all_containers(docker_client, docker_images, laravel_app):
    """Start all containers and keep them running for the session."""
    # Clean up any stale containers from a previous run
    for engine, target in COMBOS:
        name = f"laravel-test-{engine}-{target}"
        try:
            old = docker_client.containers.get(name)
            old.remove(force=True)
        except docker.errors.NotFound:
            pass

    containers = {}

    runtime_env = {
        "APP_NAME": "LaravelTest",
        "APP_ENV": "testing",
        "APP_KEY": "base64:dGVzdGtleWZvcnRlc3RpbmcxMjM0NTY3ODkwYWJjZGU=",
        "APP_DEBUG": "true",
        "DB_CONNECTION": "null",
        "LOG_CHANNEL": "stderr",
        "SESSION_DRIVER": "file",
        "CACHE_STORE": "array",
        "QUEUE_CONNECTION": "sync",
    }

    for engine, target in COMBOS:
        tag = image_tag(engine, target)
        combo = f"{engine}-{target}"
        print(f"\n==> Starting container for {combo}")

        run_kwargs = dict(
            image=tag,
            detach=True,
            ports={"8080/tcp": None},
            environment=runtime_env,
            name=f"laravel-test-{combo}",
            remove=False,
        )

        # Development images don't contain source code -- bind-mount the
        # scaffolded Laravel app so that start-container.sh can find artisan.
        if target == "development":
            run_kwargs["volumes"] = {
                laravel_app: {"bind": "/app", "mode": "rw"},
            }
            # Development expects APP_ENV=local so start-container.sh
            # runs composer install / npm install if needed.
            # HOME=/tmp ensures npm cache is writable by the non-root user.
            run_kwargs["environment"] = {
                **runtime_env,
                "APP_ENV": "local",
                "HOME": "/tmp",
            }

        container = docker_client.containers.run(**run_kwargs)

        try:
            _wait_for_container(container)
            container.reload()
            host_port = container.attrs["NetworkSettings"]["Ports"]["8080/tcp"][0]["HostPort"]
            base_url = f"http://127.0.0.1:{host_port}"
            info = ContainerInfo(container, engine, target, base_url)
            containers[combo] = info
            print(f"    OK: {combo} at {base_url}")
        except (TimeoutError, RuntimeError) as e:
            print(f"    WARN: {combo} failed to start: {e}")
            try:
                container.reload()
                host_port = container.attrs["NetworkSettings"]["Ports"]["8080/tcp"][0]["HostPort"]
                base_url = f"http://127.0.0.1:{host_port}"
            except Exception:
                base_url = "http://127.0.0.1:0"
            containers[combo] = ContainerInfo(container, engine, target, base_url)

    yield containers

    for info in containers.values():
        try:
            info.container.stop(timeout=5)
            info.container.remove(force=True)
        except Exception:
            pass


@pytest.fixture(params=COMBOS, ids=[f"{e}-{t}" for e, t in COMBOS])
def container(request, all_containers) -> ContainerInfo:
    engine, target = request.param
    return all_containers[f"{engine}-{target}"]


@pytest.fixture(params=ENGINES, ids=ENGINES)
def production_container(request, all_containers) -> ContainerInfo:
    return all_containers[f"{request.param}-production"]


@pytest.fixture(params=ENGINES, ids=ENGINES)
def development_container(request, all_containers) -> ContainerInfo:
    return all_containers[f"{request.param}-development"]
