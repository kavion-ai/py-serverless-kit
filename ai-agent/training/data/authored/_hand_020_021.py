"""Hand-authored shard 020 and 021 conversations. Serializer only."""
import json
import sys
import textwrap
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))
from check_knowledge import SYSTEM_BEFORE_ENV  # noqa: E402

OUT = Path(__file__).resolve().parent


def T(text: str) -> str:
    return textwrap.dedent(text).strip()


def rec(cid, provider, stage, mode, page, persona, card, user, answer):
    env = f"Environment: provider={provider} stage={stage} mode={mode} page={page}"
    return {
        "id": cid,
        "messages": [
            {"role": "system", "content": SYSTEM_BEFORE_ENV + env},
            {"role": "user", "content": T(user)},
            {"role": "assistant", "content": T(answer)},
        ],
        "meta": {
            "category": "k_cmd",
            "card_ids": [card],
            "grounding": "closed",
            "persona": persona,
            "sources": ["src/py_serverless_kit/cli/main.py"],
        },
    }


G = "cmd-resources-onprem-servers"
A = "cmd-resources-onprem-servers-add"
C = "cmd-resources-onprem-servers-check"
L = "cmd-resources-onprem-servers-list"
R = "cmd-resources-onprem-servers-remove"
E = "cmd-resources-onprem-servers-test"
P = "cmd-resources-onprem-servers-top"
U = "cmd-resources-onprem-servers-usage"

rows_020 = [
rec("k_cmd_0801", "digitalocean", "prod", "ask", "Functions", "beginner", G,
"`edge1` is in the help example. What command saves that server?",
"""
Saving a machine under a name is what `pskit resources onprem servers` is for. You name it once, then create services, install software, open shells, and deploy to it. The edge1 sample is the add subcommand, with `--ssh` and `--pem`.

**In the terminal**

1. Save edge1 with the login and key file from the help.

```
pskit resources onprem servers add edge1 --ssh deploy@192.0.2.10 --pem ~/.ssh/edge1.pem
```
"""),
rec("k_cmd_0802", "cloudflare", "dev", "auto", "Workflows", "beginner", G,
"`--pem ~/.ssh/edge1.pem` goes with which servers command?",
"""
The flag is `--pem`. It belongs on add, not on the bare `pskit resources onprem servers` group. `--pem` is the private key. Leave it off and the SSH agent or your default key is used.

**In the terminal**

1. Save edge1 with that key file.

```
pskit resources onprem servers add edge1 --ssh deploy@192.0.2.10 --pem ~/.ssh/edge1.pem
```
"""),
rec("k_cmd_0803", "onprem", "staging", "ask", "Resources", "beginner", G,
"`--ssh-password-env LAB_PW` puts the password in the command?",
"""
`--ssh-password-env` only names the variable. The password stays in `LAB_PW`, not on the command line and not in `pskit.yml`. The lab help line uses it while add saves (or replaces) the server.

```
pskit resources onprem servers add lab --ssh deploy@192.0.2.10 --ssh-password-env LAB_PW
```
"""),
rec("k_cmd_0804", "aws", "prod", "auto", "Cluster", "beginner", G,
"`pskit.yml` is not on the servers group. Does that command take flags?",
"""
That group command takes no flags. `pskit resources onprem servers` only groups add, check, list, remove, test, top, and usage. `pskit.yml` is selected with `-c` or `--config` on a subcommand, and the default file there is `pskit.yml`.
"""),
rec("k_cmd_0805", "azure", "dev", "ask", "Load balancers", "beginner", G,
"`servers test edge1` logs in, or does it only save the name?",
"""
`pskit resources onprem servers test` logs in. It shows the OS, CPU, memory, disk, Docker access, sudo, and installed runtimes. It does not save the server. Saving is add.

**In the terminal**

1. Log in to the saved name edge1.

```
pskit resources onprem servers test edge1
```
"""),
rec("k_cmd_0806", "gcp", "staging", "auto", "Network map", "beginner", G,
"`--ssh deploy@192.0.2.10` is how edge1 gets its address, right?",
"""
`--ssh` is required on add, and the form is `user@host[:port]`. The help sample stores edge1 as `deploy@192.0.2.10`. The group command itself has no flags. After the name exists you can create services, install software, open shells, and deploy to it.

**In the terminal**

1. Save edge1 with that SSH address and a key file.

```
pskit resources onprem servers add edge1 --ssh deploy@192.0.2.10 --pem ~/.ssh/edge1.pem
```
"""),
rec("k_cmd_0807", "alibaba", "prod", "ask", "Code", "beginner", G,
"`~/.ssh/edge1.pem` is the private key in the edge1 example?",
"""
Yes. `~/.ssh/edge1.pem` is the `--pem` path on the edge1 help line. `--pem` is the private key. If you omit it, add uses the SSH agent or your default key.

```
pskit resources onprem servers add edge1 --ssh deploy@192.0.2.10 --pem ~/.ssh/edge1.pem
```
"""),
rec("k_cmd_0808", "tencent", "dev", "auto", "Test", "beginner", G,
"`LAB_PW` is the variable for the lab server example?",
"""
Yes. The lab line passes `LAB_PW` to `--ssh-password-env`. That variable holds the password for sshpass. The edge1 line is separate and uses `--pem` instead.

**In the terminal**

1. Save lab the way the help shows.

```
pskit resources onprem servers add lab --ssh deploy@192.0.2.10 --ssh-password-env LAB_PW
```
"""),
rec("k_cmd_0809", "huawei", "staging", "ask", "Deploy", "beginner", G,
"`servers add lab` should run before `servers test`, right?",
"""
Save the name before you test it. Add saves (or replaces) the server. Test logs into a name you already saved and prints OS, CPU, memory, disk, Docker access, sudo, and installed runtimes. The help shows add, then a test of edge1.

**In the terminal**

1. Save lab, then test that saved name.

```
pskit resources onprem servers add lab --ssh deploy@192.0.2.10 --ssh-password-env LAB_PW
pskit resources onprem servers test lab
```
"""),
rec("k_cmd_0810", "oracle", "prod", "auto", "Logs", "beginner", G,
"`edge1` and `lab` in the help are two different machines?",
"""
They are two sample names, not one machine. Both samples use `--ssh deploy@192.0.2.10`. edge1 is saved with a key file. lab is saved with a password variable.

| Name | How the help saves it |
| --- | --- |
| edge1 | `--pem ~/.ssh/edge1.pem` |
| lab | `--ssh-password-env LAB_PW` |
"""),
rec("k_cmd_0811", "ibm", "dev", "ask", "YAML", "beginner", A,
"`--ssh` has to be there when I add a server name?",
"""
Yes. `--ssh` is required. It is `user@host[:port]`. Add saves (or replaces) server NAME, and this flag is the login it stores.

**In the terminal**

1. Add edge1 with the required SSH login.

```
pskit resources onprem servers add edge1 --ssh deploy@192.0.2.10
```
"""),
rec("k_cmd_0812", "digitalocean", "staging", "auto", "none", "beginner", A,
"`--no-test` means skip the login after the server is saved?",
"""
`--no-test` skips the login. `--test` is the default, and it logs in once after the save. Either way, add still saves (or replaces) the name.

**In the terminal**

1. Save edge1 and do not log in afterward.

```
pskit resources onprem servers add edge1 --ssh deploy@192.0.2.10 --pem ~/.ssh/edge1.pem --no-test
```
"""),
rec("k_cmd_0813", "cloudflare", "prod", "ask", "Overview", "beginner", A,
"`--sudo` makes docker and installs use sudo -n?",
"""
`--sudo` is off unless you set it. When it is set, docker and installs run with `sudo -n`. It does not replace `--ssh`. Add still saves (or replaces) NAME.

**In the terminal**

1. Save edge1 and mark sudo for docker and installs.

```
pskit resources onprem servers add edge1 --ssh deploy@192.0.2.10 --sudo
```
"""),
rec("k_cmd_0814", "onprem", "dev", "auto", "Setup", "beginner", A,
"`--home` defaults to what path when I add lab?",
"""
The `--home` default is `/opt/pskit`. Cluster files stay in `~`. This is where pskit keeps files on that server. `--home` is optional. Add saves (or replaces) the name.

**In the terminal**

1. Save lab and set home to that default path.

```
pskit resources onprem servers add lab --ssh deploy@192.0.2.10 --home /opt/pskit
```
"""),
rec("k_cmd_0815", "aws", "staging", "ask", "Functions", "beginner", A,
"`--bind 127.0.0.1` keeps listeners on localhost only?",
"""
`--bind` is the address functions and services listen on. `127.0.0.1` is allowed, and so are `0.0.0.0` and another IP. Add stores it when it saves (or replaces) the server.

**In the terminal**

1. Save edge1 and bind listeners to localhost.

```
pskit resources onprem servers add edge1 --ssh deploy@192.0.2.10 --bind 127.0.0.1
```
"""),
rec("k_cmd_0816", "azure", "prod", "auto", "Workflows", "beginner", A,
"`--data-dir` sets where data lives on that server?",
"""
`--data-dir` is where data lives on that server. If you omit it, the default is Docker volumes or the app. Add saves (or replaces) NAME and can store this path with the server.

```
pskit resources onprem servers add lab --ssh deploy@198.51.100.10 --data-dir /data/pskit
```
"""),
rec("k_cmd_0817", "gcp", "dev", "ask", "Resources", "beginner", A,
"`--description` is only a note, not the server address?",
"""
`--description` stores a note shown in the studio. It is not the SSH address. The address is `--ssh`. Add saves (or replaces) the server either way.

```
pskit resources onprem servers add edge1 --ssh deploy@192.0.2.10 --description edge-box
```
"""),
rec("k_cmd_0818", "alibaba", "staging", "auto", "Cluster", "beginner", A,
"`--pem ~/.ssh/edge1.pem` or can I leave the key empty?",
"""
Leave `--pem` off to use the SSH agent or your default key. Pass a path when you want that private key. `--ssh` is still required. Add saves (or replaces) the name.

**In the terminal**

1. Save edge1 with an explicit key file.

```
pskit resources onprem servers add edge1 --ssh deploy@192.0.2.10 --pem ~/.ssh/edge1.pem
```

2. Or omit `--pem` and use the agent or the default key.

```
pskit resources onprem servers add edge1 --ssh deploy@192.0.2.20
```
"""),
rec("k_cmd_0819", "tencent", "prod", "ask", "Load balancers", "beginner", A,
"`--ssh-password-file` reads a password file through sshpass?",
"""
`--ssh-password-file` points at a file. sshpass reads the password from that file. Do not put the password on the command. Add saves (or replaces) NAME.

**In the terminal**

1. Save lab using a password file.

```
pskit resources onprem servers add lab --ssh deploy@203.0.113.10 --ssh-password-file ~/.ssh/lab.pass
```
"""),
rec("k_cmd_0820", "huawei", "dev", "auto", "Network map", "beginner", A,
"`-c` lets add use a file other than pskit.yml?",
"""
`-c` and `--config` pick the config file. The default is `pskit.yml`. Add still requires `--ssh`, and it saves (or replaces) NAME.

**In the terminal**

1. Save lab and point `-c` at the default file.

```
pskit resources onprem servers add lab --ssh deploy@192.0.2.10 -c pskit.yml
```
"""),
rec("k_cmd_0821", "oracle", "staging", "ask", "Code", "informal_non_native", C,
"`--config` on servers check, it do a login?",
"""
No login. `--config` only picks the file. Check tells which saved servers answer on their SSH port. The default file is `pskit.yml`.

**In the terminal**

1. Check SSH ports with a chosen config file.

```
pskit resources onprem servers check --config pskit.yml
```
"""),
rec("k_cmd_0822", "ibm", "prod", "auto", "Test", "informal_non_native", C,
"`-c pskit.yml` for check, still no login right?",
"""
Still no login. `-c pskit.yml` only selects that file. The command reports which saved servers answer on their SSH port.

```
pskit resources onprem servers check -c pskit.yml
```
"""),
rec("k_cmd_0823", "digitalocean", "dev", "ask", "Deploy", "informal_non_native", C,
"`pskit.yml` is the default file servers check read?",
"""
Check reads `pskit.yml` when you omit `-c`. `--config` is the long name of that flag. There is no login, only which saved servers answer on their SSH port.

**In the terminal**

1. Run check and leave the default file implicit.

```
pskit resources onprem servers check
```
"""),
rec("k_cmd_0824", "cloudflare", "staging", "auto", "Logs", "informal_non_native", C,
"`servers check` need `-c`, or it run alone?",
"""
It runs alone. `-c` is optional. With no flags the file is `pskit.yml`. There is no NAME and no login, only the SSH port of each saved server.

```
pskit resources onprem servers check
```
"""),
rec("k_cmd_0825", "onprem", "prod", "ask", "YAML", "informal_non_native", C,
"`--config other.yml` still only look at SSH port?",
"""
Still no login. `--config` only changes the config file. Check reports which saved servers answer on their SSH port.

**In the terminal**

1. Point check at another config file.

```
pskit resources onprem servers check --config other.yml
```
"""),
rec("k_cmd_0826", "aws", "dev", "auto", "none", "informal_non_native", C,
"`pskit.yml` check versus test, which one login?",
"""
Check does not log in. Test does. Check only reports which saved servers answer on their SSH port. Test logs in and shows OS, CPU, memory, disk, Docker access, sudo, and installed runtimes.

| Command | Login |
| --- | --- |
| `pskit resources onprem servers check` | no |
| `pskit resources onprem servers test` | yes, and it needs NAME |
"""),
rec("k_cmd_0827", "azure", "staging", "ask", "Overview", "informal_non_native", C,
"`--config` default pskit.yml, and check do not login?",
"""
Check does not log in. `--config` defaults to `pskit.yml` and only chooses the file. You learn which saved servers answer on their SSH port.

**In the terminal**

1. Check every saved server SSH port.

```
pskit resources onprem servers check --config pskit.yml
```
"""),
rec("k_cmd_0828", "gcp", "prod", "auto", "Setup", "informal_non_native", C,
"`-c` is the only flag servers check have?",
"""
Yes. `-c` / `--config` is the only option. It chooses the config file, default `pskit.yml`. Check does not log in. It reports which saved servers answer on their SSH port.

```
pskit resources onprem servers check -c pskit.yml
```
"""),
rec("k_cmd_0829", "alibaba", "dev", "ask", "Functions", "informal_non_native", C,
"`pskit.yml` missing, can servers check still run?",
"""
The default file is `pskit.yml`. If your file has another name, pass `-c` or `--config`. Check still does not log in. It only reports which saved servers answer on their SSH port, and it takes no NAME.

```
pskit resources onprem servers check --config pskit.yml
```
"""),
rec("k_cmd_0830", "tencent", "staging", "auto", "Workflows", "informal_non_native", C,
"`--config` change the file, check still skip login?",
"""
Changing `--config` does not add a login. Check never logs in. It reports which saved servers answer on their SSH port. Omit the flag and the file stays `pskit.yml`.

**In the terminal**

1. Check SSH ports with an explicit file.

```
pskit resources onprem servers check --config pskit.yml
```
"""),
rec("k_cmd_0831", "huawei", "prod", "ask", "Resources", "informal_non_native", L,
"`--json` make servers list print JSON?",
"""
`--json` prints the saved servers as JSON. It is off unless you pass it, and the flag has no help text. The command help text is empty. List takes no NAME. `-c` or `--config` still defaults to `pskit.yml`.

**In the terminal**

1. List saved servers as JSON.

```
pskit resources onprem servers list --json
```
"""),
rec("k_cmd_0832", "oracle", "dev", "auto", "Cluster", "informal_non_native", L,
"`-c` choose which file servers list read?",
"""
`-c` selects the config file for list. `--config` is the same option. The default file is `pskit.yml`. List prints saved servers and has no NAME argument.

**In the terminal**

1. List servers from the default file.

```
pskit resources onprem servers list -c pskit.yml
```
"""),
rec("k_cmd_0833", "ibm", "staging", "ask", "Load balancers", "informal_non_native", L,
"`pskit.yml` is what list use if I pass nothing?",
"""
With no flag, list uses `pskit.yml`. `--json` stays off, so you do not get JSON unless you ask. The command help text is empty. There is no NAME argument.

```
pskit resources onprem servers list
```
"""),
rec("k_cmd_0834", "digitalocean", "prod", "auto", "Network map", "informal_non_native", L,
"`--json` plus `--config` both ok on list?",
"""
Yes, `--json` and `--config` can be combined. `--json` turns on JSON. `--config` picks the file, and the default is `pskit.yml`. List has no NAME.

**In the terminal**

1. List as JSON from `pskit.yml`.

```
pskit resources onprem servers list --json --config pskit.yml
```
"""),
rec("k_cmd_0835", "cloudflare", "dev", "ask", "Code", "informal_non_native", L,
"`servers list` flags just `--json` and `-c`?",
"""
The list command's own help text is empty. Those are the only options.

| Flag | Meaning |
| --- | --- |
| `--json` | JSON output. Default off. The flag has no help text. |
| `-c`, `--config` | Config file. Default `pskit.yml`. |

There is no NAME argument.

```
pskit resources onprem servers list --json -c pskit.yml
```
"""),
rec("k_cmd_0836", "onprem", "staging", "auto", "Test", "informal_non_native", L,
"`--config servers.yml` for list instead of pskit.yml?",
"""
Pass `--config` when the file is not `pskit.yml`. `-c` is the short form. List still has no NAME, and `--json` is optional.

**In the terminal**

1. List saved servers from `servers.yml`.

```
pskit resources onprem servers list --config servers.yml
```
"""),
rec("k_cmd_0837", "aws", "prod", "ask", "Deploy", "informal_non_native", L,
"`-c pskit.yml` list the saved servers only?",
"""
`-c pskit.yml` points list at that file. The command lists saved servers. It does not add, test, or remove them. `--json` is separate and defaults off. There is no NAME.

```
pskit resources onprem servers list -c pskit.yml
```
"""),
rec("k_cmd_0838", "azure", "dev", "auto", "Logs", "informal_non_native", L,
"`--json` off unless I add that flag?",
"""
Right. `--json` defaults off. Omit it and list does not switch to JSON. The flag has no help text. The config file stays `pskit.yml` unless you pass `-c` or `--config`.

```
pskit resources onprem servers list --json
```
"""),
rec("k_cmd_0839", "gcp", "staging", "ask", "YAML", "informal_non_native", L,
"`pskit.yml` the file that list command read?",
"""
List reads the config file, default `pskit.yml`. Change it with `-c` or `--config`. `--json` is optional and off by default. The command help text is empty, and there is no server NAME.

```
pskit resources onprem servers list --config pskit.yml
```
"""),
rec("k_cmd_0840", "alibaba", "prod", "auto", "none", "informal_non_native", L,
"`servers list` has no NAME argument, correct?",
"""
Correct. There is no NAME argument. List prints the saved servers. Optional flags are `--json` and `-c` or `--config`, and the default file is `pskit.yml`.

**In the terminal**

1. List saved servers from the default file.

```
pskit resources onprem servers list
```
"""),
]

rows_021 = [
rec("k_cmd_0841", "tencent", "dev", "ask", "Overview", "informal_non_native", R,
"`servers remove edge1` stop services or no?",
"""
No. Forget does not stop services. `pskit resources onprem servers remove` forgets NAME, and services already created there keep running.

**In the terminal**

1. Forget edge1 and leave its services running.

```
pskit resources onprem servers remove edge1
```
"""),
rec("k_cmd_0842", "huawei", "staging", "auto", "Setup", "informal_non_native", R,
"`-c` on remove, it only forget NAME?",
"""
`-c` only picks the file. Remove still forgets NAME, and services already created there keep running. The default file is `pskit.yml`. `--config` is the long flag.

```
pskit resources onprem servers remove edge1 -c pskit.yml
```
"""),
rec("k_cmd_0843", "oracle", "prod", "ask", "Functions", "informal_non_native", R,
"`--config pskit.yml` when I forget lab?",
"""
`--config` chooses the file when you forget a name. The command forgets server NAME. Services already created there keep running. `pskit.yml` is the default.

**In the terminal**

1. Forget lab using that config file.

```
pskit resources onprem servers remove lab --config pskit.yml
```
"""),
rec("k_cmd_0844", "ibm", "dev", "auto", "Workflows", "informal_non_native", R,
"`edge1` after remove, services keep running?",
"""
Services keep running after you forget edge1. Remove only drops the saved name. This command does not ask you to confirm.

**In the terminal**

1. Forget edge1 with no confirm step.

```
pskit resources onprem servers remove edge1
```
"""),
rec("k_cmd_0845", "digitalocean", "staging", "ask", "Resources", "informal_non_native", R,
"`servers remove NAME` forget, not stop services?",
"""
NAME is required. The command forgets that saved server. Services already created there keep running. The only option is `-c` or `--config`, default `pskit.yml`.

**In the terminal**

1. Forget the saved name edge1.

```
pskit resources onprem servers remove edge1 --config pskit.yml
```
"""),
rec("k_cmd_0846", "cloudflare", "prod", "auto", "Cluster", "terse_expert", R,
"`--config` on `servers remove`, what for?",
"""
`--config` selects the config file. Default is `pskit.yml`. Remove forgets NAME. Services already created there keep running.

```
pskit resources onprem servers remove edge1 --config pskit.yml
```
"""),
rec("k_cmd_0847", "onprem", "dev", "ask", "Load balancers", "terse_expert", R,
"`-c` alternate file, remove still forgets NAME?",
"""
`-c` is the file flag. The forget still only drops NAME. Services already created there keep running.

**In the terminal**

1. Forget edge1 from another config file.

```
pskit resources onprem servers remove edge1 -c other.yml
```
"""),
rec("k_cmd_0848", "aws", "staging", "auto", "Network map", "terse_expert", R,
"`edge1` remove leaves services running?",
"""
Yes. Removing edge1 forgets the saved name. Services already created there keep running. The file flag is `-c` or `--config`.

```
pskit resources onprem servers remove edge1
```
"""),
rec("k_cmd_0849", "azure", "prod", "ask", "Code", "terse_expert", R,
"`pskit.yml` default when removing a server NAME?",
"""
`pskit.yml` is the default. Pass `-c` or `--config` for another file. Remove forgets NAME and leaves services running.

```
pskit resources onprem servers remove edge1 -c pskit.yml
```
"""),
rec("k_cmd_0850", "gcp", "dev", "auto", "Test", "terse_expert", R,
"`servers remove edge1` with no extra flag?",
"""
No extra flag is required. NAME is enough. The command forgets edge1. Services already created there keep running. `-c` is optional.

**In the terminal**

1. Forget edge1 with no flags.

```
pskit resources onprem servers remove edge1
```
"""),
rec("k_cmd_0851", "alibaba", "staging", "ask", "Deploy", "terse_expert", E,
"`pskit.yml` aside, `servers test NAME` show Docker?",
"""
Test logs in and shows Docker access, plus OS, CPU, memory, disk, sudo, and installed runtimes. NAME is required. `-c` defaults to `pskit.yml`.

**In the terminal**

1. Log in to edge1 and print those facts.

```
pskit resources onprem servers test edge1
```
"""),
rec("k_cmd_0852", "tencent", "prod", "auto", "Logs", "terse_expert", E,
"`-c` on test, it still log in?",
"""
`-c` does not skip the login. Test always logs in and shows OS, CPU, memory, disk, Docker access, sudo, and installed runtimes. The flag only picks the file. Default is `pskit.yml`.

```
pskit resources onprem servers test edge1 -c pskit.yml
```
"""),
rec("k_cmd_0853", "huawei", "dev", "ask", "YAML", "terse_expert", E,
"`--config` for test edge1, which file?",
"""
`--config` sets the file. The default is `pskit.yml`. Test still logs into NAME and shows OS, CPU, memory, disk, Docker access, sudo, and installed runtimes.

**In the terminal**

1. Test edge1 with the config flag.

```
pskit resources onprem servers test edge1 --config pskit.yml
```
"""),
rec("k_cmd_0854", "oracle", "staging", "auto", "none", "terse_expert", E,
"`NAME` test include sudo and runtimes?",
"""
NAME is logged in. The report includes sudo and installed runtimes, plus OS, CPU, memory, disk, and Docker access. The only flag is `-c` or `--config`.

**In the terminal**

1. Test the saved server edge1.

```
pskit resources onprem servers test edge1 -c pskit.yml
```
"""),
rec("k_cmd_0855", "ibm", "prod", "ask", "Overview", "terse_expert", E,
"`servers test NAME` enough, no other flag?",
"""
NAME is enough. Test logs in with the saved login and shows OS, CPU, memory, disk, Docker access, sudo, and installed runtimes. `-c` is optional.

**In the terminal**

1. Test edge1 with no extra flag.

```
pskit resources onprem servers test edge1
```
"""),
rec("k_cmd_0856", "digitalocean", "dev", "auto", "Setup", "terse_expert", E,
"`pskit.yml` omitted, test still logs in?",
"""
Omitting the flag still logs in. The default file is `pskit.yml` through `-c` or `--config`. Test shows OS, CPU, memory, disk, Docker access, sudo, and installed runtimes for NAME.

```
pskit resources onprem servers test edge1
```
"""),
rec("k_cmd_0857", "cloudflare", "staging", "ask", "Functions", "terse_expert", E,
"`-c pskit.yml` test NAME, what shows up?",
"""
`-c pskit.yml` only picks the file. The login report shows OS, CPU, memory, disk, Docker access, sudo, and installed runtimes.

**In the terminal**

1. Test edge1 against `pskit.yml`.

```
pskit resources onprem servers test edge1 -c pskit.yml
```
"""),
rec("k_cmd_0858", "onprem", "prod", "auto", "Workflows", "terse_expert", E,
"`servers test` missing NAME, does it fail?",
"""
NAME is required, so the command does not run without it. With a name, it logs in and shows OS, CPU, memory, disk, Docker access, sudo, and installed runtimes. Optional flag: `-c` or `--config`.

```
pskit resources onprem servers test edge1
```
"""),
rec("k_cmd_0859", "aws", "dev", "ask", "Resources", "terse_expert", E,
"`NAME` CPU memory disk, that is test?",
"""
Test includes CPU, memory, and disk, and also OS, Docker access, sudo, and installed runtimes. It logs in once. It does not repeat on a timer. The file flag is `-c` or `--config`, default `pskit.yml`.

| Piece | Detail |
| --- | --- |
| Argument | NAME, required |
| File | `-c` or `--config` |

```
pskit resources onprem servers test edge1
```
"""),
rec("k_cmd_0860", "azure", "staging", "auto", "Cluster", "terse_expert", E,
"`--config other.yml` then test that NAME?",
"""
`--config` points test at `other.yml` instead of `pskit.yml`. NAME is still required. The command logs in and shows OS, CPU, memory, disk, Docker access, sudo, and installed runtimes.

**In the terminal**

1. Test edge1 with another config file.

```
pskit resources onprem servers test edge1 --config other.yml
```
"""),
rec("k_cmd_0861", "gcp", "prod", "ask", "Load balancers", "ops_engineer", P,
"`--watch` on servers top change the host?",
"""
`--watch` does not change the host. It only repeats the live CPU, memory, and disk reading. The default is 0, which prints once and stops. A positive number repeats until Ctrl+C. Nothing is deployed or removed, so there is nothing to roll back.

**In the terminal**

1. Read edge1 once, with no repeat.

```
pskit resources onprem servers top edge1
```
"""),
rec("k_cmd_0862", "alibaba", "dev", "auto", "Network map", "ops_engineer", P,
"`--watch 5` on NAME, how to stop?",
"""
Stop `--watch` with Ctrl+C. The flag repeats until then. It only prints live CPU, memory, and disk. It does not restart services, and there is nothing to roll back.

**In the terminal**

1. Repeat the reading for edge1.

```
pskit resources onprem servers top edge1 --watch 5
```
"""),
rec("k_cmd_0863", "tencent", "staging", "ask", "Code", "ops_engineer", P,
"`servers top NAME` once, skip `--watch`?",
"""
Skip `--watch` for one sample. The default is 0, and that prints live CPU, memory, and disk once, then stops. A positive `--watch` repeats until Ctrl+C. The host is not modified.

```
pskit resources onprem servers top edge1
```
"""),
rec("k_cmd_0864", "huawei", "prod", "auto", "Test", "ops_engineer", P,
"`-c` with top, still only live CPU?",
"""
`-c` does not add metrics and does not resize the host. Top stays live CPU, memory, and disk for NAME. The flag only selects the config file. The default file is `pskit.yml`. `--watch` defaults to 0.

**In the terminal**

1. Read edge1 once from `pskit.yml`.

```
pskit resources onprem servers top edge1 -c pskit.yml
```
"""),
rec("k_cmd_0865", "oracle", "dev", "ask", "Deploy", "ops_engineer", P,
"`--watch 0` default, does top loop?",
"""
`--watch` defaults to 0, and 0 does not loop. You get one live CPU, memory, and disk line, then the command stops. A positive number of seconds repeats until Ctrl+C. The server is not changed, so there is no rollback.

```
pskit resources onprem servers top edge1 --watch 0
```
"""),
rec("k_cmd_0866", "ibm", "staging", "auto", "Logs", "ops_engineer", P,
"`pskit.yml` with top, metrics stay read-only?",
"""
The metrics stay read-only. Top prints live CPU, memory, and disk and does not change limits, packages, or services. A bad reading has nothing to roll back. `pskit.yml` is the default for `-c` or `--config`.

**In the terminal**

1. Sample edge1 from the default file.

```
pskit resources onprem servers top edge1 --config pskit.yml
```
"""),
rec("k_cmd_0867", "digitalocean", "prod", "ask", "YAML", "ops_engineer", P,
"`--config` for top NAME in production?",
"""
`--config` is safe in production because top only reads live CPU, memory, and disk. It does not deploy or remove. If NAME does not answer, the command errors instead of printing a healthy line. Default `--watch` is 0, one sample. A positive value runs until Ctrl+C.

**In the terminal**

1. Take one production sample of edge1.

```
pskit resources onprem servers top edge1 --config pskit.yml
```
"""),
rec("k_cmd_0868", "cloudflare", "dev", "auto", "none", "ops_engineer", P,
"`--watch 30` until Ctrl+C, what breaks?",
"""
Nothing on the server is edited. `--watch 30` repeats the CPU, memory, and disk line until Ctrl+C. If the server stops answering, the command errors and the loop ends. There is no deploy to roll back.

**In the terminal**

1. Repeat the edge1 reading until you stop it.

```
pskit resources onprem servers top edge1 --watch 30
```
"""),
rec("k_cmd_0869", "onprem", "staging", "ask", "Overview", "ops_engineer", P,
"`servers top NAME` fail closed if SSH down?",
"""
Yes. If the saved server does not answer, top errors and does not print a normal CPU line. The host is still unchanged. `--watch` defaults to 0. `-c` only picks the file.

```
pskit resources onprem servers top edge1
```
"""),
rec("k_cmd_0870", "aws", "prod", "auto", "Setup", "ops_engineer", P,
"`-c pskit.yml` top NAME, one sample enough?",
"""
One sample is the default. `-c pskit.yml` only selects the file. Leave `--watch` at 0 and top prints live CPU, memory, and disk once. It writes nothing, so there is nothing to roll back.

**In the terminal**

1. Take one sample of edge1.

```
pskit resources onprem servers top edge1 -c pskit.yml
```
"""),
rec("k_cmd_0871", "azure", "dev", "ask", "Functions", "ops_engineer", U,
"`--json` for servers usage of one NAME?",
"""
`--json` prints JSON. Pass NAME to limit the report to that saved server. You get the deploy target, function groups, clusters, load balancers, services, and installed software, with the functions behind each. It reads local files only, so the host is not touched.

**In the terminal**

1. Show JSON usage for edge1.

```
pskit resources onprem servers usage edge1 --json
```
"""),
rec("k_cmd_0872", "gcp", "staging", "auto", "Workflows", "ops_engineer", U,
"`-c` with usage, it touch the server?",
"""
No. `-c` only picks the config file, default `pskit.yml`. Usage reads local files only. It reports deploy target, function groups, clusters, load balancers, services, and installed software. It does not change production.

```
pskit resources onprem servers usage -c pskit.yml
```
"""),
rec("k_cmd_0873", "alibaba", "prod", "ask", "Resources", "ops_engineer", U,
"`pskit.yml` usage show clusters on NAME?",
"""
Yes. With `pskit.yml` as the default file, usage shows clusters for that server, plus the deploy target, function groups, load balancers, services, and installed software, with the functions behind each. It reads local files only.

**In the terminal**

1. Show where edge1 is used.

```
pskit resources onprem servers usage edge1 --config pskit.yml
```
"""),
rec("k_cmd_0874", "tencent", "dev", "auto", "Cluster", "ops_engineer", U,
"`servers usage` with no NAME, every server?",
"""
Omit NAME and the report covers every saved server. Pass a name to limit it. You see the deploy target, function groups, clusters, load balancers, services, and installed software. Local files only, so the hosts stay as they are. `--json` is optional.

**In the terminal**

1. Report every saved server.

```
pskit resources onprem servers usage
```
"""),
rec("k_cmd_0875", "huawei", "staging", "ask", "Load balancers", "ops_engineer", U,
"`--config` usage before I drop a server?",
"""
Run usage first so you can see what still points at the server. `--config` only selects the file. The report lists the deploy target, function groups, clusters, load balancers, services, and installed software. It reads local files only and does not remove anything.

**In the terminal**

1. See where edge1 is used, from `pskit.yml`.

```
pskit resources onprem servers usage edge1 --config pskit.yml
```
"""),
rec("k_cmd_0876", "oracle", "prod", "auto", "Network map", "aws_migrator", U,
"`--json` usage like an IAM access report?",
"""
No. `--json` is not IAM. It prints JSON for where each saved server is used: deploy target, function groups, clusters, load balancers, services, and installed software, with the functions behind each. The command reads local files only. There is no IAM call.

```
pskit resources onprem servers usage --json
```
"""),
rec("k_cmd_0877", "ibm", "dev", "ask", "Code", "aws_migrator", U,
"`-c pskit.yml` usage, not a Lambda list?",
"""
Not a Lambda list. `-c pskit.yml` selects the config file. Usage reads local files and shows where each saved server is used, including functions behind the deploy target, clusters, load balancers, services, and installed software.

**In the terminal**

1. Print that local report from `pskit.yml`.

```
pskit resources onprem servers usage -c pskit.yml
```
"""),
rec("k_cmd_0878", "digitalocean", "staging", "auto", "Test", "aws_migrator", U,
"`servers usage NAME` instead of an SQS mapping?",
"""
This is not an SQS mapping. Pass NAME and the command shows where that saved server is used in local files: deploy target, function groups, clusters, load balancers, services, and installed software. `--json` is optional. Nothing is queued.

```
pskit resources onprem servers usage edge1
```
"""),
rec("k_cmd_0879", "cloudflare", "prod", "ask", "Deploy", "aws_migrator", U,
"`pskit.yml` usage before deploy, which servers?",
"""
Before a deploy, usage reads local files and shows which saved servers are already used. That includes the deploy target, function groups, clusters, load balancers, services, and installed software. It is not a Step Functions review. The default file is `pskit.yml`.

**In the terminal**

1. List usage for every saved server.

```
pskit resources onprem servers usage --config pskit.yml
```
"""),
rec("k_cmd_0880", "onprem", "dev", "auto", "Logs", "aws_migrator", U,
"`--json` off, usage still list functions?",
"""
Yes. With `--json` left off you still get the report, just not as JSON. It includes the functions behind each use, plus the deploy target, function groups, clusters, load balancers, services, and installed software. Local files only. NAME is optional.

```
pskit resources onprem servers usage edge1 -c pskit.yml
```
"""),
]


if __name__ == "__main__":
    raise SystemExit("Not a generator. Conversations are already in shard_020.jsonl and shard_021.jsonl.")
