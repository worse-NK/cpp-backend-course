-- Compare and delete only our own lease; this is not a fencing protocol.
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
