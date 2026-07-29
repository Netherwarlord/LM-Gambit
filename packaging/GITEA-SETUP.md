# Running CI on a self-hosted Gitea

The workflows in `.gitea/workflows/` mirror the GitHub ones in
`.github/workflows/`, with one structural difference: **releases build on a
single Linux runner** rather than three.

That is not a compromise. `packaging/build.py` normalises everything that would
otherwise vary by build host — tar member modes, uid/gid, and launcher line
endings — so the Windows `.zip` produced on Linux is equivalent to one produced
on Windows. Dropping the matrix also drops the artifact hand-off between jobs
and the race of three jobs racing to create the same release.

Multi-OS runners would still be worth adding for *testing*. Building does not
need them.

---

## 1. Enable Actions

In `app.ini`:

```ini
[actions]
ENABLED = true
DEFAULT_ACTIONS_URL = https://github.com
```

`DEFAULT_ACTIONS_URL` is where `actions/checkout` and friends are fetched from.
Public repositories clone anonymously, so a locked or absent GitHub account does
not affect this. Restart Gitea afterwards.

**Pin `actions/upload-artifact` to v3.** From v4 the action refuses to run
against any host that is not github.com — it treats everything else as GitHub
Enterprise and aborts with `GHESNotSupportedError` before uploading anything.
The check lives inside the action, so Gitea's own artifact support is
irrelevant; v4 cannot work here at any Gitea version. The same applies to
`download-artifact`.

## 2. Register a runner

Get a registration token from **Site Administration → Actions → Runners**, then:

```bash
docker run -d --restart always --name gitea-runner \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /srv/gitea-runner:/data \
  -e GITEA_INSTANCE_URL=https://git.example.lan \
  -e GITEA_RUNNER_REGISTRATION_TOKEN=<token> \
  -e GITEA_RUNNER_LABELS=ubuntu-latest:docker://catthehacker/ubuntu:act-22.04 \
  gitea/act_runner:latest
```

The label mapping is the part that matters. `runs-on: ubuntu-latest` in the
workflow resolves through it to a container image. `catthehacker/ubuntu` images
carry the tooling GitHub's hosted runners have; the bare `ubuntu:22.04` image
does not, and `actions/setup-python` will fail on it for want of basic
utilities.

Mounting the Docker socket lets the runner start job containers. It also grants
effective root on the host, which is the usual trade — acceptable on a machine
that only serves this purpose, worth knowing about regardless.

## 3. Add the release token

Releases are published through Gitea's own API by
`packaging/publish_gitea.py`, so the job needs a token:

1. **Settings → Applications → Generate New Token**, scope `write:repository`.
2. In the repository: **Settings → Actions → Secrets → Add Secret**, named
   `GITEA_TOKEN`.

`GITEA_URL` and `GITEA_REPOSITORY` come from `github.server_url` and
`github.repository`, which Gitea populates for compatibility. Nothing else to
configure.

## 4. If the runner cannot reach Gitea

Worth understanding before it bites, because the failure is confusing.

`ROOT_URL` is what Gitea advertises to the world, and job containers inherit it
as `github.server_url` — so `actions/checkout` and `publish_gitea.py` both call
the *public* address, even though the runner may be sitting on the same host as
Gitea. When that address only resolves outside your network, jobs fail at
checkout with a DNS or connection error while Gitea itself is plainly fine.

Two ways out.

**Let it hairpin.** If your router does NAT loopback, the request leaves and
comes straight back to the reverse proxy, and nothing needs configuring. Try
this first — it is the common case and costs nothing to test.

**Pin the name to a local address.** Map the public hostname to your reverse
proxy's LAN address, on the runner and on the containers it spawns:

```yaml
services:
  gitea-runner:
    extra_hosts:
      - "git.example.lan:192.0.2.10"      # the reverse proxy, not Gitea
```

and in act_runner's `config.yaml`, so job containers inherit it:

```yaml
container:
  options: --add-host=git.example.lan:192.0.2.10
```

The trap is which host to point at. It must be whatever terminates the scheme
in `ROOT_URL`. If `ROOT_URL` is `https://…` then the override has to reach
something serving TLS on 443 — your reverse proxy. Pointing it straight at the
Gitea host sends an HTTPS request to a port where Gitea is only speaking plain
HTTP, and the connection is refused.

Also: do not put Gitea behind a forward-auth proxy (Authentik outposts,
oauth2-proxy and friends). Runners authenticate with their own token and cannot
satisfy an SSO interstitial, so registration and every job will fail. Use the
identity provider as an OIDC source *inside* Gitea's own login instead.

## 5. Cut a release

Dry run first — `workflow_dispatch` builds all three archives and prints their
sizes without creating anything:

**Actions → release → Run workflow**

Then tag:

```bash
git tag v2.0.0 && git push origin v2.0.0
```

That leaves a **draft** release with the three archives attached. Review, then
publish from the web UI. Re-running the workflow on the same tag replaces the
assets rather than duplicating them, so a half-finished publish is safe to
retry.

To publish immediately instead of drafting, add `--publish` to the
`publish_gitea.py` invocation in `.gitea/workflows/release.yml`.

---

## Notes for a DL380p Gen8

Those E5-2600 v1/v2 chips are **x86-64-v2** — they have AVX but not AVX2, which
arrived with the v3 (Haswell) generation. Two consequences:

- **Pick the distribution with that in mind.** Debian, Ubuntu and RHEL 9 target
  a baseline these CPUs meet. RHEL 10 and recent Fedora raised their floor to
  x86-64-v3 and will not run. Node 22 and Docker are fine either way.

- **Don't plan to run benchmarks on this box.** Many prebuilt
  `llama-cpp-python` wheels assume AVX2, and the ones that don't will be slow
  on 2012 silicon regardless. It is a fine CI and git server; keep inference on
  the workstation. Nothing in `tests_py/` needs `llama-cpp-python`, which is
  exactly why `requirements-ci.txt` omits it.

Two dual-socket Sandy/Ivy Bridge sockets have plenty of throughput for Gitea
plus a runner — this is an I/O and RAM workload, not a vector-math one.
