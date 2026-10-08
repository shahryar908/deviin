# Orchestrator (deferred)

The reference `rshdhere/devin` uses a Go orchestrator that owns `Sandbox`
CRs and reconciles desired vs. actual sandboxes. We don't have K8s CRDs
here yet, so the current lifecycle is driven directly:

- VM lifecycle: `cmd/vmm` (`create`/`destroy`/`status`) in
  `backend/sandboxes_infra/cmd/vmm`. One VM per session, no warm pool yet.
- Sandbox images ("runtime images"): pre-baked ext4 files under
  `/home/shahryar/firecracker-lab/rootfs`. Selection happens in
  `agent_harness/tools.py` (`create_sandbox` picks the rootfs by detected
  stack; default is `base-dev.ext4`).
- A lightweight reconciliation loop (poll `vmm status`, recreate on
  failure, cap concurrency) is the intended replacement for the Go
  orchestrator and is the next infra piece.

Once we add an actual reconciler it should:
1. List desired sessions from the agent-side store (SQLite, later).
2. Ensure exactly one healthy VM per session (`vmm status` / envd
   `/health`).
3. Tear down sandboxes whose sessions ended.
