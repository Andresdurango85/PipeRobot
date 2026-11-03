#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$PWD}"
cd "$PROJECT_DIR"
PROJECT_DIR="$PWD"
: "${HISTORY_REMOTE:?HISTORY_REMOTE must be set}"

# Parse only the identity needed for the commit; Python validates all append inputs.
commit="" run_id="" run_attempt=""
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
  case "${args[i]}" in
    --commit) commit="${args[i+1]:-}" ;;
    --commit=*) commit="${args[i]#*=}" ;;
    --run-id) run_id="${args[i+1]:-}" ;;
    --run-id=*) run_id="${args[i]#*=}" ;;
    --run-attempt) run_attempt="${args[i+1]:-}" ;;
    --run-attempt=*) run_attempt="${args[i]#*=}" ;;
    --new|--history|--history=*|--new=*)
      echo "ERROR: --new and --history are managed by this script" >&2
      exit 2 ;;
  esac
done

scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
git_cmd=(git -C "$scratch")
if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  authorization=$(printf 'x-access-token:%s' "$GITHUB_TOKEN" | base64 | tr -d '\r\n')
  # Actions masks the raw token, not this encoding of it.
  if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
    echo "::add-mask::$authorization"
  fi
  git_cmd+=(-c "http.extraheader=AUTHORIZATION: basic $authorization")
fi
"${git_cmd[@]}" init -q

for attempt in 1 2 3 4 5; do
  if ! "${git_cmd[@]}" fetch --depth=1 "$HISTORY_REMOTE" "+refs/heads/history:refs/remotes/origin/history"; then
    echo "ERROR: could not fetch history; the history branch must be created first (ADR 0026)" >&2
    exit 1
  fi
  "${git_cmd[@]}" checkout -q --detach refs/remotes/origin/history
  if [[ -n "${HISTORY_PYTHON:-}" ]]; then
    # A command string supplied by the caller; append arguments remain positional, not code.
    bash -c "$HISTORY_PYTHON \"\$@\"" -- -m piperobot.reports.history append \
      --history "$scratch/history.json" "$@"
  else
    uv run --project "$PROJECT_DIR" --locked --no-dev python -m piperobot.reports.history append \
      --history "$scratch/history.json" "$@"
  fi
  if [[ -z "$("${git_cmd[@]}" status --porcelain)" ]]; then
    echo "already present"
    exit 0
  fi
  "${git_cmd[@]}" add history.json
  GIT_AUTHOR_NAME='github-actions[bot]' \
    GIT_AUTHOR_EMAIL='41898282+github-actions[bot]@users.noreply.github.com' \
    GIT_COMMITTER_NAME='github-actions[bot]' \
    GIT_COMMITTER_EMAIL='41898282+github-actions[bot]@users.noreply.github.com' \
    "${git_cmd[@]}" -c user.name='github-actions[bot]' \
    -c user.email='41898282+github-actions[bot]@users.noreply.github.com' \
    -c commit.gpgsign=false commit -q -m "History: $commit (run $run_id.$run_attempt)"
  if "${git_cmd[@]}" push "$HISTORY_REMOTE" HEAD:refs/heads/history; then
    exit 0
  fi
  if (( attempt < 5 )); then
    sleep "$((attempt * 3))"
  fi
done
echo "ERROR: history push failed after 5 attempts" >&2
exit 1
