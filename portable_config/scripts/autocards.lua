-- Copyright (C) 2025 かにふぁん
-- SPDX-License-Identifier: GPL-3.0-or-later

local utils = require 'mp.utils'

local BASE = mp.command_native({'expand-path', '~~/'}):gsub('\\', '/')

local function get_path(dir, prg)
    exe = dir .. '/' .. prg .. '.exe'
    if utils.file_info(exe) then
        return exe
    else
        return prg
    end
end

local CURL = get_path(BASE, '/autocards/curl')
local PYTHON = get_path(BASE .. '/autocards/python', 'python')

local function post(endpoint, v)
    utils.subprocess({ args = {
        CURL, '-s', '-X', 'POST', 'http://127.0.0.1:6969' .. endpoint, '--json', v
    } })
end

local function post_init(v)
    local temp = BASE .. "/autocards_temp.json"
    local f = io.open(temp, "w")
    if not f then
        return
    end
    f:write(v)
    f:close()
    utils.subprocess({ args = {
        CURL, '-s', '-X', 'POST', 'http://127.0.0.1:6969' .. '/init', '--json', '@' .. temp
    } })
    os.remove(temp)
end

local HAS_SERVER = false
local SERVER_FILE

local function update(t)
    local delay = mp.get_property_native('sub-delay')
    local payload = utils.format_json({
        time = t - delay,
        delay = delay
    })
    return post('/update', payload)
end

local function get_active_sub()
    local tracks = mp.get_property_native("track-list")
    for _, track in ipairs(tracks) do
        if track["type"] == "sub" and track["selected"] then
            if track["external"] then
                return { type = "external", path = track["external-filename"] }
            else
                -- ff-index is the stream index used by ffmpeg
                return { type = "internal", index = track["ff-index"], codec = track["codec"] }
            end
        end
    end
    return nil
end

local function get_active_audio_track_id()
    local tracks = mp.get_property_native("track-list")
    for _, track in ipairs(tracks) do
        if track["type"] == "audio" and track["selected"] then
            return track["id"]
        end
    end
    return nil
end

local function init(k, v)
    if not v or SERVER_FILE == v then
        return
    end

    mp.msg.info(mp.get_property("path"))

    local started_server = false
    if not HAS_SERVER then
        mp.command_native_async({ name = 'subprocess', args = { PYTHON, BASE .. '/autocards/server.py' }, playback_only = false })
        utils.subprocess({ args = { PYTHON, BASE .. '/autocards/wait.py' }, playback_only = false })

        HAS_SERVER = true
        started_server = true
    end

    local sub_info = get_active_sub()
    local audio_track_id = get_active_audio_track_id()
    local payload = utils.format_json({
        video = v:gsub('\\', '/'),
        sub = sub_info,
        aid = audio_track_id
    })

    post_init(payload)

    if started_server then
        update(mp.get_property_native('time-pos'))
    end
end

local function tick(k, v)
    if not v or not HAS_SERVER then
        return
    end
    update(v)
end

local function on_sub_change(name, value)
    if HAS_SERVER then
        local path = mp.get_property("path")
        if path then
            -- Re-init with new subtitle selection
            init(nil, path)
        end
    end
end

local function on_aid_change(name, value)
    if HAS_SERVER then
        local aid = get_active_audio_track_id()
        local payload = utils.format_json({ aid = aid })
        post('/aid', payload)
    end
end

mp.register_event('file-loaded', function() init(nil, mp.get_property('path')) end)
mp.observe_property('time-pos', 'number', tick)
mp.observe_property('sid', 'string', on_sub_change)
mp.observe_property('aid', 'string', on_aid_change)
