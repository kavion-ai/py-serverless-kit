"""Complete programs that use one on-prem resource through the pskit host (pskit client).

Used by section 7 of a resource's *How to use* guide. The code is for that exact resource:
its key, native name, the host URL, and whether consuming it outside pskit is safe (a
pskit trigger already consumes it, or its driver has no leases).
"""

from __future__ import annotations


def _js_name(key: str) -> str:
    parts = key.replace("_", "-").split("-")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def python_program(endpoint: str, key: str, native: str, kind: str, *, consumed: bool, builtin: bool) -> str:
    var = key.replace("-", "_")
    head = (
        f'"""Use {kind} `{key}` (native name `{native}`) from any Python program, through the pskit host."""\n\n'
        "import os\n\n"
        "from py_serverless_kit.client import PskitClient, PskitClientError\n\n"
        "# Host URL and admin token (PSKIT_ADMIN_TOKEN, if the host sets one) from the environment, or written here\n"
        f'client = PskitClient(os.environ.get("PSKIT_HOST", "{endpoint}"), timeout=10)\n'
    )
    if kind == "queue":
        if not builtin:
            consume = (
                "\n# 3. Consume: this queue uses a driver, and leases work for built-in queues only. The pskit trigger\n"
                "#    consumes it, or use the service's own client (section 7.3) with its own consumer group.\n"
            )
        elif consumed:
            consume = (
                "\n# 3. Consume: a pskit trigger already consumes this queue, so don't receive here too (the two would\n"
                "#    share its messages). Without that trigger:\n"
                f"#    for msg in {var}.receive(batch=10, visibility=60): handle(msg.json()); msg.ack()\n"
            )
        else:
            consume = (
                "\n\n# 3. Consume: lease up to 10 messages for 60 s; ack when done, nack to retry at once\n"
                "def handle(order):\n"
                '    print("processing", order)\n\n\n'
                f"for msg in {var}.receive(batch=10, visibility=60):\n"
                "    try:\n"
                "        handle(msg.json())\n"
                "        msg.ack()\n"
                "    except Exception as exc:  # keep the message for another try\n"
                '        print("will retry", msg.id, exc)\n'
                "        msg.nack()\n"
            )
        return (
            head
            + f'{var} = client.queue("{key}")\n\n'
            + "try:\n"
            + "    # 1. Add data: dicts and lists are sent as JSON; attributes are string metadata\n"
            + f'    message_id = {var}.send({{"order_id": 1, "action": "create"}}, attributes={{"source": "billing"}})\n'
            + f'    batch_ids = {var}.send_batch([{{"order_id": 2}}, {{"order_id": 3}}])\n'
            + f'    print("queued", message_id, batch_ids, "- waiting:", {var}.depth())\n\n'
            + "    # 2. Read without consuming, 50 per page, oldest first\n"
            + "    offset = 0\n"
            + "    while True:\n"
            + f"        page = {var}.peek(offset=offset, limit=50)\n"
            + "        for item in page.items:\n"
            + '            print(item["id"], item["body"], item["attributes"])\n'
            + "        if not page.has_more:\n"
            + "            break\n"
            + "        offset += len(page.items)\n"
            + "except PskitClientError as exc:\n"
            + "    # exc.status is the HTTP status, or 0 when the host was not reached (section 7.4)\n"
            + '    raise SystemExit(f"pskit host error ({exc.status}): {exc}") from None\n'
            + consume
        )
    if kind == "storage":
        return (
            head
            + f'{var} = client.bucket("{key}")\n\n'
            + "try:\n"
            + "    # 1. Add data: text, bytes or a file from disk (every write fires the bucket's storage triggers)\n"
            + f'    {var}.put("in/hello.txt", "hello from a script")\n'
            + '    with open(__file__, "rb") as source:\n'
            + f'        {var}.put("in/script.py", source.read())\n\n'
            + "    # 2. Read one object (bytes), and save it to a file\n"
            + f'    print({var}.get("in/hello.txt").decode())\n'
            + '    with open("copy-of-hello.txt", "wb") as target:\n'
            + f'        target.write({var}.get("in/hello.txt"))\n\n'
            + "    # 3. List, 100 per page, below a prefix\n"
            + f'    page = {var}.list(prefix="in/", offset=0, limit=100)\n'
            + '    print(page.total, "objects:", [(o["key"], o["size"]) for o in page.items])\n'
            + "    # ...or every key, fetched page by page\n"
            + f'    for object_key in {var}.keys(prefix="in/"):\n'
            + "        print(object_key)\n\n"
            + "    # 4. Delete (fires `deleted` triggers); False when it was not there\n"
            + f'    print({var}.delete("in/script.py"))\n'
            + "except PskitClientError as exc:\n"
            + '    raise SystemExit(f"pskit host error ({exc.status}): {exc}") from None\n'
        )
    return (
        head
        + f'{var} = client.topic("{key}")\n\n'
        + "try:\n"
        + "    # 1. Publish: every subscribed function gets it; attributes drive subscription filters\n"
        + f'    message_id = {var}.publish({{"event": "order.paid", "order_id": 1}}, attributes={{"type": "paid"}})\n'
        + '    print("published", message_id)\n\n'
        + "    # 2. Messages not yet delivered to every subscriber\n"
        + f"    page = {var}.peek(limit=50)\n"
        + '    print(page.total, "pending:", [m["body"] for m in page.items])\n'
        + "except PskitClientError as exc:\n"
        + '    raise SystemExit(f"pskit host error ({exc.status}): {exc}") from None\n'
    )


def node_program(endpoint: str, key: str, native: str, kind: str, *, consumed: bool, builtin: bool) -> str:
    var = _js_name(key)
    head = (
        f"// Use {kind} `{key}` (native name `{native}`) from any Node.js 18+ program, through the pskit host.\n"
        "// Outside a pskit project: `pskit client install-node` puts the package in ./node_modules/pskit.\n"
        'const { PskitClient, PskitClientError } = require("pskit");\n\n'
        "// Host URL and admin token (PSKIT_ADMIN_TOKEN) from the environment, or written here\n"
        f'const client = new PskitClient(process.env.PSKIT_HOST || "{endpoint}", {{ timeout: 10000 }});\n\n'
    )
    if kind == "queue":
        if not builtin:
            consume = (
                "\n  // 3. Consume: this queue uses a driver; the pskit trigger consumes it, or use the service's own\n"
                "  //    client (section 7.3) with its own consumer group.\n"
            )
        elif consumed:
            consume = (
                "\n  // 3. Consume: a pskit trigger already consumes this queue; don't receive here too. Without it:\n"
                f"  //    for (const msg of await {var}.receive({{ batch: 10 }})) {{ handle(msg.json()); await msg.ack(); }}\n"
            )
        else:
            consume = (
                "\n  // 3. Consume: lease up to 10 messages for 60 s; ack when done, nack to retry at once\n"
                f"  for (const msg of await {var}.receive({{ batch: 10, visibility: 60 }})) {{\n"
                "    try {\n"
                '      console.log("processing", msg.json());\n'
                "      await msg.ack();\n"
                "    } catch (err) {\n"
                '      console.error("will retry", msg.id, err.message);\n'
                "      await msg.nack();\n"
                "    }\n"
                "  }\n"
            )
        body = (
            f'  const {var} = client.queue("{key}");\n\n'
            "  // 1. Add data: objects are sent as JSON; attributes are string metadata\n"
            f'  const id = await {var}.send({{ orderId: 1, action: "create" }}, {{ source: "billing" }});\n'
            f"  const ids = await {var}.sendBatch([{{ orderId: 2 }}, {{ orderId: 3 }}]);\n"
            f'  console.log("queued", id, ids, "- waiting:", await {var}.depth());\n\n'
            "  // 2. Read without consuming, 50 per page, oldest first\n"
            "  for (let offset = 0; ; ) {\n"
            f"    const page = await {var}.peek({{ offset, limit: 50 }});\n"
            "    for (const item of page.items) console.log(item.id, item.body, item.attributes);\n"
            "    offset += page.items.length;\n"
            "    if (page.total === null || offset >= page.total || !page.items.length) break;\n"
            "  }\n" + consume
        )
    elif kind == "storage":
        body = (
            f'  const {var} = client.bucket("{key}");\n'
            '  const fs = require("fs");\n\n'
            "  // 1. Add data: a string, a Buffer or a file (every write fires the bucket's storage triggers)\n"
            f'  await {var}.put("in/hello.txt", "hello from a script");\n'
            f'  await {var}.put("in/script.js", fs.readFileSync(__filename));\n\n'
            "  // 2. Read one object (a Buffer), and save it to a file\n"
            f'  const data = await {var}.get("in/hello.txt");\n'
            "  console.log(data.toString());\n"
            '  fs.writeFileSync("copy-of-hello.txt", data);\n\n'
            "  // 3. List, 100 per page, below a prefix; or every key\n"
            f'  const page = await {var}.list({{ prefix: "in/", offset: 0, limit: 100 }});\n'
            '  console.log(page.total, "objects:", page.items.map((o) => [o.key, o.size]));\n'
            f'  for await (const objectKey of {var}.keys({{ prefix: "in/" }})) console.log(objectKey);\n\n'
            "  // 4. Delete (fires `deleted` triggers); false when it was not there\n"
            f'  console.log(await {var}.delete("in/script.js"));\n'
        )
    else:
        body = (
            f'  const {var} = client.topic("{key}");\n\n'
            "  // 1. Publish: every subscribed function gets it; attributes drive subscription filters\n"
            f'  const id = await {var}.publish({{ event: "order.paid", orderId: 1 }}, {{ type: "paid" }});\n'
            '  console.log("published", id);\n\n'
            "  // 2. Messages not yet delivered to every subscriber\n"
            f"  const page = await {var}.peek({{ limit: 50 }});\n"
            '  console.log(page.total, "pending:", page.items.map((m) => m.body));\n'
        )
    return (
        head
        + "async function main() {\n"
        + body
        + "}\n\n"
        + "main().catch((err) => {\n"
        + "  // err.status is the HTTP status, or 0 when the host was not reached (section 7.4)\n"
        + "  console.error(err instanceof PskitClientError ? `pskit host error (${err.status}): ${err.message}` : err);\n"
        + "  process.exit(1);\n"
        + "});\n"
    )
