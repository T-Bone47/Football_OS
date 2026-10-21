#!/usr/bin/env bash
# Stage 1 verification runner. Run from the repo root on a machine with network access and Docker
# (or set PG_START_CMD to start your own PostgreSQL 16). Every step is recorded with its exact
# command and outcome in docs/verification/. A step is PASSED only if it ran and exited 0; a missing
# tool or no network is BLOCKED (with the error text), a genuine failure is FAILED.
#
#   tools/verify_environment.sh                    # full run
#   VENV_DIR=/tmp/venv OUT_FILE=docs/verification/x.md tools/verify_environment.sh
set -u
VENV_DIR=${VENV_DIR:-.venv}
WORK=$(mktemp -d)
STEPS="$WORK/steps.jsonl"
JUNIT="$WORK/junit.xml"
OUT_FILE=${OUT_FILE:-docs/verification/$(date -u +%Y-%m-%d)-$(hostname -s).md}
SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))' 2>/dev/null || echo "unset-secret-this-run-will-fail-closed")
export DATABASE_URL=${DATABASE_URL:-postgresql+asyncpg://fios:fios@localhost:5432/fios_test}
export TEST_DATABASE_URL=${TEST_DATABASE_URL:-$DATABASE_URL}
export AUTH_JWT_SECRET=${AUTH_JWT_SECRET:-$SECRET}
PG_START_CMD=${PG_START_CMD:-'docker compose up -d postgres && for i in $(seq 1 30); do docker compose exec -T postgres pg_isready -U fios && break; sleep 2; done && (docker compose exec -T postgres createdb -U fios fios_test || true)'}

record() { python3 tools/record_verification.py add-step --file "$STEPS" --name "$1" --status "$2" --command "$3" --detail "$4"; }

declare -A STATUS

# run_step NAME [--continue] [--needs a,b] COMMAND
#   --needs: BLOCKED (not run) unless every named earlier step PASSED, so the record says exactly why.
run_step() {
  local name=$1 needs="" n; shift
  while [ "${1:-}" = "--needs" ] || [ "${1:-}" = "--continue" ]; do
    if [ "$1" = "--needs" ]; then needs=$2; shift 2; else shift; fi
  done
  local cmd=$1
  for n in ${needs//,/ }; do
    if [ "${STATUS[$n]:-}" != PASSED ]; then
      record "$name" BLOCKED "$cmd" "prerequisite step '$n' did not pass (${STATUS[$n]:-NOT_RUN})"; STATUS[$name]=BLOCKED; return
    fi
  done
  local log="$WORK/$name.log" rc=0
  bash -c "$cmd" >"$log" 2>&1 || rc=$?
  if [ "$rc" -eq 0 ]; then record "$name" PASSED "$cmd" ""; STATUS[$name]=PASSED; return; fi
  local detail status=FAILED
  detail="exit $rc: $(tail -n 4 "$log" | tr '\n' ' ' | cut -c1-400)"
  if [ "$rc" -eq 127 ] || grep -Eqi "name or service not known|could not find a version|no matching distribution|enotfound|temporary failure in name resolution|command not found|no such file or directory.*(docker|yarn|pg_)" "$log"; then status=BLOCKED; fi
  record "$name" "$status" "$cmd" "$detail"; STATUS[$name]=$status
}

run_step postgres_start "$PG_START_CMD"
run_step venv_install "python3.12 -m venv '$VENV_DIR' && . '$VENV_DIR/bin/activate' && pip install -r requirements-dev.txt"
run_step alembic_upgrade --needs venv_install,postgres_start ". '$VENV_DIR/bin/activate' && alembic upgrade head"
run_step alembic_check --needs alembic_upgrade ". '$VENV_DIR/bin/activate' && alembic check"
run_step pytest --needs alembic_upgrade ". '$VENV_DIR/bin/activate' && pytest -v --junitxml='$JUNIT'"
run_step frontend_build "cd Football_OS-frontend/frontend && yarn install --frozen-lockfile && CI=false yarn build"

python3 tools/record_verification.py render --steps "$STEPS" --junit "$JUNIT" --out "$OUT_FILE"
