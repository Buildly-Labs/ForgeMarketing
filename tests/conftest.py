from pathlib import Path


def pytest_ignore_collect(collection_path, config):
    """Limit automated collection to the curated reliability suite.

    The repository's `tests/` tree includes many standalone/manual scripts that
    are not pytest-safe (some call `sys.exit()` at import time). We gate deploys
    on the deterministic `tests/quality` suite.
    """
    path = Path(str(collection_path))
    norm = str(path).replace('\\', '/')

    if '/tests/quality' in norm:
        return False

    # Keep the tests root discoverable so pytest can descend into tests/quality.
    if norm.endswith('/tests') or norm.endswith('/tests/'):
        return False

    # Ignore any other test artifacts under tests/.
    if '/tests/' in norm:
        return True

    return False
