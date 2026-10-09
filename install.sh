#!/usr/bin/env bash
# m2res — установщик одним файлом (самораспаковывающийся). Собран m2res-pack: git
# Запуск:  bash m2res-installer.run  (или bash install.sh из клона репозитория) [--check] [--no-user] [--no-enable] [--yes] [--info]
#   --check      только проверить зависимости и конфиг Hyprland, ничего не менять
#   --no-user    не доставлять Whisper (модель ~0.5 ГБ) и словарь OCR
#   --no-enable  не подключать автозапуск и бинды к hyprland.lua
#   --yes        не задавать вопросов
# Без root. Системные конфиги (PAM, SDDM, /etc) не трогает. Прежний ~/.config/m2res сохраняется в ~/Backups/m2res/pre-install-*.tar.gz.
set -u
SELF=$(readlink -f "$0"); M2="$HOME/.config/m2res"; BK="$HOME/Backups/m2res"; H="$HOME/.config/hypr/hyprland.lua"
CHECK=0; USER_PART=1; ENABLE=1; YES=0
for a in "$@"; do case "$a" in
  --check) CHECK=1;; --no-user) USER_PART=0;; --no-enable) ENABLE=0;; --yes|-y) YES=1;;
  --info) sed -n 2,8p "$SELF" | sed 's/^# \{0,1\}//'; exit 0;;
  *) echo "неизвестный ключ: $a (см. --info)" >&2; exit 2;; esac; done
say(){ printf '\n\033[1m== %s\033[0m\n' "$*"; }
ask(){ [ "$YES" = 1 ] && return 0; [ -t 0 ] || return 1; read -r -p "$1 [y/N] " r; [[ "$r" =~ ^[yYдД] ]]; }
# Архив берём из хвоста самого файла (.run); у install.sh из git-клона хвоста нет — пакуем соседние .config/ и .local/
payload(){
  n=$(awk '/^__M2RES_PAYLOAD__$/{print NR+1; exit}' "$SELF")
  if [ -n "$n" ]; then tail -n +"$n" "$SELF"
  else ( cd "$(dirname "$SELF")" && tar -cz .config $([ -d .local ] && echo .local) ); fi
}

say "1/5 окружение"
for c in tar gzip awk; do command -v $c >/dev/null || { echo "нужен $c" >&2; exit 1; }; done
[ -r "$H" ] && echo "ok: Hyprland-конфиг на месте ($H)" || echo "конфига Hyprland нет — создам запасной с базовыми биндами"
command -v hyprland >/dev/null || echo "Hyprland ещё не установлен — поставлю на шаге 3"
payload | tar -tz >/dev/null 2>&1 || { echo "архив внутри установщика повреждён" >&2; exit 1; }
echo "ok: архив цел ($(payload | tar -tz | wc -l) файлов)"

if [ "$CHECK" = 1 ]; then
  T=$(mktemp -d); payload | tar -xz -C "$T" ".config/m2res/scripts/m2res-install" ".config/m2res/player/vendor" 2>/dev/null
  say "зависимости (проверка по копии установщика)"; HOME="$T" bash "$T/.config/m2res/scripts/m2res-install" check 2>&1 | grep -E "НЕТ  |нет  |Не хватает" || echo "всё на месте"
  rm -rf "$T"; exit 0
fi

say "2/5 копирование (прежнее сохраняется)"
mkdir -p "$BK"
if [ -d "$M2" ]; then PRE="$BK/pre-install-$(date +%Y%m%d-%H%M%S).tar.gz"; tar -C "$HOME" -czf "$PRE" --exclude='__pycache__' .config/m2res && echo "страховка: $PRE"; fi
payload | tar -xz -C "$HOME" || { echo "ошибка распаковки" >&2; exit 1; }
chmod +x "$M2"/scripts/* 2>/dev/null; echo "установлено в $M2"

say "3/5 пакеты (pacman + AUR)"
export M2_YES=$YES
"$M2/scripts/m2res-install" packages; RC=$?
if [ $RC -ne 0 ]; then
  echo; echo "Пакеты встали не полностью (код $RC). Исправьте и запустите установщик ещё раз: bash $SELF"
  echo "Конфиги уже скопированы; автозапуск НЕ подключён."; exit 3
fi

say "4/5 Whisper и словарь OCR (без root)"
if [ "$USER_PART" = 0 ]; then echo "пропущено (--no-user); позже: m2res-install user"
elif ask "Скачать модель Whisper small (~0.5 ГБ) и rus.traineddata?"; then "$M2/scripts/m2res-install" user
else echo "пропущено; позже: $M2/scripts/m2res-install user"; fi

say "5/5 автозапуск и бинды"
if [ "$ENABLE" = 0 ]; then echo "пропущено (--no-enable); позже: $M2/scripts/m2res-enable"
else
  if [ ! -r "$H" ]; then
    mkdir -p "$(dirname "$H")"; printf -- '-- создан установщиком m2res: базовые бинды (можно заменить своими)\npcall(dofile, os.getenv("HOME") .. "/.config/m2res/hypr-base.lua")\n' > "$H"; echo "создан $H"
  fi
  "$M2/scripts/m2res-enable"; [ -z "${M2_INSTALL_NORELOAD:-}" ] && command -v hyprctl >/dev/null && hyprctl reload >/dev/null 2>&1; fi
if [ -z "${M2_INSTALL_NORELOAD:-}" ] && hyprctl monitors >/dev/null 2>&1; then say "проверка"; "$M2/scripts/m2res-doctor" 2>&1 | grep -E "WARN|FAIL|итого"; fi
echo
echo "Готово. Шпаргалка: SUPER+F1, профили: SUPER+CTRL+P, док: SUPER+SHIFT+B, README: $M2/README.md"
echo "Войти: выберите Hyprland в менеджере входа или запустите Hyprland из консоли (лучше через uwsm)."
echo "Откат: $M2/scripts/m2res-enable off  (и вернуть прежнее из pre-install-*.tar.gz)"
exit 0
