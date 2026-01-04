import pytest
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Add to Python path properly
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Configure pytest-asyncio
pytest_plugins = ["pytest_asyncio"]

def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers", "unit: Unit tests"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests"
    )
    config.addinivalue_line(
        "markers", "api: API tests"
    )
    config.addinivalue_line(
        "markers", "e2e: End-to-end tests"
    )
    config.addinivalue_line(
        "markers", "edge_case: Edge case tests"
    )
    config.addinivalue_line(
        "markers", "negative: Negative tests"
    )

@pytest.fixture(autouse=True)
def reset_db_connection():
    """Reset database connection before each test to avoid loop issues."""
    import db
    # Force reset connection
    db.conn = None
    yield
    # Force reset connection after test
    db.conn = None