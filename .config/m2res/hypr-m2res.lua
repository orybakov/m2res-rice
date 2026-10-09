-- m2res: автозапуск панели и бинды. Подключается строкой dofile в ~/.config/hypr/hyprland.lua
local m2 = os.getenv("HOME") .. "/.config/m2res/scripts"

-- раскладки столов переживают hyprctl reload и подключение монитора (m2res-preset apply читает presets.conf)
hl.on("config.reloaded", function() hl.exec_cmd(m2 .. "/m2res-preset apply") end)
hl.on("monitor.added", function() hl.exec_cmd(m2 .. "/m2res-preset apply") end)

hl.on("hyprland.start", function()
    hl.exec_cmd(m2 .. "/m2res-bar start")
    hl.exec_cmd(m2 .. "/m2res-volume daemon")
    hl.exec_cmd(m2 .. "/m2res-layout daemon")
    hl.exec_cmd(m2 .. "/m2res-switch daemon")      -- Alt+Tab с превью
    hl.exec_cmd(m2 .. "/m2res-autogame daemon")    -- автоматический игровой режим
    hl.exec_cmd(m2 .. "/m2res-dock autostart")      -- боковая панель на 32:9, если AUTOSTART=1 в dock.conf
    hl.exec_cmd(m2 .. "/m2res-preset apply")       -- раскладки столов (WS_N из presets.conf)
    hl.exec_cmd(m2 .. "/m2res-night on")           -- ночной свет по закату/восходу (sunsetr)
    hl.exec_cmd("wl-paste --watch " .. m2 .. "/m2res-clip-store")   -- история буфера обмена
    hl.exec_cmd(m2 .. "/m2res-notify on")   -- mako со стилем m2res (вместо mako.service)
end)

-- уведомления выезжают справа, а не «всплывают»
hl.layer_rule({
    name = "m2res-notify-anim",
    match = { namespace = [[^(notifications)$]] },
    animation = "slide right",
})

-- карточки рисуют свою анимацию сами: штатная popin-анимация слоя масштабирует окно на весь экран
-- от центра, и карточка «ехала слева» — отключаем её
hl.layer_rule({ name = "m2res-center-noanim", match = { namespace = [[^(m2res-center)$]] }, no_anim = true })

hl.layer_rule({ name = "m2res-launcher-noanim", match = { namespace = [[^(m2res-launcher)$]] }, no_anim = true })
hl.layer_rule({ name = "m2res-wallpick-noanim", match = { namespace = [[^(m2res-wallpick)$]] }, no_anim = true })
hl.layer_rule({ name = "m2res-clip-noanim", match = { namespace = [[^(m2res-clip)$]] }, no_anim = true })
hl.layer_rule({ name = "m2res-switch-noanim", match = { namespace = [[^(m2res-switch)$]] }, no_anim = true })
hl.layer_rule({ name = "m2res-calendar-noanim", match = { namespace = [[^(m2res-calendar)$]] }, no_anim = true })
hl.layer_rule({ name = "m2res-power-noanim", match = { namespace = [[^(m2res-power)$]] }, no_anim = true })
hl.layer_rule({ name = "m2res-control-noanim", match = { namespace = [[^(m2res-control)$]] }, no_anim = true })
hl.layer_rule({ name = "m2res-cheat-noanim", match = { namespace = [[^(m2res-cheat)$]] }, no_anim = true })
hl.layer_rule({ name = "m2res-overview-noanim", match = { namespace = [[^(m2res-overview)$]] }, no_anim = true })
hl.layer_rule({ name = "m2res-wallpaper-noanim", match = { namespace = [[^(m2res-wallpaper)$]] }, no_anim = true })

hl.bind("SUPER + P", hl.dsp.exec_cmd(m2 .. "/m2res-player toggle"))
-- SUPER + L: бинд в binds.lua запускает hyprlock; конфиг ~/.config/hypr/hyprlock.conf подключает ретро-ТВ (m2res/lock)

-- SUPER + N: центр уведомлений
hl.bind("SUPER + N", hl.dsp.exec_cmd(m2 .. "/m2res-center toggle"))

-- SUPER + F1: шпаргалка по биндам (строится из binds.lua)
hl.bind("SUPER + F1", hl.dsp.exec_cmd(m2 .. "/m2res-cheat toggle"))

-- SUPER + W: револьвер выбора обоев с переходами
hl.bind("SUPER + W", hl.dsp.exec_cmd(m2 .. "/m2res-wallpick toggle"))

-- редактор скриншотов (satty запускается m2res-shot с классом com.gabm.satty): плавающее окно по центру
hl.window_rule({ name = "m2res-satty-float", match = { class = [[^(com\.gabm\.satty)$]] }, float = true })
hl.window_rule({ name = "m2res-satty-size",  match = { class = [[^(com\.gabm\.satty)$]] }, size = "1800 1000" })
hl.window_rule({ name = "m2res-satty-center", match = { class = [[^(com\.gabm\.satty)$]] }, center = true })

-- ── анимации окон в стиле райса (переопределяют ~/.config/hypr/lua/animations.lua; откат: hypr-m2res.lua.bak-anim) ──
hl.curve("m2Overshoot", { type = "bezier", points = { {0.18, 0.95}, {0.22, 1.06} } })   -- лёгкий «пружинный» перелёт
hl.curve("m2Snap",      { type = "bezier", points = { {0.20, 0.00}, {0.00, 1.00} } })
hl.animation({ leaf = "windowsIn",   enabled = true, speed = 3.6, bezier = "m2Overshoot", style = "popin 80%" })
hl.animation({ leaf = "windowsOut",  enabled = true, speed = 2.4, bezier = "m2Snap",      style = "popin 85%" })
hl.animation({ leaf = "windowsMove", enabled = true, speed = 3.4, bezier = "m2Overshoot" })
hl.animation({ leaf = "workspaces",  enabled = true, speed = 3.2, bezier = "m2Snap",      style = "slide" })
hl.animation({ leaf = "border",      enabled = true, speed = 6,   bezier = "m2Snap" })
hl.animation({ leaf = "borderangle", enabled = true, speed = 40,  bezier = "linear",      style = "loop" })

-- ── выпадающий терминал (SUPER + `): m2res-drop; окно живёт на special-столе "drop", сверху по центру, 70% x 46% экрана ──
hl.window_rule({ name = "m2res-drop-ws",    match = { class = [[^(m2\.drop)$]] }, workspace = "special:drop" })
hl.window_rule({ name = "m2res-drop-float", match = { class = [[^(m2\.drop)$]] }, float = true })
hl.window_rule({ name = "m2res-drop-size",  match = { class = [[^(m2\.drop)$]] }, size = "monitor_w*0.7 monitor_h*0.46" })
hl.window_rule({ name = "m2res-drop-move",  match = { class = [[^(m2\.drop)$]] }, move = "monitor_w*0.15 monitor_h*0.04" })
hl.bind("SUPER + grave", hl.dsp.exec_cmd(m2 .. "/m2res-drop toggle"))

-- ── запись экрана (m2res-rec, gpu-screen-recorder): SUPER+SHIFT+R — весь монитор (повторно — стоп), SUPER+CTRL+R — область ──
hl.bind("SUPER + SHIFT + R", hl.dsp.exec_cmd(m2 .. "/m2res-rec toggle"))
hl.bind("SUPER + CTRL + R", hl.dsp.exec_cmd(m2 .. "/m2res-rec area"))

-- ── экранные инструменты (m2res-tools): OCR области, пипетка, чтение QR, QR из буфера ──
hl.bind("SUPER + SHIFT + O", hl.dsp.exec_cmd(m2 .. "/m2res-tools ocr"))
hl.bind("SUPER + SHIFT + C", hl.dsp.exec_cmd(m2 .. "/m2res-tools color"))
hl.bind("SUPER + SHIFT + Q", hl.dsp.exec_cmd(m2 .. "/m2res-tools qr"))
hl.bind("SUPER + CTRL + Q", hl.dsp.exec_cmd(m2 .. "/m2res-tools qrgen"))

-- ── голосовая диктовка (m2res-dictate, локальный Whisper): SUPER+SHIFT+D — начать / закончить и вставить текст ──
hl.bind("SUPER + SHIFT + D", hl.dsp.exec_cmd(m2 .. "/m2res-dictate toggle"))

-- ── рамки окон = акцент райса: анимированный градиент (акцент → тёмный акцент, угол крутит leaf borderangle). Меняется вместе с акцентом: m2res-paint ──
do
    local f = io.open(os.getenv("HOME") .. "/.config/m2res/player/colors.json")
    local txt = f and f:read("*a") or ""
    if f then f:close() end
    local hex = txt:match('"accent"%s*:%s*"#(%x%x%x%x%x%x)"')
    local sf = io.open(os.getenv("HOME") .. "/.config/m2res/player/style.json")
    local stxt = sf and sf:read("*a") or ""
    if sf then sf:close() end
    if hex and stxt:match('"border"%s*:%s*"solid"') then
        hl.config({ general = { col = { active_border = "rgba(" .. hex .. "ff)", inactive_border = "rgba(" .. hex .. "30)" } } })
    elseif hex then
        local r, g, b = tonumber(hex:sub(1, 2), 16), tonumber(hex:sub(3, 4), 16), tonumber(hex:sub(5, 6), 16)
        local dark = string.format("%02x%02x%02x", math.floor(r * 0.35), math.floor(g * 0.35), math.floor(b * 0.35))
        hl.config({ general = { col = {
            active_border = { colors = { "rgba(" .. hex .. "ff)", "rgba(" .. dark .. "ff)", "rgba(" .. hex .. "ff)" }, angle = 45 },
            inactive_border = "rgba(" .. hex .. "30)",
        } } })
    end
end

-- ── раскладки под 32:9 (m2res-preset): SUPER+ALT+L — по кругу dwindle → scrolling → center → monocle на текущем столе ──
hl.bind("SUPER + ALT + L", hl.dsp.exec_cmd(m2 .. "/m2res-preset cycle"))

-- ── профили райса (m2res-profile): SUPER+CTRL+P — следующий профиль work → game → movie ──
hl.bind("SUPER + CTRL + P", hl.dsp.exec_cmd(m2 .. "/m2res-profile cycle"))

-- ── боковая панель для 32:9 (m2res-dock): SUPER+SHIFT+B — показать/скрыть ──
hl.bind("SUPER + SHIFT + B", hl.dsp.exec_cmd(m2 .. "/m2res-dock toggle"))

-- ── райс (m2res-rice): геометрия, анимации и рамки выбранного райса; файл пишет m2res-rice apply ──
do
    local f = io.open(os.getenv("HOME") .. "/.config/m2res/rice-hypr.lua")
    if f then
        f:close()
        local ok, err = pcall(dofile, os.getenv("HOME") .. "/.config/m2res/rice-hypr.lua")
        if not ok then print("rice-hypr.lua: " .. tostring(err)) end
    end
end

-- ── переключатель райсов: SUPER+ALT+R — карточки с живым предпросмотром, SUPER+ALT+SHIFT+R — следующий райс ──
hl.bind("SUPER + ALT + R", hl.dsp.exec_cmd(m2 .. "/m2res-rice pick"))
hl.bind("SUPER + ALT + SHIFT + R", hl.dsp.exec_cmd(m2 .. "/m2res-rice next"))
