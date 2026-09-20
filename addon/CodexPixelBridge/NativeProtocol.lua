local _,NS=...
local function uint(s,a,n)
    local result=0
    for i=a,a+n-1 do result=result*256+s:byte(i) end
    return result
end
NS.ParseNativePacket=function(data,session,request,slot)
    if data==string.rep(string.char(0),512) then return nil,'Empty reply slot' end
    if #data~=512 or data:sub(1,4)~='CFN1' or data:byte(5)~=1 then return nil,'Invalid native packet' end
    if NS.Adler(data:sub(1,508))~=data:sub(509,512) then return nil,'Invalid native checksum' end
    local state,length=data:byte(6),uint(data,7,2)
    local revision,part,total=uint(data,25,4),uint(data,29,2),uint(data,31,2)
    if state>6 or length>476 or part<1 or total<1 or total>127 or part>total then return nil,'Invalid native fields' end
    if data:sub(9,16)~=session or uint(data,17,4)~=request or uint(data,21,4)~=slot then return nil,'Stale reply packet' end
    if part<total and length~=476 then return nil,'Short native fragment' end
    for i=33+length,508 do if data:byte(i)~=0 then return nil,'Invalid native padding' end end
    return {state=state,revision=revision,part=part,total=total,text=data:sub(33,32+length)}
end
NS.NewNativeAssembly=function()
    return {revision=nil,parts={},total=0,nextPart=1,state=0}
end
NS.AcceptNativeFragment=function(assembly,packet)
    if assembly.revision~=packet.revision then
        assembly.revision=packet.revision;assembly.parts={};assembly.total=packet.total
        assembly.state=packet.state;assembly.nextPart=1
    end
    if assembly.total~=packet.total or assembly.state~=packet.state then return nil,'Conflicting reply packet' end
    if packet.part~=assembly.nextPart then return nil end
    assembly.parts[packet.part]=packet.text
    assembly.nextPart=packet.part+1
    if packet.part==packet.total then
        local text=table.concat(assembly.parts)
        if #text>60000 then return nil,'Reply exceeds preview limit' end
        assembly.nextPart=1;assembly.parts={}
        return text,packet.state
    end
    return nil
end
