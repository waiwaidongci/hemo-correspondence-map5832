import {useState} from 'react';
import type {Run,User} from '../types/domain';
import {researchApi} from '../api/research';
import {useAsync} from '../hooks/useAsync';
import {dec,scientific} from '../utils/format';
import {Notice} from './common/Notice';

export function RandomizationPanel({run,user,reload}:{run:Run;user:User;reload:()=>Promise<any>}){
 const [replications,setReplications]=useState(2000);
 const [seedText,setSeedText]=useState('2026');
 const [timeoutSeconds,setTimeoutSeconds]=useState(25);
 const {busy,error,message,act}=useAsync();
 const t=run.result.randomization_test;
 const canRun=user.role!=='viewer';
 function submit(){
  const seed=seedText.trim()===''?null:Number(seedText);
  act(async()=>{
   await researchApi.randomization(run.id,{replications,seed,timeout_seconds:timeoutSeconds});
   await reload();
  },'固定边际随机检验已完成');
 }
 return (
  <section className="diagnostics randomization">
   <header>
    <div>
     <small>FIXED-MARGIN RANDOMIZATION / 固定行列总数随机检验</small>
     <h2>{t?(t.status==='completed'?'随机检验完成，读取 Monte Carlo p 与抽样误差。':'抽样超时：证据不足，未完成结果不作确定结论。'):'为稀疏表补充固定边际随机检验。'}</h2>
    </div>
    {t&&<span className={'diagnostic-label '+(t.status==='completed'?'usable':'sparse')}>{t.status==='completed'?'检验完成':'证据不足'}</span>}
   </header>

   <p className="random-basis">
    原假设：{t?.null_hypothesis??'给定行列边际下单元计数独立（无关联）'}。随机表逐张精确保持本运行有效表的全部行总和与列总和，
    零边际剔除沿用对应分析（行 {run.result.dropped_rows?.map(c=>c.label).join('、')||'无'}；
    列 {run.result.dropped_columns?.map(c=>c.label).join('、')||'无'}）。统计量为 Pearson χ²，
    p={t?.p_formula??'(#(T_sim ≥ T_obs)+1)/(有效次数+1)'}。
   </p>

   {t&&(
    <div className="diagnostic-numbers">
     <span>观察 χ² <b>{dec(t.observed_statistic)}</b></span>
     <span>随机 p <b>{scientific(t.p_value)}</b></span>
     <span>抽样标准误 <b>{scientific(t.standard_error)}</b></span>
     <span>有效次数 <b>{t.replications_completed}<span> / {t.replications_requested}</span></b></span>
     <span>df <b>{t.df}</b></span>
    </div>
   )}

   {t&&(
    <div className="random-meta">
     <span>抽样方法：{t.sampling_scheme}</span>
     <span>随机数：{t.rng}</span>
     <span>种子 seed：<b className="mono">{t.seed??'未指定（不可复算）'}</b></span>
     <span>可复算：{t.reproducible?'是（相同计数与随机设置结果一致）':'否（未指定种子）'}</span>
     <span>耗时 {dec(t.elapsed_seconds,3)}s / 时限 {t.timeout_seconds}s</span>
     <span>计数 ≥ 观察值：{t.count_ge_observed}</span>
    </div>
   )}

   {t&&<p className={t.status==='completed'?'random-conclusion':'random-conclusion insufficient'}>{t.conclusion}</p>}

   <form className="random-form" onSubmit={e=>{e.preventDefault();submit()}}>
     <fieldset disabled={busy||!canRun}>
      <div className="random-fields">
       <label>随机次数
        <input type="number" min={100} max={100000} step={100} value={replications}
         onChange={e=>setReplications(Number(e.target.value))} required/>
       </label>
       <label>随机种子（留空不可复算）
        <input type="number" value={seedText} onChange={e=>setSeedText(e.target.value)} placeholder="例如 2026"/>
       </label>
       <label>抽样超时（秒）
        <input type="number" min={1} max={120} step={1} value={timeoutSeconds}
         onChange={e=>setTimeoutSeconds(Number(e.target.value))} required/>
       </label>
      </div>
      <p className="fine">相同计数、次数、种子与超时设置可逐次复算；超时仅按已完成有效次数给估计，并标记“证据不足”，不把未完成抽样当确定结论。</p>
      <button className="primary" disabled={!canRun}>{busy?'正在抽样…':(t?'重新运行随机检验 ↻':'运行固定边际随机检验 →')}</button>
     </fieldset>
     {!canRun&&<p className="fine">导览观察员可读取检验结果，运行需研究员权限。</p>}
   </form>
   <Notice error={error} message={message}/>
  </section>
 );
}
