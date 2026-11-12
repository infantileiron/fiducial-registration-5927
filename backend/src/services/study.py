import json,hashlib
from src.models.entities import RegistrationStudy
from src.utils import repository as repo
from src.utils.identity import new_id,now
def list_studies():
 items=[]
 for s in repo.all_rows('studies'):
  view={k:v for k,v in s.items() if k!='snapshot'}
  # 兼容版本化之前创建的历史研究：无显式字段时从快照补回。
  view['dataset_version']=s.get('dataset_version') or s['snapshot'].get('dataset_version',1)
  items.append(view)
 return items
def lock_snapshot(dataset,frame,threshold_mm,iterations,seed):
 if frame['dataset_id']!=dataset['id']:raise ValueError('轴系声明必须属于该点对数据集')
 version_no=dataset.get('current_version',1)
 snapshot={'points':dataset['points'],'frame':{k:frame[k] for k in ('id','name','source_frame','target_frame','unit','axes')},'threshold_mm':threshold_mm,'iterations':iterations,'seed':seed,'convention':'target=R@source+t','dataset_name':dataset['name'],'source':dataset['source'],'dataset_version':version_no};checksum=hashlib.sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest();return snapshot,checksum,version_no
def create(data):
 with repo.transaction() as (conn,_):
  # 与整批更新互斥读取：数据集指针与其点对来自同一事务视图，
  # 快照要么完整取自旧版、要么完整取自新版，不会拼到半套数据。
  d=repo.get('datasets',data.dataset_id,conn=conn);f=repo.get('frames',data.frame_id,conn=conn)
  snapshot,checksum,version_no=lock_snapshot(d,f,data.threshold_mm,data.iterations,data.seed)
  return repo.put('studies',RegistrationStudy(new_id('study'),data.name,data.dataset_id,data.frame_id,data.threshold_mm,data.iterations,data.seed,snapshot,checksum,version_no,now()),conn=conn)
