import math
import time
import numpy as np

# 固定行列边际随机检验（fixed-margin randomization / permutation test）
# 原假设 H0：在给定行总和与列总和的条件下，单元计数相互独立（无关联）。
# 检验统计量沿用 Pearson chi-square；随机表在“保持全部行列边际”的整数表集合上
# 条件均匀抽样，每个可行表等概率出现，行列总和逐表精确保持。
#
# 两套等价抽样器（都生成同一条件均匀分布，可对拍）：
#  - Boyett(1979) 随机标签排列：向量化、快，但工作内存随 N 线性增长，用于小 N；
#  - Patefield(1981, AS159，移植 R stats::rcont2)：逐格对数概率比接受-拒绝，
#    工作内存 O(R*C) 与 N 无关，用于大 N。
METHOD = 'fixed-margin-pearson-chi-square-monte-carlo-v1'
DEFAULT_REPLICATIONS = 2000
DEFAULT_TIMEOUT_SECONDS = 25.0
MAX_REPLICATIONS = 100000
# N 超过该阈值改用 Patefield，避免 Boyett 排列数组占用过大内存
PERMUTATION_MAX_N = 50000
BATCH_SMALL = 400
BATCH_LARGE = 100
# Boyett 单批随机键规模上限（条目数），把单批内存控制在约百 MB 内
PERMUTATION_BATCH_CELLS = 4_000_000


# --------------------------------------------------------------------------- #
# Boyett 随机标签排列（向量化，小 N）
# --------------------------------------------------------------------------- #
def _rcont_permutation(row_sums, col_sums, size, rng):
 """生成 size 个固定边际随机表（Boyett 随机标签排列，向量化批量）。"""
 R, C = len(row_sums), len(col_sums)
 labels = np.concatenate(
  [np.full(int(c), j, dtype=np.int64) for j, c in enumerate(col_sums)])
 n = int(labels.shape[0])
 order = np.argsort(rng.random((size, n)), axis=1)
 perm = labels[order]
 counts = np.empty((size, R, C), dtype=np.int64)
 pos = 0
 for i, need in enumerate(row_sums):
  need = int(need)
  counts[:, i, :] = np.apply_along_axis(
   lambda v: np.bincount(v, minlength=C), 1, perm[:, pos:pos + need])
  pos += need
 return counts


# --------------------------------------------------------------------------- #
# Patefield AS159（移植 R stats::rcont2，大 N，内存与 N 无关）
# --------------------------------------------------------------------------- #
def _patefield_cell(ia, ib, ic, id_, ie, ii, logfact, rng):
 """R rcont2 单单元对数概率比接受-拒绝，返回该单元计数。logfact 为按需记忆化函数。"""
 U = rng.random()
 while True:
  nlm = int(ia * (id_ / ie) + 0.5)
  x = math.exp(logfact(ia) + logfact(ib) + logfact(ic) + logfact(id_)
               - logfact(ie) - logfact(nlm) - logfact(id_ - nlm)
               - logfact(ia - nlm) - logfact(ii + nlm))
  if x >= U:
   return nlm
  if x == 0.0:
   raise RuntimeError('Patefield 概率下溢，算法失败')
  sumprb = y = x
  nll = nlm
  while True:
   j = (id_ - nlm) * (ia - nlm)
   lsp = (nlm == ia) or (nlm == id_)
   if not lsp:
    nlm += 1
    x *= j / (nlm * (ii + nlm))
    sumprb += x
    if sumprb >= U:
     return nlm
   while True:
    j = nll * (ii + nll)
    lsm = (nll == 0)
    if not lsm:
     nll -= 1
     y *= j / ((id_ - nll) * (ia - nll))
     sumprb += y
     if sumprb >= U:
      return nll
     if not lsp:
      break
    if lsm:
     break
   if lsp:
    break
  U = sumprb * rng.random()


def _rcont_patefield(row_sums, col_sums, size, rng, logfact):
 """生成 size 个固定边际随机表（Patefield AS159 顺序抽样）。"""
 nrow, ncol = len(row_sums), len(col_sums)
 out = np.empty((size, nrow, ncol), dtype=np.int64)
 ntotal = int(sum(row_sums))
 for k in range(size):
  jwork = [int(c) for c in col_sums[:ncol - 1]]
  mat = np.zeros((nrow, ncol), dtype=np.int64)
  jc = ntotal
  ib = 0
  for l in range(nrow - 1):
   ia = int(row_sums[l]); ic = jc; jc -= ia
   for m in range(ncol - 1):
    id_ = jwork[m]; ie = ic
    ib = ie - ia; ii = ib - id_; ic -= id_
    if ie == 0:
     for j in range(m, ncol - 1):
      mat[l, j] = 0
     ia = 0
     break
    nlm = _patefield_cell(ia, ib, ic, id_, ie, ii, logfact, rng)
    mat[l, m] = nlm
    ia -= nlm; jwork[m] -= nlm
   mat[l, ncol - 1] = ia
  for m in range(ncol - 1):
   mat[nrow - 1, m] = jwork[m]
  mat[nrow - 1, ncol - 1] = ib - mat[nrow - 1, ncol - 2]
  out[k] = mat
 return out


def _chi_square_batch(tables, expected):
 """批量计算 Pearson chi-square；固定边际下期望对所有随机表恒定。"""
 diff = tables - expected[None, :, :]
 inv = 1.0 / expected
 return np.einsum('ijk,ijk->i', diff * diff, np.broadcast_to(inv, diff.shape))


def fixed_margin_test(table, replications=DEFAULT_REPLICATIONS, seed=None,
                      timeout_seconds=DEFAULT_TIMEOUT_SECONDS, started_at=None):
 """
 固定行列总数的 Monte Carlo 随机检验。

 - 输入应为已剔除零边际后的有效表（与 CA 使用同一张表，零边际剔除沿用 CA）。
 - 相同 (table, replications, seed) 必然复算一致。
 - 超时不抛确定结论：返回 status='insufficient_evidence'，只报告已完成的有效次数。
 """
 X = np.asarray(table, dtype=np.int64)
 if X.ndim != 2 or min(X.shape) < 2:
  raise ValueError('随机检验需要至少2行2列的有效列联表')
 if (X < 0).any():
  raise ValueError('计数不能为负')
 row_sums = X.sum(axis=1)
 col_sums = X.sum(axis=0)
 if (row_sums <= 0).any() or (col_sums <= 0).any():
  raise ValueError('随机检验前须剔除零边际行/列')
 n = int(X.sum())
 if n <= 0:
  raise ValueError('总计数必须为正')
 if not isinstance(replications, int) or not 1 <= replications <= MAX_REPLICATIONS:
  raise ValueError(f'随机次数须为 1..{MAX_REPLICATIONS} 的整数')
 if seed is not None and not isinstance(seed, int):
  raise ValueError('随机种子须为整数')
 if timeout_seconds is not None and timeout_seconds <= 0:
  raise ValueError('超时秒数须为正数')

 rng = np.random.default_rng(seed)
 expected = np.outer(row_sums, col_sums).astype(float) / n
 observed = float(np.sum((X - expected) ** 2 / expected))
 df = int((X.shape[0] - 1) * (X.shape[1] - 1))

 use_permutation = n <= PERMUTATION_MAX_N
 sampler_name = 'Boyett 随机标签排列（向量化）' if use_permutation else 'Patefield AS159 顺序接受-拒绝'
 if use_permutation:
  logfact = None
  # 单批键数 size*n 受限，避免大 N 时单批随机键数组占满内存
  batch = max(1, min(BATCH_SMALL, PERMUTATION_BATCH_CELLS // max(n, 1)))
 else:
  # 按需记忆化对数阶乘：实际只访问 O(R*C) 个索引，内存与 N 无关
  _lg_cache = {0: 0.0}
  def logfact(k):
   v = _lg_cache.get(k)
   if v is None:
    v = math.lgamma(k + 1); _lg_cache[k] = v
   return v
  batch = BATCH_LARGE

 def draw(size):
  if use_permutation:
   return _rcont_permutation(row_sums, col_sums, size, rng)
  return _rcont_patefield(row_sums, col_sums, size, rng, logfact)

 started = started_at or time.monotonic()
 ge = 0
 completed = 0
 timed_out = False
 while completed < replications:
  size = min(batch, replications - completed)
  sim = draw(size)
  # 抽样恒等式校验：每张随机表都必须精确保持原边际
  if not (np.array_equal(sim.sum(axis=2), np.repeat(row_sums[None, :], size, axis=0))
          and np.array_equal(sim.sum(axis=1), np.repeat(col_sums[None, :], size, axis=0))):
   raise RuntimeError('随机表边际校验失败')
  ge += int(np.count_nonzero(_chi_square_batch(sim, expected) >= observed - 1e-12))
  completed += size
  if timeout_seconds is not None and time.monotonic() - started > timeout_seconds:
   timed_out = True
   break

 # (b+1)/(m+1)：含观察表自身的 Monte Carlo p，避免零计数与低估
 p_value = float((ge + 1) / (completed + 1))
 standard_error = float(np.sqrt(p_value * (1 - p_value) / (completed + 1)))
 if timed_out:
  status = 'insufficient_evidence'
  conclusion = '随机检验在时限内未完成：仅报告已完成抽样，证据不足，不能当作确定结论。'
 else:
  status = 'completed'
  conclusion = '固定边际随机检验已完成：p 为 Monte Carlo 估计，附抽样标准误与有效次数。'

 return {
  'method': METHOD,
  'status': status,
  'statistic_name': 'pearson_chi_square',
  'observed_statistic': observed,
  'df': df,
  'replications_requested': int(replications),
  'replications_completed': int(completed),
  'count_ge_observed': int(ge),
  'p_value': p_value,
  'standard_error': standard_error,
  'seed': seed,
  'rng': 'numpy.PCG64/default_rng',
  'sampling_scheme': f'{sampler_name}；固定全部行总和与列总和，条件均匀抽样',
  'sampler': 'boyett_permutation' if use_permutation else 'patefield_as159',
  'null_hypothesis': '给定行列边际下单元计数独立（无关联）',
  'p_formula': '(#(T_sim >= T_obs) + 1) / (有效次数 + 1)',
  'timeout_seconds': timeout_seconds,
  'elapsed_seconds': round(time.monotonic() - started, 6),
  'timed_out': timed_out,
  'reproducible': seed is not None,
  'conclusion': conclusion,
 }
