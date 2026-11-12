from fastapi import HTTPException
from src.models import InterpretationNote,CorrespondenceRun
from src.constants.enums import NoteStatus
from src.utils.csv_export import csv_response
def export_note(db,id):
 note=db.get(InterpretationNote,id)
 if not note:raise HTTPException(404,'解释记录不存在')
 if note.status!=NoteStatus.APPROVED:raise HTTPException(403,'仅获批解释可导出')
 run=db.get(CorrespondenceRun,note.run_id);rows=[]
 rt=run.result.get('randomization_test')
 if rt and rt.get('status')=='completed':
  mc_basis='固定行列边际Monte Carlo随机检验（'+rt.get('sampling_scheme','')+'）；'+rt.get('null_hypothesis','')
  mc_p=rt['p_value'];mc_se=rt['standard_error'];mc_n=rt['replications_completed']
  mc_seed=rt.get('seed');mc_status='完成'
 elif rt and rt.get('status')=='insufficient_evidence':
  mc_basis='随机检验抽样超时，证据不足，未完成结果不得当作确定结论；已完成次数见有效次数字段'
  mc_p=None;mc_se=rt.get('standard_error');mc_n=rt['replications_completed']
  mc_seed=rt.get('seed');mc_status='证据不足（超时未完成）'
 else:
  mc_basis='尚未运行固定边际随机检验，仅有渐近p（稀疏表可能不可靠）'
  mc_p=None;mc_se=None;mc_n=None;mc_seed=None;mc_status='未运行'
 for p in run.result['row_points']+run.result['column_points']:
  if p['id'] in note.category_ids:
   shown=run.result['displayed_axes'];xy=[p['coordinates'][k] if k<shown else None for k in range(2)];rows.append([note.name,p['axis'],p['code'],p['label'],p['mass'],*xy,p['display_quality'],run.result['retained_inertia'],run.result['diagnostics']['p_value'],run.result['diagnostics']['asymptotic_reliable'],mc_p,mc_se,mc_n,mc_seed,mc_status,mc_basis,note.interpretation,note.next_step,note.review_note,'行列跨集距离不可直接解释；稀疏表渐近p不可靠'])
 return csv_response(f'interpretation-{id}.csv',rows,['解释','点集','code','类别','质量mass','主坐标1','主坐标2','显示cos2','保留惯量','渐近p','期望计数条件可用','随机检验p','随机检验抽样标准误','随机检验有效次数','随机种子','随机检验状态','随机检验依据','人工解释','下一步','审阅说明','边界'])
