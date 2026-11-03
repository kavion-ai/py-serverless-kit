## In studio
1. Set How it spreads requests in the load balancer form.

## In the terminal
1. Run:

```
pskit lb algorithms
```

2. Run:

```
pskit lb update edge --algorithm least_connections
```

## In code

Static algorithms are round_robin, sticky_round_robin, weighted_round_robin, and ip_hash. Dynamic algorithms are least_connections, the default, and least_time.

## The six algorithms `pskit lb algorithms` prints the trade-offs

. The studio's **Load balancers** page shows the same with a small animation of each. | Algorithm | Kind | How it picks a server | Good for | Watch out | |---|---|---|---|---| | `round_robin` | static | each in turn | servers of the same size, requests of the same cost | ignores load; not sticky | | `sticky_round_robin` |

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
