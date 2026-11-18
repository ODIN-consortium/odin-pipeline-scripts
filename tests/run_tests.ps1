# PowerShell script to run tests on Windows

param(
    [string]$TestType = "all",
    [switch]$Coverage
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Set-Location $ProjectRoot

Write-Host "Pipeline Scripts Test Runner" -ForegroundColor Green
Write-Host "==============================" -ForegroundColor Green
Write-Host ""

# Check if pytest is installed
$pytestInstalled = $null
try {
    $pytestInstalled = Get-Command pytest -ErrorAction SilentlyContinue
} catch {}

if (-not $pytestInstalled) {
    Write-Host "ERROR: pytest is not installed" -ForegroundColor Red
    Write-Host "Please run: pip install -r requirements.txt"
    exit 1
}

switch ($TestType.ToLower()) {
    "all" {
        Write-Host "Running all tests..." -ForegroundColor Yellow
        if ($Coverage) {
            pytest tests/ -v --cov=scripts --cov-report=term-missing --cov-report=html
            Write-Host "Coverage report generated in htmlcov/index.html" -ForegroundColor Green
        } else {
            pytest tests/ -v
        }
    }

    "unit" {
        Write-Host "Running unit tests only..." -ForegroundColor Yellow
        pytest tests/ -m unit -v
    }

    "integration" {
        Write-Host "Running integration tests only..." -ForegroundColor Yellow
        pytest tests/ -m integration -v
    }

    "fast" {
        Write-Host "Running fast tests (excluding slow tests)..." -ForegroundColor Yellow
        pytest tests/ -m "not slow" -v
    }

    default {
        Write-Host "Unknown test type: $TestType" -ForegroundColor Red
        Write-Host ""
        Write-Host "Usage: .\run_tests.ps1 [-TestType <type>] [-Coverage]"
        Write-Host ""
        Write-Host "Test types:"
        Write-Host "  all         - Run all tests (default)"
        Write-Host "  unit        - Run only unit tests"
        Write-Host "  integration - Run only integration tests"
        Write-Host "  fast        - Run all tests except slow ones"
        Write-Host ""
        Write-Host "Examples:"
        Write-Host "  .\run_tests.ps1                      # Run all tests"
        Write-Host "  .\run_tests.ps1 -Coverage            # Run all tests with coverage"
        Write-Host "  .\run_tests.ps1 -TestType unit       # Run unit tests only"
        exit 1
    }
}

# Check exit code
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✓ All tests passed!" -ForegroundColor Green
    exit 0
} else {
    Write-Host ""
    Write-Host "✗ Some tests failed" -ForegroundColor Red
    exit 1
}

