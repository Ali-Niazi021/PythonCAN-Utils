curl -X POST localhost:8000/stream/forward/config \
  -H 'Content-Type: application/json' \
  -d '{
    "enabled": true,
    "url": "http://localhost:8086/api/v2/write?org=trev&bucket=can&precision=ns",
    "token": "M43asPq1a4ZvPh_MzkROsopwm18uoc4BlgMRULYOJjJrIyVRjwK03b--cPaFDD_IdCUv3bv7TR6lvidT_7dkwQ=="
  }'