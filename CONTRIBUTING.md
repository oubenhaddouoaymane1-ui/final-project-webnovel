# Contributing to CineOS

Thank you for your interest in contributing to CineOS. This guide covers everything you need to get started, from local setup through merging your first pull request.

---

## Development Setup

### Prerequisites

- Python 3.11 or higher
- Docker and Docker Compose
- PostgreSQL 15+
- Redis 7+
- Node.js 18+ (for frontend tooling)

### Getting Started

1. Fork the repository and clone your fork:

   ```bash
   git clone https://github.com/<your-username>/cineos.git
   cd cineos
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install -e ".[dev]"
   ```

4. Install pre-commit hooks:

   ```bash
   pre-commit install
   ```

5. Copy the environment template and fill in local values:

   ```bash
   cp .env.example .env
   ```

6. Start the development services:

   ```bash
   docker compose up -d
   ```

7. Run database migrations:

   ```bash
   cineos migrate
   ```

8. Verify everything works:

   ```bash
   cineos health-check
   ```

---

## Project Structure

```
cineos/
├── src/                  # Core application code
│   ├── api/              # FastAPI endpoints and middleware
│   ├── core/             # Business logic and domain models
│   ├── database/         # Migrations, models, and repositories
│   ├── security/         # Authentication and authorization
│   └── services/         # External service integrations
├── workers/              # Background task processors
├── workflows/            # JSON workflow definitions
├── tests/                # Test suite
│   ├── unit/             # Fast, isolated tests
│   └── integration/      # Tests requiring external services
├── docs/                 # Documentation
├── scripts/              # Development and CI scripts
└── docker/               # Dockerfiles and compose configs
```

---

## Code Style

### Linting and Formatting

CineOS uses Ruff for linting and formatting. Configuration lives in `pyproject.toml`.

Run the linter:

```bash
ruff check .
```

Auto-fix issues:

```bash
ruff check --fix .
```

Format code:

```bash
ruff format .
```

### Type Checking

We enforce strict type checking with mypy. Run it with:

```bash
mypy src/ workers/
```

All new code must include complete type annotations. Untyped definitions are not allowed outside of test files.

### Naming Conventions

Follow the naming standards documented in `docs/naming-standards.md`. Key rules:

- **Python files**: `snake_case.py`
- **Classes**: `PascalCase`
- **Functions and variables**: `snake_case`
- **Constants**: `UPPER_SNAKE_CASE`
- **Database tables**: `snake_case` with `cineos_schema` prefix
- **API endpoints**: `/api/resource` with plural nouns
- **Git branches**: `type/description` (e.g., `feature/add-shot-tracker`)

### Pre-Commit Hooks

Pre-commit hooks run automatically on every commit. They include:

- Ruff linting and formatting
- mypy type checking
- Trailing whitespace and end-of-file fixes
- YAML and JSON validation
- Large file detection (500 KB limit)
- Merge conflict marker detection
- Private key detection

To run all hooks manually:

```bash
pre-commit run --all-files
```

---

## Testing

### Running Tests

Run the full test suite:

```bash
pytest
```

Run only unit tests:

```bash
pytest -m unit
```

Run only integration tests:

```bash
pytest -m integration
```

Run with coverage:

```bash
pytest --cov=src --cov=workers --cov-report=term-missing
```

Coverage must stay at or above 70%. The build will fail if coverage drops below this threshold.

### Writing Tests

- Place unit tests in `tests/unit/` and integration tests in `tests/integration/`.
- Name test files `test_<module>.py`.
- Name test functions `test_<behavior>()`.
- Use descriptive test names that explain what is being verified.
- Mock external services in unit tests. Use real services only in integration tests.
- Mark slow tests with `@pytest.mark.slow`.

Example:

```python
import pytest

from cineos.core.scene import SceneRenderer


@pytest.mark.unit
class TestSceneRenderer:
    def test_render_returns_completed_status(self):
        renderer = SceneRenderer(config=mock_config)
        result = renderer.render(scene=sample_scene)
        assert result.status == "completed"

    @pytest.mark.slow
    def test_render_handles_large_scene(self):
        renderer = SceneRenderer(config=mock_config)
        result = renderer.render(scene=large_scene)
        assert result.duration > 0
```

---

## Pull Request Process

### Before Submitting

1. Create a feature branch from `main`:

   ```bash
   git checkout -b feature/your-description
   ```

2. Make your changes following the code style guidelines above.

3. Write or update tests for any new or changed functionality.

4. Run the full check suite:

   ```bash
   pre-commit run --all-files
   pytest
   mypy src/ workers/
   ```

5. Commit with a clear, imperative-mood message under 72 characters.

### Submitting the PR

1. Push your branch and open a pull request against `main`.

2. Fill out the pull request template completely.

3. Link the related issue(s).

4. Request a review from the appropriate team based on CODEOWNERS:
   - Database changes: @dba-team
   - Security changes: @security-team
   - Workflow changes: @platform-team
   - All other changes: @cineos-team

### Review Criteria

Reviewers will evaluate:

- **Correctness**: Does the code do what it claims?
- **Tests**: Are there adequate tests covering the changes?
- **Style**: Does the code follow naming and formatting standards?
- **Types**: Are all functions and variables properly annotated?
- **Performance**: Are there any obvious performance concerns?
- **Security**: Does the change introduce any security risks?
- **Documentation**: Are relevant docs updated?

### After Approval

- Squash and merge is the default merge strategy.
- The branch will be deleted automatically after merging.
- Ensure CI passes before merging.

---

## Commit Conventions

- Use imperative mood: "Add feature" not "Added feature".
- Keep the subject line under 72 characters.
- Separate subject from body with a blank line if more detail is needed.
- Reference issues: `Fixes #123` or `Relates to #456`.

Examples:

```
Add character arc tracking to scene pipeline

Implements automatic tracking of character emotional arcs
across scene boundaries. Uses the novel parser to extract
character state transitions and maps them to visual cues.

Fixes #234
```

```
Fix timeout in scene renderer under high load

Increases default timeout from 30s to 120s and adds
retry logic with exponential backoff.
```

---

## Architecture Overview

CineOS is a novel-to-cinematic production platform. The high-level architecture:

1. **Ingestion Layer** (`src/services/ingestion/`): Parses novel source material, extracts scenes, characters, and plot structure.

2. **Planning Engine** (`src/core/planning/`): Decomposes parsed narratives into production-ready shot lists and scene breakdowns.

3. **Rendering Pipeline** (`workers/`): Background workers that handle scene rendering, visual composition, and output generation.

4. **Workflow Orchestrator** (`src/core/workflows/`): Executes JSON-defined workflows that coordinate the ingestion, planning, and rendering stages.

5. **API Layer** (`src/api/`): FastAPI application exposing REST endpoints for project management, scene control, and status monitoring.

6. **Data Layer** (`src/database/`): PostgreSQL-backed storage using the `cineos_schema` namespace with SQLAlchemy models and Alembic migrations.

7. **Security Layer** (`src/security/`): Authentication, authorization, and API key management.

---

## Getting Help

- Open a discussion in GitHub Discussions for questions.
- File an issue for bugs or feature requests.
- Reach out to @cineos-team for general guidance.
