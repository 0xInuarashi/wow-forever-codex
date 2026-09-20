local _, NS = ...
local function u32(n)
    return string.char(math.floor(n/16777216)%256, math.floor(n/65536)%256,
        math.floor(n/256)%256, n%256)
end
local function adler(s)
    local a, b = 1, 0
    for i=1,#s do a=(a+s:byte(i))%65521; b=(b+a)%65521 end
    return b*65536+a
end
NS.U32 = u32
NS.Adler = function(s) return u32(adler(s)) end
function NS.Encode(text, session, message)
    assert(#text > 0 and #text <= 1280 and #session == 8)
    local frames, total = {}, math.ceil(#text/40)
    for part=0,total-1 do
        local chunk = text:sub(part*40+1,part*40+40)
        local body = 'CPB1'..string.char(1,#chunk,part,total)..session..u32(message)
            ..chunk..string.rep(string.char(0),40-#chunk)
        frames[#frames+1] = body..u32(adler(body))
    end
    return frames
end
