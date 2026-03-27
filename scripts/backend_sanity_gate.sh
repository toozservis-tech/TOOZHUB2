#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

export APP_ENV="${APP_ENV:-test}"
export ENVIRONMENT="${ENVIRONMENT:-test}"
export DATABASE_URL="${DATABASE_URL:-sqlite:///./test_vehicles.db}"
export VEHICLE_DB_URL="${VEHICLE_DB_URL:-sqlite:///./test_vehicles.db}"
export TEST_DATABASE_URL="${TEST_DATABASE_URL:-sqlite:///./test_vehicles.db}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-test-secret-key-for-ci-only}"
export HOST="${HOST:-127.0.0.1}"
export PORT="${PORT:-8000}"

./scripts/bootstrap_dev.sh
./scripts/schema_smoke.sh -q
./scripts/run_tests.sh local -q
