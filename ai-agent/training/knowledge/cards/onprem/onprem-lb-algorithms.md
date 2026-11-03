## The six algorithms

`pskit lb algorithms` prints the trade-offs. The studio's **Load balancers** page shows the same with a small
animation of each.

| Algorithm | Kind | How it picks a server | Good for | Watch out |
|---|---|---|---|---|
| `round_robin` | static | each in turn | servers of the same size, requests of the same cost | ignores load; not sticky |
| `sticky_round_robin` | static | a user's first request picks one; a cookie keeps the session there | in-memory sessions, uploads in parts, WebSockets | busy users make it uneven; sessions move when a server joins or leaves |
| `weighted_round_robin` | static | in turn, `weight` times as often | servers of different sizes | weights are set by hand |
| `ip_hash` | static | the client IP always maps to the same server | sticky without cookies (devices, API clients) | many users behind one NAT land on one server |
| `least_connections` | dynamic | fewest requests in progress (default) | mixed workloads, long requests | a fast and a slow server can look alike |
| `least_time` | dynamic | lowest average response time x requests in progress | latency-sensitive APIs on uneven hardware | can favor one fast server until it slows down |

**Static** algorithms follow a fixed rule; **dynamic** ones measure live load per request. Open-source nginx has
no sticky cookie or least time (both are NGINX Plus), so pskit builds them: sticky hashes a cookie that holds the
first request's id (`hash ... consistent`), and least time runs `balancer_by_lua` with a moving average of each
server's response header time. A server that fails is retried on the next one and rests for 10 s.

`weight` (1..100, per saved server) is used by weighted round robin, least connections and least time.
