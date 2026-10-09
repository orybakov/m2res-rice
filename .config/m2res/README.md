# m2res — свой райс для Hyprland
Всё лежит в `~/.config/m2res`, системные конфиги (PAM, SDDM, /etc) не меняются.
Проверено на Arch Linux, Hyprland 0.56 (Lua-конфиг), монитор 5120×1440 (32:9).

## Установщик одним файлом
`m2res-pack [--with-data]` собирает `~/Backups/m2res/m2res-installer-*.run` (около 9 МБ). На новой машине: `bash m2res-installer-*.run` (`--check` — только проверить, `--no-user`, `--no-enable`, `--yes`).
Он проверяет Lua-конфиг Hyprland, сохраняет прежний `~/.config/m2res` в `pre-install-*.tar.gz`, копирует райс, проверяет зависимости (пакеты печатает командой для pacman, сам не ставит), доставляет Whisper и OCR-словарь, подключает автозапуск, гоняет `m2res-doctor`.
Виджеты локального ИИ (карточка, лимиты, переключатель моделей) в установщик не входят: они только для основной машины. Пакеты (pacman + AUR, при необходимости сначала yay) ставит сам установщик: спросит пароль sudo один раз.
Личные данные (журнал уведомлений, статистика лаунчера) кладутся только с `--with-data`; история буфера не включается никогда. Если у вас не было `~/.config/hypr/hyprland.lua`, установщик создаёт его с базовыми биндами (`hypr-base.lua`: SUPER+Enter терминал, SUPER+B Chrome, SUPER+Q закрыть, SUPER+1..0 столы и т.д.).
Бэкап (`m2res-backup make`) включает журнал уведомлений; `M2_BACKUP_NODATA=1` — без него, `M2_BACKUP_CLIP=1` — с историей буфера.

## Установка вручную (без root)
1. `m2res-backup restore <архив>` — вернуть конфиги из архива (`~/Backups/m2res/*.tar.gz`; перед распаковкой делается страховочный архив).
2. `m2res-install check` — что из зависимостей есть, чего нет; `m2res-install packages` — поставить недостающее (pacman + AUR, пароль sudo).
3. `m2res-install user` — доставить без root: venv с faster-whisper + модель small, `rus.traineddata` для OCR.
4. `m2res-enable` — подключить автозапуск и бинды (откат: `m2res-enable off`). Потом `m2res-doctor` — должно быть 0 FAIL.
Резервная копия: `m2res-backup make|list|verify|restore`. Состояние и откаты: `m2res-doctor snapshot|log|diff|restore`.

## Что внутри
| Команда | Что делает | Бинд |
|---|---|---|
| `m2res-bar` start/stop/restart/reload/ensure | панель Waybar; `reload` перекрашивает на лету, `ensure` чинит пропавшую | |
| `m2res-accent` set/auto/show | акцент: панель, виджеты, замок, mako, рамки окон | |
| `m2res-profile` work/game/movie/cycle/back | профили райса одним действием (`profiles.conf`) | `SUPER+CTRL+P` |
| `m2res-dock` toggle/start/stop | боковая панель для 32:9: ярлыки, SHOT, мини-плеер, CPU/GPU/VRAM/RAM; выезжает у левого края (`dock.conf`) | `SUPER+SHIFT+B` |
| `m2res-preset` scrolling/center/dwindle/monocle/cycle | раскладки столов для 32:9 | `SUPER+ALT+L` |
| `m2res-control` | Центр управления: плитки и ползунки | `SUPER+X` |
| `m2res-game` | игровой режим: без анимаций, DND, освобождает VRAM | `SUPER+CTRL+SHIFT+G` |
| `m2res-night` | ночной свет по закату (sunsetr) | `SUPER+CTRL+N` |
| `m2res-rec` screen/area/stop | запись экрана (gpu-screen-recorder), индикатор в Waybar | `SUPER+SHIFT+R`, `SUPER+CTRL+R` |
| `m2res-shot` area/edit/screen/window | скриншоты, редактор satty | `Print`, `Shift+Print`, `Ctrl+Print` |
| `m2res-dictate` | голосовая диктовка (Whisper) | `SUPER+SHIFT+D` |
| `m2res-wallpick` | револьвер выбора обоев | `SUPER+W` |
| `m2res-launcher`, `-clip`, `-power`, `-overview`, `-switch` | лаунчер, буфер, меню выключения, обзор столов, Alt+Tab | `SUPER+D`, `SUPER+V`, `SUPER+Esc`, `SUPER+Tab`, `Alt+Tab` |
| `m2res-center`, `-player`, `-cheat`, `-drop` | центр уведомлений, плеер, шпаргалка биндов, выпадающий терминал | `SUPER+N`, `SUPER+P`, `SUPER+F1`, `` SUPER+` `` |
| `lock/hyprlock.conf` | экран блокировки с HUD | `SUPER+L` |
Полный список: `m2res-binds list`, проверка дублей: `m2res-binds dups`. Браузер по умолчанию — Chrome (`SUPER+B`).

## Профили (`profiles.conf`)
Профиль = акцент, обои (необязательно), «не беспокоить», профиль питания, раскладка текущего стола, ночной свет, игровой режим.
`work`, `game`, `movie` правятся в файле. `m2res-profile back` возвращает всё, как было до первого профиля.

## Док (`dock.conf`)
`AUTOHIDE=1` — выезжает при наведении на левый край (`EDGE` px, `HIDE_MS` мс); `SIDE=left|right`; `AUTOSTART=1` — старт при входе (только на мониторах шире 2.2:1).
Кнопка SHOT: ЛКМ — область, ПКМ — весь экран.

## Старые разделы
- Тема: `scripts/m2res-theme <картинка> [lime|pink|yellow|#hex]` — моно-обои + палитра matugen + перезапуск панели.
- Блокировка вручную: `hyprlock -c ~/.config/m2res/lock/hyprlock.conf`; сцена: `lock/make_scene.py <обои> lock/scene.png 5120 1440`.
- Уведомления (mako): `mako/config`, `scripts/m2res-notify on|off|dnd|test` (`on` останавливает `mako.service` и запускает mako с конфигом m2res, `off` возвращает системный).
