# Cloud backtest compute: platform comparison

REVISION: r2 (Codex corrective review) — the r1 cost table applied Modal's A10
GPU per-second rate to this CPU-only workload, understating Modal's true cost
by ~28× (correctly, in the wrong direction for the actual recommendation: it
made Modal look artificially *more* expensive than it is). r2 recomputes
Modal and AWS Fargate costs from each platform's verified current CPU+memory
pricing (modal.com/pricing and aws.amazon.com/fargate/pricing, both checked
2026-07-07) and revises the recommendation accordingly. Beam/Fal.ai/Anyscale
figures are carried over from r1 and are explicitly flagged as not
independently re-verified in this pass.

Evaluated for: embarrassingly parallel CPU-bound Python backtests (~30min each,
74 concurrent workers, complex deps torch+xgboost+pandas+8 internal subrepos,
~3GB persistent data volume, streaming results back, $5/sweep budget, 4 GiB
memory per worker).

---

## Comparison matrix

| Criterion | Modal | Beam (beam.cloud) | Fal.ai | Anyscale (Ray) | AWS Batch (Fargate) |
|-----------|-------|--------------------|--------|----------------|---------------------|
| **Pricing model** | Per-physical-core·s ($0.0000131/core·s, 1 core = 2 vCPU equiv.) + $0.00000222/GiB·s memory [modal.com/pricing](https://modal.com/pricing) (verified 2026-07-07; **r1 wrongly used the $0.000306/sec A10 GPU rate here**) | Per-core·h ($0.19/core·h ≈ $0.0000528/core·s) [beam.cloud/pricing](https://www.beam.cloud/pricing) (not re-verified in r2) | Per-second by machine tier ($0.0003–0.0006/s for CPU) [fal.ai/pricing](https://fal.ai/pricing) (not re-verified in r2) | Per-vCPU·min (~$0.00006/min, varies by instance) [anyscale.com/pricing](https://www.anyscale.com/pricing) (not re-verified in r2; see caveat below) | Per-vCPU·s ($0.000011244/vCPU·s) + $0.000001235/GB·s memory [aws.amazon.com/fargate/pricing](https://aws.amazon.com/fargate/pricing/) (verified 2026-07-07; Spot ~70% off) |
| **Min billing** | Per-millisecond | Per-second | Per-second | Per-minute | Per-second |
| **Cold start** | ~1–5s (warm containers ~180ms with keep-warm) [modal.com/docs/guide/cold-start](https://modal.com/docs/guide/cold-start) | <1s (custom runtime optimized for fast boot) [beam.cloud/blog/top-serverless-gpu-providers](https://www.beam.cloud/blog/top-serverless-gpu-providers) | Not benchmarked for CPU; GPU ~2–5s | 30–120s (cluster spin-up, not per-container) | 20–60s (ENI + image pull + bootstrap) [aws.plainenglish.io](https://aws.plainenglish.io/taming-cold-starts-on-aws-fargate-the-architecture-behind-sub-5-second-task-launches-622ebd73b051) |
| **Persistent volume** | Yes — `modal.Volume`, supports `.commit()` for immutable snapshots [modal.com/docs](https://modal.com/docs/guide/volumes) | Yes — distributed volumes, shared across apps; eventual consistency ~60s [docs.beam.cloud/data/volumes](https://docs.beam.cloud/v2/data/volume) | Yes — `/data` mount, multi-layer cache (NVMe → DC cache → object store) [docs.fal.ai](https://docs.fal.ai/serverless/development/use-persistent-storage) | Via cloud object storage (S3/GCS); no built-in volume abstraction [docs.anyscale.com](https://docs.anyscale.com/configuration) | EFS or S3 mount; no built-in volume concept in Batch itself |
| **Custom image** | Yes — Python-native image builder (`modal.Image.debian_slim().pip_install(...)`) or Dockerfile [modal.com/docs](https://modal.com/docs/guide/custom-container) | Yes — Dockerfile or base image from Docker Hub/ECR; Debian-only [docs.beam.cloud](https://docs.beam.cloud/development/custom-containers) | Yes — Dockerfile import or `fal.App` class [docs.fal.ai](https://docs.fal.ai/compute) | Yes — extend Anyscale base images with Dockerfile [docs.anyscale.com](https://docs.anyscale.com/configuration/dependency-management/dependency-byod/) | Yes — any Docker image via ECR |
| **Max concurrency** | `.map()` cap: 1000 concurrent inputs; container limit configurable [modal.com/docs/guide/scale](https://modal.com/docs/guide/scale) | Configurable via `QueueDepthAutoscaler`; no documented hard cap [docs.beam.cloud](https://docs.beam.cloud/v2/scaling/concurrent-inputs) | Not documented for CPU burst use case | Depends on cluster size; autoscales but needs cluster spin-up | Effectively unlimited (Fargate capacity); queue-based dispatch |
| **Failure handling** | `retries=N` per function; timeout per invocation; OOM triggers retry [modal.com/docs](https://modal.com/docs/reference/modal.Function) | Built-in: 3 retries on failure (OOM, exception); task moves to failed state [docs.beam.cloud](https://docs.beam.cloud/v2/task-queue/running-tasks) | Not documented for custom CPU workloads | Ray has built-in task retry + fault tolerance [docs.ray.io](https://docs.ray.io/) | Retry via job definition `attempts` field; spot interruption = retry |
| **Python SDK** | Excellent — decorator-based, `.map()`/`.starmap()` for parallel, Python-native image builder, live reload [modal.com](https://modal.com/) | Good — decorator-based, task queues, hot-reload; less mature ecosystem [docs.beam.cloud](https://docs.beam.cloud/getting-started/quickstart) | Good for inference — `fal.App` class; less oriented to batch compute [docs.fal.ai](https://docs.fal.ai/compute) | Ray API — powerful but heavy; designed for distributed computing, not serverless batch [ray.io](https://www.ray.io/) | No Python SDK for dispatch; boto3 + JSON job defs; imperative, not declarative |
| **Vendor lock-in** | Medium — proprietary SDK, but worker code is standard Python; easy to run locally | Low–Medium — open-source engine (beta9); can self-host [github.com/beam-cloud/beta9](https://github.com/beam-cloud/beta9) | Medium — proprietary; focused on GenAI inference, not general compute | Medium — Ray is open-source; Anyscale is proprietary managed layer | Low — standard Docker + AWS APIs; portable to any container platform |
| **Free tier** | $30/month credits [modal.com/pricing](https://modal.com/pricing) | 10h GPU free; CPU credits unclear [beam.cloud/pricing](https://www.beam.cloud/pricing) | Credits for model APIs; custom compute unclear [fal.ai/pricing](https://fal.ai/pricing) | Free account but no documented free compute credits [anyscale.com/pricing](https://www.anyscale.com/pricing) | None (pay-as-you-go from $0) |

---

## Cost estimate for our 75-variant sweep (2 vCPU + 4 GiB × 30min × 74 workers)

Modal and AWS Fargate rows are recomputed with **verified** current CPU+memory
pricing (both checked 2026-07-07) and include memory cost, which the r1 table
omitted entirely for every platform. Beam/Fal.ai/Anyscale are carried over
from r1 unchanged (not re-verified) — treat those three as lower-confidence.

| Platform | Unit price | Calculation | Est. cost |
|----------|-----------|-------------|-----------|
| **Modal** | $0.0000131/core·s + $0.00000222/GiB·s | 74 × [(1 core × 1800s × $0.0000131) + (4 GiB × 1800s × $0.00000222)] | **$2.93** |
| **Beam** (not re-verified) | $0.19/core·h | 74 × 2 cores × 0.5h × $0.19 | **$14.06** |
| **Fal.ai** (not re-verified) | ~$0.0004/s (CPU-M est.) | 74 × 1800s × $0.0004 | **$53.28** |
| **Anyscale** (not re-verified) | ~$0.0036/vCPU·h (low-end) | 74 × 2 vCPU × 0.5h × $0.0036 | **$0.27** |
| **AWS Batch (Fargate on-demand)** | $0.000011244/vCPU·s + $0.000001235/GB·s | 74 × [(2 vCPU × 1800s × $0.000011244) + (4 GB × 1800s × $0.000001235)] | **$3.66** |
| **AWS Batch (Fargate Spot)** | ~70% off on-demand | $3.66 × 0.30 | **$1.10** |

**r1→r2 correction**: the r1 table applied Modal's A10 **GPU** rate
($0.000306/sec) to this CPU workload and omitted memory cost for every
platform. Modal's real per-physical-core rate is $0.0000131/sec — about
23× lower than the mistaken r1 figure — and its memory-inclusive real cost
for this workload is **$2.93/sweep**, not $81.56. Once AWS Fargate's memory
cost is also included, Modal is now *cheaper* than on-demand Fargate ($3.66)
and only ~2.7× Fargate Spot ($1.10) — not the ~27× gap r1 claimed. See the
main RFC (`2026-07-07-cloud-backtest-compute.md` §3.3) for the revised
platform recommendation this correction drives.

The Anyscale price looks unrealistically low — their $0.00006/min figure may be a
platform fee on top of underlying cloud compute, or for the smallest instance type
that wouldn't run our workload. **Could not verify** from public docs; unchanged
from r1, still unresolved.

---

## Platform-specific notes

### Modal
- **Strengths**: Best Python SDK by far. `.map()` is exactly our dispatch pattern.
  Volume `.commit()` gives immutable snapshots (critical for result reproducibility).
  Millisecond billing. $30/mo free tier.
- **Weaknesses**: Real CPU+memory cost is $2.93/sweep — corrected from r1's
  mistaken $81.56 (GPU-rate bug). This is now *cheaper* than on-demand Fargate
  and only ~2.7× Fargate Spot, not a "27× premium." Vendor lock-in (proprietary
  SDK) is the more relevant remaining weakness than cost.
- **Fit for us**: Excellent DX, and cost-competitive once correctly priced.

### Beam (beam.cloud)
- **Strengths**: Open-source engine (beta9) = self-hostable = zero lock-in escape
  hatch. Sub-1s cold starts. Built-in 3× retry. Distributed volumes.
- **Weaknesses**: Younger ecosystem. Volume eventual consistency (60s) could matter
  if workers write intermediate results (ours don't). CPU pricing ~$0.38/core·h
  is still ~5× Modal's corrected rate and well above Fargate. Documentation
  less comprehensive than Modal. (Pricing not re-verified in r2 — see caveat
  above.)
- **Fit for us**: Interesting for the open-source angle, but not cost-competitive
  with the corrected Modal/Fargate numbers.

### Fal.ai
- **Strengths**: Fast inference platform. Good persistent storage with multi-layer
  cache.
- **Weaknesses**: Focused on GenAI inference (image/video generation), not general
  CPU batch compute. CPU instance pricing poorly documented. No `.map()` equivalent
  for batch dispatch. Least relevant platform for our use case.
- **Fit for us**: Wrong tool for the job. Built for GPU inference, not CPU backtests.

### Anyscale (Ray)
- **Strengths**: Ray is the gold standard for distributed Python. Handles complex
  DAGs, not just embarrassingly parallel. Open-source core (Ray). Good for workloads
  that might evolve to need inter-worker communication.
- **Weaknesses**: Cluster spin-up is slow (30–120s) — designed for long-running
  clusters, not burst serverless. Overhead of Ray runtime for simple parallel map
  is unjustified. Pricing opaque (no public per-vCPU rates). No free tier with
  meaningful compute. Learning curve is steep for simple map/reduce.
- **Fit for us**: Over-engineered for embarrassingly parallel. Right tool if we ever
  need distributed training or complex DAGs, but we don't.

### AWS Batch (Fargate)
- **Strengths**: Cheap Spot pricing (~$1.10/sweep with memory included). No
  vendor lock-in (standard Docker). Effectively unlimited concurrency. Mature,
  battle-tested. Fargate Spot = 70% savings for interrupt-tolerant work (ours is).
- **Weaknesses**: Worst DX (boto3 + JSON job definitions, no Python-native SDK).
  Slowest cold starts (20–60s, irrelevant for 30-min jobs). Significant one-time
  infra setup (ECR repo, job definitions, compute environments, IAM roles).
  No built-in volume (need EFS or S3 mount). On-demand Fargate ($3.66/sweep,
  memory included) is actually *more expensive* than Modal ($2.93/sweep) once
  correctly priced.
- **Fit for us**: Spot is cheapest, but the margin over Modal is now small
  (~$1.83/sweep, not ~$81/sweep) and doesn't clearly outweigh the DX/setup
  cost for a 1-person team.

---

## Recommendation (r2, corrected)

**Modal as primary AND production platform.** The r1 recommendation
("two-tier: Modal for prototyping, AWS Batch Spot for production") was driven
entirely by a pricing bug (§ above) that made Modal look ~27× more expensive
than it actually is. With correct CPU+memory pricing, Modal ($2.93/sweep) is
cheaper than on-demand Fargate ($3.66/sweep) and only ~2.7× Fargate Spot
($1.10/sweep) — a gap of ~$1.83/sweep, or roughly $13-18/month at the
project's actual 2-7 sweeps/month cadence. That gap is small enough that
Modal's DX advantage (best-in-class Python SDK, no IAM/VPC/ECR setup, faster
iteration for a 1-person team) is the deciding factor, not cost.

### Rationale

1. **Our workload is CPU-bound, long-running (30min), and embarrassingly parallel.**
   Cold start is irrelevant (<3% of runtime) for platform choice, but DX and
   setup cost are not irrelevant for a 1-person team.

2. **Cost difference is now ~$1.83/sweep (Modal vs Fargate Spot), not 27×.**
   At 7 sweeps/month, that's ~$20/month, not ~$568/month. This does not
   justify eating AWS Batch's one-time IAM/VPC/ECR/job-definition setup cost
   (~4-8h of engineering time) up front.

3. **Modal is actually cheaper than on-demand Fargate** ($2.93 vs $3.66), so
   "AWS Batch is the cheap option" is only true if the Spot market is used —
   which itself carries interruption risk this workload has to tolerate.

4. **Modal's DX makes iteration 10× faster during development and ongoing
   operation.** Building and debugging the worker function, testing data sync,
   validating result schemas — all faster with `.map()` than with boto3 job
   definitions, and this benefit recurs every time the sweep toolchain changes,
   not just once during setup.

### Proposed approach

| Phase | Platform | Why |
|-------|----------|-----|
| Now | **Modal** | Cost-competitive once correctly priced; best DX; $30/mo free tier covers ~10 sweeps |
| Escape hatch, if needed later | **AWS Batch Spot** (or Anyscale/Ray) | Available via the abstraction layer if sweep volume grows enough that the ~$1.83/sweep gap starts to matter, or if Modal's pricing/limits become unfavorable |
| Bridge: abstraction layer | Backend interface | `BacktestExecutor` protocol with `dispatch()`/`collect()` — swap Modal → Batch without changing controller logic, if that day comes |

The abstraction layer is still valuable even though Modal is now the
straightforward choice: it keeps the migration option open cheaply, and it
is what lets Phase 1 (§9 of the main RFC) ship value on the local backend
before any cloud backend is even built.

### If forced to pick ONE platform

**Modal.** At the corrected pricing, cost is no longer the reason to avoid
it, and its DX is the best fit for a 1-person team's iteration speed. AWS
Batch Spot remains the fallback if sweep volume or pricing changes enough
to revisit this.

### Fal.ai verdict

**Eliminated.** Wrong tool — built for GenAI inference, not CPU batch compute.

### Anyscale verdict

**Eliminated.** Over-engineered for embarrassingly parallel work. Revisit only if we
need distributed training or complex DAGs (we don't).

---

## Sources

- [Modal pricing](https://modal.com/pricing)
- [Modal cold start docs](https://modal.com/docs/guide/cold-start)
- [Modal scaling docs](https://modal.com/docs/guide/scale)
- [Beam pricing](https://www.beam.cloud/pricing)
- [Beam volumes](https://docs.beam.cloud/v2/data/volume)
- [Beam task queue](https://docs.beam.cloud/v2/task-queue/running-tasks)
- [Beam custom containers](https://docs.beam.cloud/development/custom-containers)
- [Beam cold start benchmark](https://www.beam.cloud/blog/top-serverless-gpu-providers)
- [Fal.ai pricing](https://fal.ai/docs/documentation/model-apis/pricing)
- [Fal.ai persistent storage](https://docs.fal.ai/serverless/development/use-persistent-storage)
- [Anyscale pricing](https://www.anyscale.com/pricing)
- [Anyscale custom images](https://docs.anyscale.com/configuration/dependency-management/dependency-byod/)
- [AWS Fargate pricing](https://aws.amazon.com/fargate/pricing/)
- [Fargate cold start analysis](https://aws.plainenglish.io/taming-cold-starts-on-aws-fargate-the-architecture-behind-sub-5-second-task-launches-622ebd73b051)
- [Serverless GPU comparison (RunPod)](https://www.runpod.io/articles/guides/top-serverless-gpu-clouds)
- [Modal alternatives (Spheron)](https://www.spheron.network/blog/modal-alternatives/)
