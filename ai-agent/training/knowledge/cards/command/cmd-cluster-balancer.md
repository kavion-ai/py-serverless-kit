# pskit cluster balancer

Purpose: A load balancer in front of the cluster: one more saved server (outside the cluster) running OpenResty.

When to use:
- The command help says: A load balancer in front of the cluster: one more saved server (outside the cluster) running OpenResty.
- Http://<lb1>/ spreads over the cluster's servers

Usage:

```
pskit cluster balancer COMMAND
```

Options:
- (no options)

Examples:

```
pskit cluster balancer set prod lb1
```

http://<lb1>/ spreads over the cluster's servers

```
pskit cluster balancer set prod lb1 --port 8000 --algorithm least_time
```

Example copied from this command's help text.

```
pskit cluster balancer set prod lb1 --algorithm weighted_round_robin --weight edge1=3 --weight edge2=1
```

Example copied from this command's help text.

```
pskit cluster balancer logs prod -n 200
```

one line per request, with the server that answered

Studio equivalent: none

Related: `pskit cluster balancer logs`, `pskit cluster balancer remove`, `pskit cluster balancer set`, `pskit cluster balancer sync`

Safety: callback for `pskit cluster balancer` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
