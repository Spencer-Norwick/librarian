#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
INBOX="$ROOT/inbox"

notify() {
  /usr/bin/osascript -e "display notification \"$1\" with title \"Librarian\"" >/dev/null 2>&1 || true
}

unique_target() {
  source_path="$1"
  base_name="$(basename "$source_path")"
  stem="${base_name%.*}"
  ext="${base_name##*.}"
  if [ "$stem" = "$base_name" ]; then
    ext=""
  else
    ext=".$ext"
  fi

  target="$INBOX/$base_name"
  if [ ! -e "$target" ]; then
    printf '%s\n' "$target"
    return 0
  fi

  n=2
  while :; do
    target="$INBOX/${stem}_$n$ext"
    if [ ! -e "$target" ]; then
      printf '%s\n' "$target"
      return 0
    fi
    n=$((n + 1))
  done
}

supported_file() {
  case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
    *.pdf|*.epub|*.txt|*.md|*.docx) return 0 ;;
    *) return 1 ;;
  esac
}

if [ "$#" -eq 0 ]; then
  notify "No files selected."
  exit 0
fi

mkdir -p "$INBOX"

moved=0
skipped=0

for source in "$@"; do
  if [ ! -f "$source" ] || [ -L "$source" ] || ! supported_file "$source"; then
    skipped=$((skipped + 1))
    continue
  fi

  target="$(unique_target "$source")"
  mv "$source" "$target"
  moved=$((moved + 1))
done

if [ "$moved" -gt 0 ] && [ "$skipped" -gt 0 ]; then
  notify "Added $moved file(s) to inbox; skipped $skipped."
elif [ "$moved" -gt 0 ]; then
  notify "Added $moved file(s) to inbox."
else
  notify "No supported files selected."
fi
