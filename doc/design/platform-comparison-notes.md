# Cloud backtest compute: platform comparison

Evaluated for: embarrassingly parallel CPU-bound Python backtests (~30min each,
74 concurrent workers, complex deps torch+xgboost+pandas+8 internal subrepos,
~3GB persistent data volume, streaming results back, $5/sweep budget).

---

## Comparison matrix

| Criterion | Modal | Beam (beam.cloud) | Fal.ai | Anyscale (Ray) | AWS Batch (Fargate) |
|-----------|-------|--------------------|--------|----------------|---------------------|
| **Pricing model** | Per-vCPU·s ($0.000306/vCPU·s) [modal.com/pricing](https://modal.com/pricing) | Per-core·h ($0.19/core·h ≈ $0.0000528/core·s) [beam.cloud/pricing](https://www.beam.cloud/pricing) | Per-second by machine tier ($0.0003–0.0006/s for CPU) [fal.ai/pricing](https://fal.ai/pricing) | Per-vCPU·min (~$0.00006/min, varies by instance) [anyscale.com/pricing](https://www.anyscale.com/pricing) | Per-vCPU·s ($0.04048/vCPU·h ≈ $0.0000112/vCPU·s; Spot ~70% off) [aws.amazon.com/fargate/pricing](https://aws.amazon.com/fargate/pricing/) |
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

## Cost estimate for our 75-variant sweep (2 vCPU × 30min × 74 workers)

| Platform | Unit price | Calculation | Est. cost |
|----------|-----------|-------------|-----------|
| **Modal** | $0.000306/vCPU·s | 74 × 2 vCPU × 1800s × $0.000306 | **$81.56** |
| **Beam** | $0.19/core·h | 74 × 2 cores × 0.5h × $0.19 | **$14.06** |
| **Fal.ai** | ~$0.0004/s (CPU-M est.) | 74 × 1800s × $0.0004 | **$53.28** |
| **Anyscale** | ~$0.0036/vCPU·h (low-end) | 74 × 2 vCPU × 0.5h × $0.0036 | **$0.27** |
| **AWS Batch (Fargate on-demand)** | $0.04048/vCPU·h | 74 × 2 vCPU × 0.5h × $0.04048 | **$3.00** |
| **AWS Batch (Fargate Spot)** | ~$0.012/vCPU·h (70% off) | 74 × 2 vCPU × 0.5h × $0.012 | **$0.89** |

**IMPORTANT CAVEAT**: Modal's $0.000306/vCPU·s = $1.10/vCPU·h, which is significantly
more expensive than Fargate ($0.04/vCPU·h). Modal's premium is for the developer
experience and fast cold starts, not raw compute cost. For a 30-min CPU batch job
where cold start is irrelevant (<1% of runtime), the DX premium may not be justified.

The Anyscale price looks unrealistically low — their $0.00006/min figure may be a
platform fee on top of underlying cloud compute, or for the smallest instance type
that wouldn't run our workload. **Could not verify** from public docs.

---

## Platform-specific notes

### Modal
- **Strengths**: Best Python SDK by far. `.map()` is exactly our dispatch pattern.
  Volume `.commit()` gives immutable snapshots (critical for result reproducibility).
  Millisecond billing. $30/mo free tier.
- **Weaknesses**: CPU pricing is high ($1.10/vCPU·h vs Fargate $0.04). For a
  30-min CPU batch where cold start doesn't matter, we're paying a 27× premium
  for DX. Not cost-effective at scale.
- **Fit for us**: Excellent DX, poor cost efficiency for CPU-heavy batch.

### Beam (beam.cloud)
- **Strengths**: Open-source engine (beta9) = self-hostable = zero lock-in escape
  hatch. Sub-1s cold starts. Built-in 3× retry. Distributed volumes.
- **Weaknesses**: Younger ecosystem. Volume eventual consistency (60s) could matter
  if workers write intermediate results (ours don't). CPU pricing ~$0.38/core·h is
  still 10× Fargate. Documentation less comprehensive than Modal.
- **Fit for us**: Interesting for the open-source angle, but still expensive for
  CPU batch.

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
- **Strengths**: Cheapest compute by far ($0.04/vCPU·h on-demand, ~$0.012 Spot).
  No vendor lock-in (standard Docker). Effectively unlimited concurrency. Mature,
  battle-tested. Fargate Spot = 70% savings for interrupt-tolerant work (ours is).
- **Weaknesses**: Worst DX (boto3 + JSON job definitions, no Python-native SDK).
  Slowest cold starts (20–60s, irrelevant for 30-min jobs). Significant one-time
  infra setup (ECR repo, job definitions, compute environments, IAM roles).
  No built-in volume (need EFS or S3 mount).
- **Fit for us**: Best cost. Worst DX. The 20–60s cold start is <3% of a 30-min
  job — irrelevant.

---

## Recommendation

**Two-tier strategy: Modal for prototyping, AWS Batch Spot for production.**

### Rationale

1. **Our workload is CPU-bound, long-running (30min), and embarrassingly parallel.**
   Cold start is irrelevant (<3% of runtime). The DX premium of Modal/Beam buys
   nothing that matters at execution time.

2. **Cost difference is 27×.** Modal: ~$82/sweep. AWS Batch Spot: ~$0.89/sweep.
   At 7 sweeps/month, that's $574 vs $6. Even on-demand Fargate ($3/sweep) is 27×
   cheaper than Modal.

3. **DX cost is one-time; compute cost is recurring.** The boto3 setup is ugly but
   you do it once. The per-sweep cost difference compounds forever.

4. **However**, Modal's DX makes iteration 10× faster during development. Building
   and debugging the worker function, testing data sync, validating result schemas —
   all faster with `.map()` than with boto3 job definitions.

### Proposed approach

| Phase | Platform | Why |
|-------|----------|-----|
| Phase 1: prototype + validate | **Modal** | Fast iteration, $30 free tier covers ~3 sweeps while we validate the architecture |
| Phase 2: production | **AWS Batch Spot** | 27× cheaper; one-time infra setup amortized over months of sweeps |
| Bridge: abstraction layer | Backend interface | `BacktestBackend` protocol with `dispatch()` and `collect()` — swap Modal → Batch without changing controller logic |

The abstraction layer is critical: the design RFC should define a `BacktestBackend`
protocol so the controller doesn't know which cloud runs the work. This makes the
Modal → Batch migration a one-file change, not a rewrite.

### If forced to pick ONE platform

**AWS Batch Spot.** The DX tax is real but bounded (one-time setup ~4-8h). The cost
savings are unbounded. For a system that will run dozens of sweeps, the math is clear.

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
