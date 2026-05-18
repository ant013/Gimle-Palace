# Sandbox preflight

- Date: `2026-05-06`

## Unsandboxed control

```bash
/Library/Developer/CommandLineTools/usr/bin/python3 -c 'import socket; socket.create_connection(('"'"'1.1.1.1'"'"', 443), timeout=5).close(); print('"'"'UNSANDBOXED_CONTROL_OK'"'"')'
```

Result: `PASS`

```text
UNSANDBOXED_CONTROL_OK
```

## Sandboxed probe

```bash
/usr/bin/sandbox-exec -p '(version 1) (allow default) (deny network*)' /Library/Developer/CommandLineTools/usr/bin/python3 -c 'import socket; socket.create_connection(('"'"'1.1.1.1'"'"', 443), timeout=5).close(); print('"'"'SANDBOXED_PROBE_OK'"'"')'
```

Result: `PASS`

## Observed stderr

```text
Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/socket.py", line 843, in create_connection
    raise err
  File "/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/socket.py", line 831, in create_connection
    sock.connect(sa)
PermissionError: [Errno 1] Operation not permitted
```

## Interpretation

The preflight passes only if the same network connect succeeds unsandboxed and then fails under `sandbox-exec` with an explicit sandbox denial (`PermissionError` / `Operation not permitted`).
