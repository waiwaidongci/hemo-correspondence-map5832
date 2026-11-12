from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.models import CorrespondenceRun
from src.constants.enums import RunStatus
from src.utils.serialize import row
from .randomization import fixed_margin_test, DEFAULT_REPLICATIONS, DEFAULT_TIMEOUT_SECONDS
from .audit import record


def get_randomization(db: Session, run_id: int):
 run = db.get(CorrespondenceRun, run_id)
 if not run:
  raise HTTPException(404, '对应分析不存在')
 return run.result.get('randomization_test')


def attach_run_context(test: dict, result: dict) -> dict:
 """把 CA 结果中的零边际剔除与有效表维度附加到随机检验，供页面与导出核对。"""
 test['effective_table_dimensions'] = {
  'rows': len(result.get('row_categories', [])),
  'columns': len(result.get('column_categories', [])),
 }
 test['dropped_rows'] = result.get('dropped_rows', [])
 test['dropped_columns'] = result.get('dropped_columns', [])
 return test


def run_randomization(db: Session, data, user):
 run = db.get(CorrespondenceRun, data.run_id)
 if not run:
  raise HTTPException(404, '对应分析不存在')
 if run.status != RunStatus.SUCCEEDED:
  raise HTTPException(422, '请选择成功分析后再运行随机检验')
 result = run.result
 if not result.get('table'):
  raise HTTPException(422, '分析结果缺少有效计数表，无法运行随机检验')

 replications = data.replications or DEFAULT_REPLICATIONS
 timeout_seconds = data.timeout_seconds or DEFAULT_TIMEOUT_SECONDS
 # 零边际剔除沿用 CA：result['table'] 已是剔除零行/零列后的有效表
 test = fixed_margin_test(
  result['table'],
  replications=replications,
  seed=data.seed,
  timeout_seconds=timeout_seconds,
 )
 attach_run_context(test, result)

 result['randomization_test'] = test
 run.result = result
 db.commit()
 record(db, user.email, 'randomization.run', {
  'run_id': run.id,
  'status': test['status'],
  'replications_completed': test['replications_completed'],
  'p_value': test['p_value'],
  'seed': test['seed'],
  'timed_out': test['timed_out'],
 })
 return row(run)
