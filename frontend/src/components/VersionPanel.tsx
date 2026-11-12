import {useState} from 'react';
import * as api from '../api/datasets';
import Notice from './common/Notice';
import {shortHash} from '../utils/format';
import type {Dataset, DatasetVersion} from '../types/entities';

export default function VersionPanel(
  {dataset, versions, readonly, onChanged, onNotice}:
  {dataset:Dataset; versions:DatasetVersion[]; readonly:boolean;
   onChanged:()=>void; onNotice:(s:string)=>void}){
  const [csvText,setCsvText]=useState('');
  const [source,setSource]=useState('');
  const [busy,setBusy]=useState(false);
  const [localMsg,setLocalMsg]=useState('');
  const [viewVersion,setViewVersion]=useState<DatasetVersion|null>(null);

  const submit=async()=>{
    if(!csvText.trim()){setLocalMsg('请先选择或粘贴整批点对CSV');return}
    setBusy(true);
    try{
      const res=await api.updatePoints(dataset.id,{csv_text:csvText,source});
      setLocalMsg(res.changed
        ? `已生成新版本 v${res.version.version}，当前版已切换；历史版本与既有快照、结果、报告保持不变。`
        : '上传内容与当前版本完全相同，未产生新版本，原数据不变。');
      setCsvText('');setSource('');
      onChanged();
    }catch(e:any){
      setLocalMsg('整批退回：'+e.message+'（未写入任何版本，当前数据不变）');
    }finally{setBusy(false)}
  };

  const openVersion=async(version:number)=>{
    try{setViewVersion(await api.versionDetail(dataset.id,version));setLocalMsg('')}
    catch(e:any){onNotice(e.message)}
  };

  return <section className="paper version-panel">
    <h2>版本链 / {dataset.name} <small>当前版 v{dataset.current_version}，共 {versions.length} 版</small></h2>
    <Notice error={localMsg}/>
    <div className="version-list">
      {[...versions].reverse().map(v=>{
        const isCurrent=v.version===dataset.current_version;
        return <article key={v.id} className={'version-row'+(isCurrent?' is-current':'')}>
          <div>
            <span className={'version-tag '+(isCurrent?'current':'history')}>
              v{v.version}{isCurrent?' 当前版':' 历史版'}
            </span>
            <b>{v.point_count} 组点对</b>
            <small>{v.source} · {new Date(v.created_at).toLocaleString('zh-CN')}</small>
            <small className="hash">SHA256 {shortHash(v.content_hash)}</small>
          </div>
          <button className="link-button" onClick={()=>openVersion(v.version)}>查看该版点对</button>
        </article>;
      })}
    </div>

    {viewVersion && <div className="paper version-detail">
      <h3>v{viewVersion.version} 点对明细
        <small>{viewVersion.version===dataset.current_version?'（当前版）':'（历史版 · 只读，不随后续更新改变）'}</small>
        <button className="link-button" onClick={()=>setViewVersion(null)}>关闭</button>
      </h3>
      <div className="table-scroll">
        <table>
          <thead><tr><th>ID</th><th>源xyz / mm</th><th>目标xyz / mm</th></tr></thead>
          <tbody>{viewVersion.points.map(p=>
            <tr key={p.id}>
              <td>{p.id}</td>
              <td>{p.source.map(x=>x.toFixed(3)).join(' / ')}</td>
              <td>{p.target.map(x=>x.toFixed(3)).join(' / ')}</td>
            </tr>)}
          </tbody>
        </table>
      </div>
    </div>}

    {!readonly && <div className="version-upload form-grid">
      <h3>整批补测 / 更正点对</h3>
      <p className="method-note">
        全量替换并按点对内容生成新版本：任一坏行（缺列、重复ID、非有限坐标等）整批退回，不写入任何版本；
        与当前版点对完全相同则不产生新版本。历史快照只绑定其创建时的版本，计算与报告始终可追溯对应版本。
      </p>
      <label>更正批次CSV（可选，留空沿用上一版来源名）
        <input aria-label="更正批次来源文件" type="file" accept=".csv" onChange={async e=>{
          const f=e.target.files?.[0];
          if(f){if(f.size>350000){setLocalMsg('CSV不能超过350KB');return}setSource(f.name);setCsvText(await f.text())}
        }}/>
      </label>
      <label className="wide">批次内容
        <textarea aria-label="整批点对内容" value={csvText} onChange={e=>setCsvText(e.target.value)} placeholder="id,sx,sy,sz,tx,ty,tz"/>
      </label>
      <button className="primary" disabled={busy} onClick={e=>{e.preventDefault();submit()}}>
        {busy?'校验并写入中…':'校验并整批更新（生成新版本）'}
      </button>
    </div>}
  </section>;
}
