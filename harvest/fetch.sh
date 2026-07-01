#!/bin/bash
# Download recipe pages listed in harvest/worklist.tsv from the Wayback Machine.
# Resumable: skips files already present (>200 bytes). Rate-limited, retrying.
# Uses the "id_" raw-content suffix to get original HTML without the WB toolbar.
set -u
cd "$(dirname "$0")/.."               # project root
WORKLIST="harvest/worklist.tsv"
DEST="contribution"
MANIFEST="harvest/fetch-manifest.tsv"

[ -f "$MANIFEST" ] || echo -e "file\thttp\tsize\tattempts" > "$MANIFEST"

total=$(($(wc -l < "$WORKLIST") - 1)); i=0; got=0; skip=0; fail=0
# Skip header (NR>1)
while IFS=$'\t' read -r fname ts orig; do
  [ "$fname" = "file" ] && continue
  i=$((i+1))
  if [ -f "$DEST/$fname" ] && [ "$(wc -c < "$DEST/$fname")" -gt 200 ]; then
    skip=$((skip+1)); continue
  fi
  url="https://web.archive.org/web/${ts}id_/${orig}"
  code=000; size=0; a=0
  for a in 1 2 3; do
    code=$(curl -sL "$url" -o "$DEST/$fname" -w "%{http_code}" --max-time 45 2>/dev/null || echo 000)
    size=$(wc -c < "$DEST/$fname" 2>/dev/null || echo 0)
    [ "$code" = "200" ] && [ "$size" -gt 200 ] && break
    sleep $((a * 3))
  done
  if [ "$code" = "200" ] && [ "$size" -gt 200 ]; then
    got=$((got+1))
  else
    fail=$((fail+1)); rm -f "$DEST/$fname"
  fi
  echo -e "$fname\t$code\t$size\t$a" >> "$MANIFEST"
  [ $((i % 100)) -eq 0 ] && echo "[$i/$total] got=$got skip=$skip fail=$fail last=$fname ($code)"
  sleep 0.8
done < "$WORKLIST"
echo "DONE: total=$total got=$got skip=$skip fail=$fail"
