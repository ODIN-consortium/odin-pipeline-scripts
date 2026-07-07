# Test Suite for Pipeline Scripts

This directory contains comprehensive unit and integration tests for the pipeline Python scripts.

## Test Structure

```
tests/
├── __init__.py                           # Test package initialization
├── conftest.py                           # Shared fixtures and configuration
├── test_nanopore_metadata.py            # Tests for nanopore_metadata.py
├── test_parse_amr_json.py               # Tests for parse_amr_json.py
├── test_concatenate_fastq_by_sample.py  # Tests for concatenate_fastq_by_sample.py
├── test_create_kraken_datasets.py       # Tests for create_kraken_datasets.py
└── test_kraken_parser.py                # Tests for kraken_parser.py
```

## Requirements

Install testing dependencies:

```bash
pip install -r requirements.txt
```

This will install:
- `pytest>=7.0.0` - Testing framework
- `pytest-cov>=4.0.0` - Coverage reporting

## Running Tests

### Run All Tests

```bash
# From the project root directory
pytest tests/

# Or with verbose output
pytest tests/ -v
```

### Run Specific Test File

```bash
pytest tests/test_nanopore_metadata.py -v
```

### Run Specific Test Class

```bash
pytest tests/test_nanopore_metadata.py::TestSetColumnDtypes -v
```

### Run Specific Test Method

```bash
pytest tests/test_nanopore_metadata.py::TestSetColumnDtypes::test_convert_single_column -v
```

### Run Tests by Marker

Tests are marked with pytest markers for categorization:

```bash
# Run only unit tests
pytest tests/ -m unit

# Run only integration tests
pytest tests/ -m integration

# Run only slow tests
pytest tests/ -m slow
```

### Run with Coverage Report

```bash
# Generate coverage report
pytest tests/ --cov=scripts --cov-report=html

# View coverage in terminal
pytest tests/ --cov=scripts --cov-report=term-missing
```

Coverage reports will be generated in `htmlcov/index.html`.

## Test Categories

### Unit Tests (`@pytest.mark.unit`)

Tests individual functions and methods in isolation. These tests:
- Run quickly
- Don't require external files or services
- Use mocked dependencies when needed
- Focus on single units of functionality

Examples:
- `test_convert_single_column` - Tests dtype conversion
- `test_extract_site_and_type_from_sample_id` - Tests regex parsing
- `test_parse_simple_json` - Tests JSON parsing logic

### Integration Tests (`@pytest.mark.integration`)

Tests interactions between multiple components. These tests:
- May be slower than unit tests
- Test complete workflows
- May create temporary files
- Verify end-to-end functionality

Examples:
- `test_read_and_enrich_workflow` - Tests reading and enriching Kraken reports
- `test_concatenate_multiple_runs_merged` - Tests full FASTQ concatenation workflow

### Slow Tests (`@pytest.mark.slow`)

Tests that take significant time to run. These are:
- Typically excluded from regular test runs
- Run in CI/CD pipelines
- Focus on performance and large datasets

## Test Fixtures

Shared fixtures are defined in `conftest.py`:

- `temp_dir`: Temporary directory for file operations
- `sample_metadata_dict`: Sample metadata for testing
- `sample_sites_dict`: Sample site information for testing
- `sample_amr_json`: Sample AMR JSON structure
- `sample_kraken_report`: Sample Kraken2 report content
- `kraken_column_names`: Standard Kraken2 column names

## Writing New Tests

### Test File Naming

- Test files should start with `test_`
- Name should correspond to the module being tested
- Example: `test_my_module.py` tests `my_module.py`

### Test Class Naming

```python
class TestFunctionName:
    """Tests for function_name function."""
    
    @pytest.mark.unit
    def test_basic_functionality(self):
        """Test basic use case."""
        # Arrange
        input_data = ...
        
        # Act
        result = function_name(input_data)
        
        # Assert
        assert result == expected
```

### Using Fixtures

```python
def test_with_fixture(self, tmp_path, sample_metadata_dict):
    """Test using pytest fixtures."""
    # tmp_path is a built-in pytest fixture
    # sample_metadata_dict is from conftest.py
    
    df = pd.DataFrame(sample_metadata_dict)
    file_path = tmp_path / "test.csv"
    df.to_csv(file_path)
    
    assert file_path.exists()
```

### Mocking External Dependencies

```python
from unittest.mock import patch, MagicMock

@patch('module.external_function')
def test_with_mock(self, mock_external):
    """Test with mocked external dependency."""
    mock_external.return_value = "mocked_result"
    
    result = function_that_uses_external()
    
    assert result == "mocked_result"
    mock_external.assert_called_once()
```

## Test Coverage Goals

Target coverage levels:
- **Overall**: >80%
- **Core modules**: >90%
- **Utility functions**: >95%

Focus on:
- All public functions and methods
- Error handling paths
- Edge cases and boundary conditions
- Different input types and formats

## Continuous Integration

Tests are designed to run in CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run tests
  run: |
    pip install -r requirements.txt
    pytest tests/ --cov=scripts --cov-report=xml
```

## Troubleshooting

### Tests Not Found

Ensure you're running pytest from the project root:
```bash
cd /path/to/pipeline_scripts
pytest tests/
```

### Import Errors

If tests can't import modules from `scripts/`:
```bash
# Add scripts to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)/scripts"
pytest tests/
```

### Permission Errors (Windows/WSL)

If you encounter permission errors with temporary files:
```bash
# Run with explicit temp directory
pytest tests/ --basetemp=/tmp/pytest
```

### Slow Tests

Skip slow tests during development:
```bash
pytest tests/ -m "not slow"
```

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Pytest Best Practices](https://docs.pytest.org/en/stable/goodpractices.html)
- [Python Testing Tutorial](https://realpython.com/pytest-python-testing/)

## Contributing

When adding new functionality:

1. Write tests first (TDD approach)
2. Ensure all tests pass: `pytest tests/`
3. Check coverage: `pytest tests/ --cov=scripts`
4. Add appropriate markers (`@pytest.mark.unit`, etc.)
5. Document complex test cases
6. Update this README if needed

