#!/usr/bin/env bash
# NorthFraim full health check — nine layers, self-contained.
# Prints length + first 4 chars of keys only. No secrets displayed.

ROOT="$HOME/northfraim-job77"
cd "$ROOT" 2>/dev/null || { echo "PROJECT ROOT NOT FOUND: $ROOT"; exit 1; }

line() { printf '%s\n' "------------------------------------------------------------"; }
hdr()  { echo; line; echo "  $1"; line; }

echo "============================================================"
echo "  NORTHFRAIM HEALTH CHECK — $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Root: $ROOT"
echo "============================================================"

# 1. DISK
hdr "1. DISK"
df -h "$ROOT" | awk 'NR==1 || NR==2'

# 2. PROCESSES
hdr "2. PROCESSES (python pipeline)"
ps -eo pid,etime,cmd | grep -E "python3?.*(northfraim|governor|doctor|api_health_check|neverx)" | grep -v grep || echo "  (no matching python processes found)"

# 3. SUPERVISOR
hdr "3. SUPERVISOR STATUS"
if command -v supervisorctl >/dev/null 2>&1; then
  sudo supervisorctl status 2>&1 || echo "  (supervisorctl call failed — check socket perms)"
else
  echo "  supervisorctl not on PATH"
fi

# 4. PYTHON COMPILE
hdr "4. PYTHON COMPILE"
COMPILE_FAIL=0
while IFS= read -r f; do
  if ! python3 -m py_compile "$f" 2>/dev/null; then
    echo "  FAIL: $f"
    COMPILE_FAIL=$((COMPILE_FAIL+1))
  fi
done < <(find "$ROOT" -name "*.py" -not -path "*/__pycache__/*" 2>/dev/null)
[ "$COMPILE_FAIL" -eq 0 ] && echo "  All .py files compile clean." || echo "  $COMPILE_FAIL file(s) failed to compile."

# 5. DB INTEGRITY
hdr "5. DATABASE INTEGRITY"
if command -v sqlite3 >/dev/null 2>&1; then
  DBS=$(find "$ROOT" -name "*.db" -not -path "*/__pycache__/*" 2>/dev/null)
  if [ -z "$DBS" ]; then
    echo "  No .db files found."
  else
    while IFS= read -r db; do
      RES=$(sqlite3 "$db" "PRAGMA integrity_check;" 2>&1 | head -1)
      echo "  $db -> $RES"
    done <<< "$DBS"
  fi
else
  echo "  sqlite3 not installed."
fi

# 6. ACTOR PROFILES
hdr "6. ACTOR PROFILES"
MAINDB=$(find "$ROOT" -name "*.db" 2>/dev/null | xargs -I{} sh -c 'sqlite3 "{}" ".tables" 2>/dev/null | grep -q actor_profiles && echo "{}"' | head -1)
if [ -n "$MAINDB" ]; then
  echo "  DB: $MAINDB"
  sqlite3 -header -column "$MAINDB" "SELECT id, name, voice_clone_id, face_reference_id FROM actor_profiles;" 2>/dev/null
  echo
  echo "  File-reference durability check:"
  sqlite3 "$MAINDB" "SELECT id, face_reference_id FROM actor_profiles;" 2>/dev/null | while IFS='|' read -r id ref; do
    [ -z "$ref" ] && continue
    case "$ref" in
      /tmp/*) echo "  id=$id  DURABILITY WARNING: reference in /tmp -> $ref" ;;
    esac
    if [[ "$ref" == /* ]]; then
      [ -e "$ref" ] && echo "  id=$id  ref exists: $ref" || echo "  id=$id  MISSING FILE: $ref"
    fi
  done
else
  echo "  No DB with actor_profiles table found."
fi

# 7. ERRORS TABLE
hdr "7. ERRORS TABLE"
ERRDB=$(find "$ROOT" -name "*.db" 2>/dev/null | xargs -I{} sh -c 'sqlite3 "{}" ".tables" 2>/dev/null | grep -q errors && echo "{}"' | head -1)
if [ -n "$ERRDB" ]; then
  CNT=$(sqlite3 "$ERRDB" "SELECT COUNT(*) FROM errors;" 2>/dev/null)
  echo "  Total rows: $CNT   (DB: $ERRDB)"
  echo "  Most recent 5:"
  sqlite3 -header -column "$ERRDB" "SELECT * FROM errors ORDER BY rowid DESC LIMIT 5;" 2>/dev/null | sed 's/^/    /'
else
  echo "  No DB with errors table found."
fi

# 8. GIT STATUS
hdr "8. GIT STATUS"
if [ -d "$ROOT/.git" ]; then
  git -C "$ROOT" status -sb 2>/dev/null | head -20
  AHEAD=$(git -C "$ROOT" rev-list --count @{u}..HEAD 2>/dev/null)
  [ -n "$AHEAD" ] && echo "  Commits ahead of origin: $AHEAD"
else
  echo "  Not a git repository."
fi

# 9. KEY FORMAT CHECK (length + first 4 only)
hdr "9. API KEY FORMAT (.env — no secrets shown)"
if [ -f "$ROOT/.env" ]; then
  grep -E '^[A-Za-z0-9_]+=' "$ROOT/.env" | while IFS='=' read -r k v; do
    v="${v%\"}"; v="${v#\"}"; v="${v%\'}"; v="${v#\'}"
    len=${#v}
    first4="${v:0:4}"
    if [ "$len" -eq 0 ]; then
      echo "  $k : EMPTY"
    elif [[ "$v" == *placeholder* || "$v" == *YOUR_* || "$v" == *xxxx* ]]; then
      echo "  $k : len=$len  first4=$first4  <-- LOOKS LIKE PLACEHOLDER"
    else
      echo "  $k : len=$len  first4=$first4"
    fi
  done
else
  echo "  No .env file found."
fi

echo
echo "============================================================"
echo "  END OF REPORT"
echo "============================================================"
