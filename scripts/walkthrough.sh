#!/usr/bin/env bash
# Exercise the fictional local demo without putting passwords or tokens in command arguments.
set -euo pipefail
umask 077

for command in curl jq python3; do
    command -v "$command" >/dev/null || { printf 'Required command missing: %s\n' "$command" >&2; exit 1; }
done
base_url=${APP_BASE_URL:-http://127.0.0.1:8000}
base_url=${base_url%/}
temporary=$(mktemp -d)
class_id=''

cleanup() {
    result=$?
    trap - EXIT
    if [[ -n "$class_id" && -f "$temporary/owner.headers" ]]; then
        curl --silent --max-time 10 --output /dev/null --request POST \
            --header "@$temporary/owner.headers" --header 'Content-Type: application/json' \
            --data-binary "@$temporary/cancel.json" \
            "$base_url/api/v1/sessions/$class_id/cancellation" || true
    fi
    for role in member owner; do
        if [[ -f "$temporary/$role.headers" ]]; then
            curl --silent --max-time 10 --output /dev/null --request POST \
                --header "@$temporary/$role.headers" "$base_url/api/v1/auth/logout" || true
        fi
    done
    rm -rf -- "$temporary"
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

request() {
    local expected=$1 method=$2 path=$3 data=${4:-} headers=${5:-} status
    local options=(--silent --show-error --max-time 15 --output "$temporary/response.json"
        --write-out '%{http_code}' --request "$method")
    if [[ -n "$data" ]]; then
        options+=(--header 'Content-Type: application/json' --data-binary "@$data")
    fi
    if [[ -n "$headers" ]]; then
        options+=(--header "@$headers")
    fi
    status=$(curl "${options[@]}" "$base_url$path")
    if [[ "$status" != "$expected" ]]; then
        printf 'Unexpected HTTP %s for %s %s (expected %s).\n' "$status" "$method" "$path" "$expected" >&2
        return 1
    fi
    printf '%s %s -> %s\n' "$method" "$path" "$status"
}

login() {
    local email=$1 destination=$2
    python3 - "$email" "$temporary/password" "$temporary/login.json" <<'PY'
import json, sys
from pathlib import Path
Path(sys.argv[3]).write_text(json.dumps({'email':sys.argv[1],'password':Path(sys.argv[2]).read_text()}))
PY
    request 200 POST /api/v1/auth/login "$temporary/login.json"
    jq -er '"Authorization: Bearer " + .access_token' "$temporary/response.json" > "$destination"
    rm -- "$temporary/login.json"
}

read -r -s -p 'Password chosen for the fictional demo accounts: ' password
printf '\n'
printf '%s' "$password" > "$temporary/password"
unset password
login owner@example.test "$temporary/owner.headers"
login member@example.test "$temporary/member.headers"
rm -- "$temporary/password"
request 200 GET /health/ready
request 200 GET /api/v1/me '' "$temporary/member.headers"
request 200 GET /api/v1/trainers '' "$temporary/owner.headers"
trainer_id=$(jq -er '.items[0].id' "$temporary/response.json")
suffix=$(python3 -c 'from uuid import uuid4; print(uuid4().hex)')
jq -n --arg name "Walkthrough $suffix" '{name:$name,capacity:2}' > "$temporary/room.json"
request 201 POST /api/v1/rooms "$temporary/room.json" "$temporary/owner.headers"
room_id=$(jq -er '.id' "$temporary/response.json")
request 200 GET /api/v1/rooms '' "$temporary/member.headers"
python3 - "$trainer_id" "$room_id" "$temporary/class.json" <<'PY'
from datetime import UTC,datetime,timedelta
from pathlib import Path
import json,sys
starts=datetime.now(UTC)+timedelta(days=3)
Path(sys.argv[3]).write_text(json.dumps({'title':'Walkthrough class','trainer_id':sys.argv[1],
    'room_id':sys.argv[2],'capacity':2,'starts_at':starts.isoformat(),
    'ends_at':(starts+timedelta(hours=1)).isoformat()}))
PY
printf '%s' '{"reason":"Walkthrough cleanup"}' > "$temporary/cancel.json"
request 201 POST /api/v1/sessions "$temporary/class.json" "$temporary/owner.headers"
class_id=$(jq -er '.id' "$temporary/response.json")
request 200 GET /api/v1/sessions '' "$temporary/member.headers"
jq -n --arg id "$class_id" '{session_id:$id}' > "$temporary/booking.json"
request 201 POST /api/v1/bookings "$temporary/booking.json" "$temporary/member.headers"
booking_id=$(jq -er '.id' "$temporary/response.json")
request 409 POST /api/v1/bookings "$temporary/booking.json" "$temporary/member.headers"
jq -e '.code=="BOOKING_ALREADY_EXISTS"' "$temporary/response.json" >/dev/null
request 200 GET /api/v1/me/bookings '' "$temporary/member.headers"
request 200 POST "/api/v1/bookings/$booking_id/cancellation" '' "$temporary/member.headers"
cp "$temporary/response.json" "$temporary/cancelled.json"
request 200 POST "/api/v1/bookings/$booking_id/cancellation" '' "$temporary/member.headers"
cmp -s "$temporary/response.json" "$temporary/cancelled.json"
request 201 POST /api/v1/bookings "$temporary/booking.json" "$temporary/member.headers"
request 200 POST "/api/v1/sessions/$class_id/cancellation" "$temporary/cancel.json" "$temporary/owner.headers"
request 204 POST /api/v1/auth/logout '' "$temporary/member.headers"
request 401 GET /api/v1/me '' "$temporary/member.headers"
printf 'Walkthrough passed. Temporary credentials are removed on exit.\n'
