# ecomm-search 因 OOM 导致索引重建中断与请求延迟飙升

## 适用范围
- **仅适用于服务 `ecomm-search`**。
- 不适用于因网络抖动、下游依赖（如 catalog-api）超时、或 Lucene 段合并异常引发的延迟问题。
- 不适用于内存未超限但 CPU 持续 100% 的场景（该场景应走 CPU 饱和类 runbook）。

## 症状
- Pod 状态显示 `1/2 ready`，`healthy=False`，`restarts ≥ 5`（K8s `kubectl get pod ecomm-search-*`）。
- 应用日志持续出现 `[WARN] catalog index rebuild stalled` 和 `[ERROR] degraded request latency spike`。
- Metrics 中 `error_rate` 突增至 ≥ 0.20，P99 请求延迟 > 3s（持续 ≥ 2 分钟）。
- `/data/search-index` 目录下存在陈旧索引文件（mtime > 24h），且无 `.rebuild.lock` 或 `.snapshot.done` 标记文件。

## 诊断（先确认再动手）
1. 执行 `kubectl get pod -l app=ecomm-search -o wide`，确认存在 `RESTARTS ≥ 5` 且 `READY` 状态为 `1/2` 的 Pod。
2. 执行 `kubectl describe pod <pod-name>`，检查 `Events` 虽无显式 OOMKilled 记录，但结合 `Last State: Terminated (OOMKilled)` 或 `Exit Code: 137` 确认 OOM。
3. 查看最近日志：`kubectl logs <pod-name> --previous | grep -E "(OOM|stalled|latency spike)" | tail -10`，确认 `[WARN] catalog index rebuild stalled` 与重启时间窗口重合。
4. 登录 Pod（若仍存活）：`kubectl exec -it <pod-name> -- sh -c "ls -la /data/search-index && stat /data/search-index"`，验证索引目录修改时间早于上次部署时间，且无有效 snapshot 标记。

## 根因
Pod 内存配置不足（当前 limit=2Gi），在全量索引重建期间内存持续超限，触发 Kubernetes OOMKiller 强制终止容器，导致重建流程中断、索引陈旧、查询性能断崖式下降。

## 处置（标准修复）
- **人工执行索引重建**：  
  使用 `search-index-rebuild` write tool（service: `ecomm-search`），参数：`--from-snapshot=true --force=true --timeout=600`，风险级别：**高**（会短暂中断写入并占用全部内存，需确保集群有 ≥ 4Gi 可用内存余量）。  
- **同步调高内存 limit**（必须紧随重建后执行）：  
  修改 Helm values 中 `resources.limits.memory = "4Gi"`，执行 `helm upgrade ecomm-search ./charts/ecomm-search -f values-prod.yaml`。

## 验证（修复后必须满足）
- Pod `READY` 状态恢复为 `2/2`，`RESTARTS` 归零且 5 分钟内无新增重启。
- 日志中连续 3 分钟无 `[WARN] catalog index rebuild stalled`，出现 `[INFO] index rebuild completed successfully`。
- Metrics 中 `error_rate < 0.01`，P99 延迟回落至 `< 300ms` 并稳定 ≥ 10 分钟。
- `/data/search-index` 下存在 `snapshot_*.tar.gz` 与 `.snapshot.done` 文件，mtime ≤ 5 分钟前。

## 勿用手段（易误判或无效）
- **不要**执行 `search-index-optimize` tool：该工具仅优化段合并，无法修复因 OOM 中断导致的索引损坏或陈旧问题，且会加剧内存压力。
- **不要**仅扩容 JVM heap（如 `-Xmx1g`）而不调整 K8s memory limit：K8s 限制优先于 JVM 参数，heap 调整无效且可能掩盖真实 OOM 根因。
- **不要**手动 `rm -rf /data/search-index/*` 后 `touch .rebuild.lock`：缺失 snapshot 校验，将导致重建数据不一致，引发搜索结果丢失。

## 后续与升级
- 若 `search-index-rebuild` 工具执行失败（超时/校验失败）或重建后 `error_rate` 仍 > 0.05，**立即升级至 Search Platform Team**（on-call + 主责开发）。
- 若同一 Pod 在 24 小时内再次发生 OOMKilled（即使已调高 limit），**必须升级至 SRE & Platform Infra 团队**，排查是否存在内存泄漏或索引分片设计缺陷。
