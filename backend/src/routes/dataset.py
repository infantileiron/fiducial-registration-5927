from fastapi import APIRouter,Depends
from src.controllers import dataset as controller
from src.schemas.entities import DatasetInput, DatasetVersionInput, RenameDataset
from src.services.auth import current,editor
router=APIRouter(prefix="/datasets",tags=["datasets"])
@router.get("")
def list_items(user=Depends(current)): return controller.list_items()
@router.post("",status_code=201)
def create(data:DatasetInput,user=Depends(editor)): return controller.create(data)
@router.get("/{id}")
def detail(id:str,user=Depends(current)): return controller.detail(id)
@router.get("/{id}/versions")
def versions(id:str,user=Depends(current)): return controller.versions(id)
@router.get("/{id}/versions/{version}")
def version_detail(id:str,version:int,user=Depends(current)): return controller.version_detail(id,version)
@router.put("/{id}/points")
def update_points(id:str,data:DatasetVersionInput,user=Depends(editor)): return controller.update_points(id,data)
@router.patch('/{id}')
def rename(id:str,data:RenameDataset,user=Depends(editor)):
 from src.services.dataset import rename
 return rename(id,data)
