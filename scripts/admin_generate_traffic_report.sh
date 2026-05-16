#!/usr/bin/env bash
# Idempotentní generování GoAccess HTML z nginx access logu (Správa vozidel — admin).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKSPACE_ROOT="$(cd "${APP_ROOT}/.." && pwd)"

REPORT_DIR="${GOACCESS_REPORT_DIR:-${WORKSPACE_ROOT}/runtime/reports}"
REPORT_HTML="${GOACCESS_REPORT_HTML_PATH:-${REPORT_DIR}/goaccess-admin.html}"
META_JSON="${GOACCESS_REPORT_META_PATH:-${REPORT_DIR}/goaccess-admin.meta.json}"
LOG_DIAG="${REPORT_DIR}/goaccess-generate.log"

GOACCESS_BIN="${GOACCESS_BIN:-goaccess}"
LOG_FORMAT="${GOACCESS_LOG_FORMAT:-COMBINED}"

mkdir -p "${REPORT_DIR}"
touch "${LOG_DIAG}" || true

iso_now() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

write_meta() {
  local ok="$1" source_log="$2" err="${3:-}"
  local tmp
  tmp="$(mktemp)"
  python3 - "${tmp}" "${ok}" "${source_log}" "${REPORT_HTML}" "$(iso_now)" "${err}" <<'PY'
import json, sys
path, ok, source, report, ts, err = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6]
payload = {
  "ok": ok == "1",
  "generated_at": ts,
  "source_log": source or "",
  "report_path": report or "",
  "error": err or None,
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
PY
  mv -f "${tmp}" "${META_JSON}"
}

log_line() {
  echo "[$(iso_now)] $*" >> "${LOG_DIAG}" || true
}

resolve_access_log() {
  if [[ -n "${NGINX_ACCESS_LOG:-}" ]]; then
    echo "${NGINX_ACCESS_LOG}"
    return 0
  fi

  local dump picked
  if command -v nginx >/dev/null 2>&1; then
    dump="$(nginx -T 2>/dev/null || true)"
    if echo "${dump}" | grep -Fq "server_name hub.toozservis.cz"; then
      picked="$(echo "${dump}" | awk '
        /server_name hub\.toozservis\.cz/ { inhub=1; next }
        inhub && /^[[:space:]]*server[[:space:]]*\{/ { inhub=0; next }
        inhub && /^[[:space:]]*\}/ { inhub=0; next }
        inhub && $0 ~ /^[[:space:]]*access_log/ {
          line=$0
          sub(/^[[:space:]]*access_log[[:space:]]+/, "", line)
          split(line, a, /[[:space:];]+/)
          print a[1]
          exit
        }
      ')"
      if [[ -n "${picked}" ]]; then
        echo "${picked}"
        return 0
      fi
    fi
  fi

  for path in /var/log/nginx/access.log /var/log/nginx/hub.access.log; do
    if [[ -r "${path}" ]]; then
      echo "${path}"
      return 0
    fi
  done

  echo ""
  return 1
}

main() {
  local src
  if ! src="$(resolve_access_log)"; then
    src=""
  fi

  if [[ -z "${src}" ]] || [[ ! -r "${src}" ]]; then
    log_line "ERROR: nginx access log nenalezen nebo není čitelný (zkuste NGINX_ACCESS_LOG=...). src=${src:-<empty>}"
    write_meta 0 "${src}" "Access log není dostupný. Nastavte NGINX_ACCESS_LOG nebo oprávnění ke čtení /var/log/nginx/*.log (skupina adm)."
    exit 0
  fi

  if ! command -v "${GOACCESS_BIN}" >/dev/null 2>&1; then
    log_line "ERROR: příkaz ${GOACCESS_BIN} není k dispozici"
    write_meta 0 "${src}" "GoAccess není nainstalovaný (apt install goaccess)."
    exit 0
  fi

  local tmp_html
  tmp_html="$(mktemp "${REPORT_DIR}/.goaccess-admin.XXXXXX.html")"
  local ga_opts=(
    --log-format="${LOG_FORMAT}"
    --anonymize-ip
    --no-query-string
    --output "${tmp_html}"
    --no-parsing-spinner
    --no-progress
  )

  set +e
  "${GOACCESS_BIN}" "${ga_opts[@]}" -- "${src}" >>"${LOG_DIAG}" 2>&1
  local ga_ec=$?
  set -e

  if [[ "${ga_ec}" -ne 0 ]]; then
    log_line "ERROR: goaccess exit ${ga_ec} pro ${src}"
    rm -f "${tmp_html}"
    write_meta 0 "${src}" "GoAccess selhal (exit ${ga_ec}). Zkontrolujte GOACCESS_LOG_FORMAT — viz ${LOG_DIAG}."
    exit 0
  fi

  mv -f "${tmp_html}" "${REPORT_HTML}"
  chmod 0640 "${REPORT_HTML}" 2>/dev/null || true
  log_line "OK: report -> ${REPORT_HTML} z ${src}"
  write_meta 1 "${src}" ""
  exit 0
}

main "$@"
