# m2res

Свой райс для Hyprland: панель Waybar, док, замок с HUD, центр уведомлений, плеер, лаунчер, профили, запись экрана, скриншоты, OCR, диктовка.
Рассчитан на Arch Linux, Hyprland 0.56+ (Lua-конфиг) и широкий монитор 32:9.

![m2res: рабочий стол 5120×1440](docs/hero.jpg)

<p align="center"><i>Панель Waybar, плеер с визуализацией, терминалы. Скриншот с реального монитора 5120×1440@120.</i></p>

## Демо

| Лаунчер `SUPER+D` | Шпаргалка по биндам `SUPER+F1` |
|:--:|:--:|
| ![Лаунчер](docs/launcher.jpg) | ![Бинды](docs/binds.jpg) |

| Центр управления `SUPER+X` | Выбор обоев `SUPER+W` |
|:--:|:--:|
| <img src="docs/control.jpg" width="420"> | ![Обои](docs/wallpick.jpg) |

| Уведомления | Док `SUPER+SHIFT+B` |
|:--:|:--:|
| ![Уведомления](docs/notif.jpg) | <img src="docs/dock.jpg" width="100"> |

## Райсы — переключатель оформления

Один райс меняет всё: палитру, обои, Waybar, геометрию и анимации Hyprland, форму и стиль виджетов, уведомления, экран блокировки, Ghostty, док и звуки. 7 авторских райсов (m2res, paper, zen, brutal, cyber, glass, tty) и 6 с палитрами популярных тем: Catppuccin, Everforest, Matte Black, Nord, Osaka Jade, Ristretto.

![Райсы: m2res, paper, zen, brutal, cyber, glass, tty, nord, osaka-jade](docs/rices.jpg)

`SUPER+ALT+R` — карусель с превью: **Enter** примеряет райс на 10 секунд, потом «оставить?» (Enter — оставить, Esc — вернуть; без ответа вернётся само). В консоли: `m2res-rice list|apply|preview|back|shoot|new|pack|install|import-themes`. Подробнее — в [README райса](.config/m2res/README.md#райсы--переключатель-оформления-m2res-rice).

## Установка

```bash
git clone https://github.com/orybakov/m2res-rice.git
cd m2res-rice
bash install.sh
```

Скрипт сам: ставит недостающие пакеты через pacman и AUR (при необходимости сначала соберёт `yay`; один раз спросит пароль sudo), сохранит прежний `~/.config/m2res` в `~/Backups/m2res/pre-install-*.tar.gz`, скопирует райс, подключит автозапуск и бинды и запустит `m2res-doctor`. Если у вас нет `~/.config/hypr/hyprland.lua`, создаст его с базовыми биндами.

Ключи: `--check` (ничего не менять), `--no-user` (без Whisper ~0,5 ГБ), `--no-enable` (не трогать Hyprland), `--yes` (без вопросов). Откат: `~/.config/m2res/scripts/m2res-enable off`.

Подробнее: [.config/m2res/README.md](.config/m2res/README.md). После установки: `SUPER+F1` шпаргалка по биндам, `SUPER+CTRL+P` профили, `SUPER+SHIFT+B` док.
