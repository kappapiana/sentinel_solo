# Sentinel Solo Test Optimization Plan

## Current State Analysis

### Test Suite Overview
| File | Size | Test Classes | Focus Area |
|------|------|--------------|------------|
| [`tests/test_database_manager.py`](tests/test_database_manager.py:1) | ~41K chars | 10 classes | Comprehensive DB layer tests |
| [`tests/test_regression.py`](tests/test_regression.py:1) | ~6.6K chars | 3 classes | High-level regression tests |
| [`tests/test_date_picker.py`](tests/test_date_picker.py:1) | ~1.5K chars | N/A | Date/time conversion tests |
| [`tests/conftest.py`](tests/conftest.py:1) | ~1.9K chars | 6 fixtures | Test setup and user creation |

### Current Test Structure

#### Test Classes in `test_database_manager.py`
1. **TestHierarchicalMatterCreation** - Tree structure creation tests
2. **TestGetFullPath** - Path generation accuracy tests
3. **TestSuggestUniqueCode** - Unique code generation tests
4. **TestOwnerFiltering** - RLS-style owner filtering tests (8 sub-tests)
5. **TestReportingAggregation** - Time aggregation tests
6. **TestHourlyRates** - Rate resolution precedence tests
7. **TestContinueTimeEntry** - Activity grouping tests
8. **TestDeleteTimeEntry** - Deletion operation tests
9. **TestMatterBudget** - Budget tracking tests (7 sub-tests)
10. **TestBackupRestore** - Export/import round-trip tests
11. **TestRequireUser** - User context guard tests
12. **TestMatterSharing** - Cross-user sharing tests
13. **TestUserMatterRate** - Per-user rate override tests
14. **TestSameNameConflict** - Same-name conflict resolution tests

#### Test Classes in `test_regression.py`
1. **TestUserAndMatterCreation** - User/matter creation flows
2. **TestGetFullPathRecursion** - Multi-level path recursion tests
3. **TestPrivacyRlsCheck** - Privacy/RLS verification tests

### Current Fixture Structure (`conftest.py`)
- `db_path` - Temporary SQLite database path
- `db_no_user` - Database manager with no current_user_id
- `db_with_two_users` - Creates admin + normal user (returns tuple)
- `db_user1` - Admin user scoped DatabaseManager
- `db_user2` - Normal user scoped DatabaseManager

---

## Optimization Opportunities

### 1. Test Parallelization (High Impact)

**Current State**: Tests run sequentially, each creating fresh database instances.

**Optimization Strategy**:
- Add `pytest-xdist` for parallel execution across CPU cores
- Ensure test isolation through unique tmp_path per test
- Use `--dist=loadscope` or `--dist=loadfile` for optimal load balancing

**Implementation**:
```ini
# pytest.ini
[pytest]
addopts = -n auto --cov=database_manager --cov=main --cov-report=html --cov-report=term-missing
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

**Expected Improvement**: 3-5x faster execution on multi-core systems

---

### 2. Fixture Optimization (Medium Impact)

**Current State**: Each test creates fresh database and users via fixtures.

**Optimization Strategy**:
- Implement `scope="session"` for fixtures that don't need isolation
- Use autouse fixtures for common setup patterns
- Cache expensive operations where safe

**Proposed Fixture Hierarchy**:
```python
# Optimized conftest.py structure

# Session-scoped: Database template (created once)
@pytest.fixture(scope="session")
def db_template_path(tmp_path_factory):
    """Create a base database with schema and first admin."""
    path = tmp_path_factory.mktemp("db_templates") / "base.db"
    dm = DatabaseManager(db_path=path)
    dm.init_db()
    pw_hash = bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode("utf-8")
    user1_id = dm.create_first_admin("admin", pw_hash)
    return path, user1_id

# Session-scoped: Second user creation (once per session)
@pytest.fixture(scope="session", autouse=False)
def second_user_template(db_template_path):
    """Create second user on template database."""
    base_path, admin_id = db_template_path
    # Copy template and create user2
    ...

# Per-test: Fresh isolated database
@pytest.fixture
def db_user1(db_template_path, tmp_path):
    """Fresh DB copy with admin user for each test."""
    import shutil
    test_db = tmp_path / "test.db"
    shutil.copy(str(db_template_path[0]), str(test_db))
    return DatabaseManager(db_path=test_db, current_user_id=db_template_path[1])

# Per-test: Fresh isolated database for non-admin user
@pytest.fixture
def db_user2(db_template_path, tmp_path):
    """Fresh DB copy with normal user for each test."""
    import shutil
    test_db = tmp_path / "test.db"
    shutil.copy(str(db_template_path[0]), str(test_db))
    # Create user2 on this copy
    ...
```

**Expected Improvement**: 30-50% faster fixture setup time

---

### 3. Test Categorization and Selective Execution (Medium Impact)

**Current State**: All tests run together without categorization.

**Optimization Strategy**:
- Add pytest markers for test categories
- Enable selective test execution via CLI flags
- Configure CI to run different subsets based on changes

**Proposed Markers**:
```python
# In each test file
@pytest.mark.unit
class TestUnitCategory:
    """Fast, isolated unit tests."""
    def test_something(self):
        pass

@pytest.mark.integration
class TestIntegrationCategory:
    """Tests requiring database operations."""
    def test_something(self):
        pass

@pytest.mark.regression
class TestRegressionCategory:
    """High-level regression tests."""
    def test_something(self):
        pass

@pytest.mark.slow
def test_slow_operation():
    """Tests that take significant time."""
    pass
```

**Usage**:
```bash
# Run only unit tests (fast)
pytest -m unit

# Run integration and regression tests
pytest -m "integration or regression"

# Skip slow tests in CI
pytest -m "not slow"

# Run specific test categories with parallelization
pytest -n auto -m "unit or integration"
```

**Expected Improvement**: Faster feedback loops, targeted test runs

---

### 4. Database Isolation Improvements (High Impact)

**Current State**: Each test gets unique tmp_path, but SQLite file locking could cause issues in parallel mode.

**Optimization Strategy**:
- Use `:memory:` databases for maximum isolation
- Implement WAL (Write-Ahead Logging) mode for better concurrency
- Add retry logic for transient database lock errors

**Implementation**:
```python
# Option 1: In-memory databases (maximum isolation)
@pytest.fixture
def db_user1():
    dm = DatabaseManager(db_path="sqlite:///:memory:")
    dm.init_db()
    # Create users...
    return dm

# Option 2: SQLite with WAL mode for file-based tests
@pytest.fixture
def db_user1(tmp_path):
    db_path = tmp_path / "test.db"
    dm = DatabaseManager(db_path=str(db_path))
    dm.init_db()
    # Enable WAL mode after init
    dm._execute_sql("PRAGMA journal_mode=WAL;")
    return dm

# Option 3: Retry decorator for transient failures
def retry_on_lock(max_attempts=3, delay=0.1):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except OperationalError as e:
                    if "database is locked" in str(e) and attempt < max_attempts - 1:
                        time.sleep(delay * (2 ** attempt))
                        continue
                    raise
        return wrapper
    return decorator
```

**Expected Improvement**: Eliminate parallel test conflicts, enable true concurrent execution

---

### 5. Coverage Reporting and Metrics (Medium Impact)

**Current State**: No coverage tracking configured.

**Optimization Strategy**:
- Add `pytest-cov` for code coverage reporting
- Set minimum coverage thresholds
- Generate HTML reports for detailed analysis
- Track coverage trends over time

**Implementation**:
```ini
# pytest.ini
[pytest]
addopts = 
    -n auto
    --cov=database_manager
    --cov=main
    --cov=models
    --cov-report=html:coverage/html
    --cov-report=term-missing
    --cov-fail-under=80
    -m "not slow"

# In CI pipeline
- Run full test suite with coverage on push
- Generate coverage diff on PR (if tools available)
- Fail if coverage drops below threshold
```

**Expected Improvement**: Visibility into test effectiveness, early detection of untested code

---

### 6. Test Data Generation Improvements (Low-Medium Impact)

**Current State**: Test data created manually in each test method.

**Optimization Strategy**:
- Use `pytest-factoryboy` or `faker` for realistic test data
- Create factory functions for common test scenarios
- Implement fixture composition for complex setups

**Proposed Factories**:
```python
# factories.py
from datetime import date, timedelta

def create_test_matter(db_manager, name, code, parent_id=None, **kwargs):
    """Create a matter with optional attributes."""
    return db_manager.add_matter(name, code, parent_id=parent_id, **kwargs)

def create_matter_hierarchy(db_manager, levels=3):
    """Create a nested matter hierarchy."""
    current = None
    for i in range(levels):
        current = create_test_matter(
            db_manager, 
            f"Level {i}", 
            f"level-{i}", 
            parent_id=current.id if current else None
        )
    return current

def create_time_entry(db_manager, matter_id, duration_hours=1, invoiced=False):
    """Create a time entry with specified duration."""
    from datetime import datetime
    start = datetime.now() - timedelta(hours=duration_hours)
    end = datetime.now()
    return db_manager.add_manual_time_entry(
        matter_id, 
        "Test entry", 
        start_time=start, 
        end_time=end,
        # ... handle invoiced flag
    )
```

**Expected Improvement**: More maintainable tests, reduced code duplication

---

### 7. Performance Benchmarking (Low Impact)

**Current State**: No performance testing.

**Optimization Strategy**:
- Add `pytest-benchmark` for regression testing
- Benchmark critical paths (rate resolution, path building, budget calculation)
- Set performance baselines and alert on regressions

**Implementation**:
```python
# tests/benchmarks.py
import pytest

@pytest.mark.benchmark
class TestRateResolution:
    def test_resolved_hourly_rate(self, benchmark):
        client = db_user1.add_matter("C", "c", parent_id=None)
        project = db_user1.add_matter("P", "p", parent_id=client.id)
        
        result = benchmark(db_user1.get_resolved_hourly_rate, project.id)
        assert result[0] > 0

@pytest.mark.benchmark
class TestPathBuilding:
    def test_get_matters_with_full_paths(self, benchmark):
        # Create hierarchy
        ...
        
        result = benchmark(db_user1.get_matters_with_full_paths)
        assert len(result) > 0
```

**Expected Improvement**: Early detection of performance regressions

---

## Recommended Implementation Order

### Phase 1: Quick Wins (Week 1)
1. Add `pytest.ini` with basic configuration
2. Install `pytest-xdist` and `pytest-cov`
3. Enable parallel execution (`-n auto`)
4. Add coverage reporting

### Phase 2: Fixture Optimization (Week 2)
5. Refactor fixtures for better reuse
6. Implement session-scoped caching where safe
7. Test parallel execution stability

### Phase 3: Test Categorization (Week 3)
8. Add pytest markers to all test classes
9. Configure selective test execution
10. Update CI pipeline for categorized runs

### Phase 4: Advanced Improvements (Week 4+)
11. Implement database isolation improvements
12. Add test data factories
13. Set up performance benchmarking
14. Configure coverage thresholds and CI gates

---

## Expected Outcomes

| Metric | Current | Target | Improvement |
|--------|---------|--------|-------------|
| Test execution time (full suite) | ~60s (sequential) | ~15-20s | 3-4x faster |
| Fixture setup overhead | High (per-test) | Medium | 30-50% reduction |
| Code coverage visibility | None | HTML + CLI | Full visibility |
| Test isolation | File-based | Memory/WAL | Zero conflicts |
| Selective execution | Manual | Markers | Targeted runs |

---

## Dependencies to Add

```txt
# requirements-dev.txt or update requirements.txt
pytest>=7.0.0
pytest-xdist>=3.0.0
pytest-cov>=4.0.0
pytest-factoryboy>=2.6.0
faker>=18.0.0
pytest-benchmark>=4.0.0
```

---

## CI/CD Integration Recommendations

### GitHub Actions Example
```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-xdist pytest-cov
    
    - name: Run unit tests (fast feedback)
      run: pytest -n auto -m "unit" --cov=database_manager --cov-report=term
    
    - name: Run full test suite
      run: pytest -n auto --cov=database_manager --cov=main --cov-report=html --cov-fail-under=80
    
    - name: Upload coverage report
      uses: codecov/codecov-action@v3
      with:
        files: ./coverage/html/index.html
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Parallel test conflicts | Use unique tmp_path per test, WAL mode for SQLite |
| Fixture caching issues | Clear cache between test classes, verify isolation |
| Coverage threshold failures | Set reasonable initial thresholds (70%), incrementally increase |
| Test flakiness in parallel mode | Add retry decorators, identify and fix race conditions |
| CI timeout with parallel tests | Configure appropriate timeouts, use matrix strategy |

---

## Summary

This optimization plan focuses on:
1. **Speed**: 3-4x faster execution through parallelization
2. **Isolation**: Better test independence for reliable results
3. **Visibility**: Coverage reporting and metrics tracking
4. **Maintainability**: Better fixture structure and test data generation
5. **Feedback**: Selective test execution for faster CI feedback

The phased approach allows for incremental adoption, with quick wins in Phase 1 providing immediate value while more complex optimizations are developed and tested in subsequent phases.
