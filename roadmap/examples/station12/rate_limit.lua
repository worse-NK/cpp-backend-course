-- Fixed window beginning with the first accepted request for this key.
-- Validation precedes mutation: atomic execution is not rollback.
local limit = tonumber(ARGV[1])
local duration = tonumber(ARGV[2])
if not limit or limit < 1 or limit > 1000000 or limit ~= math.floor(limit) or
   not duration or duration < 1 or duration > 3600000 or duration ~= math.floor(duration) then
    return redis.error_reply('invalid limit or duration')
end
local current = redis.call('GET', KEYS[1])
if current and (#current > 7 or not string.match(current, '^%d+$')) then
    return redis.error_reply('counter is not a nonnegative integer')
end
local n = tonumber(current or '0')
if current and (n > 1000000 or redis.call('PTTL', KEYS[1]) < 0) then
    return redis.error_reply('invalid counter state')
end
if n >= limit then
    return {0, n, redis.call('PTTL', KEYS[1])}
end
n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('PEXPIRE', KEYS[1], duration) end
return {1, n, redis.call('PTTL', KEYS[1])}
