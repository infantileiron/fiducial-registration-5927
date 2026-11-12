import {useState} from 'react';
import * as api from '../api/datasets';
import {useResource} from '../hooks/useResource';
import {refreshResources} from '../stores/resources';
import PageTitle from '../components/common/PageTitle';
import Notice from '../components/common/Notice';
import VersionPanel from '../components/VersionPanel';
import type {User, DatasetVersion} from '../types/entities';

export default function Datasets({user}:{user:User}){
  const {data,error}=useResource(api.list,[]);
  const [name,setName]=useState('补充相机台架点对');
  const [source,setSource]=useState('haochuan_fiducials_import.csv');
  const [text,setText]=useState('');
  const [message,setMessage]=useState('');
  const [openId,setOpenId]=useState('');
  const [versions,setVersions]=useState<DatasetVersion[]>([]);
  const readonly = user.role==='viewer';

  const openVersions=async(id:string)=>{
    if(openId===id){setOpenId('');return;}
    setOpenId(id);
    try{setVersions(await api.versions(id));setMessage('')}
    catch(e:any){setMessage(e.message)}
  };

  return <>
    <PageTitle chapter="02 / POINT PAIRS" title="每个ID，连接源点与目标点"
      description="CSV包含id,sx,sy,sz,tx,ty,tz；全部毫米。3—500组，有限坐标且绝对值≤1e6。现场补测可整批替换点对并生成新版本：相同内容重复上传不产生新版本，坏行整批退回且原数据不变；历史版本永久保留、可查看与计算。"/>
    <Notice error={error||message}/>
    <section className="paper table-scroll">
      <table>
        <thead><tr><th>标志点来源</th><th>当前版本</th><th>点对数量</th><th>存储口径</th><th>版本链</th></tr></thead>
        <tbody>{data.map(d=>
          <tr key={d.id}>
            <td><b>{d.name}</b><small>{d.source}</small></td>
            <td><span className="version-tag current">v{d.current_version} 当前版</span></td>
            <td>{d.point_count}</td>
            <td>源xyz ↔ 目标xyz / float64</td>
            <td><button className="link-button" onClick={()=>openVersions(d.id)}>
              {openId===d.id?'收起版本链':'查看当前版与历史版'}
            </button></td>
          </tr>)}
        </tbody>
      </table>
    </section>

    {openId && (
      <VersionPanel
        dataset={data.find(d=>d.id===openId)!}
        versions={versions}
        readonly={readonly}
        onChanged={()=>{refreshResources();api.versions(openId).then(setVersions)}}
        onNotice={setMessage}
      />
    )}

    {!readonly && <form className="paper form-grid" onSubmit={async e=>{
      e.preventDefault();
      try{
        const created=await api.create({name,source,csv_text:text});
        setMessage('');setText('');refreshResources();setOpenId(created.id);
        setVersions(await api.versions(created.id));
      }catch(e:any){setMessage(e.message)}
    }}>
      <label>数据集名称<input aria-label="数据集名称" value={name} onChange={e=>setName(e.target.value)}/></label>
      <label>点对CSV文件<input aria-label="点对CSV文件" type="file" accept=".csv" onChange={async e=>{
        const f=e.target.files?.[0];
        if(f){if(f.size>350000){setMessage('CSV不能超过350KB');return}setSource(f.name);setText(await f.text())}
      }}/></label>
      <label className="wide">点对内容<textarea aria-label="点对内容" value={text} onChange={e=>setText(e.target.value)} placeholder="id,sx,sy,sz,tx,ty,tz"/></label>
      <button className="primary">校验并导入点对（v1）</button>
    </form>}
  </>;
}
